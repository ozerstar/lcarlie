from __future__ import annotations

import time
import unittest

from jarvis.memory import CompanyMemory, Evidence
from jarvis.specialist_pool import (
    ALLOWLISTED_QUERIES, DATA_UNAVAILABLE, PROPOSED, REGISTRY, SPECIALISTS,
    CompanyMemoryGateway, DeterministicSpecialist, ResearchRequest,
    SpecialistContext, SpecialistContextCompiler, SpecialistPool,
    SpecialistRouter, benchmark_routing, deterministic_confidence,
)


class FakeMemory:
    QUERIES = CompanyMemory.QUERIES
    def _fetch(self, name):
        rows = {
            "sales_orders": [{"olcumde": True, "ciro_dogrulanmis_net": 100}],
            "sales_items": [{"adet": 1}],
            "ecommerce_profitability": [{"ciro_net": 100, "kapsama_yuzde": 50}],
            "ecommerce_price": [{"base_price": 100}],
            "ecommerce_funnel": [{"oran_yuzde": 10}],
            "advertising_performance": [{"pencere": 30, "harcama": 50,
                                          "commercial_confirmation": "NOT_AVAILABLE"}],
            "advertising_spend": [{"harcama": 50}],
            "crm_customers": [{"entity_id": 1}],
            "crm_unanswered": [{"bekleme_saat": 12}],
            "operations_shipments": [{"alarm": True}],
            "open_work": [{"tur": "x"}],
            "system": [{"healthy": True}],
        }.get(name, [{"metric": 1}])
        return Evidence(f"memory:{name}", "CANONICAL_COMPANY_MEMORY", "live", rows, 1.0)


class EmptyMemory(FakeMemory):
    def _fetch(self, name):
        raise RuntimeError("unavailable")


class SlowMemory(FakeMemory):
    def _fetch(self, name):
        time.sleep(.02)
        return super()._fetch(name)


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
        self.assertEqual(("ecommerce_sales", "meta_performance"), plan.primary)
        self.assertEqual(5, len(plan.selected))
        self.assertNotIn("finance", plan.selected)

    def test_parallel_stage_and_dependency_order(self):
        plan = SpecialistRouter().route(("advertising", "crm", "operations"))
        self.assertEqual(("meta_performance", "crm_customer", "operations"), plan.stages[0])
        self.assertEqual(("red_team",), plan.stages[1])
        self.assertEqual(("strategy",), plan.stages[2])
        self.assertEqual(("managing_director",), plan.stages[3])

    def test_company_memory_allowlist_and_unknown_query(self):
        gateway = CompanyMemoryGateway(FakeMemory())
        self.assertNotIn("sql", ALLOWLISTED_QUERIES)
        value, refs, freshness = gateway.read("DROP TABLE x")
        self.assertIsNone(value); self.assertEqual((), refs); self.assertEqual(DATA_UNAVAILABLE, freshness)

    def test_missing_data_is_not_faked(self):
        result = SpecialistPool(EmptyMemory()).execute("sales", ("sales",))
        finding = result["findings"][0]
        self.assertEqual(DATA_UNAVAILABLE, finding["finding_type"])
        self.assertEqual("", finding["claim"])
        self.assertIn("sales_orders", finding["missing_data"])

    def test_context_isolation(self):
        compiler = SpecialistContextCompiler(CompanyMemoryGateway(FakeMemory()))
        ctx = compiler.compile(REGISTRY["crm_customer"], "crm", "crm")
        self.assertEqual({"crm_customers", "crm_unanswered", "open_work"}, set(ctx.query_results))
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
        self.assertIn("CRM response backlog", result["findings"][-1]["claim"])

    def test_red_team_objects_to_missing_and_source_independence(self):
        result = SpecialistPool(EmptyMemory()).execute("sales", ("sales",))
        red = next(f for f in result["findings"] if f["specialist_id"] == "red_team")
        self.assertEqual("OBJECTION", red["finding_type"])
        self.assertIn("source_independence", red["contradictions"])

    def test_fusion_counts_evidence_sources_not_specialists(self):
        result = SpecialistPool(FakeMemory()).execute("crm ops", ("crm", "operations"))
        # Shared open_work counts once; domain-specific sources stay distinct.
        self.assertEqual(5, result["fusion"]["independent_sources"])
        self.assertFalse(result["fusion"]["contradiction"])

    def test_real_domain_mappings_are_current_and_gaps_stay_unavailable(self):
        self.assertEqual(("sales_orders", "sales_items"), REGISTRY["ecommerce_sales"].required_data)
        self.assertIn("ecommerce_profitability", REGISTRY["product_portfolio"].required_data)
        self.assertIn("crm_unanswered", REGISTRY["crm_customer"].required_data)
        self.assertIn("operations_shipments", REGISTRY["operations"].required_data)
        gaps = {item for specialist in SPECIALISTS for item in specialist.optional_data}
        self.assertTrue({"ga4_site_traffic", "real_inventory", "gunluk_marj"} <= gaps)
        self.assertTrue(gaps.isdisjoint(ALLOWLISTED_QUERIES))

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
        primary = result["findings"][:5]
        self.assertEqual({"sales", "ecommerce", "advertising", "crm", "operations"},
                         {item["domain"] for item in primary})
        self.assertTrue(all(item["evidence_refs"] for item in primary))

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
