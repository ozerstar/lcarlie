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


class YAZIM_HATASI_TOLERANSI(unittest.TestCase):
    """🔴 Sahip "kinesis" yerine "kimesis" yazdi ve urun atanmadi (15.10.2026).
    Musteriler de duzgun yazmaz. Ama bulanik esleme yanlis urunu secerse
    Jarvis BASKA bir urunun fiyatini guvenle soyler -- en pahali hata.

    Katalogdaki 36 anahtarin birbirine uzakligi olculdu: esik 1'de carpisma
    YOK, esik 2'de babysoft/babysol ve calmaros/calmoris karisiyor."""

    def test_bir_harf_hatasi_duzelir(self):
        for yanlis in ("hydravve", "hydrarie", "hydrabie"):
            with self.subTest(yanlis=yanlis):
                self.assertEqual(
                    urun_atama.metinde_urun("%s fiyati" % yanlis, ANAHTAR),
                    "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi")

    def test_tam_yazim_hala_calisir(self):
        self.assertEqual(urun_atama.metinde_urun("hydravie fiyati", ANAHTAR),
                         "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi")

    def test_IKI_HARF_hatasi_atanmaz(self):
        # Esik 1: iki harf sapma artik "hangi urun" belirsizligidir.
        self.assertIsNone(urun_atama.metinde_urun("hydrxxie fiyati", ANAHTAR))

    def test_KISA_kelimede_bulanik_KAPALI(self):
        # 6 harften kisa kelimede bir harf fark cok seye benzer.
        self.assertIsNone(urun_atama.metinde_urun("babi fiyati", ANAHTAR))

    def test_iki_urune_esit_uzaklik_atanmaz(self):
        sozluk = urun_atama.anahtarlar(["ALFABET (A)", "ALFABEX (B)"])
        self.assertIsNone(urun_atama.metinde_urun("alfabez fiyati", sozluk))


class ONEK_CAKISMASI(unittest.TestCase):
    """🔴 "BABY RESCUE" ilk kelimesi "baby"; BABYDENT/BABYSOFT/BABYSOL'un
    hepsinin on eki. Boyle birakilinca "babysoft fiyati" IKI anahtarla
    eslesip belirsiz sayiliyor ve CAKISMAYAN urun de kayboluyordu."""

    def test_onek_olan_anahtar_uzatilir(self):
        sozluk = urun_atama.anahtarlar([
            "BABY RESCUE (Anlık Yatıştırıcı)", "BABYSOFT (Bebek Vücut Losyonu)",
            "BABYSOL (Güneş Kremi)"])
        self.assertNotIn("baby", sozluk)
        self.assertIn("baby rescue", sozluk)
        self.assertIn("babysoft", sozluk)

    def test_cakismayan_urun_kaybolmaz(self):
        sozluk = urun_atama.anahtarlar([
            "BABY RESCUE (Anlık Yatıştırıcı)", "BABYSOFT (Bebek Vücut Losyonu)"])
        self.assertEqual(urun_atama.metinde_urun("babysoft fiyati", sozluk),
                         "BABYSOFT (Bebek Vücut Losyonu)")


class AYIRAC_TEMIZLIGI(unittest.TestCase):
    def test_nokta_ayiraci(self):
        sozluk = urun_atama.anahtarlar(["VIREON FOR MEN · Erkek Bakım Kremi"])
        self.assertIn("vireon", sozluk)

    def test_arti_isareti_anahtara_girmez(self):
        sozluk = urun_atama.anahtarlar(["KINESIS + (Sporcu Bakım Kremi)"])
        self.assertIn("kinesis", sozluk)
        self.assertEqual(urun_atama.metinde_urun("kimesis fiyati", sozluk),
                         "KINESIS + (Sporcu Bakım Kremi)")


if __name__ == "__main__":
    unittest.main()
