"""sistem.py sozlesmesi.

Bu testlerin asil isi tek bir seyi kilitlemek: YOKLUGUN SEBEBI AYRILIR.
Bir PC'nin verisi yoksa bunun iki ayri sebebi olabilir (hic rapor
gelmemis / rapor eskimis) ve ikisini ayni cumleye cevirmek bu projede
tekrar eden bir kok hatadir. Bir de "bayat" bir raporun makinenin KAPALI
oldugunu KANITLAMADIGI -- panelin bunu iddia etmemesi gerekiyor.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sistem  # noqa: E402


class RaporTazeligi(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "hosts").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _yaz(self, ad, govde, yas_s=0):
        yol = self.state / "hosts" / (ad + ".json")
        yol.write_text(json.dumps(govde), encoding="utf-8")
        if yas_s:
            eski = time.time() - yas_s
            os.utime(yol, (eski, eski))
        return yol

    def test_dosya_yoksa_RAPOR_YOK(self):
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "RAPOR_YOK")
        self.assertIsNone(m["veri"])
        self.assertIn("toplayici", m["sebep"])

    def test_taze_dosya_TAZE(self):
        self._yaz("pc1", {"cpu_yuzde": 5})
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "TAZE")
        self.assertEqual(m["veri"]["cpu_yuzde"], 5)
        self.assertIsNone(m["sebep"])

    def test_eski_dosya_BAYAT_ama_veriyi_birakir(self):
        """Bayat rapor SILINMEZ: son bilinen deger, hicbir degerden iyidir."""
        self._yaz("pc2", {"cpu_yuzde": 71}, yas_s=sistem.BAYAT_ESIGI_S + 60)
        m = sistem._rapor_oku(self.state, "pc2")
        self.assertEqual(m["durum"], "BAYAT")
        self.assertEqual(m["veri"]["cpu_yuzde"], 71)
        self.assertGreater(m["yas_s"], sistem.BAYAT_ESIGI_S)

    def test_BAYAT_makinenin_kapali_oldugunu_IDDIA_ETMEZ(self):
        """Yoklugun sebebini bilmeden cumleye cevirmek yasak.

        "PC-2 kapali" demek bir IDDIA'dir ve elimizde onu destekleyen
        olcum yok -- itme de basarisiz olmus olabilir. Sebep metni bunu
        acikca soylemek zorunda.
        """
        self._yaz("pc2", {}, yas_s=sistem.BAYAT_ESIGI_S + 5)
        sebep = sistem._rapor_oku(self.state, "pc2")["sebep"]
        self.assertIn("kanitlamaz", sebep.lower())

    def test_bozuk_json_OKUNAMADI(self):
        (self.state / "hosts" / "pc1.json").write_text("{yarim", encoding="utf-8")
        m = sistem._rapor_oku(self.state, "pc1")
        self.assertEqual(m["durum"], "OKUNAMADI")
        self.assertIsNone(m["veri"])


class Politika(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dosya_yokken_varsayilan_okunur_ve_YAZILMAZ(self):
        p = sistem.politika_oku(self.state)
        self.assertEqual(p["kaynak"], "varsayilan")
        self.assertFalse((self.state / "kaynak_politikasi.json").exists())

    def test_sahibin_karari_varsayilan_olarak_gecerli(self):
        """PC-2'den YALNIZ ekran karti kullanilir (24.09.2026 karari)."""
        a = sistem.politika_oku(self.state)["anahtarlar"]
        self.assertTrue(a["pc2_gpu"]["acik"])
        self.assertFalse(a["pc2_cpu_ram"]["acik"])
        self.assertEqual(a["pc2_cpu_ram"]["kilit"], "ozel_izin")
        self.assertTrue(a["sunucu_cpu_ram"]["acik"])
        self.assertTrue(a["pc1_cpu_ram"]["acik"])

    def test_siralama_sunucu_pc1_pc2(self):
        self.assertEqual(sistem.politika_oku(self.state)["siralama"],
                         ["sunucu", "pc1", "pc2_gpu"])

    def test_cevirme_kalici_ve_kim_cevirdigi_yazili(self):
        sistem.politika_yaz(self.state, "pc2_cpu_ram", True, "ozer")
        a = sistem.politika_oku(self.state)["anahtarlar"]["pc2_cpu_ram"]
        self.assertTrue(a["acik"])
        self.assertEqual(a["degistiren"], "ozer")
        self.assertTrue(a["degistirildi"])
        self.assertTrue(sistem.izinli_mi(self.state, "pc2_cpu_ram"))

    def test_bilinmeyen_anahtar_SESSIZCE_yutulmaz(self):
        with self.assertRaises(ValueError):
            sistem.politika_yaz(self.state, "pc3_gpu", True, "ozer")

    def test_sonradan_eklenen_anahtar_eski_dosyada_KAYBOLMAZ(self):
        """Eski bir politika dosyasi yeni bir anahtari bilmez.

        O anahtarin "kapali" gorunup sessizce devre disi kalmasi en kotu
        sonuc olurdu; varsayilan degeriyle gelmeli.
        """
        (self.state / "kaynak_politikasi.json").write_text(
            json.dumps({"anahtarlar": {"sunucu_cpu_ram": {"acik": False}}}),
            encoding="utf-8")
        a = sistem.politika_oku(self.state)["anahtarlar"]
        self.assertFalse(a["sunucu_cpu_ram"]["acik"])      # kayitli deger korunur
        self.assertTrue(a["pc2_gpu"]["acik"])              # eksik anahtar varsayilana duser
        self.assertIn("pc1_gpu", a)

    def test_bozuk_dosya_varsayilana_duser_cokmez(self):
        (self.state / "kaynak_politikasi.json").write_text("{bozuk", encoding="utf-8")
        p = sistem.politika_oku(self.state)
        self.assertEqual(p["kaynak"], "varsayilan")
        self.assertTrue(p["anahtarlar"]["pc2_gpu"]["acik"])


