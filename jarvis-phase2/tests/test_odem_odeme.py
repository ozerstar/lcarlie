# -*- coding: utf-8 -*-
"""Kısa terim / uzun kelime çakışması: "ödem" (hastalık) vs "ödeme" (para).

🔴 BU TEST BİR ÜRETİM KUSURUNDAN DOĞDU — ölçüldü 15.10.2026.
Kısa terimlerde sağ tarafta kelime sınırı aranmıyor (Türkçe ek alsın diye,
doğru karar). Ama "ödem" + "e" = "ödeme": PARA kelimesi hastalık adı
sayılıyordu ve mevzuat kapısı WhatsApp gönderimini tuttuğu için
"Kapıda ödeme yapabilirsiniz" cümlesi müşteriye GİDEMİYORDU. İşletme
kapıda ödemeyle satış yapıyor; kusur tam kritik yoldaydı.

Test İKİ YÖNÜ de kilitler: yanlış alarm dönmemeli, ama gerçek iddia da
kaçmamalı. Tek yönü test etmek, kapıyı sessizce gevşetmenin yoludur.
"""
import unittest

from jarvis import compliance


def bloke(metin: str) -> bool:
    return bool(compliance.review(metin).blocked)


class OdemeENGELLENMEZ(unittest.TestCase):
    def test_kapida_odeme(self):
        self.assertFalse(bloke("Kapıda ödeme yapabilirsiniz."))

    def test_guvenli_odeme(self):
        self.assertFalse(bloke("Güvenli ödeme seçenekleri mevcut."))

    def test_odeme_cekimleri(self):
        for m in ("Ödemenizi kredi kartıyla yapabilirsiniz.",
                  "Ödeme linki gönderiyorum.",
                  "Ödemeyi havale ile yapabilirsiniz.",
                  "Ödemesi kapıda alınır.",
                  "Tek çekim ödemeli."):
            with self.subTest(m=m):
                self.assertFalse(bloke(m), m)

    def test_aksansiz_yazim_da_gecer(self):
        self.assertFalse(bloke("Kapida odeme yapabilirsiniz."))
        self.assertFalse(bloke("odemenizi yapabilirsiniz"))


class OdemHALA_YAKALANIR(unittest.TestCase):
    def test_duz_iddia(self):
        for m in ("Ödem giderir.", "Ödem ve şişlik için.",
                  "Bu krem ödemleri yok eder."):
            with self.subTest(m=m):
                self.assertTrue(bloke(m), m)

    def test_ekli_haller(self):
        self.assertTrue(bloke("Bacaklardaki ödemi azaltır."))
        self.assertTrue(bloke("Ödemde rahatlama sağlar."))

    def test_aksansiz_yazim(self):
        self.assertTrue(bloke("odem sorununa birebir"))


class AYNI_CUMLEDE_IKISI(unittest.TestCase):
    """İstisna kelimenin varlığı, aynı metindeki GERÇEK ihlali gizlememeli."""

    def test_ikisi_birden_varsa_yakalanir(self):
        self.assertTrue(bloke(
            "Kapıda ödeme yapabilirsiniz, ayrıca ödem giderir."))

    def test_sira_degisse_de_yakalanir(self):
        self.assertTrue(bloke(
            "Ödem giderir. Ayrıca kapıda ödeme yapabilirsiniz."))


class DIGER_TERIMLER_BOZULMADI(unittest.TestCase):
    def test_hastalik_adlari(self):
        for m in ("Egzamayı tedavi eder.", "Selülit giderir.",
                  "Akne karşıtı etki.", "Mantar sorununu çözer."):
            with self.subTest(m=m):
                self.assertTrue(bloke(m), m)

    def test_yapisal_degisim(self):
        self.assertTrue(bloke("Kolajen üretimini artırır."))


if __name__ == "__main__":
    unittest.main()
