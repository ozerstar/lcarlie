"""V2.1 -- urun gercegi hiyerarsisi, baski durumu, urun varligi testleri."""
from __future__ import annotations

import unittest

from jarvis import katalog_konsept_v21 as k21
from jarvis import katalog_urun_gercegi as ug
from jarvis import katalog_urun_varligi as uv


class KaynakHiyerarsisi(unittest.TestCase):
    """Dusuk otoriteli kaynak yuksek otoriteliyi EZEMEZ."""

    def test_kutu_metni_dosyayi_ezer(self):
        g = ug.yukle("femisia")
        self.assertEqual(g["alanlar"]["tanim"]["source"],
                         "approved_packaging_label")

    def test_kinesis_inci_dosyadan_geliyor(self):
        """V2'de 'INCI yok' denmisti -- kutu-gercegi icin dogru,
        SISTEM icin yanlisti."""
        g = ug.yukle("kinesis+")
        self.assertIn("inci", g["alanlar"])
        self.assertEqual(g["alanlar"]["inci"]["source"], "product_dossier")
        self.assertIn("AQUA", ug.deger(g, "inci").upper())

    def test_kinesis_tanim_dosyadan_geliyor(self):
        g = ug.yukle("kinesis+")
        self.assertNotEqual(ug.deger(g, "tanim"), ug.BILINMIYOR)

    def test_hydravie_inci_dosyadan_geliyor(self):
        g = ug.yukle("hydravie")
        self.assertNotEqual(ug.deger(g, "inci"), ug.BILINMIYOR)

    def test_otorite_sirasi_tutarli(self):
        self.assertLess(ug.OTORITE["human_verified_override"],
                        ug.OTORITE["approved_packaging_label"])
        self.assertLess(ug.OTORITE["approved_packaging_label"],
                        ug.OTORITE["product_dossier"])
        self.assertLess(ug.OTORITE["product_dossier"],
                        ug.OTORITE["packshot_label_read"])

    def test_her_alan_provenance_tasiyor(self):
        for a in ("hydravie", "kinesis+", "femisia", "babysol"):
            for alan, k in ug.yukle(a)["alanlar"].items():
                for f in ("value", "source", "source_authority", "status",
                          "last_verified"):
                    self.assertIn(f, k, "%s.%s" % (a, alan))


class CelismeVeBilinmeyen(unittest.TestCase):
    def test_babysol_net_miktar_conflict(self):
        g = ug.yukle("babysol")
        self.assertEqual(g["alanlar"]["net_miktar"]["status"], ug.CELISKI)

    def test_conflict_basilmaz(self):
        g = ug.yukle("babysol")
        self.assertEqual(ug.deger(g, "net_miktar"), ug.BILINMIYOR)

    def test_blocked_basilmaz(self):
        g = ug.yukle("babysol")
        if "mevzuat_bulgusu" in g["alanlar"]:
            self.assertEqual(ug.deger(g, "mevzuat_bulgusu"), ug.BILINMIYOR)

    def test_bulunmayan_alan_unknown(self):
        g = ug.yukle("kinesis+")
        self.assertEqual(ug.deger(g, "olmayan_alan"), ug.BILINMIYOR)


class BaskiDurumu(unittest.TestCase):
    """Uc durum; FINAL_PRINT_APPROVED fiziksel prova ister."""

    def test_250_ustu_aday(self):
        d, i = k21.baski_durumu(260.0)
        self.assertEqual(d, "PRINT_READY_CANDIDATE")
        self.assertIsNone(i)

    def test_150_249_istisna(self):
        d, i = k21.baski_durumu(212.0)
        self.assertEqual(d, "PRINT_EXCEPTION")
        self.assertIsNotNone(i)

    def test_238_de_istisna(self):
        """V2 raporunda 238 PPI istisna sayilmamis gibi anlatilmisti."""
        self.assertEqual(k21.baski_durumu(238.0)[0], "PRINT_EXCEPTION")

    def test_insan_ozne_asla_print_ready_olamaz(self):
        d, i = k21.baski_durumu(400.0, insan=True)
        self.assertEqual(d, "DIGITAL_PROTOTYPE_OK")
        self.assertIn("rights", i)

    def test_150_altinda_reddedilir(self):
        self.assertEqual(k21.baski_durumu(120.0)[0], "REDDEDILDI")

    def test_final_print_approved_uretilmez(self):
        for p in (100.0, 200.0, 260.0, 400.0):
            for insan in (True, False):
                self.assertNotEqual(k21.baski_durumu(p, insan)[0],
                                    "FINAL_PRINT_APPROVED")


