import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "webconsole"))
import push_store  # noqa: E402
import mobile_features  # noqa: E402

spec = importlib.util.spec_from_file_location("push_send", ROOT / "scripts" / "push-send.py")
push_send = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push_send)


class PushSenderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        state = Path(self.temporary.name)
        for name, value in (
            ("STATE_DIR", state), ("SUBSCRIPTIONS_FILE", state / "push-subscriptions.json"),
            ("SEEN_FILE", state / "push-seen.json"), ("LOCK_FILE", state / "push-subscriptions.lock"),
        ):
            patcher = patch.object(push_store, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_existing_approvals_are_baseline_and_new_ones_send_once(self):
        push_store.save({"endpoint": "https://web.push.apple.com/example",
                         "keys": {"p256dh": "a" * 87, "auth": "b" * 22}})
        first = {"action_id": 108, "payload": {"reason": "Existing approval"}}
        second = {"action_id": 109, "payload": {"reason": "New approval"}}
        with patch.object(push_send, "pending_approvals", side_effect=[[first], [first, second], [first, second]]), \
             patch.object(push_send, "send", return_value=True) as sender:
            push_send.notify_new_approvals()
            sender.assert_not_called()
            push_send.notify_new_approvals()
            sender.assert_called_once()
            self.assertIn("#109", sender.call_args.args[2])
            push_send.notify_new_approvals()
            sender.assert_called_once()

    def test_external_approval_uses_red_push_title(self):
        push_store.save({"endpoint": "https://web.push.apple.com/example",
                         "keys": {"p256dh": "a" * 87, "auth": "b" * 22}})
        proposal = {"action_id": 110, "action_type": "WHATSAPP_SEND_TEMPLATE",
                    "payload": {"reason": "Approval needed"}}
        with patch.object(push_send, "pending_approvals", side_effect=[[], [proposal]]), \
             patch.object(push_send, "send", return_value=True) as sender:
            push_send.notify_new_approvals()
            push_send.notify_new_approvals()
        self.assertTrue(sender.call_args.args[1].startswith("🔴"))

    def test_personal_reminder_only_reaches_owner_once(self):
        subscription = {"endpoint": "https://web.push.apple.com/example",
                        "keys": {"p256dh": "a" * 87, "auth": "b" * 22}}
        push_store.save(subscription, owner="alice")
        reminder = {"id": "one", "user": "alice", "text": "Su iç", "due_at": "2026-01-01T00:00:00+00:00", "sent_to": []}
        other = {**reminder, "id": "two", "user": "bob"}
        with patch.object(mobile_features, "due_reminders", return_value=[reminder, other]), \
             patch.object(mobile_features, "mark_sent", side_effect=lambda identifier, sub: reminder["sent_to"].append(sub)), \
             patch.object(push_send, "send", return_value=True) as sender:
            push_send.notify_due_reminders()
            push_send.notify_due_reminders()
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[2], "Su iç")


if __name__ == "__main__":
    unittest.main()