class SunucuBellegi(unittest.TestCase):
    """Sanal makinede `free`'nin "used" degeri uygulamalarin kullanimi DEGIL.

    24.09.2026'da sunucuda olculdu: balon 15,25 GB almisti ve panel ham
    yuzdeyi gosterseydi "sunucunun RAM'i bitti" diye yanlis bir karara
    goturur. Ust politika "once sunucu RAM'i" dedigi icin bu sayinin
    dogru olmasi ayrica onemli.
    """

    def test_balon_okunamazsa_DUZELTILEMEDI_der_tahmin_uretmez(self):
        eski = sistem._balon_gib
        sistem._balon_gib = lambda: None
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 90.5, "used_gib": 21.2,
                                              "total_gib": 23.47})
        finally:
            sistem._balon_gib = eski
        self.assertEqual(s["durum"], "DUZELTILEMEDI")
        self.assertNotIn("gercek_yuzde", s)
        self.assertIn("HAM", s["not"])

    def test_balon_varsa_gercek_toplam_dusulur(self):
        eski_b, eski_r = sistem._balon_gib, sistem._surec_rss_gib
        sistem._balon_gib = lambda: 15.25
        sistem._surec_rss_gib = lambda: 7.2
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 90.5, "used_gib": 21.2,
                                              "total_gib": 23.47})
        finally:
            sistem._balon_gib, sistem._surec_rss_gib = eski_b, eski_r
        self.assertEqual(s["durum"], "BALON_VAR")
        self.assertAlmostEqual(s["gercek_toplam_gib"], 8.22, places=2)
        self.assertAlmostEqual(s["gercek_bos_gib"], 1.02, places=2)
        # Ham %90,5 ile gercek %87,6 farkli sayilardir; ikisi de raporlanir.
        self.assertEqual(s["ham_yuzde"], 90.5)
        self.assertGreater(s["gercek_yuzde"], 80)

    def test_balon_sifirsa_ham_degerler_gercek_sayilir(self):
        eski_b, eski_r = sistem._balon_gib, sistem._surec_rss_gib
        sistem._balon_gib = lambda: 0.0
        sistem._surec_rss_gib = lambda: 8.66
        try:
            s = sistem.sunucu_bellek_gercegi({"percent": 12.0, "used_gib": 5.0,
                                              "total_gib": 43.1})
        finally:
            sistem._balon_gib, sistem._surec_rss_gib = eski_b, eski_r
        self.assertEqual(s["durum"], "BALON_YOK")
        self.assertEqual(s["gercek_toplam_gib"], 43.1)


class Gorunum(unittest.TestCase):

    def test_uc_makine_de_her_zaman_var(self):
        with tempfile.TemporaryDirectory() as t:
            g = sistem.gorunum(Path(t), {"cpu": {}, "ram": {}, "disk": {}})
            self.assertEqual(set(g["makineler"]), {"sunucu", "pc1", "pc2"})
            # Eksik PC panelden DUSMEZ; sebebiyle birlikte gorunur kalir.
            self.assertEqual(g["makineler"]["pc1"]["durum"], "RAPOR_YOK")
            self.assertTrue(g["makineler"]["pc1"]["sebep"])


if __name__ == "__main__":
    unittest.main()
