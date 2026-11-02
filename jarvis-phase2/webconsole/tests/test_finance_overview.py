"""Finans Merkezi özeti: defterler birlikte gösterilince para iki kez sayılmaz (sahip, 02.11.2026)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_overview as fo  # noqa: E402
import money_ledger  # noqa: E402


def mv(rid, book, day, direction, party, cents, category="", account="A"):
    return {"id": rid, "book": book, "tx_date": date.fromisoformat(day), "direction": direction, "party": party,
            "party_key": money_ledger.key_of(party), "amount_cents": cents, "category": category, "scope": "",
            "account": account, "kind": "transfer", "subcategory": "", "receipt": "not_needed", "note": "",
            "document_id": None, "foreign_currency": None, "foreign_cents": None, "hand": False}


ROWS = [
    # 02.10: şahsi hesaptan MOY'a 50.000 (vergi), MOY'dan muhasebeciye 49.980
    mv("p1", "kisisel", "2026-10-02", "out", "Moy Danışmanlık Tekn Org San Ve Tic Aş", 5000000, "ofis"),
    mv("c1", "moy", "2026-10-02", "in", "MURAT ÖZER YILDIZ", 5000000, "ortaktan"),
    mv("c2", "moy", "2026-10-02", "out", "salih tekintaş", 4998000, "ofis"),
    # MOY'dan sahibine 100.000
    mv("c3", "moy", "2026-10-08", "out", "Murat Özer Yıldız", 10000000, "ortaga"),
    mv("p2", "kisisel", "2026-10-08", "in", "MOY DAN.TEK.ORG.SAN.VE TİC.AŞ.", 10000000, "sirketten"),
    # Lemos'tan MOY'a 20.000 (grup içi)
    mv("l1", "lemos", "2026-10-10", "out", "MOY DANIŞMANLIK", 2000000, "diger"),
    mv("c4", "moy", "2026-10-10", "in", "LEMOS MEDİKAL SAĞLIK", 2000000, "diger_gelen"),
    # gerçek dış hareketler
    mv("p3", "kisisel", "2026-10-15", "out", "Migros", 150000, "market"),
    mv("l2", "lemos", "2026-10-20", "in", "PAYTR", 3000000, "tahsilat"),
    mv("p4", "kisisel", "2026-10-21", "out", "Kendi hesabım", 9900000, "ic_transfer"),
    mv("p5", "kisisel", "2026-09-15", "out", "Migros", 100000, "market"),
]
OCT = (date(2026, 10, 1), date(2026, 11, 1), date(2026, 9, 1), date(2026, 10, 1))


class InternalTest(unittest.TestCase):
    def test_everything_together_counts_only_outside_money(self):
        got = fo.summarize(ROWS, fo.WORKSPACES["tumu"], *OCT)
        self.assertEqual(got["out_total"], 4998000 + 150000)   # muhasebeci + market; vergi parası bir kez
        self.assertEqual(got["in_total"], 3000000)             # yalnız PayTR tahsilatı
        self.assertEqual(got["net"], 3000000 - 5148000)
        reasons = {m["id"]: m["internal"] for m in got["movements"]}
        self.assertEqual(reasons["p1"], "Şirket ↔ şahsi aktarım")
        self.assertEqual(reasons["c4"], "Grup içi (Lemos ↔ MOY)")
        self.assertIsNone(reasons["p3"])
        self.assertEqual(got["owner_flow"]["company_to_owner"], 10000000)

    def test_single_book_is_counted_as_its_own_ledger_says(self):
        got = fo.summarize(ROWS, fo.WORKSPACES["sahsi"], *OCT)
        self.assertEqual(got["out_total"], 5000000 + 150000)  # tek defterde MOY'a giden para gider
        self.assertEqual(got["in_total"], 10000000)           # ve şirketten gelen para gelir
        self.assertEqual(got["prev_out_total"], 100000)

    def test_companies_together_drop_group_money_only(self):
        got = fo.summarize(ROWS, fo.WORKSPACES["sirketler"], *OCT)
        self.assertEqual(got["in_total"], 5000000 + 3000000)  # sahibinden gelen kalır, Lemos→MOY çıkar
        self.assertEqual(got["out_total"], 4998000 + 10000000)

    def test_transfer_pair_is_internal_even_without_a_label(self):
        rows = [mv("x1", "lemos", "2026-10-05", "out", "Ayşe", 100000), mv("x2", "kisisel", "2026-10-05", "in", "Ayşe", 100000)]
        got = fo.summarize(rows, fo.WORKSPACES["tumu"], *OCT, pair_ids=frozenset({"x1", "x2"}))
        self.assertEqual((got["in_total"], got["out_total"]), (0, 0))


class OwnerGapTest(unittest.TestCase):
    """02.11.2026 ölçüldü: MOY → sahip transferleri Enpara'ya gidiyor, Enpara dökümü 19.06'da başlıyor."""

    def test_gap_reasons(self):
        def sent(rid, day, cents, desc):
            r = mv(rid, "moy", day, "out", "Murat özer yıldız", cents, "")
            r["description"] = desc
            return r
        rows = [sent("a", "2026-03-30", 4329700, "ENPARA BANK A.Ş./IBAN MERKEZ ŞUBESİ gönderilen havale .ozer"),
                sent("b", "2026-04-08", 385400, "DENIZBANK A.Ş. ozer"),
                sent("c", "2026-07-16", 11998500, "ENPARA BANK A.Ş. ozer"),
                mv("d", "kisisel", "2026-07-16", "in", "MOY DAN.TEK.ORG.SAN.VE TİC.AŞ.", 11998500, "sirketten"),
                mv("e", "kisisel", "2026-07-31", "in", "LEMOS MEDİKAL SAĞLIK", 6666667, "gelir")]
        got = fo.summarize(rows, fo.WORKSPACES["tumu"], date(2026, 1, 1), date(2027, 1, 1), date(2025, 1, 1), date(2026, 1, 1),
                           pair_ids=frozenset({"c", "d"}), statement_starts={"Enpara hesap": date(2026, 6, 19)})["owner_flow"]
        self.assertEqual(got["matched"], 11998500)
        self.assertEqual([(g["bank"], g["total"], g["statement_from"]) for g in got["no_statement"]], [("Enpara", 4329700, "2026-06-19")])
        self.assertEqual([(g["bank"], g["total"]) for g in got["other_bank"]], [("DenizBank", 385400)])
        self.assertEqual(got["unmatched"], [])
        self.assertEqual([(g["party"], g["total"]) for g in got["no_company_side"]], [("LEMOS MEDİKAL SAĞLIK", 6666667)])


class PeriodTest(unittest.TestCase):
    def test_year_and_range(self):
        self.assertEqual(fo.period("year", date(2026, 5, 3)),
                         (date(2026, 1, 1), date(2027, 1, 1), date(2025, 1, 1), date(2026, 1, 1)))
        s, e, ps, pe = fo.period("range", None, date(2026, 10, 10), date(2026, 10, 19))
        self.assertEqual((s, e, ps, pe), (date(2026, 10, 10), date(2026, 10, 20), date(2026, 9, 30), date(2026, 10, 10)))

    def test_monthly_series_has_twelve_months(self):
        got = fo.summarize(ROWS, fo.WORKSPACES["sahsi"], *OCT)
        self.assertEqual(len(got["monthly"]), 12)
        self.assertEqual(got["monthly"][-1]["month"], "2026-10")
        self.assertEqual(got["monthly"][-2]["out"], 100000)


if __name__ == "__main__":
    unittest.main()
