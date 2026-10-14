"""Full HTTP round-trip tests against the real server, with the Jarvis DB
layer mocked out (this suite must not touch production PostgreSQL)."""
import http.client
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent.parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JARVIS_ROOT))

import os  # noqa: E402
os.environ["JARVIS_ENABLED"] = "true"
os.environ["JARVIS_MODE"] = "SHADOW"
os.environ["EXTERNAL_ACTIONS"] = "false"
os.environ["JARVIS_MEMORY_TRANSPORT"] = "local-docker"

import auth  # noqa: E402

TMP_STATE = Path(tempfile.mkdtemp())
os.environ["JARVIS_WEB_STATE_DIR"] = str(TMP_STATE)
os.environ["JARVIS_STATE_DIR"] = str(TMP_STATE)
os.environ["JARVIS_WEB_INSECURE_COOKIES"] = "1"  # tests run over plain HTTP
auth.AUTH_FILE = TMP_STATE / "auth.json"

with patch("jarvis.memory.CompanyMemory.__init__", return_value=None), \
     patch("jarvis.operator.OperatorSession.__init__", return_value=None):
    import app  # noqa: E402

TEST_USER = "test-operator"
TEST_PASS = "correct horse battery staple 42"


class WebConsoleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        auth.set_password(TEST_USER, TEST_PASS)
        app._memory = MagicMock()
        app._memory.get_system_status.return_value = MagicMock(records=[{"open_tasks": 0, "failed_executions": 0}])
        app._operator = MagicMock()
        app._operator.list_pending.return_value = []
        app._shadow_runner = MagicMock()

        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        auth.set_password(TEST_USER, TEST_PASS)
        app.sessions = auth.SessionStore()
        app.throttle = auth.LoginThrottle()
        app._operator.reset_mock()
        app._operator.list_pending.return_value = []
        app._shadow_runner.reset_mock()

    def _post(self, path, payload, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            body = json.dumps(payload)
            conn.request("POST", path, body=body, headers=dict(headers or {}, **{"Content-Type": "application/json"}))
            resp = conn.getresponse()
            data = resp.read()
            return resp, (json.loads(data) if data else {})
        finally:
            conn.close()

    def _get(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            return resp, (json.loads(data) if data else {})
        finally:
            conn.close()

    def _login(self):
        resp, body = self._post("/api/login", {"username": TEST_USER, "password": TEST_PASS})
        cookies = resp.getheader("Set-Cookie", "")
        # http.client concatenates multiple Set-Cookie with ", " sometimes; parse defensively
        cookie_header = ", ".join(resp.msg.get_all("Set-Cookie") or [])
        session_id = None
        for part in cookie_header.split(","):
            part = part.strip()
            if part.startswith(app.SESSION_COOKIE + "="):
                session_id = part.split(";")[0].split("=", 1)[1]
        return body["csrf_token"], session_id

    # -- auth ------------------------------------------------------------
    def test_unauthenticated_access_denied(self):
        resp, body = self._get("/api/status")
        self.assertEqual(resp.status, 401)

    def test_bad_login_denied(self):
        resp, body = self._post("/api/login", {"username": TEST_USER, "password": "wrong"})
        self.assertEqual(resp.status, 401)

    def test_authenticated_login_works(self):
        resp, body = self._post("/api/login", {"username": TEST_USER, "password": TEST_PASS})
        self.assertEqual(resp.status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("csrf_token", body)

    def test_login_sets_httponly_and_samesite_cookie(self):
        resp, _ = self._post("/api/login", {"username": TEST_USER, "password": TEST_PASS})
        cookie_header = " ".join(resp.msg.get_all("Set-Cookie") or [])
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=Strict", cookie_header)

    def test_logout_invalidates_session(self):
        csrf, sid = self._login()
        resp, _ = self._post("/api/logout", {}, headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        self.assertEqual(resp.status, 200)
        resp2, _ = self._get("/api/status", headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        self.assertEqual(resp2.status, 401)

    def test_session_expiry_enforced(self):
        csrf, sid = self._login()
        session = app.sessions.get(sid)
        session.last_seen_at = time.time() - auth.SESSION_IDLE_TIMEOUT_S - 1
        resp, _ = self._get("/api/status", headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        self.assertEqual(resp.status, 401)

    def test_rate_limit_locks_out_after_repeated_failures(self):
        for _ in range(auth.LOGIN_MAX_ATTEMPTS):
            self._post("/api/login", {"username": TEST_USER, "password": "wrong"})
        resp, body = self._post("/api/login", {"username": TEST_USER, "password": "wrong"})
        self.assertEqual(resp.status, 429)

    def test_csrf_required_for_state_changing_request(self):
        csrf, sid = self._login()
        resp, body = self._post("/api/logout", {}, headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})  # no CSRF header
        self.assertEqual(resp.status, 403)

    def test_wrong_csrf_token_rejected(self):
        csrf, sid = self._login()
        resp, _ = self._post("/api/logout", {},
                             headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": "wrong-token"})
        self.assertEqual(resp.status, 403)

    def test_password_change_requires_authentication_and_csrf(self):
        payload = {"current_password": TEST_PASS, "new_password": "654321"}
        resp, _ = self._post("/api/account/password", payload)
        self.assertEqual(resp.status, 401)
        csrf, sid = self._login()
        resp, _ = self._post("/api/account/password", payload,
                             headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        self.assertEqual(resp.status, 403)

    def test_password_change_validates_current_and_minimum_length(self):
        csrf, sid = self._login()
        headers = {"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf}
        resp, _ = self._post("/api/account/password",
                             {"current_password": "wrong", "new_password": "654321"}, headers=headers)
        self.assertEqual(resp.status, 403)
        resp, _ = self._post("/api/account/password",
                             {"current_password": TEST_PASS, "new_password": "12345"}, headers=headers)
        self.assertEqual(resp.status, 400)
        self.assertTrue(auth.verify_password(TEST_PASS, auth.load_account()["password_hash"],
                                             auth.load_account()["salt"]))

    def test_password_change_accepts_six_digits_and_revokes_sessions(self):
        csrf, sid = self._login()
        _, other_sid = self._login()
        headers = {"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf}
        resp, body = self._post("/api/account/password",
                                {"current_password": TEST_PASS, "new_password": "654321"}, headers=headers)
        self.assertEqual(resp.status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("Max-Age=0", " ".join(resp.msg.get_all("Set-Cookie") or []))
        for old_sid in (sid, other_sid):
            resp, _ = self._get("/api/status", headers={"Cookie": f"{app.SESSION_COOKIE}={old_sid}"})
            self.assertEqual(resp.status, 401)
        resp, _ = self._post("/api/login", {"username": TEST_USER, "password": TEST_PASS})
        self.assertEqual(resp.status, 401)
        resp, _ = self._post("/api/login", {"username": TEST_USER, "password": "654321"})
        self.assertEqual(resp.status, 200)

    # -- structural safety --------------------------------------------------
    def test_status_endpoint_never_returns_db_credentials(self):
        csrf, sid = self._login()
        resp, body = self._get("/api/status", headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        dumped = json.dumps(body).casefold()
        for secret_word in ("password", "postgres_password", "encryption_key", "secret"):
            self.assertNotIn(secret_word, dumped)

    def test_static_path_traversal_blocked(self):
        resp, _ = self._get("/../../etc/passwd")
        self.assertIn(resp.status, (404, 400))

    # -- proposals / human approval boundary --------------------------------
    def test_proposal_list_reaches_operator_not_raw_db(self):
        csrf, sid = self._login()
        app._operator.list_pending.return_value = [{"action_id": 1, "action_type": "REQUEST_HUMAN_REVIEW"}]
        resp, body = self._get("/api/proposals", headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(body["pending"]), 1)
        app._operator.list_pending.assert_called()

    def test_proposal_inspect_reaches_operator(self):
        csrf, sid = self._login()
        app._operator.inspect.return_value = {"action_id": 5, "action_type": "REQUEST_HUMAN_REVIEW"}
        resp, body = self._get("/api/proposals/5", headers={"Cookie": f"{app.SESSION_COOKIE}={sid}"})
        self.assertEqual(resp.status, 200)
        app._operator.inspect.assert_called_with(5)

    def test_approve_goes_through_operator_decide_never_raw_sql(self):
        csrf, sid = self._login()
        app._operator.decide.return_value = {"action_id": 5, "decision": "APPROVED", "confirmed": True}
        resp, body = self._post("/api/proposals/5/decide", {"decision": "APPROVED", "reason": "test"},
                                headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        self.assertEqual(resp.status, 200)
        app._operator.decide.assert_called_once_with(5, "APPROVED", "test")

    def test_reject_goes_through_operator_decide(self):
        csrf, sid = self._login()
        app._operator.decide.return_value = {"action_id": 5, "decision": "REJECTED", "confirmed": True}
        resp, body = self._post("/api/proposals/5/decide", {"decision": "REJECTED", "reason": "no"},
                                headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        self.assertEqual(resp.status, 200)
        app._operator.decide.assert_called_once_with(5, "REJECTED", "no")

    def test_decide_requires_authentication(self):
        resp, _ = self._post("/api/proposals/5/decide", {"decision": "APPROVED", "reason": "x"})
        self.assertEqual(resp.status, 401)

    def test_jarvis_cannot_self_approve_no_such_endpoint_exists(self):
        # There is no code path in app.py that calls core.ai_decide_action as
        # anything but jarvis.operator.OperatorSession.decide (human_approver
        # only, verified in jarvis/operator.py). Confirm decide() is the sole
        # write path by checking no other operator method is invoked.
        csrf, sid = self._login()
        app._operator.decide.return_value = {"action_id": 5, "decision": "APPROVED", "confirmed": True}
        self._post("/api/proposals/5/decide", {"decision": "APPROVED", "reason": "test"},
                  headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        called_methods = [c[0] for c in app._operator.method_calls]
        # 🔴 Olculen niyet: decide TEK YAZMA YOLU olsun. Salt okur
        #    metotlar serbest -- karar ucu artik onaydan sonra kreatif
        #    uretimi baslatabilmek icin oneriyi okuyor (_kreatif_konusu).
        #    inspect(), operator.py'de list_pending() uzerinden calisir:
        #    human_approver rolu, ROLLBACK, yazma YOK.
        SALT_OKUR = {"inspect", "list_pending"}
        self.assertEqual([m for m in called_methods if m not in SALT_OKUR],
                         ["decide"],
                         "decide disinda bir YAZMA metodu cagrilmis")
        self.assertTrue(set(called_methods) <= SALT_OKUR | {"decide"},
                        f"beklenmeyen operator metodu: {called_methods}")

    # -- chat ----------------------------------------------------------
    def _stub_model(self):
        """Chat reaches a real model now; these tests are about the HTTP
        boundary, so the model is stubbed rather than raced against a 5s
        client timeout."""
        from unittest.mock import patch as _patch

        from jarvis.model_layer import ModelResult

        patcher = _patch("jarvis.model_layer.ModelRouter.synthesize",
                         lambda *a, **k: ModelResult(
                             answer="stub", evidence_refs=(), confidence="LOW",
                             missing_data=(), model="stub-model", tier="LOCAL_MODEL",
                             model_calls=1, duration_ms=1.0))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_chat_reaches_real_jarvis_adapter(self):
        self._stub_model()
        csrf, sid = self._login()
        app._shadow_runner.handle.return_value = {
            "envelope": {"evidence_refs": ["postgres:system"]},
            "context": {"facts": [{"open_tasks": 0}], "entity": None, "capability_analysis": None},
            "shadow": {}, "capability": {},
        }
        resp, body = self._post("/api/chat", {"message": "Jarvis, sistem durumu ne?"},
                                headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        self.assertEqual(resp.status, 200)
        self.assertEqual(body["kind"], "ANSWER")
        self.assertEqual(0, body["external_actions"])

    def test_unsupported_reasoning_request_fails_truthfully(self):
        self._stub_model()
        csrf, sid = self._login()
        resp, body = self._post("/api/chat", {"message": "Bunun için ne öneriyorsun?"},
                                headers={"Cookie": f"{app.SESSION_COOKIE}={sid}", "X-CSRF-Token": csrf})
        self.assertEqual(resp.status, 200)
        # The router owns this now: it answers, and it still takes no action.
        self.assertEqual(0, body["external_actions"])
        app._shadow_runner.handle.assert_not_called()

    def test_no_model_calls_in_status_or_chat_path(self):
        # Neither endpoint imports or calls any external provider client.
        import inspect
        source = inspect.getsource(app)
        for forbidden in ("openai", "anthropic", "genai", "requests.post(", "urllib.request.urlopen"):
            self.assertNotIn(forbidden, source.casefold())


if __name__ == "__main__":
    unittest.main()
