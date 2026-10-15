import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import push_store  # noqa: E402


class PushStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        state = Path(self.temporary.name)
        for name, value in (
            ("STATE_DIR", state), ("SUBSCRIPTIONS_FILE", state / "push-subscriptions.json"),
            ("LOCK_FILE", state / "push-subscriptions.lock"),
        ):
            patcher = patch.object(push_store, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def subscription(self, endpoint="https://web.push.apple.com/example"):
        return {"endpoint": endpoint, "keys": {"p256dh": "a" * 87, "auth": "b" * 22}}

    def test_save_and_remove_subscription(self):
        subscription = self.subscription()
        identifier = push_store.save(subscription)
        self.assertEqual(push_store.get(identifier)["endpoint"], subscription["endpoint"])
        self.assertEqual(os.stat(push_store.SUBSCRIPTIONS_FILE).st_mode & 0o777, 0o600)
        push_store.remove(subscription["endpoint"])
        self.assertIsNone(push_store.get(identifier))

    def test_rejects_non_push_endpoint(self):
        for endpoint in ("http://web.push.apple.com/example", "https://127.0.0.1/example",
                         "https://web.push.apple.com.evil.example/test"):
            with self.assertRaises(ValueError):
                push_store.save(self.subscription(endpoint))

    def test_rejects_invalid_keys(self):
        subscription = self.subscription()
        subscription["keys"]["auth"] = "not valid"
        with self.assertRaises(ValueError):
            push_store.save(subscription)

    def test_subscription_owner_limits_removal(self):
        subscription = self.subscription()
        identifier = push_store.save(subscription, owner="alice")
        with self.assertRaises(ValueError):
            push_store.save(subscription, owner="bob")
        push_store.remove(subscription["endpoint"], owner="bob")
        self.assertEqual(push_store.get(identifier)["owner"], "alice")
        push_store.remove(subscription["endpoint"], owner="alice")
        self.assertIsNone(push_store.get(identifier))


if __name__ == "__main__":
    unittest.main()
