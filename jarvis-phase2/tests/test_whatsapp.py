# -*- coding: utf-8 -*-
"""Gönderme kapılarının testleri.

🔴 BU TESTLER AĞA ÇIKMAZ. Hiçbiri gerçek mesaj göndermez; kapıların
gönderimi DURDURDUĞUNU kanıtlarlar. Bir kapı sessizce gevşerse müşteriye
yanlış mesaj gider ve geri alınamaz.
"""
import os
import tempfile
import unittest
from pathlib import Path

from jarvis import whatsapp


class KapilarKAPATIR(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "gonderim.jsonl"
        self.eski_defter = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        self.eski_env = os.environ.get("JARVIS_WHATSAPP_GONDER")
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski_defter
        if self.eski_env is None:
            os.environ.pop("JARVIS_WHATSAPP_GONDER", None)
        else:
            os.environ["JARVIS_WHATSAPP_GONDER"] = self.eski_env
        self.gecici.cleanup()

    def test_1_onaysiz_gonderilmez(self):
        for onay in ("", None, "rastgele", "SAHIP-PANEL"):
            with self.subTest(onay=onay):
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    whatsapp.gonder("905550000000", "merhaba",
                                    onay_kaynagi=onay)

    def test_2_bos_metin_gonderilmez(self):
        for metin in ("", "   ", "\n"):
            with self.subTest(metin=metin):
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    whatsapp.gonder("905550000000", metin,
                                    onay_kaynagi=whatsapp.ONAY_INSAN)

    def test_2_uzun_metin_gonderilmez(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", "a" * (whatsapp.METIN_SINIRI + 1),
                            onay_kaynagi=whatsapp.ONAY_INSAN)

    def test_4_gonderme_kapaliyken_gonderilmez(self):
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"
        with self.assertRaises(whatsapp.GondermeReddedildi) as kutu:
            whatsapp.gonder("905550000000", "Merhaba, nasil yardimci olabilirim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertIn("KAPALI", str(kutu.exception))

    def test_gecersiz_telefon_gonderilmez(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("123", "Merhaba",
                            onay_kaynagi=whatsapp.ONAY_INSAN)


class MevzuatKapisiINSAN_ONAYIYLA_DA_ASILMAZ(unittest.TestCase):
    """🔴 Sahip yanlislikla onaylasa bile iddia iceren metin gitmemeli."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = Path(self.gecici.name) / "g.jsonl"
        os.environ["JARVIS_WHATSAPP_GONDER"] = "1"  # kapi ACIK olsa bile

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"
        self.gecici.cleanup()

    def test_blocked_metin_insan_onayiyla_da_gitmez(self):
        iddia = "Bu krem egzamayı tedavi eder ve hastalığı geçirir."
        bulgular = whatsapp.denetle(iddia)
        if not bulgular:
            self.skipTest("mevzuat motoru bu ifadeyi BLOCKED saymiyor")
        with self.assertRaises(whatsapp.GondermeReddedildi) as kutu:
            whatsapp.gonder("905550000000", iddia,
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertIn("mevzuat", str(kutu.exception))


class KuruKosuAGA_CIKMAZ(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "g.jsonl"
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        self.gecici.cleanup()

    def test_kuru_kosu_gonderme_kapaliyken_de_calisir(self):
        sonuc = whatsapp.gonder("905550000000", "Merhaba, size nasil yardimci olabilirim",
                                onay_kaynagi=whatsapp.ONAY_INSAN, kuru=True)
        self.assertFalse(sonuc["gonderildi"])
        self.assertTrue(sonuc["kuru"])

    def test_kuru_kosu_da_mevzuattan_gecer(self):
        iddia = "Bu krem egzamayı tedavi eder ve hastalığı geçirir."
        if not whatsapp.denetle(iddia):
            self.skipTest("mevzuat motoru bu ifadeyi BLOCKED saymiyor")
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", iddia,
                            onay_kaynagi=whatsapp.ONAY_INSAN, kuru=True)


class DefterREDDEDILENI_DE_YAZAR(unittest.TestCase):
    """"Hic denenmedi" ile "engellendi" ayni gorunmemeli."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "g.jsonl"
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        self.gecici.cleanup()

    def test_reddedilen_deneme_deftere_yazilir(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", "Merhaba efendim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertTrue(self.defter.exists(), "reddedilen deneme kaydedilmemis")
        satir = self.defter.read_text(encoding="utf-8").strip()
        self.assertIn("REDDEDILDI", satir)

    def test_defterde_TAM_telefon_YOK(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905551234567", "Merhaba efendim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        satir = self.defter.read_text(encoding="utf-8")
        self.assertNotIn("905551234567", satir, "deftere tam numara yazilmis")
        self.assertIn("4567", satir, "son dort hane de yok, iz surulemez")


class VarsayilanKAPALI(unittest.TestCase):
    def test_anahtar_yoksa_kapali(self):
        eski = os.environ.pop("JARVIS_WHATSAPP_GONDER", None)
        try:
            self.assertFalse(whatsapp.gonderme_acik())
        finally:
            if eski is not None:
                os.environ["JARVIS_WHATSAPP_GONDER"] = eski


if __name__ == "__main__":
    unittest.main()
