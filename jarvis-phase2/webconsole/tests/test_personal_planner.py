import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mobile_features
import google_workspace
import personal_planner
import app


class PersonalPlannerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patcher = patch.object(mobile_features, "STATE", Path(temporary.name) / "mobile")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_today_and_tomorrow_are_owner_scoped(self):
        now = datetime(2026, 10, 15, 9, tzinfo=ZoneInfo("Europe/Istanbul"))
        mobile_features.save_contact("alice", "Talha", "Yakın", special_day="15.10")
        mobile_features.save_contact("bob", "Başka", "Yakın", special_day="15.10")
        with patch.object(google_workspace, "status", return_value={"connected": True}), \
             patch.object(google_workspace, "calendar_events", return_value=[
                 {"title": "Bugünkü görüşme", "start": "2026-10-15T11:00:00+03:00"},
                 {"title": "Yarınki görüşme", "start": "2026-10-16T11:00:00+03:00"}]), \
             patch.object(google_workspace, "pending_actions", return_value=[]):
            result = personal_planner.overview("alice", now)
        self.assertEqual(result["today_events"][0]["title"], "Bugünkü görüşme")
        self.assertEqual(result["tomorrow_events"][0]["title"], "Yarınki görüşme")
        self.assertEqual([row["name"] for row in result["special_days"]], ["Talha"])

    def test_google_failure_does_not_hide_local_reminders(self):
        with patch.object(google_workspace, "status", return_value={"connected": True}), \
             patch.object(google_workspace, "calendar_events", side_effect=google_workspace.GoogleError("offline")), \
             patch.object(google_workspace, "pending_actions", return_value=[]):
            result = personal_planner.overview("alice")
        self.assertTrue(result["calendar_error"])
        self.assertEqual(result["today_events"], [])

    def test_contacts_api_uses_authenticated_owner(self):
        class FakeHandler:
            def _current_session(self):
                return type("Session", (), {"username": "alice"})()

            def _require_csrf(self, _session):
                return True

            def _send_json(self, code, body):
                self.result = (code, body)

        handler = FakeHandler()
        body = {"action": "save", "name": "Talha", "relationship": "Yakın"}
        with patch.object(app, "_read_json_body", return_value=body):
            app.Handler._route_api_post(handler, "/api/mobile/contacts")
        self.assertEqual(handler.result[0], 200)
        self.assertEqual(len(mobile_features.contacts("alice")), 1)
        self.assertEqual(mobile_features.contacts("bob"), [])


if __name__ == "__main__":
    unittest.main()
