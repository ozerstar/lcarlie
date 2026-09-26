"""Tasarim sistemi, foto analizi ve render kapilari.

En onemli testler: yukari ornekleme REDDEDILIYOR mu, kontrast kapisi
GERCEKTEN yakaliyor mu, Metropolis'te olmayan glif ikame ediliyor mu.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_konsept as kk            # noqa: E402
from jarvis import katalog_render as rd             # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts    # noqa: E402

try:
    import numpy as np
    from PIL import Image
    ARAC_VAR = True
except ImportError:                                  # pragma: no cover
    ARAC_VAR = False


def _urun_foto(yol, en=1254, boy=1254):
    """Sentetik studyo urun fotografi: gradyanli fon + koyu sise."""
    yy, xx = np.mgrid[0:boy, 0:en].astype("float32")
    zemin = 0.92 - 0.06 * (yy / boy) + 0.02 * (xx / en)
    kare = np.clip(np.dstack([zemin * 1.01, zemin, zemin * 0.98]), 0, 1)
    u_en, u_boy = int(en * 0.20), int(boy * 0.62)
    x0, y0 = int(en * 0.40), int(boy * 0.16)
    kare[y0:y0 + u_boy, x0:x0 + u_en] = 0.16
    kare[y0 + u_boy // 3:y0 + u_boy // 3 + u_boy // 8, x0:x0 + u_en] = 0.62
    for i in range(int(boy * 0.04)):
        ys = y0 + u_boy + i
        if ys < boy:
            kare[ys, x0 - u_en // 3:x0 + u_en + u_en // 3] *= 1 - 0.35 * (1 - i / (boy * 0.04))
    Image.fromarray((np.clip(kare, 0, 1) * 255).astype("uint8")).save(yol)
    return yol


class Geometri(unittest.TestCase):
    def test_kare_format(self):
        self.assertEqual(ts.KESIM_MM, 210.0)
        self.assertAlmostEqual(ts.SAYFA_MM, 216.0)

    def test_guvenli_kutu_kesimden_icerde(self):
        k = ts.GEO.kesim_kutusu
        g = ts.GEO.guvenli_kutu
        self.assertGreater(g[0], k[0])
        self.assertLess(g[2], k[2])

    def test_azami_mm_buyutmesiz(self):
        # 1000 px, 200 DPI tabani -> 127 mm
        self.assertAlmostEqual(ts.azami_mm(1000, 200.0), 127.0, delta=0.1)

    def test_yerlesim_dpi(self):
        self.assertAlmostEqual(ts.yerlesim_dpi(1000, 127.0), 200.0, delta=0.5)

    def test_zemin_murekkebi_koyu_zeminde_beyaz(self):
        m, s = ts.zemin_murekkebi({"foto_zemin": (30, 28, 26)})
        self.assertEqual(m, ts.BEYAZ)
        m2, _ = ts.zemin_murekkebi({"foto_zemin": (240, 236, 230)})
        self.assertEqual(m2, ts.MUREKKEP)


class GlifIkamesi(unittest.TestCase):
    def test_metropolis_ayraci_degistirilir(self):
        """OLCULDU: Metropolis'te U+00B7 glifi YOK."""
        s = rd.guvenli_metin("50 ml · SPF 50+", "Metropolis-Regular")
        self.assertNotIn("·", s)
        self.assertIn("–", s)

    def test_monument_degistirilmez(self):
        s = rd.guvenli_metin("A · B", "MonumentExtended-Ultrabold")
        self.assertIn("·", s)


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class RenderKapilari(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)
        self.foto = _urun_foto(self.d / "u.png")

    def tearDown(self):
        self.g.cleanup()

    def _analiz(self):
        from jarvis import katalog_foto_analiz as fa
        return fa.analiz(self.foto).sozluk()

    def test_yukari_ornekleme_REDDEDILIR(self):
        """Bu sistemin temel kurali: piksel uydurulmaz."""
        a = self._analiz()
        plan = rd.SayfaPlani("t", "test", 300.0)
        kad = {"x": 0.4, "y": 0.16, "en": 0.2, "boy": 0.62,
               "piksel": [250, 780]}
        # 250 px'i 200 mm'ye koymak 300 DPI tuvalde buyutme demektir
        plan.ekle("foto", kaynak=str(self.foto), kadraj=kad,
                  x=0, y=0, en=200.0, boy=200.0)
        with self.assertRaises(ValueError) as c:
            rd.goruntu_katmani(plan, a)
        self.assertIn("yukari ornekleme reddedildi", str(c.exception))

    def test_native_yerlesim_gecer(self):
        a = self._analiz()
        plan = rd.SayfaPlani("t", "test", 200.0)
        kad = {"x": 0.4, "y": 0.16, "en": 0.2, "boy": 0.62,
               "piksel": [250, 780]}
        plan.ekle("foto", kaynak=str(self.foto), kadraj=kad,
                  x=10, y=10, en=30.0, boy=93.0)
        g = rd.goruntu_katmani(plan, a)
        self.assertEqual(g.size[0], int(round(ts.SAYFA_MM / 25.4 * 200.0)))

    def test_kontrast_kapisi_yakalar(self):
        """Koyu zemin uzerine koyu metin -> ihlal."""
        a = self._analiz()
        plan = rd.SayfaPlani("t", "test", 200.0)
        plan.ekle("alan", x=0, y=0, en=ts.SAYFA_MM, boy=ts.SAYFA_MM,
                  renk=(22, 20, 20))
        plan.ekle("metin", stil="govde", metin="okunmayan koyu metin",
                  x=20, y=40, en=80, renk=ts.MUREKKEP)
        g = rd.goruntu_katmani(plan, a)
        ihlal = rd.metin_kontrast_denetimi(plan, g)
        self.assertTrue(ihlal, "koyu zeminde koyu metin yakalanmali")
        self.assertLess(ihlal[0]["kontrast_orani"], 3.2)

    def test_kontrast_kapisi_yanlis_pozitif_uretmez(self):
        a = self._analiz()
        plan = rd.SayfaPlani("t", "test", 200.0)
        plan.ekle("alan", x=0, y=0, en=ts.SAYFA_MM, boy=ts.SAYFA_MM,
                  renk=(245, 242, 236))
        plan.ekle("metin", stil="govde", metin="okunur koyu metin",
                  x=20, y=40, en=80, renk=ts.MUREKKEP)
        g = rd.goruntu_katmani(plan, a)
        self.assertEqual(rd.metin_kontrast_denetimi(plan, g), [])

    def test_satir_sayisi_olculebiliyor(self):
        n = rd.satir_sayisi("kelime " * 40, "govde", 60.0)
        self.assertGreater(n, 3)
        self.assertLess(rd.satir_sayisi("kisa", "govde", 60.0), 2)


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class KonseptUretimi(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)
        self.foto = _urun_foto(self.d / "u.png")
        from jarvis import katalog_foto_analiz as fa
        self.a = fa.analiz(self.foto).sozluk()
        self.palet = ts.sayfa_paleti(self.a)
        self.ic = kk.Icerik(
            slug="t", ad="TEST", alt_ad="Alt baslik",
            ust_etiket="ETIKET", manset="Iki satirlik bir manset burada.",
            govde="Govde metni " * 12, hacim="50 ml",
            inci="INCI " + "madde " * 10, kaynak_foto=str(self.foto),
            analiz=self.a)

    def tearDown(self):
        self.g.cleanup()

    def test_tip_b_uc_konsept(self):
        p = kk.uret_sinifa_gore(self.ic, self.palet, "B")
        self.assertEqual(len(p), 3)
        self.assertEqual(len({x.konsept for x in p}), 3)

    def test_tip_a_butun_goruntu_kullanir(self):
        """TYPE A'da urune kirpma YASAK -- kadraj 'tam' olmali."""
        for plan in kk.uret_sinifa_gore(self.ic, self.palet, "A"):
            self.assertEqual(plan.olcumler.get("kadraj"), "tam",
                             "%s siki kadraj kullaniyor" % plan.konsept)

    def test_kapak_kendi_havuzu(self):
        p = kk.uret_sinifa_gore(self.ic, self.palet, "A", "KAPAK")
        self.assertTrue(any("kapak" in x.konsept for x in p))

    def test_her_urun_sayfasinda_not_alani(self):
        for plan in kk.uret_sinifa_gore(self.ic, self.palet, "B"):
            turler = [o.tur for o in plan.ogeler]
            self.assertIn("not_alani", turler,
                          "%s not alani tasimiyor" % plan.konsept)

    def test_urun_dpi_tabanin_altina_dusmez(self):
        for plan in kk.uret_sinifa_gore(self.ic, self.palet, "B"):
            self.assertGreaterEqual(plan.olcumler["urun_dpi"],
                                    ts.URUN_TABAN_DPI - 0.5)

    def test_zorunlu_uyari_basilir(self):
        self.ic.uyari = "Zorunlu mevzuat uyarisi burada."
        plan = kk.konsept_c(self.ic, self.palet)
        metinler = [o.veri.get("metin", "") for o in plan.ogeler
                    if o.tur == "metin"]
        self.assertTrue(any("Zorunlu mevzuat" in m for m in metinler),
                        "mevzuat uyarisi sayfada basilmali")


if __name__ == "__main__":
    unittest.main()
