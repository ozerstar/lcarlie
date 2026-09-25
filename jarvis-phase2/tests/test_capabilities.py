"""Phase 2D / F-2: capability registry and real capability-gap analysis,
plus the cross-check that a gap cannot bypass the Action Firewall."""
import unittest
from unittest.mock import patch

from jarvis import capabilities as caps
from jarvis.action_contract import build_contract
from jarvis.context import ContextCompiler
from jarvis.firewall import FirewallError, validate_proposal
from jarvis.memory import Evidence
from jarvis.phase2 import Phase2Runtime

from test_action_contract import LIVE_ROWS

HEALTHY_PROBE = {
    "pgvector_version": "0.8.6",
    "semantic_table": 1,
    "semantic_indexes": 3,
    "state_functions": 2,
    # Same single round trip the real adapter makes: infrastructure facts and
    # the health record come back together.
    "health": {"checked_at": "2026-09-18T00:00:00+03:00", "open_tasks": 0,
               "pending_actions": 0},
}


class FakeMemory:
    """Mirrors the real adapter's surface; records what was asked."""

    def __init__(self, probe=None, healthy=True):
        self.probe = HEALTHY_PROBE if probe is None else probe
        self.healthy = healthy
        self.calls = []

    def _evidence(self, source, records):
        self.calls.append(source)
        return Evidence(source, "CANONICAL_COMPANY_MEMORY", "test", records, 1.0)

    def get_capability_state(self):
        return self._evidence("postgres:capability_state", [self.probe])

    def get_system_status(self):
        if not self.healthy:
            raise RuntimeError("memory down")
        return self._evidence("postgres:system", [{"open_tasks": 0, "pending_actions": 0}])

    def get_company_context(self):
        return self._evidence("postgres:decision_summary", [{"karar": 1}])

    def get_company_agenda(self):
        return self._evidence("postgres:agenda", [{"soru": "x"}])

    def get_product_context(self, entity):
        return self._evidence("postgres:agenda", [{"entity": entity}])

    def get_action_contract(self):
        return self._evidence("postgres:action_contract", LIVE_ROWS)


def contract():
    return build_contract(LIVE_ROWS, source="postgres:action_contract")


