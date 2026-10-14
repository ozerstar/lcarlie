import unittest

from jarvis.state_pg import PostgresTaskStateStore


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.rows = [(1,), ({"status": "RUNNING", "evidence": ["ref:1"]}, 2)]

    def fetch_one(self, sql, params):
        self.calls.append((sql, params))
        return self.rows.pop(0)


class PostgresStateTests(unittest.TestCase):
    def test_controlled_save_and_reload(self):
        executor = FakeExecutor()
        store = PostgresTaskStateStore(executor)
        version = store.save(42, {"status": "RUNNING"}, expected_version=0)
        state, next_version = store.load(42)
        self.assertEqual(version, 1)
        self.assertEqual(next_version, 2)
        self.assertEqual(state["evidence"], ["ref:1"])
        self.assertIn("ai_save_jarvis_task_state", executor.calls[0][0])
        self.assertNotIn("INSERT", executor.calls[0][0])
