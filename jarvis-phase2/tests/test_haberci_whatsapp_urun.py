# -*- coding: utf-8 -*-
"""Siparis haberinde WhatsApp'a yalniz urun kodu gider (mevzuat kapisi).

🔴 BU TESTLER AĞA ÇIKMAZ.
"""
import unittest
from unittest.mock import patch

from jarvis import haberci
from jarvis import whatsapp

TRENDYOL = "SUNACNEA SPF 30+ Hassas ve Akne Eğilimli"


class WhatsappUrunTest(unittest.TestCase):
    def test_kod_kalir(self):
        self.assertEqual(haberci.whatsapp_urun(TRENDYOL), "SUNACNEA")

    def test_coklu_ve_fazlasi(self):
        ozet = TRENDYOL + ", DERMAVASC Onarıcı Bakım Kremi, MINISOOTH (+2)"
        self.assertEqual(haberci.whatsapp_urun(ozet),
                         "SUNACNEA, DERMAVASC, MINISOOTH (+2)")

    def test_bos(self):
        self.assertEqual(haberci.whatsapp_urun(""), "-")

    def test_cok_kelimeli_kodlar(self):
        ornekler = {
            "HAIR NOURISHER (Saç Bakım Yağı)": "HAIR NOURISHER",
            "BABY RESCUE (Anlık Yatıştırıcı)": "BABY RESCUE",
            "CAL JAW (Gece Çene Bakım RollOnu)": "CAL JAW",
            "VIREON FOR MEN · Erkek Bakım Kremi": "VIREON FOR MEN",
            "KINESIS + (Sporcu Bakım Kremi)": "KINESIS +",
            "FEMISIA for WOMEN (Kadınlara Özel": "FEMISIA",
            "Dermanova - Liftelle": "Dermanova",
            "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi": "HYDRAVIE",
        }
        for ad, kod in ornekler.items():
            self.assertEqual(haberci.whatsapp_urun(ad), kod, ad)

    def test_once_tam_ad_denenir(self):
        with patch.object(whatsapp, "sablon_gonder", return_value={"wamid": "w1"}) as g:
            haberci.whatsapp_gonder(["wix", "1", "10", "-", "L’CARLIÉ Dry Bag"])
        self.assertEqual(g.call_count, 1)
        self.assertEqual(g.call_args[0][2][-1], "L’CARLIÉ Dry Bag")

    def test_mevzuata_takilirsa_kodla_tekrar(self):
        with patch.object(whatsapp, "sablon_gonder", side_effect=[
                whatsapp.GondermeReddedildi("mevzuat kapisi: 4 bulgu"), {"wamid": "w2"}]) as g:
            self.assertEqual(haberci.whatsapp_gonder(["trendyol", "1", "10", "-", TRENDYOL]), "w2")
        self.assertEqual(g.call_args[0][2][-1], "SUNACNEA")

    def test_baska_ret_tekrar_denenmez(self):
        with patch.object(whatsapp, "sablon_gonder",
                          side_effect=whatsapp.GondermeReddedildi("Meta HTTP 400")) as g:
            with self.assertRaises(whatsapp.GondermeReddedildi):
                haberci.whatsapp_gonder(["wix", "1", "10", "-", "X"])
        self.assertEqual(g.call_count, 1)

    def test_11_11_siparisi_kapidan_gecer(self):
        # Ayni degerler 11.11.2026'da "mevzuat kapisi: 4 bulgu" ile reddedildi.
        eski = " | ".join(["trendyol", "11817125853", "2560.00", "-", TRENDYOL])
        self.assertTrue(whatsapp.denetle(eski),
                        "desen sinamasi: tam baslik bulgu uretmeli")
        yeni = " | ".join(["trendyol", "11817125853", "2560.00", "-",
                           haberci.whatsapp_urun(TRENDYOL)])
        self.assertEqual(whatsapp.denetle(yeni), [])


if __name__ == "__main__":
    unittest.main()
