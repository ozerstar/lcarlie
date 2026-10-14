import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent.parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JARVIS_ROOT))

# chat -> conversation -> conversation_memory zinciri ICE AKTARILMADAN
# ONCE izole edilir. Bu dosyanin fixture'lari ("Naber", "Jarvis, sistem
# durumu ne?") ve sahte cevabi ("stub reply") izolasyon olmadan gercek
# sohbet dokumune yaziliyordu; history() onlari modele baglam olarak
# verdigi icin Jarvis kullaniciya "Stub reply" demeye basladi.
os.environ.setdefault("JARVIS_STATE_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

import chat  # noqa: E402



# Conversation now reaches a real model. These tests are about routing and
# safety, not about the model, so it is stubbed: deterministic and offline.
import contextlib as _contextlib
from unittest.mock import patch as _patch

from jarvis.model_layer import ModelResult as _ModelResult


def _stub_result(*_args, **_kwargs):
    return _ModelResult(answer="stub reply", evidence_refs=(), confidence="LOW",
                        missing_data=(), model="stub-model", tier="LOCAL_MODEL",
                        model_calls=1, duration_ms=1.0)


@_contextlib.contextmanager
def _stub_model():
    with _patch("jarvis.model_layer.ModelRouter.synthesize", _stub_result):
        yield


def _install_model_stub(testcase):
    patcher = _patch("jarvis.model_layer.ModelRouter.synthesize", _stub_result)
    patcher.start()
    testcase.addCleanup(patcher.stop)

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

    def test_why_created_without_id_is_error_not_guess(self):
        result = chat.route("bu proposal neden oluşturuldu?", self.runtime, self.operator)
        self.assertEqual(result["kind"], "ERROR")
        self.operator.inspect.assert_not_called()

    def test_every_chat_message_reaches_the_conversational_router(self):
        """chat.route is a delegate now. The Phase 2 shadow runner is no longer
        the chat path -- routing a message through it is what answered "Naber"
        with a Company Memory row count."""
        with _stub_model():
            for message in ("Naber", "Jarvis, sistem durumu ne?",
                            "Bunun için ne öneriyorsun?"):
                result = chat.route(message, self.runtime, self.operator)
                self.assertIn("intent", result)
                self.assertEqual(0, result["external_actions"])
        self.runtime.handle.assert_not_called()

    def test_a_greeting_is_answered_as_a_greeting(self):
        with _stub_model():
            result = chat.route("Naber", self.runtime, self.operator)
        self.assertEqual("SIMPLE_CONVERSATION", result["intent"])
        self.assertEqual("ANSWERED", result["status"])
        self.assertEqual(0, result["external_actions"])

    def test_nothing_is_fabricated_and_nothing_is_executed(self):
        with _stub_model():
            for message in ("Naber", "Bunun için ne öneriyorsun?"):
                result = chat.route(message, self.runtime, self.operator)
                self.assertIsNotNone(result.get("evidence_refs"))
                self.assertEqual(0, result["external_actions"])


if __name__ == "__main__":
    unittest.main()
