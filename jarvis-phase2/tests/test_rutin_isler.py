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
    rutin_ac,
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

    def test_gunluk_rutin_ve_icat_birlikte(self):
        s = IsUretici(self.o, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 3)
        self.assertEqual(s["gorev"], 2)   # sahip 03.11: rutin + icat birlikte (günde 4-5 iş)
        self.assertEqual(s["arastirma"], 0)   # bayrak kapalı
        g = self.gorevler()
        self.assertEqual([x["id"] for x in g][:3],
                         ["rutin-seo-g-2026-10-26", "rutin-seo-h-2026-W44", "rutin-seo-a-2026-10"])
        self.assertEqual(g[2]["tip"], "ANALIZ")          # katalog dış eylem/onay işi üretemez
        self.assertEqual(g[0]["sorumlu"], "seo_icerik")   # sorumlu yoksa departman lideri
        self.assertEqual(len(self.defter.works), 5)

    def test_ikinci_kosu_cift_eklemez(self):
        IsUretici(self.o, gunluk_tavan=50).gunluk()
        s = IsUretici(self.o, gunluk_tavan=50).gunluk()
        self.assertEqual(s["rutin"], 0)
        self.assertEqual(len(self.gorevler()), 5)

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

    def test_dongu_urun_ve_liste(self):
        kat = [{"id": "ugc", "departman": "SEO", "siklik": "gunluk", "dongu": "urun", "adet": 2,
                "baslik": "{x} için UGC senaryosu", "cikti": "senaryo", "kabul_olcutu": "x"},
               {"id": "ulke", "departman": "SEO", "siklik": "gunluk", "dongu": ["Irak", "BAE", "Azerbaycan"],
                "baslik": "{x} distribütörleri", "cikti": "liste", "kabul_olcutu": "x"}]
        acik = rutin_ac(kat, SAAT.date(), ["BABYSOFT", "LIPVORA", "VIREON", "HYDRAVIE"])
        self.assertEqual(len(acik), 3)
        u = [e for e in acik if e["rutin_kok"] == "ugc"]
        self.assertTrue(all(e["urun"] in e["baslik"] for e in u))
        self.assertNotEqual(u[0]["id"], u[1]["id"])
        ertesi = rutin_ac(kat, SAAT.date() + timedelta(days=1), ["BABYSOFT", "LIPVORA", "VIREON", "HYDRAVIE"])
        self.assertNotEqual({e["urun"] for e in u}, {e["urun"] for e in ertesi if e.get("urun")})

    def test_urun_bilgisi_ve_kismi_teslim(self):
        kat = [{"id": "ugc", "departman": "SEO", "siklik": "gunluk", "dongu": "urun", "adet": 1, "tip": "TASLAK",
                "baslik": "{x} için UGC senaryosu", "cikti": "senaryo", "kabul_olcutu": "x"}]
        def model(m, kw):
            u = m[-1]["content"]
            if "Görevi şimdi yap" in u:
                self.assertIn("ürün bilgisi: LIPVORA", u)
                self.assertIn("Shea yağı", u)
                return {"teslim_ozeti": "Senaryo yazıldı.", "icerik": "## Senaryo\n- a\n- b\n- c\n" + " ".join(["k"] * 130),
                        "kullanilan_kanit": ["K1"], "kabul_karsilandi_mi": False, "eksik": "fiyat verisi yok"}
            return cevap(m, kw)
        o = replace(self.o, rutin=lambda: kat, urunler=lambda: [("LIPVORA", "Shea yağı içerir")],
                    uret=SahteModel(model))
        IsUretici(o, gunluk_tavan=50).gunluk()
        s = IsUretici(o, gunluk_tavan=50).yurut(sinir=1)
        self.assertEqual(s["teslim"], 1)
        g = next(x for x in self.gorevler() if x.get("urun"))
        self.assertEqual(g["durum"], "TESLIM_EDILDI")
        self.assertEqual(g["teslim"]["kalite"], "KISMI")
        self.assertIn("fiyat verisi yok", Path(g["teslim"]["yol"]).read_text(encoding="utf-8"))

    def test_gunluk_arastirma_ve_kaynakli_arama(self):
        o = replace(self.o, rutin=list, gunluk_arastirma=True,
                    grounded=lambda soru: ("Bulgu: GSC rehberi yapılandırılmış veri önerir.", ["https://developers.google.com/x"]))
        s = IsUretici(o, gunluk_tavan=50).gunluk()
        self.assertEqual(s["arastirma"], 1)
        a = next(x for x in self.gorevler() if x["id"].endswith("-a1"))
        self.assertEqual(a["tip"], "ARASTIRMA")
        istemler = []
        def model(m, kw):
            istemler.append(m[-1]["content"])
            return cevap(m, kw)
        o2 = replace(o, uret=SahteModel(model))
        IsUretici(o2, gunluk_tavan=50).yurut(sinir=5)
        self.assertTrue(any("kaynaklı arama: https://developers.google.com/x" in i for i in istemler))

    def test_bilgi_dosyasi_kanita_girer(self):
        kat = [{"id": "hook", "departman": "SEO", "siklik": "gunluk", "tip": "TASLAK", "bilgi": ["hook-ve-ugc"],
                "baslik": "Hook bankası", "cikti": "10 hook", "kabul_olcutu": "x"}]
        istemler = []
        def model(m, kw):
            istemler.append(m[-1]["content"])
            return cevap(m, kw)
        dosyalar = {"hook-ve-ugc": "Hook kuralı: ilk 2 saniyede dert söylenir.", "kasim-2026-plani": "11.11 Çarşamba."}
        o = replace(self.o, rutin=lambda: kat, uret=SahteModel(model), odak_bilgi=("kasim-2026-plani",),
                    bilgi_dosyasi=lambda ad: dosyalar.get(ad, ""))
        IsUretici(o, gunluk_tavan=50).gunluk()
        self.assertIn("şirket bilgisi: kasim-2026-plani", istemler[0])   # odak her birimin günlük planında
        IsUretici(o, gunluk_tavan=50).yurut(sinir=1)
        self.assertIn("[K1] (şirket bilgisi: hook-ve-ugc) Hook kuralı", istemler[-1])

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
            for ad in e.get("bilgi", []):
                self.assertTrue((yol.parent.parent / "knowledge" / f"{ad}.md").exists(), (e["id"], ad))
            if e.get("dongu"):
                self.assertIn("{x}", e["baslik"], e["id"])
            if e["siklik"] == "aylik":
                self.assertIn(e["ay_gunu"], range(1, 29))


if __name__ == "__main__":
    unittest.main()
