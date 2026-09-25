"""Capability Adapter Factory: contract, resource rule, and reuse."""
from __future__ import annotations

import unittest

from jarvis import adapter_factory as af
from jarvis.routing import ProviderState

from test_execution_runtime import FakeMemory


class AdapterContractTests(unittest.TestCase):
    """The generic contract test any future adapter must also pass."""

    def adapters(self):
        return (af.CompanyMemoryAdapter(FakeMemory()), af.CodingExecutorAdapter())

    def test_every_adapter_implements_the_whole_contract(self):
        for adapter in self.adapters():
            for method in af.REQUIRED_ADAPTER_METHODS:
                self.assertTrue(callable(getattr(adapter, method, None)),
                                f"{adapter.name} is missing {method}()")

    def test_health_reports_and_never_raises(self):
        for adapter in self.adapters():
            health = adapter.health()
            self.assertIn("state", health)
            self.assertIn(health["state"], {state.value for state in af.AdapterState})

    def test_health_of_an_unreadable_binary_path_is_reported_not_raised(self):
        """CI 25.09.2026'da yakaladi: is_file() PermissionError firlatiyordu.

        Varsayilan ikili yolu /root altinda. Uretimde servis root olarak
        kostugu icin hic tetiklenmedi -- kusur vardi, yalniz o makinede
        gorunmuyordu. CI root degil ve ilk kosuda iki test dustu.

        🔴 "Bakamadim" ile "yok" ayri raporlanmali: izin hatasini
        UNAVAILABLE yazmak, var olan bir ikiliyi yok ilan etmek olurdu.
        """
        from unittest import mock
        adapter = af.CodingExecutorAdapter()
        with mock.patch("pathlib.Path.is_file",
                        side_effect=PermissionError(13, "Permission denied")):
            health = adapter.health()          # firlatmamali
        self.assertEqual(health["state"], af.AdapterState.DEGRADED.value)
        self.assertIsNone(health["binary_present"])
        self.assertIn("PermissionError", health["reason"])

    def test_health_of_a_broken_upstream_is_reported_not_raised(self):
        class Broken(FakeMemory):
            def get_system_status(self):
                raise RuntimeError("postgres is down")

        health = af.CompanyMemoryAdapter(Broken()).health()
        self.assertEqual(health["state"], af.AdapterState.UNAVAILABLE.value)

    def test_capabilities_evidence_and_metrics_are_structured(self):
        for adapter in self.adapters():
            self.assertIsInstance(adapter.capabilities(), tuple)
            self.assertTrue(adapter.capabilities())
            for item in adapter.evidence():
                self.assertIsInstance(item, af.AdapterEvidence)
                self.assertTrue(item.source)
            self.assertEqual(adapter.metrics()["model_calls"], 0)

    def test_cancel_and_resume_answer_honestly_rather_than_being_absent(self):
        for adapter in self.adapters():
            self.assertIsInstance(adapter.cancel("handle"), bool)
            self.assertIsInstance(adapter.resume("handle"), bool)

    def test_registering_something_that_is_not_an_adapter_is_refused(self):
        class NotAnAdapter:
            name = "bogus"

        with self.assertRaises(TypeError):
            af.AdapterFactory().register(NotAnAdapter())


class AdapterStateTests(unittest.TestCase):
    def test_state_vocabulary_is_compatible_with_the_existing_router(self):
        adapter_values = {state.value for state in af.AdapterState}
        provider_values = {state.value for state in ProviderState}
        self.assertTrue(provider_values <= adapter_values)
        self.assertIn("REQUIRES_RESOURCE_UPGRADE", adapter_values - provider_values)


