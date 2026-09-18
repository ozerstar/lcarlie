"""Business-signal rules: firing, silence, and refusal to fabricate.
No DB, no network, no model."""
import unittest
from datetime import datetime, timedelta, timezone

from jarvis import business_signals as bs
from jarvis.memory import Evidence

NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def decision(**overrides):
    row = {"acik_karar": 4, "insan_onayi_bekleyen": 0, "uygulandi_olculuyor": 2,
           "sonuclanan": 10, "reddedilen": 1, "ertelenen": 0, "sonucsuz": 0,
           "red_team_itirazi": 0, "itiraz_alan_karar": 0, "toplam": 20}
    row.update(overrides)
    return [row]


def agenda_row(days_old=1, soru_id=1, kaynak_plani="wix+meta"):
    return {"soru_id": soru_id, "hedef": "satis", "oncelik": "x",
            "soru": f"soru {soru_id}", "neden_onemli": "n",
            "kaynak_plani": kaynak_plani, "durum": "d",
            "olusturma": (NOW - timedelta(days=days_old)).isoformat()}


def work_row(days_old=1, tur="satis", anahtar="k1"):
    return {"tur": tur, "anahtar": anahtar, "detay": "d",
            "zaman": (NOW - timedelta(days=days_old)).isoformat(),
            "yapilacak": "y"}


class NoFabricationTests(unittest.TestCase):
    def test_empty_everything_is_noop_and_fires_nothing(self):
        report = bs.analyze_business([], [], [], now=NOW)
        self.assertEqual(report.status, "NOOP")
        self.assertEqual(report.signals, [])
        self.assertEqual(len(report.skipped), len(bs.RULES))

    def test_healthy_company_is_noop(self):
        report = bs.analyze_business(decision(), [agenda_row()], [work_row()], now=NOW)
        self.assertEqual(report.status, "NOOP")
        self.assertEqual(report.signals, [])

    def test_missing_column_is_skipped_not_reported_as_issue(self):
        report = bs.analyze_business([{"toplam": 20}], [], [], now=NOW)
        self.assertEqual(report.status, "NOOP")
        skipped_rules = {entry["rule"] for entry in report.skipped}
        self.assertIn("rule_approval_backlog", skipped_rules)

    def test_unparseable_timestamp_is_skipped_not_treated_as_stale(self):
        rows = [dict(agenda_row(), olusturma="not-a-date") for _ in range(5)]
        report = bs.analyze_business(decision(), rows, [], now=NOW)
        self.assertNotIn("agenda_aging", [s.code for s in report.signals])
        self.assertIn("rule_agenda_aging", {e["rule"] for e in report.skipped})

    def test_no_model_calls_or_external_actions(self):
        report = bs.analyze_business(decision(insan_onayi_bekleyen=99),
                                     [agenda_row()], [work_row()], now=NOW)
        self.assertEqual(report.model_calls, 0)
        self.assertEqual(report.external_actions, 0)


class DecisionRuleTests(unittest.TestCase):
    def test_approval_backlog_fires_at_threshold(self):
        report = bs.analyze_business(decision(insan_onayi_bekleyen=5), [], [], now=NOW)
        signal = next(s for s in report.signals if s.code == "approval_backlog")
        self.assertEqual(signal.severity, "WARN")
        self.assertEqual(signal.evidence["insan_onayi_bekleyen"], 5)

    def test_approval_backlog_silent_below_threshold(self):
        report = bs.analyze_business(decision(insan_onayi_bekleyen=4), [], [], now=NOW)
        self.assertNotIn("approval_backlog", [s.code for s in report.signals])

    def test_approval_backlog_escalates_to_critical(self):
        report = bs.analyze_business(decision(insan_onayi_bekleyen=15), [], [], now=NOW)
        signal = next(s for s in report.signals if s.code == "approval_backlog")
        self.assertEqual(signal.severity, "CRITICAL")
        self.assertEqual(report.status, "CRITICAL")

    def test_decision_stall_ratio(self):
        report = bs.analyze_business(decision(ertelenen=4, sonucsuz=3, toplam=20), [], [], now=NOW)
        signal = next(s for s in report.signals if s.code == "decision_stall")
        self.assertEqual(signal.evidence["ratio"], 0.35)

    def test_decision_stall_needs_minimum_sample(self):
        report = bs.analyze_business(decision(ertelenen=3, sonucsuz=0, toplam=5), [], [], now=NOW)
        self.assertNotIn("decision_stall", [s.code for s in report.signals])
        self.assertIn("rule_decision_stall", {e["rule"] for e in report.skipped})

    def test_red_team_objection_is_critical(self):
        report = bs.analyze_business(decision(red_team_itirazi=2, itiraz_alan_karar=1),
                                     [], [], now=NOW)
        signal = next(s for s in report.signals if s.code == "red_team_objection")
        self.assertEqual(signal.severity, "CRITICAL")
        self.assertEqual(report.signals[0].code, "red_team_objection")  # sorted first


