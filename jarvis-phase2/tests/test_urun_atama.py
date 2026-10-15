# -*- coding: utf-8 -*-
"""Konuşmadan ürün atamasının testleri.

🔴 BU KAPININ YANLIŞ AÇILMASI PAHALIDIR. Ürün yanlış atanırsa Jarvis
BAŞKA bir ürünün fiyatını güvenle söyler -- ve kaynağı veritabanı olduğu
için cevap son derece ikna edici görünür.
"""
import unittest

from jarvis import urun_atama

KATALOG = [
    "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi",
    "BABYSOFT (Bebek Vücut Losyonu)",
    "DERMANOVA (Yenileyici Krem)",
    "VIREON FOR MEN · Erkek Bakım Kremi",
]
ANAHTAR = urun_atama.anahtarlar(KATALOG)


class AnahtarAYIRT_EDICI_KISIMDAN(unittest.TestCase):
    def test_marka_kismi_alinir(self):
        self.assertIn("hydravie", ANAHTAR)
        self.assertIn("babysoft", ANAHTAR)
        self.assertIn("dermanova", ANAHTAR)

    def test_tarif_kismi_anahtar_OLMAZ(self):
        # "yuz kremi" birden cok uruntde gecer; anahtar olsaydi yanlis baglardi.
        self.assertNotIn("yogun nemlendirici yuz kremi", ANAHTAR)

    def test_kisa_ad_anahtar_olmaz(self):
        self.assertEqual(urun_atama.anahtarlar(["AB", "X"]), {})


class TekEslesmeKABUL(unittest.TestCase):
    def test_duz_ad(self):
        self.assertEqual(urun_atama.metinde_urun("HYDRAVIE istiyorum", ANAHTAR),
                         "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi")

    def test_kucuk_harf_ve_aksansiz(self):
        self.assertEqual(urun_atama.metinde_urun("hydravie fiyati", ANAHTAR),
                         "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi")

    def test_cumle_icinde(self):
        self.assertEqual(
            urun_atama.metinde_urun("Merhaba, babysoft kac para acaba?", ANAHTAR),
            "BABYSOFT (Bebek Vücut Losyonu)")


class BELIRSIZ_OLAN_ATANMAZ(unittest.TestCase):
    def test_iki_urun_gecerse_None(self):
        self.assertIsNone(urun_atama.metinde_urun(
            "HYDRAVIE mi DERMANOVA mi daha iyi", ANAHTAR))

    def test_hic_gecmezse_None(self):
        self.assertIsNone(urun_atama.metinde_urun("Fiyati nedir", ANAHTAR))

    def test_bos_metin_None(self):
        for m in ("", "   ", None):
            with self.subTest(m=m):
                self.assertIsNone(urun_atama.metinde_urun(m, ANAHTAR))


class YalnizMUSTERI_MESAJI(unittest.TestCase):
    """Kendi cevabimizda urun adi gecmesi, musterinin onu sordugu anlamina
    GELMEZ -- Jarvis "hangi urun?" diye sorarken ornek vermis olabilir."""

    def test_giden_mesajdaki_ad_sayilmaz(self):
        mesajlar = [
            {"yon": "giden", "metin": "HYDRAVIE mi arıyorsunuz?"},
            {"yon": "gelen", "metin": "Fiyati nedir"},
        ]
        self.assertIsNone(urun_atama.konusmada_urun(mesajlar, ANAHTAR))

    def test_gelen_mesajdaki_ad_sayilir(self):
        mesajlar = [
            {"yon": "giden", "metin": "Hangi ürünümüzü soruyorsunuz?"},
            {"yon": "gelen", "metin": "babysoft"},
        ]
        self.assertEqual(urun_atama.konusmada_urun(mesajlar, ANAHTAR),
                         "BABYSOFT (Bebek Vücut Losyonu)")

    def test_ILK_atama_kalir(self):
        mesajlar = [
            {"yon": "gelen", "metin": "hydravie fiyati"},
            {"yon": "gelen", "metin": "babysoft da var mi"},
        ]
        self.assertEqual(urun_atama.konusmada_urun(mesajlar, ANAHTAR),
                         "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi")

    def test_bos_konusma_None(self):
        self.assertIsNone(urun_atama.konusmada_urun([], ANAHTAR))


if __name__ == "__main__":
    unittest.main()