class ResourceRuleTests(unittest.TestCase):
    SMALL_HOST = {"ram_gib": 13.65, "cpu_cores": 4, "gpu": None}

    def test_a_fitting_requirement_is_available(self):
        requirement = af.ResourceRequirement(ram_gib_min=4, ram_gib_recommended=8,
                                             cpu_cores=2, disk_gib=5)
        verdict = af.assess_resources(requirement, self.SMALL_HOST)
        self.assertTrue(verdict.fits)
        self.assertEqual(verdict.state, af.AdapterState.AVAILABLE)
        self.assertEqual(verdict.recommendation, af.NO_UPGRADE_NEEDED)

    def test_a_shortfall_is_an_upgrade_requirement_not_an_elimination(self):
        verdict = af.assess_resources(af.BGE_M3_RESOURCE, self.SMALL_HOST)
        self.assertFalse(verdict.fits)
        self.assertEqual(verdict.state, af.AdapterState.REQUIRES_RESOURCE_UPGRADE)
        self.assertNotEqual(verdict.state, af.AdapterState.UNAVAILABLE)
        self.assertTrue(verdict.shortfalls)
        self.assertEqual(verdict.current, self.SMALL_HOST)

    def test_the_verdict_carries_every_number_a_decision_needs(self):
        verdict = af.assess_resources(af.BGE_M3_RESOURCE, self.SMALL_HOST).to_dict()
        requirement = verdict["requirement"]
        for key in ("ram_gib_min", "ram_gib_recommended", "cpu_cores", "disk_gib",
                    "gpu_required", "vram_gib_min", "vram_gib_recommended",
                    "concurrency_headroom"):
            self.assertIn(key, requirement)
        self.assertIn("current", verdict)
        self.assertIn("recommendation", verdict)

    def test_a_far_larger_requirement_recommends_a_dedicated_worker(self):
        verdict = af.assess_resources(af.BGE_M3_RESOURCE, self.SMALL_HOST)
        self.assertEqual(verdict.recommendation, af.DEDICATED_WORKER)

    def test_a_modest_shortfall_recommends_upgrading_the_main_vds(self):
        requirement = af.ResourceRequirement(ram_gib_min=16, ram_gib_recommended=20,
                                             cpu_cores=4, disk_gib=10)
        verdict = af.assess_resources(requirement, self.SMALL_HOST)
        self.assertEqual(verdict.recommendation, af.MAIN_VDS_UPGRADE)

    def test_a_gpu_requirement_always_goes_to_its_own_box(self):
        requirement = af.ResourceRequirement(ram_gib_min=8, ram_gib_recommended=8,
                                             cpu_cores=2, disk_gib=5,
                                             gpu_required=True, vram_gib_min=12)
        verdict = af.assess_resources(requirement, self.SMALL_HOST)
        self.assertEqual(verdict.recommendation, af.DEDICATED_WORKER)


class UpstreamReuseTests(unittest.TestCase):
    def setUp(self):
        self.factory = af.AdapterFactory()

    def test_previously_verified_upstreams_are_reused_not_re_benchmarked(self):
        for name in ("RouteLabs Router", "pgvector", "Qwen-Agent", "smolagents",
                     "Agno", "Kimi Code", "BGE-M3", "Ruflo", "Yemaka"):
            evaluation = self.factory.evaluate(name)
            self.assertTrue(evaluation["known"], f"{name} lost its recorded evidence")
            self.assertTrue(evaluation["reused_evidence"])

    def test_already_integrated_upstreams_are_not_reinstalled(self):
        for name in ("pgvector", "Kimi Code"):
            evaluation = self.factory.evaluate(name)
            self.assertTrue(evaluation["already_integrated"])
            self.assertIn("do not reinstall", evaluation["constraint"])

    def test_bge_m3_is_held_for_resources_not_rejected(self):
        evaluation = self.factory.evaluate("BGE-M3", ResourceRuleTests.SMALL_HOST)
        self.assertEqual(evaluation["state"], af.AdapterState.REQUIRES_RESOURCE_UPGRADE.value)
        self.assertIsNotNone(evaluation["resource_verdict"])
        self.assertTrue(evaluation["resource_verdict"]["shortfalls"])

    def test_blocked_upstreams_are_not_pushed_to_production(self):
        for name in ("Ruflo", "Yemaka"):
            evaluation = self.factory.evaluate(name)
            self.assertEqual(evaluation["state"], af.AdapterState.UNAVAILABLE.value)
            self.assertNotEqual(evaluation["disposition"], "ALREADY_INTEGRATED")

    def test_routelabs_stays_a_routing_boundary_only(self):
        evaluation = self.factory.evaluate("RouteLabs Router")
        self.assertEqual(evaluation["disposition"], "ROUTING_BOUNDARY_ONLY")
        self.assertIn("never own truth", evaluation["constraint"])

    def test_an_unknown_upstream_is_not_waved_through(self):
        evaluation = self.factory.evaluate("some-random-github-project")
        self.assertFalse(evaluation["known"])
        self.assertIn("human must run", evaluation["next_action"])


