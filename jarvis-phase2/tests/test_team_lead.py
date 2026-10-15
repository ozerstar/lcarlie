import unittest
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis.team_lead import build_brief, explain_result
from jarvis import role_activity


class TeamLeadTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        self.departments = [{"ad": "Strateji", "uyeler": [
            {"key": "managing_director", "ad": "Genel Müdür", "durum": "KONUŞTU"},
            {"key": "strategy", "ad": "Strateji", "durum": "KONUŞTU"},
        ]}]

    def test_legacy_output_is_not_execution(self):
        report = {"generated_at": (self.now - timedelta(hours=2)).isoformat(), "roles": {
            "managing_director": {"status": "PRODUCED", "statement": "Kanıtlı özet", "evidence_refs": ["postgres:orders"]},
            "strategy": {"status": "PRODUCED", "statement": "Kaynağı yok", "evidence_refs": []},
        }}
        brief = build_brief(self.departments, report, [], self.now)
        self.assertEqual(brief["kanitli_cikti"], 0)
        self.assertEqual(brief["uyeler"][1]["durum"], "İZLENMİYOR")
        self.assertEqual(build_brief(self.departments, {**report, "generated_at": (self.now - timedelta(days=2)).isoformat()}, [], self.now)["kanitli_cikti"], 0)

    def test_activity_separates_work_wait_error_and_untracked(self):
        report = {"generated_at": self.now.isoformat(), "activity": {
            "managing_director": {"status": "WORKED", "task": "Analiz", "result": "Özet",
                                   "evidence_refs": ["postgres:orders"], "finished_at": self.now.isoformat()},
            "strategy": {"status": "ERROR", "task": "Analiz", "result": "ValueError",
                         "evidence_refs": [], "finished_at": self.now.isoformat()},
        }}
        brief = build_brief(self.departments, report, [], self.now)
        self.assertEqual(brief["durum_sayilari"], {"ÇALIŞTI": 1, "GÖREV BEKLİYOR": 0, "HATA": 1, "İZLENMİYOR": 0})
        self.assertEqual(brief["uyeler"][0]["kanitlar"], ["postgres:orders"])
        self.assertEqual(brief["uyeler"][1]["durum"], "HATA")

    def test_unregistered_member_is_not_treated_as_idle_worker(self):
        report = {"generated_at": self.now.isoformat(), "activity": {
            "research": {"status": "WAITING", "task": "Kaynak tara", "result": "Kaynak yok", "evidence_refs": []}
        }}
        brief = build_brief(self.departments, report, [], self.now)
        self.assertEqual(brief["durum_sayilari"]["İZLENMİYOR"], 2)

    def test_waiting_and_stale_activity_are_separate(self):
        departments = [{"ad": "Araştırma", "uyeler": [{"key": "research", "ad": "Araştırmacı"}]}]
        report = {"generated_at": self.now.isoformat(), "activity": {
            "research": {"status": "WAITING", "task": "Kaynak tara", "result": "Kaynak yok", "evidence_refs": []}
        }}
        self.assertEqual(build_brief(departments, report, [], self.now)["uyeler"][0]["durum"], "GÖREV BEKLİYOR")
        report["generated_at"] = (self.now - timedelta(days=2)).isoformat()
        self.assertEqual(build_brief(departments, report, [], self.now)["uyeler"][0]["durum"], "İZLENMİYOR")

    def test_overdue_is_follow_up_not_execution(self):
        works = [{"id": 7, "objective": "Kaynağı doğrula", "owner": "operations",
                  "due": (self.now - timedelta(days=1)).isoformat(), "approval_state": None,
                  "has_application": 0, "has_measurement": 0}]
        brief = build_brief(self.departments, {}, works, self.now)
        self.assertEqual(brief["oncelikler"][0]["durum"], "GECİKMİŞ")
        self.assertEqual(brief["oncelikler"][0]["sorumlu"], "operations")

    def test_management_summary_is_turkish_without_changing_evidence(self):
        report = {"generated_at": self.now.isoformat(), "activity": {
            "managing_director": {
                "status": "WORKED",
                "result": "PROPOSED: first clear the CRM response backlog; then validate advertising sales, revenue, cost, margin, and inventory evidence before approving growth actions.",
                "evidence_refs": ["postgres:sales_orders"],
            },
        }}
        member = build_brief(self.departments, report, [], self.now)["uyeler"][0]
        self.assertIn("Genel müdür önerisi", member["son_is_acik"])
        self.assertIn("PROPOSED", member["son_is"])
        self.assertEqual(member["kanitlar"], ["postgres:sales_orders"])

    def test_known_technical_summaries_have_plain_language(self):
        cases = {
            "ecommerce_sales": ("Sales bounded context: 29 orders and 32 line items; 1 measured orders represent a 0.00 net-revenue subtotal.", "0,00"),
            "product_portfolio": ("E-commerce bounded context: 20 product profitability rows, 17 price rows and 5 funnel transitions; net revenue is 60186.25, with 1 product rows below full cost coverage.", "60.186,25"),
            "meta_performance": ("Advertising bounded context: 13 30-day ad rows with a 23089.26 spend subtotal; 13 rows lack commercial confirmation.", "satış sonucu doğrulanmamış"),
            "crm_customer": ("CRM bounded context: 32 customer records and 43 unanswered conversations; longest wait is 924.8 hours.", "yanıtsız görüşme"),
            "operations": ("Operations bounded context: 26 shipment records, 0 shipment alarms and 25 open-work records.", "gönderi kaydı"),
            "CREATIVE_DIRECTOR": ("VIREON için kampanya önerisi hazırla — creative_concepts: 3. Taslak üretildi; yayımlanmadı.", "3 reklam fikri"),
            "research": ("Son 14 günde 20 kaynak kaydı incelendi. Son başlık: Karmaşık başlık.", "20 dış kaynak"),
        }
        for key, (raw, expected) in cases.items():
            with self.subTest(key=key):
                self.assertIn(expected, explain_result(key, raw))
        self.assertEqual(explain_result("unknown", "Ölçüm yok"), "Ölçüm yok")


