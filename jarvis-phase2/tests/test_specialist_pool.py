from __future__ import annotations

import time
import unittest

from jarvis.memory import Evidence
from jarvis.specialist_pool import (
    ALLOWLISTED_QUERIES, DATA_UNAVAILABLE, PROPOSED, REGISTRY, SPECIALISTS,
    CompanyMemoryGateway, DeterministicSpecialist, ResearchRequest,
    SpecialistContext, SpecialistContextCompiler, SpecialistPool,
    SpecialistRouter, benchmark_routing, deterministic_confidence,
)


class FakeMemory:
    def _e(self, name): return Evidence(f"memory:{name}", "CANONICAL_COMPANY_MEMORY", "live", [{"metric": 1}], 1.0)
    def get_open_work(self): return self._e("open_work")
    def get_system_status(self): return self._e("system")
    def get_company_context(self): return self._e("decision_summary")
    def get_capability_state(self): return self._e("capability_state")


class SlowMemory(FakeMemory):
    def get_open_work(self):
        time.sleep(.02)
        return super().get_open_work()


class SpecialistPoolTests(unittest.TestCase):
    def test_registry_has_twenty_roles_and_nine_families(self):
        self.assertEqual(20, len(SPECIALISTS))
        self.assertEqual(len(SPECIALISTS), len(REGISTRY))
        families = {f for item in SPECIALISTS for f in item.capabilities}
        self.assertEqual(9, len(families))

    def test_contract_and_evidence_requirement(self):
        definition = REGISTRY["operations"]
        specialist = DeterministicSpecialist(definition)
        ctx = SpecialistContext("t", "operations", (), {}, (), "unknown", (), 0)
        result = specialist.analyze(ctx)
        self.assertEqual(DATA_UNAVAILABLE, result.finding_type)
        self.assertEqual("", result.claim)
        self.assertEqual(0, result.model_calls)
        self.assertEqual((), specialist.evidence())
        self.assertIn("deterministic_operations", specialist.metrics())

    def test_deterministic_minimum_routing(self):
        plan = SpecialistRouter().route(("sales", "advertising"))
        self.assertEqual(("ecommerce_sales", "meta_performance", "data_measurement"), plan.primary)
        self.assertEqual(6, len(plan.selected))
        self.assertNotIn("finance", plan.selected)

    def test_parallel_stage_and_dependency_order(self):
        plan = SpecialistRouter().route(("advertising", "crm", "operations"))
        self.assertEqual(("meta_performance", "data_measurement", "crm_customer", "operations"), plan.stages[0])
        self.assertEqual(("red_team",), plan.stages[1])
        self.assertEqual(("strategy",), plan.stages[2])
        self.assertEqual(("managing_director",), plan.stages[3])

    def test_company_memory_allowlist_and_unknown_query(self):
        gateway = CompanyMemoryGateway(FakeMemory())
        self.assertNotIn("sql", ALLOWLISTED_QUERIES)
        value, refs, freshness = gateway.read("DROP TABLE x")
        self.assertIsNone(value); self.assertEqual((), refs); self.assertEqual(DATA_UNAVAILABLE, freshness)

    def test_missing_data_is_not_faked(self):
        result = SpecialistPool(FakeMemory()).execute("sales", ("sales",))
        finding = result["findings"][0]
        self.assertEqual(DATA_UNAVAILABLE, finding["finding_type"])
        self.assertEqual("", finding["claim"])
        self.assertIn("sales", finding["missing_data"])

    def test_context_isolation(self):
        compiler = SpecialistContextCompiler(CompanyMemoryGateway(FakeMemory()))
        ctx = compiler.compile(REGISTRY["crm_customer"], "crm", "crm")
        self.assertEqual({"open_work"}, set(ctx.query_results))
        self.assertNotIn("system", ctx.query_results)

    def test_context_budget(self):
        compiler = SpecialistContextCompiler(CompanyMemoryGateway(FakeMemory()), max_bytes=2)
        ctx = compiler.compile(REGISTRY["crm_customer"], "crm", "crm")
        self.assertEqual({}, ctx.query_results)
        self.assertLessEqual(ctx.context_bytes, 2)

    def test_confidence_penalizes_contradiction_and_missing(self):
        high = deterministic_confidence(2, 1, independence=2)
        low = deterministic_confidence(1, .5, contradictions=1, independence=1)
        self.assertGreater(high, low)

    def test_cache_and_invalidation_by_evidence_version(self):
        pool = SpecialistPool(FakeMemory())
        first = pool.execute("crm", ("crm",), evidence_version="v1")
        second = pool.execute("crm", ("crm",), evidence_version="v1")
        third = pool.execute("crm", ("crm",), evidence_version="v2")
        self.assertEqual(0, first["metrics"]["cache_hits"])
        self.assertEqual(1, second["metrics"]["cache_hits"])
        self.assertEqual(0, third["metrics"]["cache_hits"])

    def test_red_team_strategy_md_order_and_proposed_only(self):
        result = SpecialistPool(FakeMemory()).execute("crm ops", ("crm", "operations"))
        ids = [item["specialist_id"] for item in result["findings"]]
        self.assertEqual(["red_team", "strategy", "managing_director"], ids[-3:])
        self.assertEqual(PROPOSED, result["status"])
        self.assertEqual(0, result["external_actions"])
        self.assertEqual(0, result["metrics"]["model_calls"])

    def test_red_team_objects_to_missing_and_source_independence(self):
        result = SpecialistPool(FakeMemory()).execute("sales", ("sales",))
        red = next(f for f in result["findings"] if f["specialist_id"] == "red_team")
        self.assertEqual("OBJECTION", red["finding_type"])
        self.assertIn("source_independence", red["contradictions"])

    def test_fusion_counts_evidence_sources_not_specialists(self):
        result = SpecialistPool(FakeMemory()).execute("crm ops", ("crm", "operations"))
        # CRM and Operations both see open_work; Operations additionally sees
        # system, so the pool has two independent evidence refs, not three
        # independent specialists.
        self.assertEqual(2, result["fusion"]["independent_sources"])
        self.assertFalse(result["fusion"]["contradiction"])

    def test_research_controller_contract_compatibility(self):
        plan = SpecialistRouter().route(("competitor",))
        self.assertTrue(plan.requires_research)
        request = ResearchRequest("competitor", ("price",))
        self.assertEqual("fresh_research_source", request.capability)
        self.assertFalse(request.external_execution_allowed)

    def test_parallel_execution_compatibility(self):
        result = SpecialistPool(SlowMemory(), max_concurrency=3).execute(
            "crm operations", ("crm", "operations"))
        self.assertEqual(2, result["parallelism"])

    def test_multidomain_regression_uses_minimum_set(self):
        task = ("L'CARLIE şirketinin mevcut durumunu analiz et. Satış, e-ticaret, "
                "reklam, CRM ve operasyon alanlarına bak. Problemleri, açık işleri "
                "ve fırsatları evidence ile belirle. Sonunda uygulanabilir sonraki "
                "adım planı çıkar. Hiçbir işlemi onay olmadan uygulama.")
        result = SpecialistPool(FakeMemory()).execute(
            task, ("sales", "ecommerce", "advertising", "crm", "operations"))
        self.assertEqual(8, result["specialists_executed"])
        self.assertEqual(12, result["specialists_skipped"])
        self.assertEqual(["red_team"], result["stages"][-3])
        self.assertEqual(["strategy"], result["stages"][-2])
        self.assertEqual(["managing_director"], result["stages"][-1])
        self.assertEqual(PROPOSED, result["status"])

    def test_benchmark_beats_all_specialists_with_coverage(self):
        bench = benchmark_routing(("sales", "ecommerce", "advertising", "crm", "operations"))
        self.assertEqual(20, bench["naive_specialists"])
        self.assertEqual(8, bench["routed_specialists"])
        self.assertTrue(bench["same_requested_domain_coverage"])
        self.assertGreater(bench["reduction_pct"], 50)
        self.assertLess(bench["routed_context_units"], bench["naive_context_units"])
        self.assertLess(bench["routed_latency_work_units"], bench["naive_latency_work_units"])


if __name__ == "__main__":
    unittest.main()
