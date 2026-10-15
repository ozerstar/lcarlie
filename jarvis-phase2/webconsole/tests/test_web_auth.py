import sys
import tempfile
from contextlib import closing
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import auth  # noqa: E402


class PasswordHashTests(unittest.TestCase):
    def test_correct_password_verifies(self):
        h, s = auth.hash_password("correct horse battery staple")
        self.assertTrue(auth.verify_password("correct horse battery staple", h, s))

    def test_wrong_password_fails(self):
        h, s = auth.hash_password("correct horse battery staple")
        self.assertFalse(auth.verify_password("wrong password", h, s))

    def test_different_salts_produce_different_hashes(self):
        h1, s1 = auth.hash_password("same password")
        h2, s2 = auth.hash_password("same password")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)

    def test_plaintext_never_stored(self):
        h, s = auth.hash_password("my-secret")
        self.assertNotIn("my-secret", h)
        self.assertNotIn("my-secret", s)


class SessionStoreTests(unittest.TestCase):
    def test_created_session_is_retrievable(self):
        store = auth.SessionStore()
        session = store.create("operator")
        self.assertEqual(store.get(session.session_id).username, "operator")

    def test_unknown_session_returns_none(self):
        store = auth.SessionStore()
        self.assertIsNone(store.get("does-not-exist"))

    def test_idle_timeout_expires_session(self):
        store = auth.SessionStore()
        session = store.create("operator")
        session.last_seen_at = time.time() - auth.SESSION_IDLE_TIMEOUT_S - 1
        self.assertIsNone(store.get(session.session_id))

    def test_absolute_timeout_expires_session(self):
        store = auth.SessionStore()
        session = store.create("operator")
        session.created_at = time.time() - auth.SESSION_ABSOLUTE_TIMEOUT_S - 1
        session.last_seen_at = time.time()
        self.assertIsNone(store.get(session.session_id))

    def test_destroy_removes_session(self):
        store = auth.SessionStore()
        session = store.create("operator")
        store.destroy(session.session_id)
        self.assertIsNone(store.get(session.session_id))

    def test_destroy_all_removes_every_session(self):
        store = auth.SessionStore()
        first = store.create("operator")
        second = store.create("operator")
        store.destroy_all()
        self.assertIsNone(store.get(first.session_id))
        self.assertIsNone(store.get(second.session_id))

    def test_each_session_has_unique_csrf_token(self):
        store = auth.SessionStore()
        a = store.create("operator")
        b = store.create("operator")
        self.assertNotEqual(a.csrf_token, b.csrf_token)
        self.assertNotEqual(a.session_id, b.session_id)


class DurableSessionStoreTests(unittest.TestCase):
    def test_survives_restart_without_storing_bearer_token(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sessions.sqlite3"
            first = auth.DurableSessionStore(path)
            session = first.create("operator", "iPhone Safari", "192.0.2.1")
            self.assertNotIn(session.session_id, path.read_bytes().decode("latin-1"))
            second = auth.DurableSessionStore(path)
            self.assertEqual(second.get(session.session_id).username, "operator")
            devices = second.list_devices("operator", session.session_id)
            self.assertEqual(len(devices), 1)
            self.assertTrue(devices[0]["current"])
            self.assertEqual(devices[0]["device"], "iPhone Safari")

    def test_revoke_one_device_preserves_another_and_rejects_foreign_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            store = auth.DurableSessionStore(Path(folder) / "sessions.sqlite3")
            phone = store.create("operator", "iPhone")
            computer = store.create("operator", "Chrome")
            target = next(d["id"] for d in store.list_devices("operator", computer.session_id)
                          if d["device"] == "iPhone")
            self.assertFalse(store.revoke_device("someone-else", target))
            self.assertTrue(store.revoke_device("operator", target))
            self.assertIsNone(store.get(phone.session_id))
            self.assertIsNotNone(store.get(computer.session_id))

    def test_expired_session_is_removed_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sessions.sqlite3"
            store = auth.DurableSessionStore(path)
            session = store.create("operator")
            import sqlite3
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE sessions SET last_seen_at=?", (time.time()-auth.SESSION_IDLE_TIMEOUT_S-1,))
                db.commit()
            self.assertIsNone(auth.DurableSessionStore(path).get(session.session_id))


class LoginThrottleTests(unittest.TestCase):
    def test_allowed_before_threshold(self):
        throttle = auth.LoginThrottle()
        for _ in range(auth.LOGIN_MAX_ATTEMPTS - 1):
            throttle.record_failure("1.2.3.4")
        allowed, _ = throttle.check("1.2.3.4")
        self.assertTrue(allowed)

    def test_locked_out_after_threshold(self):
        throttle = auth.LoginThrottle()
        for _ in range(auth.LOGIN_MAX_ATTEMPTS):
            throttle.record_failure("1.2.3.4")
        allowed, remaining = throttle.check("1.2.3.4")
        self.assertFalse(allowed)
        self.assertGreater(remaining, 0)

    def test_success_clears_failures(self):
        throttle = auth.LoginThrottle()
        for _ in range(auth.LOGIN_MAX_ATTEMPTS - 1):
            throttle.record_failure("1.2.3.4")
        throttle.record_success("1.2.3.4")
        for _ in range(auth.LOGIN_MAX_ATTEMPTS - 1):
            throttle.record_failure("1.2.3.4")
        allowed, _ = throttle.check("1.2.3.4")
        self.assertTrue(allowed)

    def test_lockout_is_per_source(self):
        throttle = auth.LoginThrottle()
        for _ in range(auth.LOGIN_MAX_ATTEMPTS):
            throttle.record_failure("1.2.3.4")
        allowed, _ = throttle.check("5.6.7.8")
        self.assertTrue(allowed)


class AccountCreationTests(unittest.TestCase):
    def test_ensure_operator_account_creates_once(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "auth.json"
        with patch.object(auth, "AUTH_FILE", tmp):
            first = auth.ensure_operator_account()
            second = auth.ensure_operator_account()
        self.assertIsNotNone(first)
        self.assertIsNone(second)  # already exists, no new password generated

    def test_created_account_password_verifies(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "auth.json"
        with patch.object(auth, "AUTH_FILE", tmp):
            username, password = auth.ensure_operator_account()
            account = auth.load_account()
            self.assertTrue(auth.verify_password(password, account["password_hash"], account["salt"]))
        self.assertEqual(username, account["username"])

    def test_auth_file_is_not_world_readable(self):
        import os
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "auth.json"
        with patch.object(auth, "AUTH_FILE", tmp):
            auth.ensure_operator_account()
            mode = os.stat(tmp).st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
