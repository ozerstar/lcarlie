"""L'CARLIÉ ürün maliyet / kâr tablosu (sahip, 02.11.2026)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_profit as pp  # noqa: E402


def row(b, t, p, n, v, q=0, g=None, z="lcarlie", m="2026-06", k="lemos", f="NEVA"):
    return {"k": k, "b": b, "t": t, "z": z, "c": "dogrudan", "p": p, "n": n, "f": f, "v": v, "g": g if g is not None else round(v * 1.2), "q": q, "m": m}


ROWS = [
    row("in", "lcarlie_urun", "Vireon", "L'Carlié Vireon", 495000, q=90),          # 90 × 55 TL
    row("in", "lcarlie_urun", "Vireon", "L'Carlié Vireon", 891000, q=162, m="2025-12"),
    row("in", "numune_tester", "", "L'Carlié Vireon Tester", 2058000, q=4900),      # 4.900 × 4,20 TL
    row("in", "lcarlie_urun", "Femisia", "L'Carlié Femisia", 1402500, q=255, m="2025-12"),
    row("in", "urun_test", "", "Danışmanlık Hizmetleri", 5550000, q=37, z="lcarlie", f="REGNOVİS"),
    row("out", "lcarlie_urun", "Vireon", "L'Carlié Vireon", 8498928, q=87),
    row("out", "lcarlie_urun", "Femisia", "L'Carlié Femisia", 5912698, q=67),
    row("in", "grup_ici", "", "MOY hizmet", 999999, z="grup"),                     # grup içi sayılmaz
]


class BuildTest(unittest.TestCase):
    def test_layers_and_coverage(self):
        got = pp.build(ROWS, [], "esit")
        v = next(x for x in got["products"] if x["product"] == "Vireon")
        self.assertEqual((v["produced"], v["production"], v["tester"]), (252, 1386000, 2058000))
        self.assertEqual(v["general"], 2775000)                  # 55.500 TL ÜGR iki ürüne eşit
        self.assertEqual(v["total_cost"], 1386000 + 2058000 + 2775000)
        self.assertEqual(v["profit"], 8498928 - v["total_cost"])
        self.assertEqual(v["coverage"], round(8498928 / v["total_cost"] * 100, 1))
        self.assertEqual(got["totals"]["general"], 5550000)      # dağıtılan genel maliyet kuruşu kuruşuna

    def test_added_costs(self):
        extras = [{"cost_id": "a" * 32, "spent_on": "2026-11-01", "description": "TTS analiz", "net_cents": 300000, "target": "genel", "product": None},
                  {"cost_id": "b" * 32, "spent_on": "2026-11-01", "description": "Femisia çekim", "net_cents": 100000, "target": "urun", "product": "Femisia"}]
        got = pp.build(ROWS, extras, "esit")
        f = next(x for x in got["products"] if x["product"] == "Femisia")
        self.assertEqual(f["special"], 100000)
        self.assertEqual(got["totals"]["general"], 5550000 + 300000)

    def test_breakeven_units(self):
        rows = [row("in", "lcarlie_urun", "Liftelle", "L'Carlié Liftelle", 1000000, q=100), row("out", "lcarlie_urun", "Liftelle", "x", 400000, q=4)]
        x = pp.build(rows, [], "esit")["products"][0]
        self.assertEqual((x["remaining"], x["avg_price"], x["units_to_breakeven"]), (600000, 100000, 6))

    def test_allocation_by_quantity(self):
        got = pp.build(ROWS, [], "adet")
        shares = {x["product"]: x["general"] for x in got["products"]}
        self.assertEqual(shares["Vireon"] + shares["Femisia"], 5550000)
        self.assertGreater(shares["Femisia"], shares["Vireon"] * 0.9)  # 255 ↔ 252 adet


if __name__ == "__main__":
    unittest.main()
