"""CODE_CHANGE_REVIEW bridge in jarvis/loop.py, and jarvis/operator.py's
create_coding_task. No DB, no Kimi -- everything below this layer is mocked;
these tests only prove the WIRING (spec file -> CodingExecutor -> firewall ->
propose, or -> fail_task on denial) is correct."""
import json
import tempfile
import unittest
from tests import EnterContextMixin
from pathlib import Path
from unittest.mock import patch

from jarvis import loop
from jarvis import operator as jarvis_operator
from jarvis.action_contract import build_contract
from test_action_contract import LIVE_ROWS
from test_capabilities import FakeMemory, HEALTHY_PROBE


def contract():
    return build_contract(LIVE_ROWS, source="postgres:action_contract")


class LoopCodingBridgeTests(EnterContextMixin, unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.enterContext(patch.object(loop, "STATE_DIR", tmp))
        self.enterContext(patch.object(loop, "STATE_FILE", tmp / "loop-state.json"))
        self.enterContext(patch.object(loop, "FINDINGS_LOG", tmp / "findings.jsonl"))
        self.enterContext(patch.object(loop, "AUDIT_LOG", tmp / "audit.jsonl"))
        self.enterContext(patch.object(loop, "CODING_TASK_PENDING_DIR", tmp / "coding_executor" / "pending"))
        self.pending_dir = tmp / "coding_executor" / "pending"
        self.pending_dir.mkdir(parents=True)

    def _healthy_memory(self):
        return patch.object(loop, "CompanyMemory", return_value=FakeMemory(probe=HEALTHY_PROBE))

    def _claimed(self, slug):
        return {"task_id": 200, "task_type": "PROPOSE_ACTION",
                "idempotency_key": f"jarvis:CODE_CHANGE_REVIEW:{slug}",
                "lease_token": "44444444-4444-4444-4444-444444444444", "source_type": "MANUAL",
                "source_id": None, "context_profile": "default", "attempt_count": 1}

    def test_missing_spec_file_denies_without_running_coding_executor(self):
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=self._claimed("nospec")), \
             patch.object(loop, "ContractCache", return_value=type("C", (), {"get": lambda self: contract()})()), \
             patch.object(loop, "run_coding_task") as run_mock, \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "CODING_TASK_DENIED")
        run_mock.assert_not_called()
        fail_mock.assert_called_once()

    def test_successful_coding_task_proposes_with_real_evidence_summary(self):
        (self.pending_dir / "goodslug.json").write_text(json.dumps({
            "objective": "add a helper", "allowed_files": ["jarvis-phase2/jarvis/x.py"]}))
        fake_result = loop_result = type("R", (), {
            "success": True, "denied_reason": None, "files_changed": ("jarvis-phase2/jarvis/x.py",),
            "test_passed": True, "test_summary": "OK", "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
            "evidence_dir": "/opt/lcarlie/jarvis-phase2/state/coding_executor/goodslug", "duration_s": 1.2,
        })()
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=self._claimed("goodslug")), \
             patch.object(loop, "ContractCache", return_value=type("C", (), {"get": lambda self: contract()})()), \
             patch.object(loop, "run_coding_task", return_value=fake_result) as run_mock, \
             patch.object(loop, "_propose_action", return_value=999) as propose_mock, \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "PROPOSED")
        self.assertIsNone(report["model_calls"])
        self.assertEqual("NOT_MEASURED", report["coding_model_usage"])
        self.assertEqual(report["task_detail"]["action_type"], "REQUEST_HUMAN_REVIEW")
        self.assertEqual(report["task_detail"]["proposal_id"], 999)
        run_mock.assert_called_once()
        fail_mock.assert_not_called()
        payload = propose_mock.call_args[0][4]
        self.assertEqual(payload["subject_ref"], "coding-task:goodslug")
        self.assertIn("x.py", payload["reason"])

    def test_denied_coding_task_fails_the_task_and_proposes_nothing(self):
        (self.pending_dir / "badslug.json").write_text(json.dumps({
            "objective": "x", "allowed_files": ["a.py"]}))
        fake_result = type("R", (), {"success": False, "denied_reason": "tests failed"})()
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=self._claimed("badslug")), \
             patch.object(loop, "ContractCache", return_value=type("C", (), {"get": lambda self: contract()})()), \
             patch.object(loop, "run_coding_task", return_value=fake_result), \
             patch.object(loop, "_propose_action") as propose_mock, \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "CODING_TASK_DENIED")
        propose_mock.assert_not_called()
        fail_mock.assert_called_once()
        self.assertIn("tests failed", fail_mock.call_args[0][2])

    def test_coding_executor_error_is_treated_as_denial_not_a_crash(self):
        (self.pending_dir / "errslug.json").write_text(json.dumps({
            "objective": "x", "allowed_files": ["a.py"]}))
        with self._healthy_memory(), patch.object(loop, "_claim_task", return_value=self._claimed("errslug")), \
             patch.object(loop, "ContractCache", return_value=type("C", (), {"get": lambda self: contract()})()), \
             patch.object(loop, "run_coding_task", side_effect=loop.CodingExecutorError("clone failed")), \
             patch.object(loop, "_fail_task") as fail_mock:
            report = loop.run_cycle(host=None)
        self.assertEqual(report["result"], "CODING_TASK_DENIED")
        fail_mock.assert_called_once()

    def test_slug_without_pending_file_never_reaches_kimi(self):
        with patch.object(loop, "run_coding_task") as run_mock:
            with self.assertRaises(loop.CodingTaskDenied):
                loop._build_coding_review_payload("does-not-exist")
        run_mock.assert_not_called()


