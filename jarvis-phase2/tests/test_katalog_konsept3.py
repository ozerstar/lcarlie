"""TUR 3 -- dizi konseptleri ve kadraj sozlesmesi testleri."""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from jarvis import katalog_konsept3 as k3
from jarvis import katalog_tasarim_sistemi as ts


def _foto(en: int, boy: int) -> str:
    from PIL import Image
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / ("t-%dx%d.png" % (en, boy))
    Image.new("RGB", (en, boy), (200, 210, 220)).save(p)
    return str(p)


class KadrajSozlesmesi(unittest.TestCase):
    """Kadraj orani yerlesim oranina BIREBIR esit olmali."""

    def test_kadraj_orani_yerlesim_oranina_esit(self):
        y = _foto(1800, 1200)
        for en_mm, boy_mm in ((216.0, 144.0), (88.0, 88.0), (70.0, 83.0),
                              (73.0, 200.0), (212.0, 212.0)):
            k = k3.kadraj(y, en_mm, boy_mm)
            pw, ph = k["piksel"]
            self.assertAlmostEqual(pw / ph, en_mm / boy_mm, places=2,
                                   msg="%gx%g" % (en_mm, boy_mm))

    def test_kadraj_kutusu_goruntu_icinde(self):
        y = _foto(1800, 1200)
        for odak in (0.0, 0.2, 0.5, 0.9, 1.0):
            k = k3.kadraj(y, 70.0, 83.0, odak, odak)
            self.assertGreaterEqual(k["x"], 0.0)
            self.assertGreaterEqual(k["y"], 0.0)
            self.assertLessEqual(k["x"] + k["en"], 1.0 + 1e-9)
            self.assertLessEqual(k["y"] + k["boy"], 1.0 + 1e-9)

    def test_sik_kadraji_daraltir(self):
        y = _foto(1800, 1200)
        genis = k3.kadraj(y, 216.0, 144.0, 0.5, 0.5, 1.0)
        dar = k3.kadraj(y, 216.0, 144.0, 0.5, 0.5, 0.8)
        self.assertLess(dar["piksel"][0], genis["piksel"][0])
        self.assertAlmostEqual(dar["piksel"][0] / dar["piksel"][1],
                               216.0 / 144.0, places=2)


class DpiTabani(unittest.TestCase):
    """1800x1200 kaynakta tam tasma kare IMKANSIZ -- sessizce gecmemeli."""

    def test_tam_tasma_kare_reddedilir(self):
        y = _foto(1800, 1200)
        with self.assertRaises(ValueError):
            k3._dpi_kur(y, ts.SAYFA_MM, ts.SAYFA_MM)

    def test_uc_iki_bandi_gecer(self):
        y = _foto(1800, 1200)
        self.assertGreaterEqual(k3._dpi_kur(y, 216.0, 144.0),
                                ts.SAHNE_TABAN_DPI)

    def test_boy_siniri_203mm(self):
        y = _foto(1800, 1200)
        self.assertGreaterEqual(k3._dpi_kur(y, 216.0, 203.0),
                                ts.SAHNE_TABAN_DPI)
        with self.assertRaises(ValueError):
            k3._dpi_kur(y, 216.0, 205.0)

    def test_sik_dpi_dusurur_ve_denetlenir(self):
        y = _foto(1800, 1200)
        tam = k3._dpi_kur(y, 216.0, 144.0, 1.0)
        dar = k3._dpi_kur(y, 216.0, 144.0, 0.8)
        self.assertLess(dar, tam)
        with self.assertRaises(ValueError):
            k3._dpi_kur(y, 216.0, 144.0, 0.30)

    def test_azami_dpi_formulu(self):
        y = _foto(1800, 1200)
        self.assertAlmostEqual(k3.azami_dpi(y, 216.0, 144.0), 211.66, places=1)
        self.assertAlmostEqual(k3.azami_dpi(y, 216.0, 216.0), 141.11, places=1)


class DiziSozlesmesi(unittest.TestCase):
    """Her sayfa dizideki rolunu tasimali -- sayfa tek tek tasarlanmaz."""

    def test_bes_sayfanin_dizi_rolu_var(self):
        self.assertEqual(len(k3.DIZI), 5)
        for _k, v in k3.DIZI.items():
            self.assertIn("sira", v)
            self.assertIn("rol", v)
            self.assertIn("isik", v)
            self.assertIn("insan", v)

    def test_sira_numaralari_benzersiz_ve_tam(self):
        s = sorted(v["sira"] for v in k3.DIZI.values())
        self.assertEqual(s, [1, 2, 3, 4, 5])

    def test_roller_benzersiz(self):
        r = [v["rol"] for v in k3.DIZI.values()]
        self.assertEqual(len(r), len(set(r)))

    def test_dizide_tam_olarak_bir_insan_sayfasi(self):
        self.assertEqual(sum(1 for v in k3.DIZI.values() if v["insan"]), 1)

    def test_dizide_koyu_sayfa_var(self):
        self.assertTrue(any(v["isik"] == "KOYU" for v in k3.DIZI.values()))


class TicariKatman(unittest.TestCase):
    """Fiyat/barkod editoryal kompozisyona GIRMEZ -- ayri katman."""

    def test_sku_plani_kurulur(self):
        satir = [dict(ad="X", sku="868", hacim="50 ml", kod="LC-X",
                      fiyat="—")]
        p = k3.sku_indeksi(satir)
        self.assertEqual(p.konsept, "ticari_katman")
        self.assertEqual(p.olcumler["satir"], 1)

    def test_editoryal_sayfalarda_fiyat_alani_yok(self):
        for ad in ("kapak_uc_urun", "hydravie_numune_foyu", "kinesis_salon",
                   "femisia_cift", "babysol_alt_bant"):
            kaynak = k3.__dict__[ad].__doc__ or ""
            self.assertNotIn("fiyat", kaynak.lower())


if __name__ == "__main__":
    unittest.main()
