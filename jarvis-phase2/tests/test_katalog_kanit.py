"""Kanit paketi + karar kaydi sozlesmesi.

En onemli test: SAHTE SKOR uretilemiyor. Sozlesme bunu yapisal olarak
engellemeli, yalnizca belgede yasaklamakla yetinmemeli.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_kanit as kanit    # noqa: E402

try:
    import pymupdf
    PDF_VAR = True
except ImportError:                           # pragma: no cover
    PDF_VAR = False

MM = 72.0 / 25.4


class KararKaydiSozlesmesi(unittest.TestCase):
    def _gecerli(self, **kw):
        varsayilan = dict(
            gozlem="Urun sayfa yuksekliginin %46'sini kapliyor ancak "
                   "arka planla kontrasti dusuk.",
            kanit={"saliency_payi": 0.19, "konu_zemin_kontrasti": 0.08},
            gerekce="Baskinlik boyutla degil figur-zemin ayrimiyla kurulur.",
            karar="REVIZE",
            eylem="Faz 4'e gonderildi.",
            veren="C07",
        )
        varsayilan.update(kw)
        return kanit.KararKaydi(**varsayilan)

    def test_gecerli_kayit_kurulur(self):
        k = self._gecerli()
        self.assertEqual(k.karar, "REVIZE")
        self.assertIn("GOZLEM", k.metin())
        self.assertIn("GEREKCE", k.metin())

    def test_kanitsiz_karar_reddedilir(self):
        with self.assertRaises(ValueError):
            self._gecerli(kanit={})

    def test_gerekcesiz_karar_reddedilir(self):
        with self.assertRaises(ValueError):
            self._gecerli(gerekce="   ")

    def test_gozlemsiz_karar_reddedilir(self):
        with self.assertRaises(ValueError):
            self._gecerli(gozlem="")

    def test_eylemsiz_karar_reddedilir(self):
        with self.assertRaises(ValueError):
            self._gecerli(eylem="")

    def test_gecersiz_karar_degeri_reddedilir(self):
        with self.assertRaises(ValueError):
            self._gecerli(karar="GUZEL_OLMUS")

    def test_veren_zorunlu(self):
        with self.assertRaises(ValueError):
            self._gecerli(veren="")


class SahteSkorEngellenir(unittest.TestCase):
    def test_skor_alani_yakalanir(self):
        p = kanit.KanitPaketi(sayfa=1, renk={"premium_skoru": 82.7})
        sorunlar = p.dogrula()
        self.assertTrue(any("sahte skor" in s for s in sorunlar), sorunlar)

    def test_ic_ice_skor_alani_yakalanir(self):
        p = kanit.KanitPaketi(
            sayfa=1, duzen_olcumleri={"alt": {"kalite_puani": 7}})
        self.assertTrue(any("sahte skor" in s for s in p.dogrula()))

    def test_ingilizce_score_de_yakalanir(self):
        p = kanit.KanitPaketi(sayfa=1, saliency={"aesthetic_score": 0.8})
        self.assertTrue(any("sahte skor" in s for s in p.dogrula()))

    def test_normal_olcum_yakalanmaz(self):
        p = kanit.KanitPaketi(
            sayfa=1,
            duzen_olcumleri={"gorsel_alan_orani": 0.42, "bosluk_orani": 0.31},
            renk={"baskin_dE": 12.4, "kontrast_orani": 4.2})
        self.assertEqual(p.dogrula(), [])

    def test_gecersiz_sayfa_rolu_yakalanir(self):
        p = kanit.KanitPaketi(sayfa=1, sayfa_rolu="COK_GUZEL")
        self.assertTrue(any("sayfa rolu" in s for s in p.dogrula()))

    def test_gecerli_sayfa_rolleri(self):
        for rol in kanit.SAYFA_ROLLERI:
            self.assertEqual(kanit.KanitPaketi(sayfa=1, sayfa_rolu=rol).dogrula(), [])


class EksikKanitGorunur(unittest.TestCase):
    def test_toplanmayan_baslik_raporlanir(self):
        p = kanit.KanitPaketi(sayfa=1, duzen_olcumleri={"a": 1})
        eksik = p.eksikler()
        self.assertIn("varlik_siniflandirmasi", eksik)
        self.assertIn("urun_butunlugu", eksik)
        self.assertNotIn("duzen_olcumleri", eksik)

    def test_bos_deger_sorun_yok_anlamina_gelmez(self):
        """Sozlesme: None 'temiz' degil 'toplanmadi' demektir."""
        p = kanit.KanitPaketi(sayfa=1)
        self.assertTrue(p.eksikler())
        self.assertNotIn("urun_butunlugu", p.sozluk())


@unittest.skipUnless(PDF_VAR, "pymupdf yok")
class PaketUretimi(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)

    def tearDown(self):
        self.g.cleanup()

    def _pdf(self):
        b = pymupdf.open()
        for i in range(2):
            s = b.new_page(width=216 * MM, height=216 * MM)
            s.draw_rect(pymupdf.Rect(20 * MM, (20 + i * 10) * MM,
                                     150 * MM, 120 * MM),
                        color=(0.3, 0.3, 0.3), fill=(0.3, 0.3, 0.3))
        p = self.d / "t.pdf"
        b.save(str(p)); b.close()
        return p

    def test_paket_uretilir_ve_dogrulanir(self):
        p = kanit.paket_uret(self._pdf(), sayfa_no=1, sayfa_rolu="HERO")
        self.assertEqual(p.sayfa, 1)
        self.assertIsNotNone(p.duzen_olcumleri)
        self.assertEqual(p.dogrula(), [])

    def test_olmayan_sayfa_bilinmeyen_uretir(self):
        p = kanit.paket_uret(self._pdf(), sayfa_no=99)
        self.assertIsNone(p.duzen_olcumleri)
        self.assertTrue(p.bilinmeyenler)

    def test_paket_diske_yazilir_eksiklerle(self):
        import json
        p = kanit.paket_uret(self._pdf(), sayfa_no=1)
        yol = self.d / "paket.json"
        kanit.paket_yaz(p, yol)
        veri = json.loads(yol.read_text(encoding="utf-8"))
        self.assertIn("_eksik_kanit_basliklari", veri)
        self.assertIn("varlik_siniflandirmasi", veri["_eksik_kanit_basliklari"])


if __name__ == "__main__":
    unittest.main()
