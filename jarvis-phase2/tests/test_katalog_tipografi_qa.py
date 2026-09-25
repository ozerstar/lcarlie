"""Tipografi QA: kapinin GERCEKTEN reddettigini negatif fixture ile kanitla.

"Temiz PDF geciyor" testi tek basina degersizdir. Her ihlal tipi icin
bilerek bozuk bir sayfa uretilir ve kapinin yakaladigi dogrulanir.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_tipografi_qa as tqa   # noqa: E402

try:
    import pymupdf
    PDF_VAR = True
except ImportError:                              # pragma: no cover
    PDF_VAR = False

# 210x210 mm kare + 3 mm tasma -> 216 x 216 mm
MM = 72.0 / 25.4
SAYFA = (216 * MM, 216 * MM)
TASMA, GUVENLI = 3.0, 5.0
IC_KENAR = (TASMA + GUVENLI) * MM


def _ttf_bul():
    for kok in (pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar-ttf"),
                KOK / "varliklar" / "fontlar-ttf"):
        if kok.is_dir():
            for p in sorted(kok.rglob("*.ttf")):
                return p
    return None


def _belge():
    d = pymupdf.open()
    d.new_page(width=SAYFA[0], height=SAYFA[1])
    return d


def _yaz(sayfa, metin, x, y, boyut=10.0, ttf=None):
    if ttf:
        sayfa.insert_text((x, y), metin, fontsize=boyut,
                          fontfile=str(ttf), fontname="gomulu")
    else:
        sayfa.insert_text((x, y), metin, fontsize=boyut, fontname="helv")


@unittest.skipUnless(PDF_VAR, "pymupdf yok")
class GlifKapsama(unittest.TestCase):
    def test_okunamayan_font_eksik_degil_okunamadi(self):
        s = tqa.glif_kapsama("/olmayan/font.ttf")
        self.assertEqual(s["durum"], "OKUNAMADI")

    def test_gercek_font_turkce_kapsamasi(self):
        ttf = _ttf_bul()
        if ttf is None:
            self.skipTest("ttf bulunamadi")
        s = tqa.glif_kapsama(ttf)
        self.assertIn(s["durum"], ("OK", "EKSIK"))
        self.assertGreater(s["kapsam_buyuklugu"], 100)
        # Eksikse hangi glifin eksik oldugu YAZILI olmali -- sessiz gecmemeli
        if s["durum"] == "EKSIK":
            self.assertTrue(s["eksik_glifler"])


@unittest.skipUnless(PDF_VAR, "pymupdf yok")
class KapiGercektenReddediyor(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.gecici.name)
        self.ttf = _ttf_bul()

    def tearDown(self):
        self.gecici.cleanup()

    def _kaydet(self, belge, ad):
        p = self.d / ad
        belge.save(str(p))
        belge.close()
        return p

    # --- POZITIF: temiz sayfa gecer
    def test_temiz_sayfa_gecer(self):
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        for i in range(4):
            _yaz(s, "L'CARLIE dermokozmetik katalogu ornek satir %d" % i,
                 IC_KENAR + 10, IC_KENAR + 40 + i * 16, 10.0, self.ttf)
        p = self._kaydet(b, "temiz.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        self.assertTrue(sonuc["gecti"], sonuc["tip_dagilimi"])

    # --- NEGATIF fixture'lar
    def test_gomulmemis_font_yakalanir(self):
        b = _belge(); s = b[0]
        _yaz(s, "gomulmemis base-14 font", IC_KENAR + 10, IC_KENAR + 40, 10.0, None)
        p = self._kaydet(b, "gomsuz.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        self.assertFalse(sonuc["gecti"])
        self.assertIn("font_gomulmemis", sonuc["tip_dagilimi"])

    def test_guvenli_alan_ihlali_yakalanir(self):
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        _yaz(s, "kesim payina giren satir", 2.0, 12.0, 10.0, self.ttf)
        p = self._kaydet(b, "kenar.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        self.assertFalse(sonuc["gecti"])
        self.assertIn("guvenli_alan_ihlali", sonuc["tip_dagilimi"])

    def test_cok_kucuk_punto_yakalanir(self):
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        _yaz(s, "okunamayacak kadar kucuk dipnot", IC_KENAR + 10,
             IC_KENAR + 60, 4.0, self.ttf)
        p = self._kaydet(b, "kucuk.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        self.assertFalse(sonuc["gecti"])
        self.assertIn("punto_cok_kucuk", sonuc["tip_dagilimi"])

    def test_metin_carpismasi_yakalanir(self):
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        _yaz(s, "UST USTE BINEN BASLIK", IC_KENAR + 10, IC_KENAR + 80, 14.0, self.ttf)
        _yaz(s, "UST USTE BINEN BASLIK", IC_KENAR + 12, IC_KENAR + 82, 14.0, self.ttf)
        p = self._kaydet(b, "carpisma.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        self.assertFalse(sonuc["gecti"])
        self.assertIn("metin_carpismasi", sonuc["tip_dagilimi"])

    def test_pdf_uzerinden_glif_denetimi_YAPILMAZ(self):
        """GERILEME KORUMASI -- bu denetim bilerek kaldirildi.

        OLCULDU: PDF'e gomulu alt kume fontun cmap'i Unicode degil;
        denendi ve gercek katalogda 258 YANLIS POZITIF uretti. Sayfa
        render edildiginde Turkce karakterler dogru basiliyor.
        Glif denetimi KAYNAK font uzerinde yapilir: glif_kapsama().

        Biri bu denetimi PDF'e geri eklerse bu test kirilir."""
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        _yaz(s, "çğıİöşüÇĞÖŞÜ L'CARLIÉ", IC_KENAR + 10, IC_KENAR + 100,
             10.0, self.ttf)
        p = self._kaydet(b, "turkce.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        glif = [i for i in sonuc["ihlaller"] if i["ihlal_tipi"] == "eksik_glif"]
        self.assertEqual(glif, [],
                         "PDF uzerinden glif denetimi geri eklenmis -- yanlis pozitif uretir")

    def test_kullanilmayan_gomulmemis_font_durdurmaz(self):
        """OLCULDU: katalog PDF'inde Helvetica her sayfanin kaynak
        listesinde ama hicbir metin span'i onu kullanmiyor."""
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        _yaz(s, "yalniz gomulu font kullaniliyor", IC_KENAR + 10,
             IC_KENAR + 40, 10.0, self.ttf)
        p = self._kaydet(b, "kullanilmayan.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        durduran = [i for i in sonuc["ihlaller"]
                    if i["ihlal_tipi"] == "font_gomulmemis"]
        self.assertEqual(durduran, [], "kullanilmayan font uretimi durdurmamali")

    def test_kisa_son_satir_uyari_ama_durdurmaz(self):
        """Dul satir vekili UYARI'dir -- PDF paragraf sinirini tasimaz,
        bu yuzden yanlis pozitif riski var ve uretimi durdurmamali."""
        if self.ttf is None:
            self.skipTest("gomulu font yok")
        b = _belge(); s = b[0]
        uzun = "Bu satir blogun tam genisligini kaplayan uzun bir govde satiridir"
        for i in range(3):
            _yaz(s, uzun, IC_KENAR + 10, IC_KENAR + 40 + i * 14, 9.0, self.ttf)
        _yaz(s, "tek", IC_KENAR + 10, IC_KENAR + 40 + 3 * 14, 9.0, self.ttf)
        p = self._kaydet(b, "dul.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        durdurucu = [i for i in sonuc["ihlaller"] if i["agirlik"] == tqa.AGIRLIK_DURDURUR]
        self.assertEqual(durdurucu, [], "kisa son satir uretimi durdurmamali")

    def test_ihlal_her_zaman_konum_tasir(self):
        b = _belge(); s = b[0]
        _yaz(s, "kenarda", 2.0, 10.0, 4.0, None)
        p = self._kaydet(b, "konum.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        for i in sonuc["ihlaller"]:
            if i["ihlal_tipi"] == "font_gomulmemis":
                continue
            self.assertIsNotNone(i["konum"], i)

    def test_kapi_ciktisi_sozlesmeye_uyuyor(self):
        b = _belge(); _yaz(b[0], "x", IC_KENAR + 10, IC_KENAR + 20, 10.0, None)
        p = self._kaydet(b, "sozlesme.pdf")
        sonuc = tqa.kapi(p, tasma_mm=TASMA, guvenli_mm=GUVENLI)
        for anahtar in ("gecti", "durduran_ihlal", "uyari", "tip_dagilimi", "ihlaller"):
            self.assertIn(anahtar, sonuc)
        self.assertIsInstance(sonuc["gecti"], bool)


if __name__ == "__main__":
    unittest.main()
