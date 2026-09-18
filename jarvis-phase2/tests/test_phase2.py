import tempfile
import unittest
from pathlib import Path

from jarvis.cache import QueryCache
from jarvis.governors import ResourceBudget, ResourceGovernor
from jarvis.research import SourceRecord, fuse
from jarvis.routing import CapabilityRouter, Provider, ProviderState
from jarvis.state import TaskStateStore


class Phase2Tests(unittest.TestCase):
    def test_cache_hit_and_invalidation(self):
        cache, calls = QueryCache(), []
        loader = lambda: calls.append(1) or {"safe": True}
        self.assertFalse(cache.get_or_load("q", loader)[1])
        self.assertTrue(cache.get_or_load("q", loader)[1])
        cache.invalidate()
        self.assertFalse(cache.get_or_load("q", loader)[1])
        self.assertEqual(len(calls), 2)

    def test_provider_failure_preserves_state_and_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStateStore(Path(tmp) / "state.db")
            store.save("t1", {"status": "RUNNING", "evidence": ["e1"]})
            router = CapabilityRouter([
                Provider("A", {"reasoning"}, 1, ProviderState.AVAILABLE,
                         lambda _: (_ for _ in ()).throw(TimeoutError())),
                Provider("B", {"reasoning"}, 2, ProviderState.AVAILABLE,
                         lambda _: {"status": "DONE"}),
            ])
            result, attempts = router.run("reasoning", store.load("t1"))
            self.assertEqual(attempts, ["A", "B"])
            self.assertEqual(store.load("t1")["evidence"], ["e1"])
            self.assertEqual(result["status"], "DONE")

    def test_non_available_provider_is_skipped(self):
        router = CapabilityRouter([
            Provider("A", {"classification"}, 1, ProviderState.RATE_LIMITED, lambda _: {}),
            Provider("B", {"classification"}, 2, ProviderState.AVAILABLE, lambda _: {"ok": True}),
        ])
        result, attempts = router.run("classification", {})
        self.assertEqual((result, attempts), ({"ok": True}, ["B"]))

    def test_research_dedup_and_contradiction(self):
        rows = [
            SourceRecord("1", "A", "Vireon", "claim true", "2026-09-18", 0.9),
            SourceRecord("2", "A", "Vireon", "claim true", "2026-09-18", 0.9),
            SourceRecord("3", "B", "Vireon", "claim false", "2026-09-18", 0.8),
        ]
        result = fuse(rows)
        self.assertEqual(len(result["records"]), 2)
        self.assertTrue(result["contradiction"])
        self.assertTrue(result["needs_more_sources"])

    def test_resource_governor_releases_slot(self):
        governor = ResourceGovernor(ResourceBudget(max_concurrency=1))
        with governor.slot():
            pass
        with governor.slot():
            pass


if __name__ == "__main__":
    unittest.main()
