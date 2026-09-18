import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import conversation


class Evidence:
    def __init__(self, source, records): self.source, self.records = source, records


class Memory:
    def __init__(self): self.calls = []
    def _fetch(self, name):
        self.calls.append(name)
        data = {
            "crm_unanswered": [{"bekleme_saat": 12.5}, {"bekleme_saat": 3}],
            "sales_orders": [{"olcumde": True, "ciro_dogrulanmis_net": 100}],
            "advertising_performance": [{"pencere": 30, "harcama": 50}],
        }
        return Evidence("postgres:" + name, data[name])
    def get_executive_brief(self):
        self.calls.append("company_dashboard")
        return Evidence("postgres:company_dashboard", [{"proposed": 2, "approved": 3,
            "red_team_pending": 0, "unsafe_external_actions": 0}])


class Runtime:
    def __init__(self):
        self.runtime = type("Phase", (), {})()
        self.runtime.compiler = type("Compiler", (), {})()
        self.runtime.compiler.memory = Memory()


class Tests(unittest.TestCase):
    def test_simple(self):
        result = conversation.route("Merhaba, sen ne yapabiliyorsun?", Runtime())
        self.assertEqual(("SIMPLE_CONVERSATION", "ANSWERED", 0),
                         (result["intent"], result["status"], result["model_calls"]))
    def test_crm_minimal_query(self):
        rt = Runtime(); result = conversation.route("Şirkette cevapsız müşteri var mı?", rt)
        self.assertEqual(["crm_unanswered"], rt.runtime.compiler.memory.calls)
        self.assertEqual(["postgres:crm_unanswered"], result["evidence_refs"])
        self.assertIn("2 cevapsız", result["answer"])
    def test_domains(self):
        self.assertEqual("sales", conversation.classify("kaç siparişimiz var").domain)
        self.assertEqual("advertising", conversation.classify("reklam harcamamız ne durumda").domain)
    def test_analysis_handoff(self):
        result = conversation.route("Satışlarımızı analiz et.", Runtime())
        self.assertEqual("PROPOSED", result["status"]); self.assertFalse(result["execution_started"])
    def test_research_unavailable(self):
        result = conversation.route("Rakiplerimizi araştır.", Runtime())
        self.assertEqual("RESEARCH_CAPABILITY_UNAVAILABLE", result["error_code"])
    def test_action_proposed_only(self):
        result = conversation.route("Vireon fiyatını değiştir.", Runtime())
        self.assertEqual("ACTION_REQUEST", result["intent"]); self.assertEqual(0, result["external_actions"])
        self.assertTrue(result["approval_required"]); self.assertFalse(result["execution_started"])
        self.assertEqual("BLOCKED_EXTERNAL_ACTION", result["plan"]["status"])
    def test_provider_unavailable(self):
        result = conversation.route("Bana yaratıcı bir fikir ver", Runtime())
        self.assertEqual("AI_PROVIDER_UNAVAILABLE", result["status"]); self.assertIsNone(result["model"])
    def test_contract(self):
        result = conversation.route("merhaba", Runtime())
        for key in ("request_id", "intent", "status", "answer", "evidence_refs", "missing_data",
                    "duration_ms", "model", "model_calls"): self.assertIn(key, result)
    def test_voice_same_boundary(self):
        result = conversation.route("Şirkette en önemli problem ne?", Runtime())
        self.assertEqual("ANALYSIS_REQUEST", result["intent"]); self.assertEqual(0, result["external_actions"])


if __name__ == "__main__": unittest.main()
