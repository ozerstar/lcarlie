import unittest

from jarvis.kapida_onay import (TeyitHatasi, ayrinti_metni, kapida_odeme_mi,
                               sablon_parametreleri, taslak, yaniti_tani)


def ornek():
    return {
        "siparis_no": 1234, "odeme_yontemi": "Çevrim Dışı Ödemeler",
        "odeme_durumu": "NOT_PAID",
        "teslimat_durumu": "NOT_FULFILLED", "para_birimi": "TRY",
        "toplam": "425.50", "ham": {
            "buyerInfo": {"phone": "05320000000"},
            "shippingInfo": {"shipmentDetails": {"address": {
                "phone": "+90 532 000 00 00", "fullName": "Örnek Alıcı",
                "addressLine1": "Örnek sokak 1",
                "city": "İstanbul"}}},
            "lineItems": [{"name": "Örnek ürün", "quantity": 2}],
        },
    }


class KapidaOnayTest(unittest.TestCase):
    def test_ayrinti_ve_kesin_onay(self):
        hazir = taslak(ornek(), whatsapp_izni=True)
        self.assertIn("Örnek ürün ×2", ayrinti_metni(hazir))
        self.assertIn("425.50 TL", ayrinti_metni(hazir))
        self.assertIn("Teslimat adresi: Örnek sokak 1, İstanbul", ayrinti_metni(hazir))
        self.assertIn("Telefon: +905320000000", ayrinti_metni(hazir))
        self.assertIn("ONAYLIYORUM NAKİT veya ONAYLIYORUM KART", ayrinti_metni(hazir))
        self.assertIn("nakit mi, kredi kartıyla mı", ayrinti_metni(hazir))
        self.assertEqual(len(sablon_parametreleri(hazir)), 6)
        self.assertEqual(yaniti_tani("onaylıyorum nakit 1234", "1234"), "ONAY_NAKIT")
        self.assertEqual(yaniti_tani("onaylıyorum kart 1234", "1234"), "ONAY_KART")
        self.assertEqual(yaniti_tani("onaylıyorum kredi kartı 1234", "1234"), "ONAY_KART")
        self.assertEqual(yaniti_tani("Nakit onaylıyorum", "1234", tek_bekleyen=True), "ONAY_NAKIT")
        self.assertEqual(yaniti_tani("Kartla onaylıyorum", "1234", tek_bekleyen=True), "ONAY_KART")
        self.assertEqual(yaniti_tani("Kartla onaylıyorum", "1234"), "SORU_VEYA_DUZELTME")
        self.assertEqual(yaniti_tani("onaylıyorum nakit", "1234", tek_bekleyen=True), "ONAY_NAKIT")
        self.assertEqual(yaniti_tani("onaylıyorum kart", "1234", tek_bekleyen=True), "ONAY_KART")
        self.assertEqual(yaniti_tani("onaylıyorum kart", "1234"), "SORU_VEYA_DUZELTME")
        self.assertEqual(yaniti_tani("onaylıyorum nakit 1235", "1234"), "SORU_VEYA_DUZELTME")
        self.assertEqual(yaniti_tani("onaylıyorum", "1234", tek_bekleyen=True), "ODEME_YONTEMI_SOR")
        self.assertEqual(yaniti_tani("onaylıyorum 1234", "1234"), "ODEME_YONTEMI_SOR")

    def test_belirsiz_odeme_veya_izin_reddedilir(self):
        kayit = ornek()
        kayit["odeme_yontemi"] = "PayTR"
        with self.assertRaises(TeyitHatasi):
            taslak(kayit, whatsapp_izni=True)
        with self.assertRaises(TeyitHatasi):
            taslak(ornek(), whatsapp_izni=False)
        self.assertTrue(kapida_odeme_mi({"odeme_yontemi": "Офлайн-оплата"}))

    def test_telefon_eslesmezse_reddedilir(self):
        kayit = ornek()
        kayit["ham"]["buyerInfo"]["phone"] = "05320000001"
        with self.assertRaises(TeyitHatasi):
            taslak(kayit, whatsapp_izni=True)

    def test_odeme_iptal_ve_para_birimi(self):
        for alan, deger in (("odeme_durumu", "PAID"), ("teslimat_durumu", "CANCELED"),
                            ("para_birimi", "USD"), ("toplam", "0")):
            kayit = ornek()
            kayit[alan] = deger
            with self.subTest(alan=alan), self.assertRaises(TeyitHatasi):
                taslak(kayit, whatsapp_izni=True)

    def test_soru_onay_sayilmaz(self):
        self.assertEqual(yaniti_tani("Tamam, kargo ne zaman gelir?", "1234"),
                         "SORU_VEYA_DUZELTME")
        self.assertEqual(yaniti_tani("bana ait değil", "1234"), "ITIRAZ")


if __name__ == "__main__":
    unittest.main()