class UrunVarligi(unittest.TestCase):
    """TEK SAHTE SKOR URETILMEZ."""

    def _olc(self):
        class _P:
            ogeler = []
        y = [{"source": "x", "crop": {"x": 0.0, "y": 0.0, "en": 1.0,
                                      "boy": 1.0},
              "placement_xy_mm": [0.0, 0.0],
              "placement_size_mm": [100.0, 100.0]}]
        a = {"x": {"urun_kutusu": {"x": 0.25, "y": 0.25, "en": 0.5,
                                   "boy": 0.5},
                   "ton_hiyerarsisi": {"kontrast_farki": 0.3},
                   "kenar_gerilimi": {"en_dar": 0.2},
                   "saliency_urun_payi": 0.6, "keskinlik": 0.9}}
        return uv.olc(_P(), y, a)

    def test_tek_skor_alani_yok(self):
        m = self._olc()
        for yasak in ("score", "skor", "puan", "total", "toplam", "premium"):
            self.assertFalse([k for k in m if yasak in k.lower()],
                             "sahte skor alani: %s" % yasak)

    def test_on_metrik_ayri(self):
        m = self._olc()
        for h in "ABCDEFGHIJ":
            self.assertTrue([k for k in m if k.startswith(h + "_")],
                            "metrik %s yok" % h)

    def test_bbox_en_boy_uzun_ayri(self):
        m = self._olc()
        for k in ("bbox_width_mm", "bbox_height_mm", "bbox_long_edge_mm",
                  "bbox_area_over_page"):
            self.assertIn(k, m)

    def test_saliency_proxy_olarak_etiketli(self):
        m = self._olc()
        self.assertIn("F_saliency_proxy", m)
        self.assertIn("proxy", m["measurement_method"]["F"].lower())

    def test_olcum_yontemi_ve_guven_kayitli(self):
        m = self._olc()
        self.assertIn("measurement_method", m)
        self.assertIn("confidence", m)
        self.assertIn("LOW", m["confidence"]["F"])

    def test_bbox_geometrisi_dogru(self):
        m = self._olc()
        self.assertAlmostEqual(m["bbox_width_mm"], 50.0, places=1)
        self.assertAlmostEqual(m["bbox_height_mm"], 50.0, places=1)


class UrunKadraji(unittest.TestCase):
    """Kadraj URUN KUTUSUNA gore kurulur, kare ortalanmaz."""

    def _foto(self, w=1800, h=1200):
        import pathlib
        import tempfile

        from PIL import Image
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "t.png"
        Image.new("RGB", (w, h), (200, 200, 200)).save(p)
        return str(p)

    def test_kadraj_urunu_icerir(self):
        y = self._foto()
        a = {"urun_kutusu": {"x": 0.10, "y": 0.30, "en": 0.40, "boy": 0.50}}
        k = k21.urun_kadraji(y, a, 100.0, 100.0, pay=0.15)
        self.assertLessEqual(k["x"], 0.10 + 1e-6)
        self.assertGreaterEqual(k["x"] + k["en"], 0.50 - 1e-6)

    def test_kadraj_goruntu_icinde(self):
        y = self._foto()
        for ux in (0.0, 0.3, 0.6):
            a = {"urun_kutusu": {"x": ux, "y": 0.2, "en": 0.3, "boy": 0.4}}
            k = k21.urun_kadraji(y, a, 120.0, 90.0)
            self.assertGreaterEqual(k["x"], 0.0)
            self.assertLessEqual(k["x"] + k["en"], 1.0 + 1e-9)
            self.assertLessEqual(k["y"] + k["boy"], 1.0 + 1e-9)

    def test_kadraj_orani_yerlesime_esit(self):
        y = self._foto()
        a = {"urun_kutusu": {"x": 0.2, "y": 0.2, "en": 0.4, "boy": 0.4}}
        for en, boy in ((100.0, 100.0), (120.0, 90.0), (80.0, 120.0)):
            k = k21.urun_kadraji(y, a, en, boy)
            pw, ph = k["piksel"]
            self.assertAlmostEqual(pw / ph, en / boy, places=2)


if __name__ == "__main__":
    unittest.main()
