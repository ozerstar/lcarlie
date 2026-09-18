"""Web console <-> ExecutionPlanner wiring.

Exercises the REAL route dispatch in webconsole.app rather than a
re-implementation of it: a stub handler records what _send_json was called
with, so the assertions are about what the browser would actually receive.

No socket is opened, no database is touched and no model is called; the
registry probe is the only I/O in the real endpoint and it is injected here.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis import capabilities as caps
from jarvis import execution_planner as ep

from webconsole import app as webapp


def _registry(external_provider_status=caps.BLOCKED,
              memory_status=caps.AVAILABLE):
    return {
        "deterministic_company_memory": caps.Capability(
            capability_id="deterministic_company_memory", capability_name="m",
            status=memory_status, executor="postgres:ai_reader", source="probe"),
        "external_model_provider": caps.Capability(
            capability_id="external_model_provider", capability_name="p",
            status=external_provider_status, executor="none", source="policy",
            blocker="SHADOW_MODE_NO_EXTERNAL_PROVIDER"),
        "external_business_action": caps.Capability(
            capability_id="external_business_action", capability_name="a",
            status=caps.CONTROLLED, executor="firewall", source="probe"),
    }


class _StubHandler:
    """Enough of Handler for _route_api_post to run unchanged."""

    def __init__(self, message):
        self._message = message
        self.sent = None

    # the real dispatcher calls these
    def _current_session(self):
        return object()

    def _require_csrf(self, session):
        return True

    def _send_json(self, status, payload, extra_headers=None):
        self.sent = (status, payload)


def _post_plan(message, registry=None):
    handler = _StubHandler(message)
    with patch.object(webapp, "_read_json_body", return_value={"message": message}), \
         patch.object(webapp, "_live_registry", return_value=registry if registry is not None else _registry()):
        webapp.Handler._route_api_post(handler, "/api/plan")
    return handler.sent


class RequestToPlanTests(unittest.TestCase):
    def test_natural_language_request_returns_a_plan(self):
        status, plan = _post_plan("Vireon satışları neden düşük")
        self.assertEqual(status, 200)
        self.assertEqual(plan["status"], ep.STATUS_PLANNED)
        self.assertTrue(plan["steps"])
        for key in ("intent", "mode", "risk", "steps", "parallel_groups",
                    "required_capabilities", "required_internal_data",
                    "requires_fresh_research", "approval_required", "plan_id"):
            self.assertIn(key, plan)

    def test_fast_mode_reaches_the_browser(self):
        _, plan = _post_plan("sistem durumu")
        self.assertEqual(plan["mode"], ep.MODE_FAST)

    def test_smart_mode_reaches_the_browser(self):
        _, plan = _post_plan("vireon satışları neden düşük")
        self.assertEqual(plan["mode"], ep.MODE_SMART)

    def test_deep_mode_reaches_the_browser(self):
        _, plan = _post_plan("rakipleri araştır, satışlarımızı analiz et ve ne yapmalıyız")
        self.assertEqual(plan["mode"], ep.MODE_DEEP)
        self.assertGreaterEqual(len(plan["parallel_groups"]), 2)

    def test_ambiguous_request_is_returned_as_rejected_not_as_an_error(self):
        status, plan = _post_plan("  ")
        self.assertEqual(status, 200)
        self.assertEqual(plan["status"], ep.STATUS_REJECTED_AMBIGUOUS)
        self.assertEqual(plan["steps"], [])
        self.assertTrue(plan["reason"])  # the UI shows this to the operator

    def test_blocked_capability_is_visible_to_the_operator(self):
        _, plan = _post_plan("rakipleri araştır")
        self.assertEqual(plan["status"], ep.STATUS_BLOCKED_CAPABILITY)
        blocked = [step for step in plan["steps"] if step["blocked_by"]]
        self.assertTrue(blocked)
        self.assertIn("external_model_provider", blocked[0]["blocked_by"])

    def test_capability_becomes_available_when_the_registry_says_so(self):
        _, plan = _post_plan("rakipleri araştır",
                             registry=_registry(external_provider_status=caps.AVAILABLE))
        self.assertEqual(plan["status"], ep.STATUS_PLANNED)


class NoExecutionTests(unittest.TestCase):
    def test_coding_request_plans_but_never_runs_codingexecutor(self):
        with patch("jarvis.coding_executor.run_coding_task",
                   side_effect=AssertionError("CodingExecutor was executed by the planner path")), \
             patch("jarvis.coding_executor._clone_canonical_source",
                   side_effect=AssertionError("a clone was created by the planner path")):
            status, plan = _post_plan("şu modüldeki bug'ı düzelt")
        self.assertEqual(status, 200)
        coding = [step for step in plan["steps"] if step["capability"] == "coding_task"]
        self.assertEqual(len(coding), 1)
        self.assertTrue(coding[0]["requires_human_origination"])
        self.assertTrue(plan["approval_required"])

    def test_plan_endpoint_makes_no_model_call(self):
        _, plan = _post_plan("rakipleri araştır ve satışları analiz et")
        self.assertEqual(plan["model_calls"], 0)

    def test_plan_endpoint_produces_no_external_action(self):
        _, plan = _post_plan("müşteriye whatsapp mesajı gönder")
        self.assertEqual(plan["status"], ep.STATUS_BLOCKED_EXTERNAL_ACTION)
        # the only step is an escalation to a human; nothing executable
        self.assertEqual([step["capability"] for step in plan["steps"]],
                         ["human_review_proposal"])
        external_steps = [step for step in plan["steps"]
                          if step["capability"] == "external_research"]
        self.assertEqual(external_steps, [])

    def test_endpoint_opens_no_subprocess_and_no_socket(self):
        with patch("subprocess.run", side_effect=AssertionError("subprocess from the plan endpoint")), \
             patch("socket.socket", side_effect=AssertionError("socket from the plan endpoint")):
            status, _ = _post_plan("rakipleri araştır, satışları analiz et ve kodu düzelt")
        self.assertEqual(status, 200)

    def test_no_execute_route_was_added(self):
        """REQUEST -> PLAN -> DISPLAY only: there must be no endpoint that runs
        a plan, and no execute control in the shipped frontend."""
        source = (webapp.HERE / "app.py").read_text(encoding="utf-8")
        for forbidden in ("/api/plan/execute", "/api/execute", "run_coding_task("):
            self.assertNotIn(forbidden, source)
        app_js = (webapp.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("executePlan", app_js)
        self.assertIn("openPlan", app_js)


class AuthBoundaryTests(unittest.TestCase):
    def test_plan_requires_a_session(self):
        handler = _StubHandler("sistem durumu")
        handler._current_session = lambda: None
        with patch.object(webapp, "_read_json_body", return_value={"message": "x"}):
            webapp.Handler._route_api_post(handler, "/api/plan")
        self.assertEqual(handler.sent[0], 401)

    def test_plan_requires_csrf(self):
        handler = _StubHandler("sistem durumu")
        handler._require_csrf = lambda session: False
        with patch.object(webapp, "_read_json_body", return_value={"message": "x"}):
            webapp.Handler._route_api_post(handler, "/api/plan")
        self.assertEqual(handler.sent[0], 403)


if __name__ == "__main__":
    unittest.main()