class RegistryTests(unittest.TestCase):
    def test_registry_entries_carry_every_required_field(self):
        registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)
        self.assertTrue(registry)
        for capability in registry.values():
            data = capability.to_dict()
            for field in ("capability_id", "capability_name", "status", "executor",
                          "source", "evidence", "last_verified_at",
                          "resource_requirement", "blocker", "fallback"):
                self.assertIn(field, data, capability.capability_id)
            self.assertTrue(capability.evidence, capability.capability_id)

    def test_status_is_derived_from_probe_not_declared(self):
        healthy = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)
        self.assertEqual(healthy["postgres_persistent_state"].status, caps.AVAILABLE)
        self.assertEqual(healthy["pgvector_retrieval_interface"].status, caps.AVAILABLE)

        broken = caps.build_registry(probe={"state_functions": 0}, contract=contract(), memory_ok=True)
        self.assertEqual(broken["postgres_persistent_state"].status, caps.MISSING)
        self.assertEqual(broken["pgvector_retrieval_interface"].status, caps.MISSING)

    def test_failed_memory_probe_is_recorded_not_assumed(self):
        registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=False)
        self.assertEqual(registry["deterministic_company_memory"].status, caps.MISSING)

    def test_unprobed_capability_is_unknown_not_available(self):
        registry = caps.build_registry()
        self.assertEqual(registry["deterministic_company_memory"].status, caps.UNKNOWN)

    def test_bge_m3_resource_blocked_from_measured_host(self):
        with patch.object(caps, "host_resources", return_value={"ram_gib": 13.65, "cpu_cores": 4}):
            registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)
        capability = registry["embedding_model_bge_m3"]
        self.assertEqual(capability.status, caps.RESOURCE_BLOCKED)
        self.assertEqual(capability.blocker, "WAITING_RESOURCE_UPGRADE")
        self.assertEqual(capability.resource_requirement["ram_gib_min"], 32)
        self.assertEqual(caps.recommend(capability), caps.REQUIRES_RESOURCE_UPGRADE)

    def test_semantic_retrieval_blocked_while_embeddings_absent(self):
        with patch.object(caps, "host_resources", return_value={"ram_gib": 13.65, "cpu_cores": 4}):
            registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)
        capability = registry["semantic_memory_retrieval"]
        self.assertEqual(capability.status, caps.RESOURCE_BLOCKED)
        self.assertEqual(capability.fallback, "deterministic_company_memory")

    def test_external_action_is_controlled_when_contract_valid(self):
        registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)
        capability = registry["external_business_action"]
        self.assertEqual(capability.status, caps.CONTROLLED)
        self.assertEqual(capability.blocker, "HUMAN_APPROVAL_REQUIRED")

    def test_external_action_blocked_when_contract_invalid(self):
        registry = caps.build_registry(probe=HEALTHY_PROBE, contract=build_contract([], "x"), memory_ok=True)
        self.assertEqual(registry["external_business_action"].status, caps.BLOCKED)

    def test_upstream_blockers_are_recorded_facts(self):
        registry = caps.build_registry()
        self.assertEqual(registry["ruflo_workflow_engine"].status, caps.UPSTREAM_BLOCKED)
        self.assertEqual(registry["yemaka_reference"].status, caps.UPSTREAM_BLOCKED)
        self.assertEqual(caps.recommend(registry["ruflo_workflow_engine"]),
                         caps.UPSTREAM_BLOCKER_REPORT)

    def test_unregistered_capability_asks_for_a_benchmark(self):
        self.assertEqual(caps.resolve("new_tool")["next"], caps.BENCHMARK_REQUIRED)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(caps, "host_resources", return_value={"ram_gib": 13.65, "cpu_cores": 4})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.registry = caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True)

    def test_company_memory_question_selects_only_relevant_capabilities(self):
        analysis = caps.analyse("Company Memory tarafında eksik capability var mı?", self.registry)
        self.assertEqual(analysis["capabilities_in_context"], 5)
        self.assertLess(analysis["capabilities_in_context"], analysis["registry_size"])
        self.assertNotIn("ruflo_workflow_engine", analysis["required_capabilities"])

    def test_gap_is_identified_with_recommendation_and_fallback(self):
        analysis = caps.analyse("Company Memory tarafında eksik capability var mı?", self.registry)
        self.assertTrue(analysis["capability_gap"])
        self.assertIn("semantic_memory_retrieval", analysis["resource_blocked_capabilities"])
        self.assertIn("deterministic_company_memory", analysis["available_capabilities"])
        self.assertIn(caps.REQUIRES_RESOURCE_UPGRADE, analysis["recommendations"])
        self.assertIn("deterministic_company_memory", analysis["fallback_capabilities"])

    def test_gap_entries_carry_evidence_and_requirements(self):
        analysis = caps.analyse("Company Memory tarafında eksik capability var mı?", self.registry)
        gap = next(row for row in analysis["gaps"] if row["capability_id"] == "embedding_model_bge_m3")
        self.assertEqual(gap["recommendation"], caps.REQUIRES_RESOURCE_UPGRADE)
        self.assertEqual(gap["resource_requirement"]["ram_gib_min"], 32)
        self.assertTrue(any("measured host RAM" in item for item in gap["evidence"]))

    def test_all_bucket_keys_present(self):
        analysis = caps.analyse("capability?", self.registry)
        for field in ("required_capabilities", "available_capabilities", "missing_capabilities",
                      "blocked_capabilities", "resource_blocked_capabilities",
                      "fallback_capabilities"):
            self.assertIn(field, analysis)

    def test_analysis_never_installs_or_names_an_action_type(self):
        analysis = caps.analyse("Company Memory tarafında eksik capability var mı?", self.registry)
        self.assertNotIn("action_type", analysis)
        for row in analysis["gaps"]:
            self.assertNotIn(row["recommendation"], {"INSTALL", "DEPLOY"})


class ContextCompilerCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.memory = FakeMemory()
        self.compiler = ContextCompiler(self.memory)

    def test_capability_question_runs_real_analysis(self):
        compiled = self.compiler.compile(
            "Jarvis, Company Memory tarafında eksik capability var mı?", contract=contract())
        self.assertIsNotNone(compiled.capability_analysis)
        self.assertIn("capability_analysis", compiled.capabilities)
        self.assertIn("postgres:capability_state", self.memory.calls)
        self.assertIn("postgres:capability_state", compiled.evidence_refs)
        # health arrives in the same row, so deterministic memory is derived
        self.assertIn("deterministic_company_memory",
                      compiled.capability_analysis["available_capabilities"])
        self.assertEqual(compiled.capability_analysis["health_checked_at"],
                         "2026-09-18T00:00:00+03:00")

    def test_capability_branch_makes_one_round_trip(self):
        self.compiler.compile("eksik capability var mı?", contract=contract())
        self.assertEqual(self.memory.calls.count("postgres:capability_state"), 1)
        self.assertEqual(self.memory.calls.count("postgres:system"), 0)

    def test_failed_probe_is_reported_not_crashed(self):
        class BrokenMemory(FakeMemory):
            def get_capability_state(self):
                raise RuntimeError("probe down")

        compiled = ContextCompiler(BrokenMemory()).compile(
            "eksik capability var mı?", contract=contract())
        analysis = compiled.capability_analysis
        self.assertIsNotNone(analysis)
        self.assertIn("deterministic_company_memory", analysis["missing_capabilities"])

    def test_phase2c_regression_capability_question_no_longer_falls_through(self):
        compiled = self.compiler.compile(
            "Jarvis, Company Memory tarafında eksik capability var mı?", contract=contract())
        # Phase 2C retrieved the decision summary and called it a pass.
        self.assertNotEqual(compiled.evidence_refs, ("postgres:decision_summary",))

    def test_non_capability_questions_are_unchanged(self):
        compiled = self.compiler.compile("Jarvis, sistem durumu ne?", contract=contract())
        self.assertIsNone(compiled.capability_analysis)
        self.assertEqual(compiled.evidence_refs, ("postgres:system",))
        self.assertNotIn("postgres:capability_state", self.memory.calls)

    def test_registry_is_not_dumped_into_context(self):
        compiled = self.compiler.compile("eksik capability var mı?", contract=contract())
        analysis = compiled.capability_analysis
        self.assertLess(analysis["capabilities_in_context"], analysis["registry_size"])


class CrossCheckTests(unittest.TestCase):
    """A capability gap must not become a back door around F-1."""

    def setUp(self):
        self.runtime = Phase2Runtime(ContextCompiler(FakeMemory()))

    def test_capability_gap_output_carries_no_action_type(self):
        result = self.runtime.handle(
            "Jarvis, Company Memory tarafında eksik capability var mı?", contract=contract())
        self.assertFalse(result["external_action_executed"])
        self.assertNotIn("action_type", result["context"]["capability_analysis"])

    def test_remediation_intent_still_has_to_pass_the_firewall(self):
        analysis = caps.analyse("Company Memory tarafında eksik capability var mı?",
                                caps.build_registry(probe=HEALTHY_PROBE, contract=contract(), memory_ok=True))
        for recommendation in analysis["recommendations"]:
            # A recommendation string is not an action type and must not resolve.
            with self.assertRaises(FirewallError):
                validate_proposal(recommendation, {"reason": "gap"}, contract())

    def test_development_proposal_uses_the_canonical_contract(self):
        result = validate_proposal("HUMAN_REVIEW_REQUEST",
                                   {"subject_ref": "capability-gap", "reason": "needs a decision"},
                                   contract())
        self.assertEqual(result["action_type"], "REQUEST_HUMAN_REVIEW")
        self.assertEqual(result["status"], "PROPOSED")
        self.assertTrue(result["human_approval_required"])


if __name__ == "__main__":
    unittest.main()
