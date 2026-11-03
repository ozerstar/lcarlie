"""Rutin iş kataloğu testleri (03.11.2026)."""
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_is_uretici import SAAT, SahteDefter, SahteModel, cevap, deps

from jarvis.is_uretici import (
    IsUretici,
    Kanit,
    Ortam,
    rutin_donem,
    rutin_vadeli,
)

KATALOG = [
    {"id": "seo-g", "departman": "SEO", "siklik": "gunluk", "tip": "ANALIZ", "kaynak": "urun_seo",
     "baslik": "Eksik SEO alanlarını say", "cikti": "tablo", "kabul_olcutu": "sayı yazılı"},
    {"id": "seo-h", "departman": "SEO", "siklik": "haftalik", "gun": SAAT.date().weekday(), "tip": "TASLAK",
     "baslik": "Haftalık SEO metin taslağı", "cikti": "taslak", "kabul_olcutu": "5 ürün"},
    {"id": "seo-h-baska-gun", "departman": "SEO", "siklik": "haftalik", "gun": (SAAT.date().weekday() + 1) % 7,
     "baslik": "Başka günün işi", "cikti": "x", "kabul_olcutu": "x"},
    {"id": "seo-a", "departman": "SEO", "siklik": "aylik", "ay_gunu": SAAT.day, "tip": "ONAY_GEREKTIREN",
     "baslik": "Aylık SEO karnesi", "cikti": "karne", "kabul_olcutu": "x"},
    {"id": "yok", "departman": "BOS", "siklik": "gunluk", "baslik": "Kadrosuz birim işi", "cikti": "x", "kabul_olcutu": "x"},
]


class TestRutin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.defter = SahteDefter()
        self.model = SahteModel(cevap)
        self.o = Ortam(departmanlar=deps,
                       uye_gorusleri=lambda d: [Kanit("", "üye:seo_teknik", "80 üründen 24'ünde meta yok")],
                       arastirma_notlari=lambda k, g: [],
                       uret=self.model, defter=self.defter, durum_dizini=Path(self.tmp.name),
                       saat=lambda: SAAT, rutin=lambda: KATALOG)

    def tearDown(self):
        self.tmp.cleanup()

    def gorevler(self):
        a = json.loads((Path(self.tmp.name) / "is-uretici" / "agac.json").read_text(encoding="utf-8"))
        return a["departmanlar"]["SEO"]["gorevler"]

    def test_donem(self):
        self.assertEqual(rutin_donem("gunluk", date(2026, 11, 3)), "2026-11-03")
        self.assertEqual(rutin_donem("haftalik", date(2026, 11, 3)), "2026-W45")
        self.assertEqual(rutin_donem("aylik", date(2026, 11, 3)), "2026-11")

    def test_vadeli_gun_ve_ay_gununa_bakar(self):
        ids = [e["id"] for e in rutin_vadeli(KATALOG, SAAT.date())]
        self.assertEqual(ids, ["seo-g", "seo-h", "seo-a", "yok"])

    def test_gunluk_rutinleri_ekler_icat_etmez(self):
        s = IsUretici(self.o, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 3)
        self.assertEqual(s["gorev"], 0)   # rutini olan birime icat görev yok
        g = self.gorevler()
        self.assertEqual([x["id"] for x in g],
                         ["rutin-seo-g-2026-10-26", "rutin-seo-h-2026-W44", "rutin-seo-a-2026-10"])
        self.assertEqual(g[2]["tip"], "ANALIZ")          # katalog dış eylem/onay işi üretemez
        self.assertEqual(g[0]["sorumlu"], "seo_icerik")   # sorumlu yoksa departman lideri
        self.assertEqual(len(self.defter.works), 3)

    def test_ikinci_kosu_cift_eklemez(self):
        IsUretici(self.o, gunluk_tavan=50).gunluk()
        s = IsUretici(self.o, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 0)
        self.assertEqual(len(self.gorevler()), 3)

    def test_acik_rutin_varken_yenisi_eklenmez(self):
        IsUretici(self.o, gunluk_tavan=50).gunluk()
        ertesi = SAAT + timedelta(days=1)
        o2 = replace(self.o, saat=lambda: ertesi)
        s = IsUretici(o2, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 1)   # yalnız salı günü haftalığı
        ids = [x["id"] for x in self.gorevler()]
        self.assertNotIn("rutin-seo-g-2026-10-27", ids)   # dünkü günlük rutin hâlâ ACIK
        self.assertIn("rutin-seo-h-baska-gun-2026-W44", ids)

    def test_yurut_once_rutin_bayat_kapanir(self):
        iu = IsUretici(self.o, gunluk_tavan=50)
        iu.gunluk()
        a = iu.agac_deposu.oku()
        a["departmanlar"]["SEO"]["gorevler"].insert(0, {
            "id": "eski", "baslik": "Çok eski icat görev", "tip": "ANALIZ", "sorumlu": "seo_teknik",
            "cikti": "x", "kabul_olcutu": "x", "durum": "ACIK", "son_tarih": "2026-10-01T00:00:00+00:00"})
        iu.agac_deposu.yaz(a, SAAT)
        s = IsUretici(self.o, gunluk_tavan=50).yurut(sinir=1)
        self.assertEqual(s["suresi_doldu"], 1)
        g = {x["id"]: x for x in self.gorevler()}
        self.assertEqual(g["eski"]["durum"], "SURESI_DOLDU")
        self.assertEqual(g["rutin-seo-g-2026-10-26"]["durum"], "TESLIM_EDILDI")

    def test_katalog_hatasi_gunlugu_durdurmaz(self):
        def bozuk():
            raise ValueError("bozuk json")
        o2 = replace(self.o, rutin=bozuk)
        s = IsUretici(o2, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 0)
        self.assertEqual(s["gorev"], 2)

    def test_gercek_katalog_gecerli(self):
        yol = Path(__file__).resolve().parent.parent / "config" / "rutin-isler.json"
        isler = json.loads(yol.read_text(encoding="utf-8"))["isler"]
        ids = [e["id"] for e in isler]
        self.assertEqual(len(ids), len(set(ids)))
        for e in isler:
            self.assertIn(e["siklik"], ("gunluk", "haftalik", "aylik"), e["id"])
            self.assertIn(e.get("tip", "ANALIZ"), ("ARASTIRMA", "ANALIZ", "TASLAK"), e["id"])
            for alan in ("departman", "baslik", "cikti", "kabul_olcutu", "kaynak"):
                self.assertTrue(e.get(alan), (e["id"], alan))
            if e["siklik"] == "haftalik":
                self.assertIn(e["gun"], range(7))
            if e["siklik"] == "aylik":
                self.assertIn(e["ay_gunu"], range(1, 29))


if __name__ == "__main__":
    unittest.main()
