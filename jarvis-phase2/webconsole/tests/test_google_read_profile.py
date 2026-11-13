import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import google_workspace as google


class GmailReadProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = patch.object(google, "STATE", Path(self.temp.name))
        self.state.start(); self.addCleanup(self.state.stop)
        self.env = patch.dict(google.os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "dummy-client", "GOOGLE_OAUTH_CLIENT_SECRET": "dummy-secret"})
        self.env.start(); self.addCleanup(self.env.stop)

    def token(self, scopes=None):
        return {"refresh_token": "dummy-refresh", "access_token": "dummy-access", "expires_in": 3600,
                "scope": " ".join(scopes or [google.GMAIL_READ_SCOPE])}

    def begin(self, profile="gmail_read"):
        query = parse_qs(urlparse(google.start("alice", profile)).query)
        return query, query["state"][0]

    def test_start_requests_only_read_and_binds_state(self):
        query, state = self.begin()
        self.assertEqual(query["scope"], [google.GMAIL_READ_SCOPE])
        self.assertEqual(query["include_granted_scopes"], ["false"])
        self.assertEqual(google._read(google.STATE / "oauth-pending.json", {})[state]["profile"], "gmail_read")

    def test_general_scopes_unchanged_and_profile_validated(self):
        query, _ = self.begin("general")
        self.assertEqual(set(query["scope"][0].split()), set(google.SCOPES))
        with self.assertRaises(google.GoogleError): self.begin("../../bad")

    def test_callback_isolated_and_state_single_use(self):
        google._write(google._path("alice"), {"refresh_token": "dummy-old", "scope": list(google.SCOPES)})
        before = google._path("alice").read_bytes()
        _, state = self.begin()
        with patch.object(google, "_token_request", return_value=self.token()):
            self.assertEqual(google.callback("dummy-code", state), "alice")
            with self.assertRaises(google.GoogleError): google.callback("dummy-code", state)
        self.assertEqual(google._path("alice").read_bytes(), before)
        self.assertEqual(google.gmail_read_status("alice")["profile"], "gmail_read")
        self.assertFalse(google.gmail_read_status("alice")["verified_live"])

    def test_broad_grant_rejected_without_touching_either_token(self):
        for profile in ("general", "gmail_read"):
            google._write(google._path("alice", profile), {"refresh_token": "dummy-existing", "scope": [google.GMAIL_READ_SCOPE]})
        before = {profile: google._path("alice", profile).read_bytes() for profile in ("general", "gmail_read")}
        _, state = self.begin()
        with patch.object(google, "_token_request", return_value=self.token(google.SCOPES)):
            with self.assertRaises(google.GoogleError): google.callback("dummy-code", state)
        for profile in before: self.assertEqual(google._path("alice", profile).read_bytes(), before[profile])

    def test_missing_refresh_never_falls_back_to_existing_token(self):
        google._write(google._path("alice"), {"refresh_token": "dummy-old"})
        google._write(google._path("alice", "gmail_read"), {"refresh_token": "dummy-old-read"})
        _, state = self.begin()
        token = self.token(); token.pop("refresh_token")
        with patch.object(google, "_token_request", return_value=token):
            with self.assertRaises(google.GoogleError): google.callback("dummy-code", state)
        self.assertEqual(google._read(google._path("alice", "gmail_read"), {})["refresh_token"], "dummy-old-read")

    def test_general_legacy_state_remains_compatible(self):
        google._write(google.STATE / "oauth-pending.json", {"old-state": {"user": "alice", "expires": time.time()+60}})
        with patch.object(google, "_token_request", return_value=self.token(google.SCOPES)):
            google.callback("dummy-code", "old-state")
        self.assertTrue(google.status("alice")["drive_write"])
        self.assertFalse(google._path("alice", "gmail_read").exists())

    def test_no_filename_collision_with_legacy_username(self):
        self.assertNotEqual(google._path("alice", "gmail_read"), google._path("alice-gmail-read"))

    def test_legacy_fallback_only_when_narrow_profile_absent(self):
        google._write(google._path("alice"), {"refresh_token": "dummy-old", "scope": list(google.SCOPES)})
        self.assertEqual(google.gmail_read_status("alice")["profile"], "legacy_general")
        with patch.object(google, "_access_token", return_value="dummy") as access:
            google.gmail_read_access_token("alice"); access.assert_called_once_with("alice")
        google._write(google._path("alice", "gmail_read"), {"refresh_token": "dummy-narrow", "scope": [google.GMAIL_READ_SCOPE]})
        with patch.object(google, "_access_token", side_effect=google.GoogleError("dummy-revoked")) as access:
            with self.assertRaises(google.GoogleError): google.gmail_read_access_token("alice")
            access.assert_called_once_with("alice", "gmail_read")

    def test_invalid_narrow_scope_does_not_fall_back(self):
        google._write(google._path("alice"), {"refresh_token": "dummy-old", "scope": list(google.SCOPES)})
        google._write(google._path("alice", "gmail_read"), {"refresh_token": "dummy-narrow", "scope": list(google.SCOPES)})
        with self.assertRaises(google.GoogleError): google.gmail_read_access_token("alice")

    def test_refresh_broader_scope_not_persisted(self):
        google._write(google._path("alice", "gmail_read"), {"refresh_token": "dummy-read", "scope": [google.GMAIL_READ_SCOPE], "expires": 0})
        before = google._path("alice", "gmail_read").read_bytes()
        with patch.object(google, "_token_request", return_value=self.token(google.SCOPES)):
            with self.assertRaises(google.GoogleError): google.gmail_read_access_token("alice")
        self.assertEqual(google._path("alice", "gmail_read").read_bytes(), before)

    def test_ui_always_offers_reconnect_without_claiming_ready(self):
        source = (Path(__file__).parents[1] / "static/belgeler.js").read_text()
        block = source.split("async function googleStatus()", 1)[1].split("function edit", 1)[0]
        self.assertIn("hidden = !data.configured", block)
        self.assertIn("profile=gmail_read", block)
        self.assertNotIn("hidden = ready", block)
        self.assertNotIn("bağlantısı hazır", block)

    def test_expense_sync_works_with_only_read_profile(self):
        import expense_vault
        token = {"refresh_token": "dummy-read", "access_token": "dummy-access", "expires": time.time()+60,
                 "scope": [google.GMAIL_READ_SCOPE]}
        google._write(google._path("alice", "gmail_read"), token)
        self.assertFalse(google._path("alice").exists())
        with patch.object(expense_vault, "_gmail_json", return_value={}) as read:
            self.assertEqual(expense_vault.sync_gmail("alice"), {"added": 0, "reused": 0})
            self.assertEqual(read.call_args.args[1], "dummy-access")

    def test_statement_sync_works_with_only_read_profile(self):
        import expense_vault
        import money_ledger
        google._write(google._path("alice", "gmail_read"), {"refresh_token": "dummy-read", "access_token": "dummy-access",
            "expires": time.time()+60, "scope": [google.GMAIL_READ_SCOPE]})
        with patch.object(expense_vault, "_gmail_json", return_value={}) as read, patch.object(money_ledger, "_connect") as connect, patch.object(money_ledger, "reread_empty", return_value=0):
            connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = []
            self.assertEqual(money_ledger.sync_gmail_statements("alice")["listed"], 0)
            self.assertEqual(read.call_args.args[1], "dummy-access")

    def test_corrupt_narrow_profile_never_silently_uses_broad_token(self):
        google._write(google._path("alice"), {"refresh_token": "dummy-old", "scope": list(google.SCOPES)})
        google._write(google._path("alice", "gmail_read"), {})
        google._path("alice", "gmail_read").write_text("broken-json")
        with self.assertRaises(google.GoogleError): google.gmail_read_access_token("alice")