if __name__ == "__main__":
    unittest.main()


class ActivityCycleTests(unittest.TestCase):
    def test_fresh_report_reuses_data_opinions_and_stale_report_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "team-cycle").mkdir()
            report = {"generated_at": datetime.now(timezone.utc).isoformat(),
                      "roles": {}, "data_opinions": [{"key": "web_gelistirici"}]}
            target = root / "team-cycle" / "latest.json"
            target.write_text(json.dumps(report))
            with patch.object(role_activity, "state_dir", return_value=root):
                self.assertEqual(role_activity.latest_report()["data_opinions"], report["data_opinions"])
                report["generated_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                target.write_text(json.dumps(report))
                self.assertEqual(role_activity.latest_report(), {})

    def test_stages_record_result_time_and_evidence(self):
        class Pool:
            router = type("Router", (), {"route": lambda self, domains: type("Plan", (), {"selected": ("strategy",)})()})()

            def __init__(self, memory):
                pass

            def execute(self, task, domains):
                return {"findings": [{"specialist_id": "strategy", "claim": "Ölçüldü",
                                      "evidence_refs": ["postgres:orders"]}]}

        class Agency:
            def __init__(self, memory):
                pass

            def run(self, task, synthesize=False):
                return {"task": task, "current_evidence": {"refs": ["postgres:orders"]},
                        "role_contributions": [{"role": "COPYWRITER", "status": "PRODUCED",
                                                "items": {"copy": 1}, "produced": 1}]}

        with patch.object(role_activity, "SpecialistPool", Pool), patch.object(role_activity, "AgencyCapability", Agency), \
             patch.object(role_activity, "select_roles", return_value=("COPYWRITER",)):
            result = role_activity.build(object(), [], datetime.now(timezone.utc))
        self.assertEqual(result["activity"]["strategy"]["status"], "WORKED")
        self.assertEqual(result["activity"]["COPYWRITER"]["status"], "WORKED")
        self.assertEqual(result["activity"]["research"]["status"], "WAITING")
        self.assertTrue(result["activity"]["strategy"]["finished_at"])
        self.assertEqual(result["activity"]["strategy"]["evidence_refs"], ["postgres:orders"])

    def test_stage_failure_is_reported_not_hidden(self):
        class BrokenPool:
            router = type("Router", (), {"route": lambda self, domains: type("Plan", (), {"selected": ("strategy",)})()})()

            def __init__(self, memory):
                pass

            def execute(self, task, domains):
                raise RuntimeError("secret details must not leak")

        class BrokenAgency:
            def __init__(self, memory):
                pass

            def run(self, task, synthesize=False):
                raise RuntimeError("secret details must not leak")

        with patch.object(role_activity, "SpecialistPool", BrokenPool), patch.object(role_activity, "AgencyCapability", BrokenAgency), \
             patch.object(role_activity, "select_roles", return_value=("COPYWRITER",)):
            result = role_activity.build(object(), [], datetime.now(timezone.utc))
        self.assertEqual(result["activity"]["strategy"]["status"], "ERROR")
        self.assertEqual(result["activity"]["COPYWRITER"]["status"], "ERROR")
        self.assertEqual(result["activity"]["strategy"]["result"], "RuntimeError")

    def test_unassigned_data_role_gets_a_real_read_task(self):
        observation = {"key": "web_gelistirici", "status": role_activity.roster.SPEAKS,
                       "statement": "36 ürün sayfası okundu.", "evidence_refs": ["postgres:urun_seo"]}
        with patch.object(role_activity.roster, "opinions", return_value=[observation]):
            result = role_activity.build(object(), [], datetime.now(timezone.utc))
        record = result["activity"]["web_gelistirici"]
        self.assertEqual(record["status"], "WORKED")
        self.assertEqual(record["evidence_refs"], ["postgres:urun_seo"])
        self.assertTrue(record["finished_at"])
        self.assertEqual(record["kind"], "VERİ KONTROLÜ")
