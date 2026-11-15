"""Ürün maliyetinin tek kaynağı = finans merkezi (sahip, 15.11.2026).

Kilitlenen üç şey:
  1. aktarım finans sayfasının hesabını AYNEN taşır (ikinci hesap yok) ve
     maliyeti olmayan ürünü düşürmez / 0 yapmaz (VERI_YOK != 0);
  2. kimlik köprüsü finans merkezinin bildiği her ürün adını kapsar;
  3. panelin toplu fiyat önizlemesi görünümle AYNI formülü kullanır (kargo dahil).
DB davranışı ayrıca: n8n-kaynak/urun-maliyet-finans-test.sql (BEGIN/ROLLBACK).
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

WC = Path(__file__).resolve().parents[1]
ROOT = WC.parent
sys.path.insert(0, str(WC))

import product_profit as pp  # noqa: E402
import invoice_topics  # noqa: E402

_spec = importlib.util.spec_from_file_location("finans_maliyet_aktar", ROOT / "scripts" / "finans-maliyet-aktar.py")
aktar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aktar)

SQL = ROOT.parent / "server" / "sql" / "urun-maliyet-finans.sql"


def row(b, t, p, n, v, q=0, z="lcarlie", m="2026-06"):
    return {"k": "lemos", "b": b, "t": t, "z": z, "c": "dogrudan", "p": p, "n": n, "f": "NEVA", "v": v,
            "g": round(v * 1.2), "q": q, "m": m}


ROWS = [
    row("in", "lcarlie_urun", "Vireon", "L'Carlié Vireon", 1386000, q=252, m="2025-12"),
    row("in", "lcarlie_urun", "Femisia", "L'Carlié Femisia", 1402500, q=255, m="2025-12"),
    row("in", "urun_test", "", "TTS analiz", 1000000, q=1),
    row("out", "lcarlie_urun", "Vireon", "L'Carlié Vireon", 8498928, q=87),
    row("out", "lcarlie_urun", "Babysol", "L'Carlié Babysol", 100000, q=1),  # satıldı, üretim faturası yok
]


class AktarimTest(unittest.TestCase):
    def test_finans_hesabi_aynen_tasinir(self):
        rapor = pp.build(ROWS, [], "esit")
        govde = aktar.yuk(rapor)
        self.assertEqual(govde["dagitim"], "esit")
        v = next(u for u in govde["urunler"] if u["product"] == "Vireon")
        kaynak = next(x for x in rapor["products"] if x["product"] == "Vireon")
        self.assertEqual(v["unit_cost"], kaynak["unit_cost"])          # ikinci hesap yok
        self.assertEqual(v["unit_cost"], round((1386000 + 500000) / 252))

    def test_maliyetsiz_urun_dusmez_ve_sifir_olmaz(self):
        govde = aktar.yuk(pp.build(ROWS, [], "esit"))
        b = next(u for u in govde["urunler"] if u["product"] == "Babysol")
        self.assertIsNone(b["unit_cost"])          # VERI_YOK -> None, 0 değil
        self.assertNotEqual(b["unit_cost"], 0)

    def test_bos_rapor_aktarilmaz(self):
        with self.assertRaises(ValueError):
            aktar.yuk({"products": [], "allocation": "esit"})


class KimlikKoprusuTest(unittest.TestCase):
    @unittest.skipUnless(SQL.exists(), "server/sql/urun-maliyet-finans.sql yok")
    def test_finans_urun_adlarinin_hepsi_koprude(self):
        metin = SQL.read_text(encoding="utf-8")
        tohum = set(re.findall(r"^ \('([^']+)',\s+'", metin, re.M))
        self.assertGreaterEqual(len(tohum), 36)
        eksik = set(invoice_topics.LCARLIE_PRODUCTS.values()) - tohum
        self.assertFalse(eksik, f"kimlik köprüsünde olmayan finans adları: {eksik}")
        # finans merkezinin ilk kelimeden ürettiği adlar (Bright, Hair) da köprüde
        self.assertTrue({"Bright", "Hair", "Babysol", "Softguard"} <= tohum)

    @unittest.skipUnless(SQL.exists(), "server/sql/urun-maliyet-finans.sql yok")
    def test_wix_kaynak_degil_ve_400_iptal(self):
        sema = (SQL.parent / "urun-maliyet-sema.sql").read_text(encoding="utf-8")
        self.assertIn("RETURN 'WIX_KOPYA'", sema)
        self.assertIn("RETURN 'KORUNDU_FINANS'", sema)
        self.assertIn("m.iptal_at IS NULL", sema)


class FiyatOnizlemeFormuluTest(unittest.TestCase):
    def test_kargo_gorunumdeki_gibi_dusulur(self):
        import app
        # mart.platform_fiyat_matrisi: (fiyat*(1-kom) - kargo)/(1+kdv) - maliyet
        r = app._marj_hesapla(1200.0, 21.5, 20.0, 80.02, 92.66)
        beklenen = (1200 * (1 - 0.215) - 92.66) / 1.2 - 80.02
        self.assertAlmostEqual(r["marj"], round(beklenen, 2), places=2)
        self.assertEqual(app._marj_hesapla(1200.0, 21.5, 20.0, None)["uyari"], "MALIYET_YOK")


if __name__ == "__main__":
    unittest.main()
