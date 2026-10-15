import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
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
        self.assertEqual(mobile_features.personal_notes("alice")[0]["source"], "Kullanıcı tarafından düzeltildi")
        self.assertEqual(mobile_features.memory_search("alice", "Mavi")["notes"], [])
        self.assertEqual(len(mobile_features.memory_search("alice", "Yeşil")["notes"]), 1)
        self.assertTrue(mobile_features.delete_note("alice", row["id"]))

    def test_contacts_are_owner_scoped_and_special_day_only_matches_today(self):
        row = mobile_features.save_contact("alice", "Talha", "Kardeşim gibi", special_day="15.10")
        self.assertEqual(mobile_features.contacts("bob"), [])
        self.assertEqual(len(mobile_features.special_days("alice", date(2026, 10, 15))), 1)
        self.assertEqual(mobile_features.special_days("alice", date(2026, 10, 16)), [])
        with self.assertRaisesRegex(ValueError, "zaten kayıtlı"):
            mobile_features.save_contact("alice", "Talha", "Arkadaş")
        mobile_features.save_contact("alice", "Talha Canal", "Çok yakın", identifier=row["id"])
        self.assertEqual(mobile_features.contacts("alice")[0]["name"], "Talha Canal")
        self.assertTrue(mobile_features.delete_contact("alice", row["id"]))

    def test_invalid_special_day_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "GG.AA"):
            mobile_features.save_contact("alice", "Test", "Arkadaş", special_day="31.02")

    def test_notification_preferences_are_owner_scoped(self):
        mobile_features.save_notification_settings("alice", False, True)
        self.assertEqual(mobile_features.notification_settings("alice"), {"morning": False, "evening": True})
        self.assertEqual(mobile_features.notification_settings("bob"), {"morning": True, "evening": True})

    def test_daily_activity_is_owner_scoped(self):
        mobile_features.record_activity("alice", "contact", "Kişi eklendi")
        today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3))).date()
        self.assertEqual(len(mobile_features.activities("alice", today)), 1)
        self.assertEqual(mobile_features.activities("bob", today), [])


if __name__ == "__main__":
    unittest.main()