class AgendaRuleTests(unittest.TestCase):
    def test_agenda_aging_fires_with_enough_stale_items(self):
        rows = [agenda_row(days_old=30, soru_id=i) for i in range(3)]
        report = bs.analyze_business(decision(), rows, [], now=NOW)
        signal = next(s for s in report.signals if s.code == "agenda_aging")
        self.assertEqual(signal.evidence["stale_count"], 3)
        self.assertEqual(signal.evidence["oldest_days"], 30.0)

    def test_agenda_aging_silent_when_fresh(self):
        rows = [agenda_row(days_old=2, soru_id=i) for i in range(10)]
        report = bs.analyze_business(decision(), rows, [], now=NOW)
        self.assertNotIn("agenda_aging", [s.code for s in report.signals])

    def test_agenda_without_source_plan(self):
        rows = [agenda_row(soru_id=1, kaynak_plani=""), agenda_row(soru_id=2, kaynak_plani=None),
                agenda_row(soru_id=3)]
        report = bs.analyze_business(decision(), rows, [], now=NOW)
        signal = next(s for s in report.signals if s.code == "agenda_without_source_plan")
        self.assertEqual(signal.evidence["missing_count"], 2)
        self.assertEqual(signal.evidence["ids"], [1, 2])


class OpenWorkRuleTests(unittest.TestCase):
    def test_open_work_aging(self):
        rows = [work_row(days_old=20, anahtar=f"k{i}") for i in range(4)]
        report = bs.analyze_business(decision(), [], rows, now=NOW)
        signal = next(s for s in report.signals if s.code == "open_work_aging")
        self.assertEqual(signal.evidence["stale_count"], 4)
        self.assertEqual(signal.evidence["by_kind"], {"satis": 4})

    def test_open_work_concentration(self):
        rows = [work_row(tur="reklam", anahtar=f"a{i}") for i in range(7)]
        rows += [work_row(tur="crm", anahtar="c1")]
        report = bs.analyze_business(decision(), [], rows, now=NOW)
        signal = next(s for s in report.signals if s.code == "open_work_concentration")
        self.assertEqual(signal.evidence["kind"], "reklam")
        self.assertEqual(signal.evidence["count"], 7)

    def test_concentration_silent_when_spread_out(self):
        rows = [work_row(tur=kind, anahtar=kind) for kind in
                ("satis", "reklam", "crm", "operasyon", "eticaret", "sistem")]
        report = bs.analyze_business(decision(), [], rows, now=NOW)
        self.assertNotIn("open_work_concentration", [s.code for s in report.signals])

    def test_concentration_needs_minimum_sample(self):
        rows = [work_row(tur="satis", anahtar=f"k{i}") for i in range(3)]
        report = bs.analyze_business(decision(), [], rows, now=NOW)
        self.assertIn("rule_open_work_concentration", {e["rule"] for e in report.skipped})


class ReportShapeTests(unittest.TestCase):
    def test_hash_is_stable_for_same_findings(self):
        args = (decision(insan_onayi_bekleyen=7), [agenda_row()], [work_row()])
        first = bs.analyze_business(*args, now=NOW)
        second = bs.analyze_business(*args, now=NOW)
        self.assertEqual(first.content_hash, second.content_hash)

    def test_hash_changes_when_findings_change(self):
        first = bs.analyze_business(decision(insan_onayi_bekleyen=7), [], [], now=NOW)
        second = bs.analyze_business(decision(insan_onayi_bekleyen=9), [], [], now=NOW)
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_signals_sorted_critical_first(self):
        report = bs.analyze_business(
            decision(red_team_itirazi=1, insan_onayi_bekleyen=6), [], [], now=NOW)
        severities = [s.severity for s in report.signals]
        self.assertEqual(severities, sorted(severities, key=lambda s: {"CRITICAL": 0, "WARN": 1, "INFO": 2}[s]))

    def test_to_dict_is_json_serializable(self):
        import json
        report = bs.analyze_business(decision(insan_onayi_bekleyen=6), [], [], now=NOW)
        self.assertIn("approval_backlog", json.dumps(report.to_dict(), ensure_ascii=False))


class CollectTests(unittest.TestCase):
    """collect() must use only getters that already exist on the adapter."""

    class FakeMemory:
        def __init__(self):
            self.calls = []

        def _ev(self, name, records):
            self.calls.append(name)
            return Evidence(f"postgres:{name}", "CANONICAL_COMPANY_MEMORY", "live", records, 1.0)

        def get_company_context(self):
            return self._ev("decision_summary", decision(insan_onayi_bekleyen=8))

        def get_company_agenda(self):
            return self._ev("agenda", [agenda_row()])

        def get_open_work(self):
            return self._ev("open_work", [work_row()])

    def test_collect_reads_three_canonical_views(self):
        memory = self.FakeMemory()
        data = bs.collect(memory)
        self.assertEqual(memory.calls, ["decision_summary", "agenda", "open_work"])
        self.assertEqual(len(data["decision_summary"]), 1)

    def test_run_end_to_end_against_fake_memory(self):
        report = bs.run(self.FakeMemory(), now=NOW)
        self.assertEqual(report.status, "ISSUE")
        self.assertIn("approval_backlog", [s.code for s in report.signals])

    def test_getters_exist_on_the_real_adapter(self):
        from jarvis.memory import CompanyMemory
        for name in ("get_company_context", "get_company_agenda", "get_open_work"):
            self.assertTrue(callable(getattr(CompanyMemory, name, None)), name)

    def test_open_work_query_is_allowlisted(self):
        from jarvis.memory import CompanyMemory
        self.assertIn("open_work", CompanyMemory.QUERIES)


if __name__ == "__main__":
    unittest.main()
