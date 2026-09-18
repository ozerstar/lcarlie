"""Execution Planner V1 tests.

Every test here runs with no database, no subprocess and no network: if the
planner ever acquired a side effect, these would start failing rather than
quietly succeeding, which is the point.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from jarvis import capabilities as caps
from jarvis import execution_planner as ep


def _plan(request, registry=None):
    return ep.plan_request(request, registry=registry)


class ContractTests(unittest.TestCase):
    def test_every_route_target_names_an_existing_module(self):
        for capability, route in ep.ROUTES.items():
            self.assertEqual(capability, route.capability)
            self.assertTrue(route.target)
            self.assertIn(route.execution_class, ep._EXEC_ORDER)

    def test_plan_output_carries_every_required_field(self):
        data = _plan("vireon satışlarını incele").to_dict()
        for key in ("plan_id", "request", "intent", "risk", "mode", "steps",
                    "dependencies", "parallel_groups", "required_capabilities",
                    "required_internal_data", "requires_fresh_research",
                    "context_requirements", "approval_required",
                    "estimated_execution_class", "status"):
            self.assertIn(key, data)
        json.dumps(data, ensure_ascii=False)  # must be serialisable for the wire

    def test_plan_id_is_deterministic_for_the_same_request(self):
        self.assertEqual(_plan("vireon satışları neden düşük").plan_id,
                         _plan("Vireon  SATIŞLARI neden düşük ").plan_id)

    def test_planning_never_calls_a_model(self):
        self.assertEqual(_plan("rakipleri araştır ve satışlarımızı analiz et").model_calls, 0)


class ModeTests(unittest.TestCase):
    def test_single_retrieval_is_fast(self):
        self.assertEqual(_plan("sistem durumu").mode, ep.MODE_FAST)

    def test_root_cause_question_is_smart(self):
        plan = _plan("vireon satışları neden düşük araştır")
        # "araştır" is an external lemma, so this particular phrasing is DEEP;
        # a purely internal root-cause question is the SMART case.
        self.assertEqual(_plan("vireon satışları neden düşük").mode, ep.MODE_SMART)
        self.assertEqual(plan.mode, ep.MODE_DEEP)

    def test_fresh_research_forces_deep(self):
        self.assertEqual(_plan("rakipleri araştır").mode, ep.MODE_DEEP)

    def test_two_workstreams_force_deep(self):
        self.assertEqual(_plan("rakipleri araştır, satışlarımızı analiz et").mode, ep.MODE_DEEP)

    def test_mode_selection_is_pure_and_rule_based(self):
        self.assertEqual(ep.select_mode(("internal_data_analysis",), False, False, False), ep.MODE_FAST)
        self.assertEqual(ep.select_mode(("internal_data_analysis",), False, True, False), ep.MODE_SMART)
        self.assertEqual(ep.select_mode(("internal_data_analysis",), True, False, False), ep.MODE_DEEP)
        self.assertEqual(ep.select_mode(("coding_task",), False, False, False), ep.MODE_DEEP)


class DagTests(unittest.TestCase):
    def test_composite_request_builds_the_expected_dag(self):
        plan = _plan("Rakipleri araştır, satışlarımızı analiz et ve bana ne yapmamız gerektiğini söyle")
        by_capability = {step.capability: step for step in plan.steps}
        self.assertIn("internal_data_analysis", by_capability)
        self.assertIn("external_research", by_capability)
        self.assertIn("evidence_fusion", by_capability)
        self.assertIn("red_team_review", by_capability)
        self.assertIn("human_review_proposal", by_capability)

        internal = by_capability["internal_data_analysis"]
        external = by_capability["external_research"]
        fusion = by_capability["evidence_fusion"]
        red = by_capability["red_team_review"]
        proposal = by_capability["human_review_proposal"]

        # A and B independent, therefore the same parallel group
        self.assertEqual(internal.parallel_group, external.parallel_group)
        self.assertEqual(internal.depends_on, ())
        self.assertEqual(external.depends_on, ())
        # C fuses both, D red-teams C, E proposes from D
        self.assertEqual(set(fusion.depends_on), {internal.step_id, external.step_id})
        self.assertEqual(red.depends_on, (fusion.step_id,))
        self.assertEqual(proposal.depends_on, (red.step_id,))
        self.assertEqual(plan.intent, "COMPOSITE")

    def test_parallel_groups_partition_every_step_exactly_once(self):
        plan = _plan("rakipleri araştır, satışlarımızı analiz et ve öneri ver")
        flat = [step_id for group in plan.parallel_groups for step_id in group]
        self.assertEqual(sorted(flat), sorted(step.step_id for step in plan.steps))
        self.assertEqual(len(flat), len(set(flat)))

    def test_dependencies_are_acyclic_and_reference_real_steps(self):
        plan = _plan("rakipleri araştır ve satışları analiz et, ne yapmalıyız")
        ids = {step.step_id for step in plan.steps}
        seen: set[str] = set()
        for group in plan.parallel_groups:
            for step_id in group:
                step = next(s for s in plan.steps if s.step_id == step_id)
                for parent in step.depends_on:
                    self.assertIn(parent, ids)
                    # a dependency must already have been scheduled
                    self.assertIn(parent, seen)
            seen.update(group)

    def test_a_step_sits_one_level_below_its_deepest_dependency(self):
        plan = _plan("rakipleri araştır, satışları analiz et, ne yapmalıyız")
        level = {step.step_id: step.parallel_group for step in plan.steps}
        for step in plan.steps:
            for parent in step.depends_on:
                self.assertGreater(level[step.step_id], level[parent])


class SafetyBoundaryTests(unittest.TestCase):
    def test_external_action_request_is_blocked_not_planned(self):
        plan = _plan("müşteriye whatsapp mesajı gönder")
        self.assertEqual(plan.status, ep.STATUS_BLOCKED_EXTERNAL_ACTION)
        self.assertEqual(plan.risk, ep.RISK_HIGH)
        self.assertTrue(plan.approval_required)
        self.assertEqual([step.capability for step in plan.steps], ["human_review_proposal"])
        self.assertNotIn("external_action", {step.capability for step in plan.steps})

    def test_price_change_is_also_blocked(self):
        plan = _plan("vireon fiyatını güncelle ve yayınla")
        self.assertEqual(plan.status, ep.STATUS_BLOCKED_EXTERNAL_ACTION)

    def test_coding_request_plans_one_step_that_a_human_must_originate(self):
        plan = _plan("şu modüldeki bug'ı düzelt")
        coding = [step for step in plan.steps if step.capability == "coding_task"]
        self.assertEqual(len(coding), 1)
        step = coding[0]
        self.assertTrue(step.requires_human_origination)
        self.assertEqual(step.execution_class, ep.EXEC_CODING_SANDBOX)
        self.assertIn("create-coding-task", step.arguments["originate_with"])
        self.assertEqual(plan.risk, ep.RISK_HIGH)
        self.assertTrue(plan.approval_required)
        self.assertEqual(plan.estimated_execution_class, ep.EXEC_CODING_SANDBOX)

    def test_no_route_bypasses_the_firewall_for_an_action(self):
        for route in ep.ROUTES.values():
            if route.produces_action:
                self.assertTrue(
                    "human approval" in route.target or "create-coding-task" in route.target,
                    f"{route.capability} produces an action without a human gate",
                )

    def test_planner_opens_no_subprocess_and_no_socket(self):
        with patch("subprocess.run", side_effect=AssertionError("planner ran a subprocess")), \
             patch("socket.socket", side_effect=AssertionError("planner opened a socket")):
            _plan("rakipleri araştır, satışları analiz et ve kodu düzelt")


class FailSafeTests(unittest.TestCase):
    def test_empty_request_is_rejected(self):
        for request in ("", "   ", "a"):
            plan = _plan(request)
            self.assertEqual(plan.status, ep.STATUS_REJECTED_AMBIGUOUS)
            self.assertEqual(plan.steps, ())
            self.assertFalse(plan.approval_required)

    def test_overlong_request_is_rejected(self):
        plan = _plan("satış " * 1000)
        self.assertEqual(plan.status, ep.STATUS_REJECTED_AMBIGUOUS)
        self.assertIn("2000", plan.reason)

    def test_unrecognised_request_still_produces_a_safe_minimal_plan(self):
        plan = _plan("zzz qqq")
        self.assertEqual(plan.status, ep.STATUS_PLANNED)
        self.assertEqual([step.capability for step in plan.steps], ["internal_data_analysis"])
        self.assertFalse(plan.requires_fresh_research)
        self.assertFalse(plan.approval_required)


class CapabilityGateTests(unittest.TestCase):
    def _registry(self, **overrides):
        registry = {
            "deterministic_company_memory": caps.Capability(
                capability_id="deterministic_company_memory", capability_name="m",
                status=caps.AVAILABLE, executor="x", source="probe"),
            "external_model_provider": caps.Capability(
                capability_id="external_model_provider", capability_name="p",
                status=caps.BLOCKED, executor="none", source="policy",
                blocker="SHADOW_MODE_NO_EXTERNAL_PROVIDER",
                fallback="deterministic_company_memory"),
            "external_business_action": caps.Capability(
                capability_id="external_business_action", capability_name="a",
                status=caps.CONTROLLED, executor="firewall", source="probe"),
        }
        registry.update(overrides)
        return registry

    def test_without_a_registry_status_is_not_evaluated_never_assumed_ok(self):
        plan = _plan("vireon satışlarını incele")
        self.assertEqual(plan.status, ep.STATUS_PLANNED)
        self.assertEqual({step.capability_status for step in plan.steps}, {"NOT_EVALUATED"})

    def test_blocked_capability_blocks_the_step_and_the_plan(self):
        plan = _plan("rakipleri araştır", registry=self._registry())
        self.assertEqual(plan.status, ep.STATUS_BLOCKED_CAPABILITY)
        research = next(s for s in plan.steps if s.capability == "external_research")
        self.assertEqual(research.capability_status, "BLOCKED")
        self.assertIn("external_model_provider", research.blocked_by)

    def test_available_capability_leaves_the_plan_planned(self):
        plan = _plan("vireon satışlarını incele", registry=self._registry())
        self.assertEqual(plan.status, ep.STATUS_PLANNED)
        internal = next(s for s in plan.steps if s.capability == "internal_data_analysis")
        self.assertEqual(internal.capability_status, "OK")

    def test_unregistered_capability_blocks_rather_than_passing_silently(self):
        registry = self._registry()
        del registry["deterministic_company_memory"]
        plan = _plan("vireon satışlarını incele", registry=registry)
        self.assertEqual(plan.status, ep.STATUS_BLOCKED_CAPABILITY)


class ContextRoutingTests(unittest.TestCase):
    def test_entity_and_internal_data_are_named_for_the_context_compiler(self):
        plan = _plan("vireon satışları neden düşük")
        self.assertEqual(plan.context_requirements["entity"], "VIREON")
        self.assertIn("product_context:VIREON", plan.required_internal_data)
        self.assertEqual(plan.context_requirements["compiler"], "jarvis.context.ContextCompiler")

    def test_capability_question_routes_to_the_capability_registry(self):
        plan = _plan("hangi yeteneklerin eksik")
        self.assertIn("capability_analysis", {step.capability for step in plan.steps})
        self.assertIn("capability_state", plan.required_internal_data)

    def test_required_capabilities_come_from_the_routing_table_only(self):
        plan = _plan("rakipleri araştır ve satışları analiz et")
        allowed = {name for route in ep.ROUTES.values() for name in route.requires_capabilities}
        self.assertTrue(set(plan.required_capabilities) <= allowed)


if __name__ == "__main__":
    unittest.main()