class IntegrationProposalTests(unittest.TestCase):
    def setUp(self):
        self.factory = af.AdapterFactory()

    def test_the_factory_installs_and_deploys_nothing(self):
        proposal = self.factory.propose_integration("Qwen-Agent", "semantic_memory_retrieval")
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertFalse(proposal["installed"])
        self.assertFalse(proposal["deployed"])
        self.assertTrue(proposal["approval_required"])

    def test_the_pipeline_stages_are_complete_and_ordered(self):
        self.assertEqual(af.INTEGRATION_STAGES[0], "CAPABILITY_GAP")
        self.assertEqual(af.INTEGRATION_STAGES[-1], "DEPLOY")
        for stage in ("REGISTRY_CHECK", "ISOLATED_INSTALL",
                      "MANIFEST_DEPENDENCY_LICENSE_SECURITY", "SMOKE", "BENCHMARK",
                      "ADAPTER", "CONTRACT_TESTS", "REGRESSION", "REGISTRY_UPDATE",
                      "PROPOSED", "HUMAN_APPROVAL"):
            self.assertIn(stage, af.INTEGRATION_STAGES)
        self.assertLess(af.INTEGRATION_STAGES.index("SMOKE"),
                        af.INTEGRATION_STAGES.index("BENCHMARK"))
        self.assertLess(af.INTEGRATION_STAGES.index("CONTRACT_TESTS"),
                        af.INTEGRATION_STAGES.index("PROPOSED"))
        self.assertLess(af.INTEGRATION_STAGES.index("HUMAN_APPROVAL"),
                        af.INTEGRATION_STAGES.index("DEPLOY"))

    def test_the_factory_cannot_claim_stages_only_a_human_can_perform(self):
        proposal = self.factory.propose_integration("Agno", "agent_runtime")
        self.assertNotIn("ISOLATED_INSTALL", proposal["stages_completed"])
        self.assertNotIn("DEPLOY", proposal["stages_completed"])
        self.assertIn("ISOLATED_INSTALL", proposal["stages_remaining"])
        self.assertIn("HUMAN_APPROVAL", proposal["stages_remaining"])

    def test_a_resource_blocked_candidate_carries_its_shortfall_as_a_blocker(self):
        proposal = self.factory.propose_integration(
            "BGE-M3", "semantic_memory_retrieval", ResourceRuleTests.SMALL_HOST)
        self.assertTrue(proposal["blockers"])
        self.assertTrue(any("RAM" in blocker for blocker in proposal["blockers"]))


class CodingBoundaryTests(unittest.TestCase):
    def test_wrapping_the_coding_executor_did_not_create_a_new_way_in(self):
        adapter = af.CodingExecutorAdapter()
        with self.assertRaises(PermissionError):
            adapter.execute({"objective": "do something"})
        self.assertEqual(adapter.metrics()["refusals"], 1)

    def test_even_a_human_originated_envelope_routes_back_to_the_operator_path(self):
        adapter = af.CodingExecutorAdapter()
        result = adapter.execute({"human_originated": True})
        self.assertFalse(result["executed"])
        self.assertIn("create-coding-task", result["originate_with"])

    def test_the_adapter_never_calls_the_executor(self):
        from unittest.mock import patch

        adapter = af.CodingExecutorAdapter()
        with patch("jarvis.coding_executor.run_coding_task",
                   side_effect=AssertionError("adapter executed CodingExecutor")):
            adapter.health()
            adapter.execute({"human_originated": True})


class MemoryAdapterTests(unittest.TestCase):
    def test_only_allowlisted_queries_are_served(self):
        adapter = af.CompanyMemoryAdapter(FakeMemory())
        self.assertEqual(adapter.execute({"query": "open_work"})["records"], 1)
        with self.assertRaises(ValueError):
            adapter.execute({"query": "mart.reklam_performans"})

    def test_default_factory_registers_working_adapters(self):
        factory = af.default_factory(FakeMemory())
        self.assertIn("company_memory", factory.names())
        self.assertIn("coding_executor", factory.names())
        self.assertTrue(factory.for_capability("deterministic_company_memory"))


if __name__ == "__main__":
    unittest.main()
