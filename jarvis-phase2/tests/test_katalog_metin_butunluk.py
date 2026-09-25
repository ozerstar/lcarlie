"""Metin tekrar motoru + urun butunlugu vetosu."""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_butunluk as but      # noqa: E402
from jarvis import katalog_metin_tekrar as mt   # noqa: E402

try:
    import numpy as np
    from PIL import Image
    ARAC_VAR = True
except ImportError:                              # pragma: no cover
    ARAC_VAR = False


class MetinTekrari(unittest.TestCase):
    def test_birebir_tekrar_yakalanir(self):
        m = {
            "a": "Cildin nem dengesini destekler. Gunluk kullanima uygundur.",
            "b": "Farkli bir giris. Cildin nem dengesini destekler.",
            "c": "Baska bir urun metni tamamen ayri.",
        }
        b = mt.birebir_tekrar(m)
        self.assertTrue(b)
        self.assertEqual(b[0].gecis_sayisi, 2)

    def test_zorunlu_uyari_tekrar_sayilmaz(self):
        """Mevzuat geregi tekrar dogru davranistir, kusur degil."""
        uyari = "Alerjik reaksiyon durumunda doktora danisin."
        m = {"a": "Ilk urun metni buraya. " + uyari,
             "b": "Ikinci urun metni burada. " + uyari,
             "c": "Ucuncu urun metni soyle. " + uyari}
        b = mt.birebir_tekrar(m)
        for bulgu in b:
            self.assertNotIn("doktora danisin", bulgu.kalip)

    def test_ngram_tekrari_olculur(self):
        m = {"u%d" % i: "Bu urun cildin nem dengesini destekler ve besler."
             for i in range(5)}
        b = mt.ngram_tekrar(m, n=3)
        self.assertTrue(b)
        self.assertEqual(b[0].gecis_sayisi, 5)
        self.assertAlmostEqual(b[0].oran, 1.0, places=3)

    def test_kalip_tekrari_farkli_kelimeyle_de_yakalanir(self):
        """Ayni iskelet, farkli ortadaki kelimeler."""
        m = {
            "a": "Arnika iceren formul cildin yatistirilmasina yardimci olur bugun.",
            "b": "Arnika iceren formul derinin onarilmasina yardimci olur bugun.",
            "c": "Arnika iceren formul bariyerin guclendirilmesine yardimci olur bugun.",
        }
        b = mt.kalip_tekrar(m)
        self.assertTrue(b, "ayni iskelet yakalanmali")
        self.assertGreaterEqual(b[0].gecis_sayisi, 3)

    def test_turkce_buyuk_I_tuzagi(self):
        """'I' ve 'İ' sadelestirmede karismamali."""
        self.assertEqual(mt._sadelestir("İLK"), "ilk")
        self.assertEqual(mt._sadelestir("ILIK"), "ılık")

    def test_anlamsal_katman_gommesizse_SORAMADIM(self):
        """DURUM AYRIMI: 'tekrar yok' ile 'bakamadim' ayni degil."""
        s = mt.anlamsal_tekrar({"a": "x", "b": "y"}, gomme_islevi=None)
        self.assertEqual(s["durum"], "SORAMADIM")
        self.assertEqual(s["ciftler"], [])

    def test_anlamsal_katman_gomme_ile_calisir(self):
        def sahte_gomme(metin):
            # "nem" iceren metinler birbirine yakin olsun
            nem = 1.0 if "nem" in metin else 0.0
            return [nem, 1.0 - nem, 0.1]
        m = {"a": "cildin nem dengesi", "b": "nem seviyesini korur",
             "c": "guclu antioksidan"}
        s = mt.anlamsal_tekrar(m, sahte_gomme, esik=0.9)
        self.assertEqual(s["durum"], "OK")
        ciftler = [tuple(c["urunler"]) for c in s["ciftler"]]
        self.assertIn(("a", "b"), ciftler)

    def test_gomme_hatasi_OKUNAMADI(self):
        def patlayan(_):
            raise RuntimeError("gomme servisi kapali")
        s = mt.anlamsal_tekrar({"a": "x", "b": "y"}, patlayan)
        self.assertEqual(s["durum"], "OKUNAMADI")

    def test_kanit_sozlesmesi(self):
        k = mt.kanit({"a": "Bir cumle burada yer alir.", "b": "Baska bir cumle."})
        for anahtar in ("urun_sayisi", "toplam_cumle", "zorunlu_cumle",
                        "birebir_tekrar", "ngram_tekrar", "kalip_tekrar",
                        "anlamsal", "en_sik_kelimeler"):
            self.assertIn(anahtar, k)


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class ButunlukVetosu(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)

    def tearDown(self):
        self.g.cleanup()

    def _gorsel(self, ad, en=400, boy=800, renk=(180, 60, 50)):
        p = self.d / ad
        Image.fromarray(np.full((boy, en, 3), renk, dtype="uint8")).save(p)
        return p

    def _koken(self, kaynak, islemler=()):
        k = but.Koken(varlik="urun", kaynak_ozeti=but.dosya_ozeti(kaynak))
        for i in islemler:
            k.ekle(i, "test", "2026-09-25", "a", "b")
        return k

    def test_koken_yoksa_BILINMIYOR_gecmez(self):
        """Kanitsiz gecis yok -- bu kapinin sozlesmesi."""
        a = self._gorsel("a.png")
        k = but.dogrula(a, a, koken=None)
        self.assertEqual(k.karar, "BILINMIYOR")
        with self.assertRaises(but.ButunlukIhlali):
            but.kapi(a, a, koken=None)

    def test_temiz_zincir_gecer(self):
        a = self._gorsel("a.png")
        b = self._gorsel("b.png")
        k = but.dogrula(a, b, koken=self._koken(a, ["background_removal", "resize"]))
        self.assertEqual(k.karar, "GECER", k.ihlaller)

    def test_uretken_islem_HARD_FAIL(self):
        a = self._gorsel("a.png")
        b = self._gorsel("b.png")
        for islem in ("diffusion", "inpaint", "product_regeneration",
                      "label_regeneration", "generative_upscale"):
            k = but.dogrula(a, b, koken=self._koken(a, [islem]))
            self.assertEqual(k.karar, "DURDUR", islem)
            self.assertTrue(any("uretken islem" in i for i in k.ihlaller))

    def test_geometri_bozan_islem_yakalanir(self):
        a = self._gorsel("a.png")
        b = self._gorsel("b.png")
        k = but.dogrula(a, b, koken=self._koken(a, ["perspective_warp"]))
        self.assertEqual(k.karar, "DURDUR")

    def test_en_boy_sapmasi_yakalanir(self):
        a = self._gorsel("a.png", 400, 800)
        b = self._gorsel("b.png", 400, 600)          # oran degismis
        k = but.dogrula(a, b, koken=self._koken(a))
        self.assertEqual(k.karar, "DURDUR")
        self.assertTrue(any("en/boy" in i for i in k.ihlaller))

    def test_govde_rengi_kaymasi_yakalanir(self):
        a = self._gorsel("a.png", 400, 800, (180, 60, 50))
        b = self._gorsel("b.png", 400, 800, (150, 100, 90))
        k = but.dogrula(a, b, koken=self._koken(a))
        self.assertEqual(k.karar, "DURDUR")
        self.assertTrue(any("govde rengi" in i for i in k.ihlaller))
        self.assertGreater(k.olcumler["govde_delta_e"], 3.0)

    def test_kaynak_degisirse_yakalanir(self):
        a = self._gorsel("a.png")
        koken = self._koken(a)
        self._gorsel("a.png", renk=(20, 200, 30))    # kaynagi degistir
        k = but.dogrula(a, a, koken=koken)
        self.assertEqual(k.karar, "DURDUR")
        self.assertTrue(any("ozetle eslesmiyor" in i for i in k.ihlaller))

    def test_veto_asilabilir_degil(self):
        a = self._gorsel("a.png")
        k = but.dogrula(a, a, koken=self._koken(a, ["diffusion"]))
        self.assertFalse(k.asilabilir)

    def test_koken_yazilip_okunabiliyor(self):
        a = self._gorsel("a.png")
        k = self._koken(a, ["background_removal"])
        yol = self.d / "koken.json"
        but.koken_yaz(k, yol)
        geri = but.koken_oku(yol)
        self.assertIsNotNone(geri)
        self.assertEqual(geri.kaynak_ozeti, k.kaynak_ozeti)
        self.assertEqual([a.islem for a in geri.adimlar], ["background_removal"])

    def test_bozuk_koken_dosyasi_None_doner(self):
        yol = self.d / "bozuk.json"
        yol.write_text("{bu gecerli json degil", encoding="utf-8")
        self.assertIsNone(but.koken_oku(yol))


if __name__ == "__main__":
    unittest.main()
