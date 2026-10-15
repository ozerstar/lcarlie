# -*- coding: utf-8 -*-
"""WhatsApp reklam referansı testleri.

🔴 BU TESTLER BİR ÖLÇÜMDEN DOĞDU. `olaylari_ayristir` WhatsApp dalında
`ad_id` alanına sabit `None` yazıyordu. Sonuç sessizdi: 535 konuşmanın
0'ında ürün çözülmüş değildi, Jarvis her fiyat sorusunda "hangi ürün?"
diye sormak zorunda kalıyordu.

🔴 ALAN ADLARI MESSENGER'DAN FARKLI. Messenger `ad_id`/`source`,
WhatsApp `source_id`/`source_type` diyor. Messenger'ın adlarını aramak
hata vermez, sessizce boş döner -- bu yüzden ikisi ayrı test ediliyor.
"""
import unittest

import meta_webhook as MW


def _yuk(mesaj: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W1", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": "PN1"},
            "messages": [mesaj],
        }}]}],
    }


BASIT = {"from": "905550000000", "id": "wamid.1", "timestamp": "1760000000",
         "type": "text", "text": {"body": "Fiyati nedir"}}


class ReklamReferansiTASINIR(unittest.TestCase):
    def test_source_id_ad_id_olur(self):
        mesaj = dict(BASIT, referral={
            "source_id": "120254057843990045",
            "source_type": "ad",
            "headline": "HYDRAVIE Nemlendirici",
            "source_url": "https://fb.me/abc",
            "ctwa_clid": "CLID123",
        })
        olay = MW.olaylari_ayristir(_yuk(mesaj))[0]
        self.assertEqual(olay["ad_id"], "120254057843990045")
        self.assertEqual(olay["referral_kaynak"], "ad")
        self.assertEqual(olay["referral_ref"], "HYDRAVIE Nemlendirici")

    def test_ctwa_clid_ve_url_ek_icinde_saklanir(self):
        mesaj = dict(BASIT, referral={
            "source_id": "A1", "ctwa_clid": "CLID123",
            "source_url": "https://fb.me/abc"})
        ek = MW.olaylari_ayristir(_yuk(mesaj))[0]["ek"]
        self.assertEqual(ek["ctwa_clid"], "CLID123")
        self.assertEqual(ek["referral_url"], "https://fb.me/abc")

    def test_MESSENGER_alan_adlari_ad_id_URETMEZ(self):
        """WhatsApp yükünde Messenger'ın alan adları gelirse ürün
        UYDURULMAMALI: yanlış ürünün fiyatını söylemek, fiyat
        söylememekten pahalıdır."""
        mesaj = dict(BASIT, referral={"ad_id": "YANLIS", "source": "ad"})
        olay = MW.olaylari_ayristir(_yuk(mesaj))[0]
        self.assertIsNone(olay["ad_id"])


class ReferansYoksaUYDURULMAZ(unittest.TestCase):
    def test_referral_yoksa_ad_id_None(self):
        olay = MW.olaylari_ayristir(_yuk(BASIT))[0]
        self.assertIsNone(olay["ad_id"])
        self.assertIsNone(olay["referral_ref"])
        self.assertIsNone(olay["referral_kaynak"])

    def test_bos_referral_ad_id_None(self):
        olay = MW.olaylari_ayristir(_yuk(dict(BASIT, referral={})))[0]
        self.assertIsNone(olay["ad_id"])

    def test_bos_source_id_None_olur(self):
        # Bos dize ad_id sayilmamali; aksi halde eslesmeyen bir anahtar
        # urun aramasina girer ve sonuc "urun bulunamadi" olur.
        olay = MW.olaylari_ayristir(_yuk(dict(BASIT, referral={"source_id": ""})))[0]
        self.assertIsNone(olay["ad_id"])

    def test_referansiz_mesajda_ek_hala_tur_tasir(self):
        ek = MW.olaylari_ayristir(_yuk(BASIT))[0]["ek"]
        self.assertEqual(ek["type"], "text")
        self.assertNotIn("ctwa_clid", ek)


if __name__ == "__main__":
    unittest.main()
