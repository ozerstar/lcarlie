from __future__ import annotations

import unittest

from jarvis.acceptance_contract import criteria_for, evaluate
from jarvis.execution_planner import plan_request


class AcceptanceContractTests(unittest.TestCase):
    def test_plan_discloses_handoff_criteria(self):
        steps = plan_request("satış ve crm analiz et").to_dict()["steps"]
        analysis = next(step for step in steps if step["capability"] == "sales_analysis")
        self.assertEqual(analysis["acceptance_criteria"], list(criteria_for("sales_analysis")))

    def test_missing_evidence_fails_even_if_executor_says_success(self):
        result = evaluate("sales_analysis", "SUCCEEDED", {"records": 2}, ())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual([item["criterion"] for item in result["checks"] if not item["passed"]],
                         ["source_traceable"])

    def test_empty_evidence_reference_is_not_traceable(self):
        self.assertEqual(evaluate("sales_analysis", "SUCCEEDED", {"records": 2}, ("",))["status"],
                         "FAILED")

    def test_read_only_step_cannot_claim_proposed(self):
        result = evaluate("sales_analysis", "PROPOSED", {"records": 2}, ("postgres:sales",))
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["checks"][0]["criterion"], "read_only_completed")

    def test_proposal_must_not_have_been_submitted(self):
        output = {"idempotency_key": "key", "payload": {"reason": "review"}, "submitted": True}
        self.assertEqual(evaluate("action_plan", "PROPOSED", output, ())["status"], "FAILED")
        output["submitted"] = False
        self.assertEqual(evaluate("action_plan", "PROPOSED", output, ())["status"], "PASSED")

    def test_red_team_clean_flag_must_match_objections(self):
        result = evaluate("red_team_review", "SUCCEEDED", {"objections": [{}], "clean": True}, ())
        self.assertEqual(result["status"], "FAILED")

    def test_missing_fusion_sources_are_explicit(self):
        self.assertEqual(evaluate("evidence_fusion", "SUCCEEDED",
                                  {"fused_inputs": 0, "missing_inputs": [{"step_id": "S1"}]},
                                  ())["status"], "PASSED")
        self.assertEqual(evaluate("evidence_fusion", "SUCCEEDED",
                                  {"fused_inputs": 0, "missing_inputs": []},
                                  ())["status"], "FAILED")
