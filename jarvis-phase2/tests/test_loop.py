"""Minimum Operational Jarvis: deterministic analysis, dedup, fail-safe claim
handling. No DB required -- run_cycle's DB calls are patched."""
import json
import unittest
from unittest.mock import patch

from jarvis import loop
from jarvis.memory import Evidence


class AnalyzeTests(unittest.TestCase):
    def _obs(self, health, agenda_count=5):
        return loop.Observation(health=health, agenda_count=agenda_count,
                                observed_at="t", content_hash="h")

    def test_healthy_system_is_noop(self):
        result = loop.analyze(self._obs({"failed_executions": 0, "open_tasks": 0}))
        self.assertEqual(result.status, "NOOP")

    def test_failed_executions_is_a_real_issue(self):
        result = loop.analyze(self._obs({"failed_executions": 3, "open_tasks": 0}))
        self.assertEqual(result.status, "ISSUE")
        self.assertEqual(result.signature, "failed_executions:3")

    def test_stuck_queue_is_a_real_issue(self):
        result = loop.analyze(self._obs({"failed_executions": 0, "open_tasks": 51}))
        self.assertEqual(result.status, "ISSUE")

    def test_no_fabricated_issue_from_agenda_alone(self):
        # agenda_count is observed but never triggers an issue by itself
        result = loop.analyze(self._obs({"failed_executions": 0, "open_tasks": 0}, agenda_count=500))
        self.assertEqual(result.status, "NOOP")


class ObserveTests(unittest.TestCase):
    def test_observe_uses_only_existing_allowlisted_queries(self):
        class FakeMemory:
            def get_system_status(self):
                return Evidence("postgres:system", "CANONICAL", "t", [{"open_tasks": 0, "failed_executions": 0}], 1.0)
            def get_company_agenda(self):
                return Evidence("postgres:agenda", "CANONICAL", "t", [{}] * 3, 1.0)
        observation = loop.observe(FakeMemory())
        self.assertEqual(observation.agenda_count, 3)
        self.assertTrue(observation.content_hash)


class RunCycleTests(unittest.TestCase):
    def setUp(self):
        import pathlib
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(patch.object(loop, "STATE_DIR", tmp))
        self.enterContext(patch.object(loop, "STATE_FILE", tmp / "loop-state.json"))
        self.enterContext(patch.object(loop, "FINDINGS_LOG", tmp / "findings.jsonl"))
        self.enterContext(patch.object(loop, "AUDIT_LOG", tmp / "audit.jsonl"))

    def _healthy_memory(self):
        return patch.object(loop, "CompanyMemory", return_value=type("M", (), {
            "get_system_status": lambda self: Evidence("postgres:system", "C", "t",
                                                        [{"open_tasks": 0, "failed_executions": 0}], 1.0),
            "get_company_agenda": lambda self: Evidence("postgres:agenda", "C", "t", [], 1.0),
        })())

    def test_noop_when_healthy_and_no_task_available(self):
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=None):
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "NOOP")
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["external_actions"], 0)

    def test_issue_logged_once_then_deduplicated(self):
        unhealthy = type("M", (), {
            "get_system_status": lambda self: Evidence("postgres:system", "C", "t",
                                                        [{"open_tasks": 0, "failed_executions": 2}], 1.0),
            "get_company_agenda": lambda self: Evidence("postgres:agenda", "C", "t", [], 1.0),
        })()
        with patch.object(loop, "CompanyMemory", return_value=unhealthy), \
             patch.object(loop, "_claim_task", return_value=None):
            first = loop.run_cycle(host=None)
            second = loop.run_cycle(host=None)
        self.assertTrue(first["finding_logged"])
        self.assertFalse(second["finding_logged"])  # same signature: not re-logged
        lines = loop.FINDINGS_LOG.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

    def test_wrong_task_type_is_handed_back_not_processed(self):
        claimed = {"task_id": 99, "task_type": "PROPOSE_DECISION", "idempotency_key": "ai:ci:x",
                  "lease_token": "11111111-1111-1111-1111-111111111111", "source_type": "MANUAL",
                  "source_id": None, "context_profile": "default", "attempt_count": 1}
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=claimed), \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "SKIPPED_NOT_MINE")
        fail_mock.assert_called_once()
        self.assertEqual(fail_mock.call_args[0][0], 99)

    def test_valid_task_produces_a_real_proposal(self):
        claimed = {"task_id": 100, "task_type": "PROPOSE_ACTION",
                  "idempotency_key": "jarvis:HUMAN_REVIEW_REQUEST:demo-1",
                  "lease_token": "22222222-2222-2222-2222-222222222222", "source_type": "MANUAL",
                  "source_id": None, "context_profile": "default", "attempt_count": 1}
        contract = type("C", (), {"get": lambda self: FakeContract()})()

        class FakeContract:
            valid = True
            contract_hash = "deadbeef"
            def canonical_for(self, intent):
                return "REQUEST_HUMAN_REVIEW"
            def action(self, canonical):
                return type("A", (), {"risk_class": "LOW", "approval_mode": "ONE_PERSON",
                                      "schema_version": "v1", "execution_enabled": True,
                                      "proposal_enabled": True})()

        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=claimed), \
             patch.object(loop, "ContractCache", return_value=contract), \
             patch.object(loop, "_propose_action", return_value=555) as propose_mock, \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "PROPOSED")
        self.assertEqual(report["task_detail"]["proposal_id"], 555)
        self.assertEqual(report["task_detail"]["action_type"], "REQUEST_HUMAN_REVIEW")
        fail_mock.assert_not_called()
        propose_mock.assert_called_once()

    def test_malformed_idempotency_key_fails_closed(self):
        claimed = {"task_id": 101, "task_type": "PROPOSE_ACTION", "idempotency_key": "not-the-convention",
                  "lease_token": "33333333-3333-3333-3333-333333333333", "source_type": "MANUAL",
                  "source_id": None, "context_profile": "default", "attempt_count": 1}
        contract = type("CC", (), {"get": lambda self: FakeContract()})()

        class FakeContract:
            valid = True
            contract_hash = "deadbeef"
            def canonical_for(self, intent):
                raise loop.FirewallError(f"unknown internal action: {intent!r}")

        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=claimed), \
             patch.object(loop, "ContractCache", return_value=contract), \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "FIREWALL_REJECTED")
        fail_mock.assert_called_once()

    def test_bounded_to_one_task_per_cycle(self):
        """The loop calls _claim_task at most once per run_cycle invocation."""
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=None) as claim_mock:
            loop.run_cycle(host=None)
        self.assertEqual(claim_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
