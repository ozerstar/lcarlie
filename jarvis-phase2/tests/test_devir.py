# -*- coding: utf-8 -*-
"""Devir kapısının testleri.

Bu testler sahibin 15.10.2026'da seçtiği DÖRT kuralı kilitler. Kural
değişirse test kırılır ve bu DOĞRUDUR: devir kuralı sessizce gevşerse
müşteri şikâyeti Jarvis'e cevaplatılmış olur.
"""
import unittest

from jarvis import devir


class SahibinSectigiDortKural(unittest.TestCase):
    def test_saglik_her_zaman_devredilir(self):
        for sinif in ("SAGLIK", "BELIRTI_ANLATIMI", "DURDURMA", "SIKAYET"):
            with self.subTest(sinif=sinif):
                gerek, sebep = devir.devir_gerekir(sinif, urun_bilindi=True)
                self.assertTrue(gerek)
                self.assertEqual(sebep, devir.SAGLIK_SIKAYET)

    def test_siparis_odeme_iade_devredilir(self):
        for sinif in ("SIPARIS", "IADE", "ODEME", "KARGO_SORUN"):
            with self.subTest(sinif=sinif):
                gerek, sebep = devir.devir_gerekir(sinif, urun_bilindi=True)
                self.assertTrue(gerek)
                self.assertEqual(sebep, devir.ISLEM)

    def test_urun_bilinmiyorsa_jarvis_URUNU_SORAR(self):
        """15.10.2026 sahip karariyla DEGISTI.

        Onceki kural: urun belirsizse devret. Olculdu -- 535 konusmanin
        0'inda urun cozulmus degil, trafigin %69'u fiyat/icerik, yani kural
        gercek yonlendirmeyi %3,3 Jarvis / %96,7 sahip yapiyordu. Sahip izin
        verdi: Jarvis fiyat SOYLEMEZ, hangi urun oldugunu SORAR.
        """
        gerek, sebep = devir.devir_gerekir("FIYAT", urun_bilindi=False)
        self.assertFalse(gerek, "urun sorusu artik devir sebebi degil")
        self.assertIsNone(sebep)
        self.assertTrue(devir.urun_sorulmali("FIYAT", urun_bilindi=False),
                        "cagiran once urunu sormali")

    def test_urun_biliniyorsa_sorulmaz(self):
        self.assertFalse(devir.urun_sorulmali("FIYAT", urun_bilindi=True))

    def test_urun_gerektirmeyen_sinifta_sorulmaz(self):
        self.assertFalse(devir.urun_sorulmali("SELAMLAMA", urun_bilindi=False))

    def test_izin_kapatilirsa_eski_davranis_geri_gelir(self):
        eski = devir.URUN_SORULABILIR
        devir.URUN_SORULABILIR = False
        try:
            gerek, sebep = devir.devir_gerekir("FIYAT", urun_bilindi=False)
            self.assertTrue(gerek)
            self.assertEqual(sebep, devir.URUN_BELIRSIZ)
        finally:
            devir.URUN_SORULABILIR = eski

    def test_mevzuat_bloke_her_seyin_onunde(self):
        # Sinif Jarvis'in cevaplayabilecegi bir sinif olsa BILE mevzuat kazanir.
        gerek, sebep = devir.devir_gerekir("FIYAT", urun_bilindi=True,
                                           mevzuat="BLOCKED")
        self.assertTrue(gerek)
        self.assertEqual(sebep, devir.MEVZUAT)

    def test_saglik_fiyattan_once_gelir(self):
        # Bir mesaj hem saglik hem fiyat olabilir; saglik kazanmali.
        gerek, sebep = devir.devir_gerekir("SAGLIK", urun_bilindi=True)
        self.assertEqual(sebep, devir.SAGLIK_SIKAYET)


class JarvisNeyiCevaplayabilir(unittest.TestCase):
    def test_urun_biliniyorsa_fiyat_jarviste_kalir(self):
        gerek, sebep = devir.devir_gerekir("FIYAT", urun_bilindi=True)
        self.assertFalse(gerek)
        self.assertIsNone(sebep)

    def test_selamlama_urun_gerektirmez(self):
        gerek, _ = devir.devir_gerekir("SELAMLAMA", urun_bilindi=False)
        self.assertFalse(gerek)

    def test_tesekkur_urun_gerektirmez(self):
        gerek, _ = devir.devir_gerekir("TESEKKUR", urun_bilindi=False)
        self.assertFalse(gerek)


class BilinmeyenSinifDEVREDILIR(unittest.TestCase):
    """783 mesajin sinifi bos. Bosu tahmin etmek yanlis urunun fiyatini
    soylemenin yoludur."""

    def test_bos_sinif_devredilir(self):
        for deger in (None, "", "   "):
            with self.subTest(deger=deger):
                gerek, sebep = devir.devir_gerekir(deger, urun_bilindi=True)
                self.assertTrue(gerek)
                self.assertEqual(sebep, devir.SINIF_YOK)

    def test_anlasilmadi_devredilir(self):
        gerek, sebep = devir.devir_gerekir("ANLASILMADI", urun_bilindi=True)
        self.assertTrue(gerek)
        self.assertEqual(sebep, devir.SINIF_YOK)

    def test_hic_gorulmemis_sinif_devredilir(self):
        gerek, sebep = devir.devir_gerekir("YEPYENI_SINIF", urun_bilindi=True)
        self.assertTrue(gerek)
        self.assertEqual(sebep, devir.SINIF_YOK)

    def test_beyaz_liste_kucuk_harfe_duyarsiz(self):
        gerek, _ = devir.devir_gerekir("fiyat", urun_bilindi=True)
        self.assertFalse(gerek)


class SebepMetni(unittest.TestCase):
    def test_her_sebebin_turkce_karsiligi_var(self):
        for sebep in (devir.SAGLIK_SIKAYET, devir.ISLEM, devir.URUN_BELIRSIZ,
                      devir.MEVZUAT, devir.SINIF_YOK):
            with self.subTest(sebep=sebep):
                self.assertTrue(devir.sebep_aciklamasi(sebep))

    def test_sebep_yoksa_bos_doner(self):
        self.assertEqual(devir.sebep_aciklamasi(None), "")


if __name__ == "__main__":
    unittest.main()