class OperatorCreateCodingTaskTests(EnterContextMixin, unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.enterContext(patch.object(jarvis_operator, "CODING_TASK_PENDING_DIR", tmp / "pending"))
        self.spec_path = tmp / "spec.json"

    def test_valid_spec_is_staged_and_task_created(self):
        self.spec_path.write_text(json.dumps({
            "objective": "add tests", "allowed_files": ["jarvis-phase2/tests/test_x.py"]}))
        session = jarvis_operator.OperatorSession(host=None)
        with patch.object(session, "create_task", return_value={"task_id": 1, "idempotency_key": "k",
                                                                 "internal_intent": "CODE_CHANGE_REVIEW"}) as ct:
            result = session.create_coding_task("myslug", str(self.spec_path))
        ct.assert_called_once_with("CODE_CHANGE_REVIEW", "myslug")
        staged = jarvis_operator.CODING_TASK_PENDING_DIR / "myslug.json"
        self.assertTrue(staged.is_file())
        self.assertEqual(json.loads(staged.read_text())["objective"], "add tests")
        self.assertEqual(result["allowed_files"], ["jarvis-phase2/tests/test_x.py"])

    def test_invalid_spec_rejected_before_staging_or_enqueueing(self):
        self.spec_path.write_text(json.dumps({"objective": ""}))  # no allowed_files
        session = jarvis_operator.OperatorSession(host=None)
        with patch.object(session, "create_task") as ct:
            with self.assertRaises(ValueError):
                session.create_coding_task("badslug", str(self.spec_path))
        ct.assert_not_called()
        self.assertFalse((jarvis_operator.CODING_TASK_PENDING_DIR / "badslug.json").exists())

    def test_forbidden_allowed_file_rejected(self):
        self.spec_path.write_text(json.dumps({
            "objective": "x", "allowed_files": ["deploy/jarvis-web.service"]}))
        session = jarvis_operator.OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.create_coding_task("x", str(self.spec_path))

    def test_malformed_json_rejected(self):
        self.spec_path.write_text("not json")
        session = jarvis_operator.OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.create_coding_task("x", str(self.spec_path))

    def test_bad_slug_rejected(self):
        self.spec_path.write_text(json.dumps({"objective": "x", "allowed_files": ["a.py"]}))
        session = jarvis_operator.OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.create_coding_task("bad slug!", str(self.spec_path))


if __name__ == "__main__":
    unittest.main()
