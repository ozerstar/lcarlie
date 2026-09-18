import os
import unittest

from jarvis.context import ContextCompiler
from jarvis.memory import CompanyMemory
from jarvis.phase2 import Phase2Runtime


@unittest.skipUnless(os.environ.get("JARVIS_LIVE_TEST") == "1", "live test disabled")
class LivePhase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = CompanyMemory()
        cls.runtime = Phase2Runtime(ContextCompiler(cls.memory))

    def test_a_real_system_status_fast(self):
        result = self.runtime.handle("Jarvis, sistem durumu ne?")
        self.assertEqual(result["envelope"]["mode"], "FAST")
        self.assertEqual(result["context"]["retrieved_records"], 1)
        self.assertFalse(result["external_action_executed"])

    def test_b_vireon_real_memory(self):
        result = self.runtime.handle("Jarvis, Vireon hakkında şirket hafızasında ne biliyoruz?")
        self.assertEqual(result["context"]["entity"], "VIREON")
        self.assertGreater(result["context"]["retrieved_records"], 0)

    def test_c_pending_task_and_proposal(self):
        result = self.runtime.handle("Jarvis, bekleyen AI task ve proposal durumunu göster.")
        fact = result["context"]["facts"][0]
        self.assertIn("open_tasks", fact)
        self.assertIn("pending_actions", fact)

    def test_d_capability_gap_does_not_install(self):
        result = self.runtime.handle("Jarvis, Company Memory tarafında eksik capability var mı?")
        self.assertFalse(result["external_action_executed"])

    def test_e_risky_action_is_proposed(self):
        result = self.runtime.handle("send whatsapp message")
        self.assertEqual(result["envelope"]["status"], "PROPOSED")
        self.assertFalse(result["external_action_executed"])
