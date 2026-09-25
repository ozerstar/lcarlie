"""Knowledge pack: koken zorunlulugu ve boilerplate yasagi."""
import json
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_bilgi as kb   # noqa: E402

PAKET = KOK / "knowledge" / "catalog"


class KokenSozlesmesi(unittest.TestCase):
    def test_kaynaksiz_oge_reddedilir(self):
        o = kb.BilgiOgesi("x", "bir iddia", "test", "", "STANDARD",
                          "YUKSEK", "her yerde", "2026-09-25")
        self.assertTrue(any("kaynaksiz" in s for s in o.dogrula()))

    def test_gecersiz_kaynak_turu_reddedilir(self):
        o = kb.BilgiOgesi("x", "iddia", "test", "bir yer", "BLOG",
                          "YUKSEK", "her yerde", "2026-09-25")
        self.assertTrue(any("source_type" in s for s in o.dogrula()))

    def test_blog_kaynagi_yuksek_guven_tasiyamaz(self):
        o = kb.BilgiOgesi("x", "iddia", "test", "Bir tasarim blogu",
                          "PROFESSIONAL_REFERENCE", "YUKSEK", "burada",
                          "2026-09-25")
        self.assertTrue(any("blog" in s for s in o.dogrula()))

    def test_applicability_zorunlu(self):
        o = kb.BilgiOgesi("x", "iddia", "test", "ISO 12647", "STANDARD",
                          "YUKSEK", "", "2026-09-25")
        self.assertTrue(any("applicability" in s for s in o.dogrula()))

    def test_gecerli_oge_temiz(self):
        o = kb.BilgiOgesi("x", "iddia", "test", "ISO 12647-2:2013", "STANDARD",
                          "YUKSEK", "kaplamali kagit icin", "2026-09-25")
        self.assertEqual(o.dogrula(), [])


class BoilerplateYasagi(unittest.TestCase):
    def test_kopya_icerik_yakalanir(self):
        with tempfile.TemporaryDirectory() as g:
            d = pathlib.Path(g)
            ayni = "x" * 500
            for ad in ("a", "b"):
                k = d / ad
                k.mkdir()
                for f in kb.ZORUNLU_DOSYALAR:
                    (k / f).write_text(ayni, encoding="utf-8")
            y = kb.yapi_dogrula(d)
            self.assertTrue(y["kopya_icerik"], "ayni metin iki klasorde -- yakalanmali")

    def test_cok_kisa_dosya_yakalanir(self):
        with tempfile.TemporaryDirectory() as g:
            d = pathlib.Path(g)
            k = d / "a"
            k.mkdir()
            for f in kb.ZORUNLU_DOSYALAR:
                (k / f).write_text("kisa", encoding="utf-8")
            y = kb.yapi_dogrula(d)
            self.assertTrue(y["cok_kisa_dosyalar"])

    def test_eksik_dosya_yakalanir(self):
        with tempfile.TemporaryDirectory() as g:
            d = pathlib.Path(g)
            k = d / "a"
            k.mkdir()
            (k / "README.md").write_text("a" * 200, encoding="utf-8")
            y = kb.yapi_dogrula(d)
            self.assertIn("a", y["eksik_dosyalar"])


@unittest.skipUnless(PAKET.is_dir(), "knowledge/catalog yok")
class GercekPaket(unittest.TestCase):
    def test_18_klasor(self):
        self.assertEqual(kb.yapi_dogrula(PAKET)["klasor_sayisi"], 18)

    def test_hicbir_zorunlu_dosya_eksik_degil(self):
        y = kb.yapi_dogrula(PAKET)
        self.assertEqual(y["eksik_dosyalar"], {})

    def test_hicbir_dosya_bos_degil(self):
        self.assertEqual(kb.yapi_dogrula(PAKET)["cok_kisa_dosyalar"], [])

    def test_hicbir_icerik_kopyalanmamis(self):
        """18 klasore ayni generic metni kopyalamak yasak."""
        self.assertEqual(kb.yapi_dogrula(PAKET)["kopya_icerik"], {})

    def test_tum_ogeler_kokenli(self):
        o = kb.ozet(PAKET)
        self.assertEqual(o["koken_sorunlari"], [], o["koken_sorunlari"])
        self.assertGreater(o["oge_sayisi"], 30)

    def test_her_klasorde_en_az_bir_oge(self):
        for d in sorted(p for p in PAKET.iterdir() if p.is_dir()):
            veri = json.loads((d / "items.json").read_text(encoding="utf-8"))
            self.assertTrue(veri, "%s bilgi ogesi tasimiyor" % d.name)

    def test_olculmus_kanit_cogunlukta(self):
        """Bu paket dis kaynak derlemesi degil; olcume dayanmali."""
        o = kb.ozet(PAKET)
        olculmus = o["kaynak_turu_dagilimi"].get("MEASURED_INTERNAL_EVIDENCE", 0)
        self.assertGreater(olculmus, o["oge_sayisi"] * 0.3)

    def test_dusuk_guvenli_kaynak_isaretli(self):
        """Blog kaynaklari DUSUK guven tasimali -- gizlenmemeli."""
        ogeler = kb.yukle(PAKET)
        dusuk = [x for x in ogeler if x.confidence == "DUSUK"]
        self.assertTrue(dusuk, "hicbir kaynak DUSUK isaretlenmemis -- supheli")


if __name__ == "__main__":
    unittest.main()
