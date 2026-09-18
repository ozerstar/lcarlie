from __future__ import annotations

import unittest

from jarvis.agency import (AgencyCapability, PROHIBITED_CLAIMS, ROLES,
                           TASK_CAMPAIGN, TASK_PERFORMANCE, TASK_SOCIAL,
                           classify_task)
from jarvis.memory import CompanyMemory, Evidence


class FakeMemory:
    QUERIES = CompanyMemory.QUERIES
    def __init__(self): self.calls = []
    def _fetch(self, query):
        self.calls.append(query)
        rows = {
            "sales_items": [{"urun_adi": "Vireon", "adet": 2, "satir_ciro_net": 1000, "olcumde": True}],
            "advertising_performance": [{"pencere": 30, "kampanya_adi": "VİREON", "harcama": 100,
                "gosterim": 1000, "tiklama": 50, "link_tiklama": 40,
                "commercial_confirmation": "NOT_AVAILABLE"}],
            "advertising_spend": [{"harcama": 100}],
            "ecommerce_price": [{"urun_adi": "Vireon", "base_price": 500}],
            "decision_summary": [{"acik_karar": 1}],
        }[query]
        return Evidence("postgres:" + query, "CANONICAL_COMPANY_MEMORY", "live", rows, 1.0)


class AgencyTests(unittest.TestCase):
    def test_task_routing_uses_minimum_roles(self):
        self.assertEqual(TASK_CAMPAIGN, classify_task("Vireon Meta kampanyası hazırla"))
        self.assertEqual(TASK_PERFORMANCE, classify_task("Performansında hangi problemler var, ne test edilmeli?"))
        self.assertEqual(TASK_SOCIAL, classify_task("7 günlük Instagram planı hazırla"))
        agency = AgencyCapability(FakeMemory())
        self.assertEqual(6, len(agency.run("Vireon Meta kampanyası hazırla")["roles_used"]))
        self.assertEqual(3, len(agency.run("Performansında hangi problemler var?")["roles_used"]))
        self.assertEqual(3, len(agency.run("7 günlük Instagram planı hazırla")["roles_used"]))

    def test_campaign_contract_and_three_complete_concepts(self):
        result = AgencyCapability(FakeMemory()).run("Vireon Meta kampanyası hazırla")
        required = ("task", "objective", "evidence_refs", "data_gaps", "roles_used", "campaign_objective",
                    "core_angle", "creative_concepts", "cro_recommendations", "test_plan", "success_metrics",
                    "regulatory_risks", "red_team_objections", "next_actions", "status")
        self.assertTrue(all(key in result for key in required))
        self.assertEqual(3, len(result["creative_concepts"]))
        fields = ("name", "audience_context", "hook", "primary_text", "headline", "cta", "visual_brief",
                  "video_15s_brief", "landing_page_message")
        self.assertTrue(all(all(field in concept for field in fields) for concept in result["creative_concepts"]))
        self.assertEqual("PROPOSED", result["status"])

    def test_guard_blocks_prohibited_claims(self):
        result = AgencyCapability(FakeMemory()).run("Vireon Meta kampanyası hazırla")
        text = str(result["creative_concepts"]).casefold()
        self.assertFalse(any(term in text for term in PROHIBITED_CLAIMS))
        self.assertEqual([], result["regulatory_risks"])

    def test_unconfirmed_meta_claim_is_not_sales(self):
        result = AgencyCapability(FakeMemory()).run("Vireon Meta kampanyası hazırla")
        self.assertEqual(0, result["performance_baseline"]["commercially_confirmed_rows"])
        self.assertTrue(any("do not treat as sales" in item["reason"] for item in result["red_team_objections"]))

    def test_evidence_is_fetched_once_and_shared(self):
        memory = FakeMemory(); result = AgencyCapability(memory).run("Vireon Meta kampanyası hazırla")
        self.assertEqual(len(memory.calls), len(set(memory.calls)))
        self.assertEqual(len(memory.calls), result["metrics"]["evidence_fetches"])
        self.assertEqual((0, 0), (result["metrics"]["model_calls"], result["metrics"]["external_actions"]))

    def test_performance_is_proposed_without_action(self):
        result = AgencyCapability(FakeMemory()).run("Mevcut reklam performansında hangi problemler var? Ne test edilmeli?")
        self.assertEqual(TASK_PERFORMANCE, result["objective"])
        self.assertEqual("PROPOSED", result["status"])
        self.assertIn("commercially_confirmed_attribution", result["data_gaps"])

    def test_social_plan_has_seven_balanced_days(self):
        result = AgencyCapability(FakeMemory()).run("L'CARLIE için 7 günlük Instagram planı hazırla")
        self.assertEqual(7, len(result["social_plan"]))
        self.assertTrue({"education", "brand", "product"} <= {day["objective"] for day in result["social_plan"]})
        self.assertEqual(3, len(result["roles_used"]))

    def test_missing_source_is_data_unavailable_not_faked(self):
        memory = FakeMemory(); memory.QUERIES = {k: v for k, v in memory.QUERIES.items() if k != "ecommerce_price"}
        self.assertIn("ecommerce_price", AgencyCapability(memory).run("Vireon Meta kampanyası")["data_gaps"])

    def test_research_and_model_are_contract_only(self):
        result = AgencyCapability(FakeMemory()).run("Vireon Meta kampanyası")
        self.assertIn(result["research_state"], {"NOT_REQUIRED", "RESEARCH_REQUIRED"})
        self.assertFalse(result["model_contract"]["implemented_here"])

    def test_competitor_request_marks_research_without_executing_it(self):
        result = AgencyCapability(FakeMemory()).run("Vireon rakip kreatif analizi ve Meta kampanyası")
        self.assertIn("COMPETITOR_CREATIVE", result["roles_used"])
        self.assertEqual("RESEARCH_REQUIRED", result["research_state"])
        self.assertEqual(0, result["metrics"]["external_actions"])

    def test_social_metrics_match_social_objectives(self):
        result = AgencyCapability(FakeMemory()).run("7 günlük Instagram planı")
        self.assertEqual(["saves", "replies", "story response rate", "qualified profile visits"],
                         result["success_metrics"])

    def test_registry_has_eight_metadata_roles(self):
        self.assertEqual(8, len(ROLES))


if __name__ == "__main__": unittest.main()
