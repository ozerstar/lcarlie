import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent.parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JARVIS_ROOT))

import chat  # noqa: E402


class ChatRoutingTests(unittest.TestCase):
    def setUp(self):
        self.runtime = MagicMock()
        self.operator = MagicMock()

    def test_empty_message_is_error(self):
        result = chat.route("", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ERROR")

    def test_pending_proposals_uses_operator_not_shadow(self):
        self.operator.list_pending.return_value = [{"action_id": 1}]
        result = chat.route("Bekleyen önerilerin neler?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ANSWER")
        self.assertEqual(result["source"], "operator.list_pending")
        self.runtime.handle.assert_not_called()

    def test_no_pending_proposals_reports_truthfully(self):
        self.operator.list_pending.return_value = []
        result = chat.route("pending proposal var mı", self.runtime, self.operator)
        self.assertIn("yok", result["text"])

    def test_why_created_with_id_uses_inspect(self):
        self.operator.inspect.return_value = {"action_id": 20, "action_type": "REQUEST_HUMAN_REVIEW",
                                               "risk_class": "LOW", "payload": {"reason": "test"}}
        result = chat.route("proposal 20 neden oluşturuldu?", self.runtime, self.operator)
        self.operator.inspect.assert_called_once_with(20)
        self.assertEqual(result["source"], "operator.inspect")

    def test_why_created_missing_proposal_is_truthful_not_fabricated(self):
        self.operator.inspect.return_value = None
        result = chat.route("proposal 999 why was it created", self.runtime, self.operator)
        self.assertIn("bulunamadı", result["text"])

    def test_why_created_without_id_is_error_not_guess(self):
        result = chat.route("bu proposal neden oluşturuldu?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ERROR")
        self.operator.inspect.assert_not_called()

    def test_pure_judgement_request_requires_reasoning(self):
        result = chat.route("Bunun için ne öneriyorsun?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "REQUIRES_REASONING_CAPABILITY")
        self.runtime.handle.assert_not_called()

    def test_judgement_request_with_grounded_topic_still_goes_to_shadow(self):
        self.runtime.handle.return_value = {
            "envelope": {"evidence_refs": ["postgres:system"]},
            "context": {"facts": [{"a": 1}], "entity": None, "capability_analysis": None},
            "shadow": {}, "capability": {},
        }
        result = chat.route("Vireon için ne öneriyorsun?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ANSWER")
        self.runtime.handle.assert_called_once()

    def test_grounded_status_question_reaches_real_shadow_runner(self):
        self.runtime.handle.return_value = {
            "envelope": {"evidence_refs": ["postgres:system"]},
            "context": {"facts": [{"open_tasks": 0}], "entity": None, "capability_analysis": None},
            "shadow": {}, "capability": {},
        }
        result = chat.route("Jarvis, sistem durumu ne?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ANSWER")
        self.assertEqual(result["source"], "jarvis.shadow")
        self.runtime.handle.assert_called_once_with("Jarvis, sistem durumu ne?")

    def test_no_facts_is_reported_truthfully_not_fabricated(self):
        self.runtime.handle.return_value = {
            "envelope": {"evidence_refs": []},
            "context": {"facts": [], "entity": None, "capability_analysis": None},
            "shadow": {}, "capability": {},
        }
        result = chat.route("gündem nedir", self.runtime, self.operator)
        self.assertIn("bulunamadı", result["text"])


if __name__ == "__main__":
    unittest.main()
