"""Renk temeli -- CIEDE2000 YAYIMLANMIS REFERANS VERIYE karsi dogrulanir.

Kaynak: Sharma G., Wu W., Dalal E.N. (2005), "The CIEDE2000 color-difference
formula: implementation notes, supplementary test data and mathematical
observations", Color Research & Application 30(1), 21-30.

Bu test kumesi formulun tum kose durumlarini (hue sarmasi, sifir kroma,
RT donme terimi) kapsar. Kendi yazdigimiz uygulamanin dogrulugu buna
baglidir -- gecmezse colour-science kurulmali.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_renk as renk   # noqa: E402

# (Lab1, Lab2, beklenen dE00)
REFERANS = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


class CIEDE2000Referans(unittest.TestCase):
    def test_referans_kumesi(self):
        hatalar = []
        for lab1, lab2, beklenen in REFERANS:
            olculen = renk.delta_e2000(lab1, lab2)
            if abs(olculen - beklenen) > 0.0002:
                hatalar.append("%s vs %s: beklenen %.4f olculen %.4f"
                               % (lab1, lab2, beklenen, olculen))
        self.assertEqual(hatalar, [], "\n".join(hatalar))

    def test_simetrik(self):
        for lab1, lab2, _ in REFERANS[:6]:
            self.assertAlmostEqual(renk.delta_e2000(lab1, lab2),
                                   renk.delta_e2000(lab2, lab1), places=9)

    def test_ayni_renk_sifir(self):
        self.assertAlmostEqual(renk.delta_e2000((50, 10, -20), (50, 10, -20)),
                               0.0, places=10)


class Donusumler(unittest.TestCase):
    def test_beyaz_lab(self):
        L, a, b = renk.srgb_lab((255, 255, 255))
        self.assertAlmostEqual(L, 100.0, delta=0.05)
        self.assertAlmostEqual(a, 0.0, delta=0.05)
        self.assertAlmostEqual(b, 0.0, delta=0.05)

    def test_siyah_lab(self):
        L, a, b = renk.srgb_lab((0, 0, 0))
        self.assertAlmostEqual(L, 0.0, delta=0.001)

    def test_lch_aci(self):
        _, C, h = renk.lab_lch((50.0, 0.0, 25.0))
        self.assertAlmostEqual(C, 25.0, delta=0.001)
        self.assertAlmostEqual(h, 90.0, delta=0.001)

    def test_kontrast_orani_siniri(self):
        self.assertAlmostEqual(renk.kontrast_orani((0, 0, 0), (255, 255, 255)),
                               21.0, delta=0.01)
        self.assertAlmostEqual(renk.kontrast_orani((120, 120, 120), (120, 120, 120)),
                               1.0, delta=0.001)


class Palet(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)

    def tearDown(self):
        self.g.cleanup()

    def _gorsel(self, renkler, ad="p.png"):
        from PIL import Image
        import numpy as np
        h = 120
        parca = h // len(renkler)
        k = np.zeros((h, 120, 3), dtype="uint8")
        for i, c in enumerate(renkler):
            k[i * parca:(i + 1) * parca] = c
        p = self.d / ad
        Image.fromarray(k).save(p)
        return p

    def test_baskin_renk_bulunur(self):
        p = self._gorsel([(200, 30, 40), (200, 30, 40), (200, 30, 40), (20, 20, 20)])
        pal = renk.palet(p, 4)
        b = renk.baskin_renk(pal)
        self.assertIsNotNone(b)
        self.assertLess(renk.rgb_delta_e(b.rgb, (200, 30, 40)), 6.0,
                        "baskin renk kirmizi olmali, bulunan %s" % (b.rgb,))

    def test_algisal_olarak_yakin_renkler_birlesir(self):
        # Iki neredeyse ayni gri -- ayri palet girdisi olmamali
        p = self._gorsel([(128, 128, 128), (129, 129, 129)])
        pal = renk.palet(p, 8)
        self.assertEqual(len(pal), 1, [r.rgb for r in pal])

    def test_vurgu_rengi_ayirt_edilir(self):
        p = self._gorsel([(240, 238, 232)] * 9 + [(190, 40, 30)])
        pal = renk.palet(p, 6)
        vurgular = renk.vurgu_renkleri(pal)
        self.assertTrue(vurgular, [(r.rgb, r.lch, r.oran) for r in pal])

    def test_palet_iliskisi_veri_yok_durumu(self):
        s = renk.palet_iliskisi([], (255, 255, 255))
        self.assertEqual(s["durum"], "VERI_YOK")

    def test_palet_iliskisi_kanit_uretir(self):
        p = self._gorsel([(30, 60, 120), (200, 200, 200)])
        s = renk.palet_iliskisi(renk.palet(p, 4), (244, 242, 236))
        self.assertEqual(s["durum"], "OK")
        for anahtar in ("en_yakin_dE", "en_uzak_dE", "baskin_dE", "kontrast_orani"):
            self.assertIn(anahtar, s)


if __name__ == "__main__":
    unittest.main()
