import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mobile_features


class MobileFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        patcher = patch.object(mobile_features, "STATE", Path(self.temporary.name) / "mobile")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reminder_owner_update_and_repeat(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        row = mobile_features.add_reminder("alice", "Toplantı", future, "daily")
        self.assertEqual(mobile_features.reminders("bob"), [])
        with self.assertRaises(ValueError):
            mobile_features.update_reminder("bob", row["id"], "Başka", future)
        mobile_features.update_reminder("alice", row["id"], "Yeni toplantı", future, "weekly")
        self.assertEqual(mobile_features.reminders("alice")[0]["repeat"], "weekly")

    def test_due_reminder_sent_once_and_advanced(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        row = mobile_features.add_reminder("alice", "Su iç", future, "daily")
        records = mobile_features._read(mobile_features._reminders_path())
        records[0]["due_at"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        mobile_features._atomic(mobile_features._reminders_path(), records)
        self.assertEqual(len(mobile_features.due_reminders()), 1)
        mobile_features.mark_sent(row["id"], "device")
        self.assertTrue(mobile_features.advance_reminder(row["id"], {"device"}))
        self.assertEqual(mobile_features.due_reminders(), [])

    def test_notes_are_owner_scoped_and_editable(self):
        row = mobile_features.add_note("alice", "Mavi severim")
        self.assertEqual(mobile_features.memory_search("bob", "Mavi")["notes"], [])
        mobile_features.update_note("alice", row["id"], "Yeşil severim")
        self.assertEqual(mobile_features.memory_search("alice", "Mavi")["notes"], [])
        self.assertEqual(len(mobile_features.memory_search("alice", "Yeşil")["notes"]), 1)
        self.assertTrue(mobile_features.delete_note("alice", row["id"]))


if __name__ == "__main__":
    unittest.main()
