"""mcp_server.py testleri.

🔴 BU TESTLER ANA VENV'DE ATLANIR. `mcp` paketi bilerek AYRI bir venv'de
(venv-mcp) durur -- uretim venv'ine 13 paket eklememek icin. Ana venv'de
import basarisiz olur ve testler skip edilir; bu bir arıza degil, tasarim.
Gercekten calistirmak icin:
    venv-mcp/bin/python -m unittest tests.test_mcp_server -v
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import mcp_server
    VAR = True
except ImportError:
    VAR = False


@unittest.skipUnless(VAR, "mcp paketi bu venv'de yok (venv-mcp'de kurulu)")
class PaketTesti(unittest.TestCase):

    def test_bos_sonuc_veri_yok_der(self):
        """0 satir 'VERI_YOK'tur -- hata degil, bilinmiyor da degil."""
        v = json.loads(mcp_server._paket("agenda", [], 5.0, 25))
        self.assertEqual(v["durum"], "VERI_YOK")
        self.assertEqual(v["toplam_satir"], 0)

    def test_dolu_sonuc_ok_der(self):
        v = json.loads(mcp_server._paket("agenda", [{"a": 1}, {"a": 2}], 5.0, 25))
        self.assertEqual(v["durum"], "OK")
        self.assertEqual(v["toplam_satir"], 2)
        self.assertEqual(v["donen_satir"], 2)

    def test_limit_uygulanir_ama_toplam_dogru_kalir(self):
        satirlar = [{"a": i} for i in range(10)]
        v = json.loads(mcp_server._paket("agenda", satirlar, 5.0, 3))
        self.assertEqual(v["donen_satir"], 3)
        self.assertEqual(v["toplam_satir"], 10, "toplam kirpmadan etkilenmemeli")

    def test_tavan_asilirsa_kirpildigi_SOYLENIR(self):
        """🔴 Sessiz kirpma, eksik veriyi tam gibi gostermek olurdu."""
        sisman = [{"metin": "x" * 500, "i": i} for i in range(200)]
        v = json.loads(mcp_server._paket("agenda", sisman, 5.0, 0))
        self.assertIn("kirpildi", v, "kirpma bildirilmedi")
        self.assertLess(v["donen_satir"], v["toplam_satir"])
        self.assertEqual(v["toplam_satir"], 200)


@unittest.skipUnless(VAR, "mcp paketi bu venv'de yok (venv-mcp'de kurulu)")
class GuvenlikTesti(unittest.TestCase):

    def test_allowlist_disi_ad_calistirilmaz(self):
        """Serbest SQL denemesi reddedilir ve izinli adlar geri verilir."""
        for kotu in ("DROP TABLE core.karar", "agenda; DELETE FROM core.karar",
                     "", "../../etc/passwd"):
            v = json.loads(mcp_server._calistir(kotu, 5))
            self.assertEqual(v["durum"], "IZINLI_DEGIL", f"reddedilmedi: {kotu!r}")
            self.assertIn("izinli_sorgular", v)

    def test_sorgu_hatasi_SORAMADIM_dir_veri_yok_degil(self):
        """🔴 Olculmus tuzak: basarisiz sorgu 'sifir' diye okunursa yanlis karar."""
        class Patlayan:
            QUERIES = mcp_server._memory.QUERIES

            def _fetch(self, ad):
                raise mcp_server.MemoryError("baglanti koptu")

        asil = mcp_server._memory
        mcp_server._memory = Patlayan()
        try:
            v = json.loads(mcp_server._calistir("agenda", 5))
        finally:
            mcp_server._memory = asil
        self.assertEqual(v["durum"], "SORAMADIM")
        self.assertNotEqual(v["durum"], "VERI_YOK")
        self.assertIn("baglanti koptu", v["sebep"])

    def test_yazma_araci_YOKTUR(self):
        """V1 salt okunur. Yazan bir arac eklenirse bu test kirilmali."""
        araclar = {ad for ad in dir(mcp_server)
                   if not ad.startswith("_") and callable(getattr(mcp_server, ad))}
        yasakli = {"hatirlatma_ekle", "kaydet", "yaz", "guncelle", "sil"}
        self.assertEqual(araclar & yasakli, set(),
                         "V1'e yazma araci eklenmis -- ayri CR gerekir")


if __name__ == "__main__":
    unittest.main()
