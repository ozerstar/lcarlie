# -*- coding: utf-8 -*-
"""Siparis haberinde WhatsApp'a yalniz urun kodu gider (mevzuat kapisi).

🔴 BU TESTLER AĞA ÇIKMAZ.
"""
import unittest

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
