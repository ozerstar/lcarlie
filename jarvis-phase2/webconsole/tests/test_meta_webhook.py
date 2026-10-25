"""Meta webhook: bu uc kimlik kapisinin ONUNDE duruyor, kendi kapisi saglam olmali.

Oturum acamayan bir cagrici icin auth atlandi. Karsiliginda iki kapi var:
GET'te dogrulama anahtari, POST'ta HMAC imzasi. Bu testler o iki kapinin
gercekten kapandigini olcer -- acik kalirsa isteyen herkes sahte musteri
mesaji enjekte eder ve sistem ona cevap uretir.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import meta_webhook as mw  # noqa: E402

GIZ = "test-gizi-123"


def _imzala(govde: bytes, giz: str = GIZ) -> str:
    return "sha256=" + hmac.new(giz.encode(), govde, hashlib.sha256).hexdigest()


class ImzaKapisi(unittest.TestCase):
    GOVDE = b'{"object":"page","entry":[]}'

    def test_dogru_imza_gecer(self):
        self.assertTrue(mw.imza_gecerli(self.GOVDE, _imzala(self.GOVDE), GIZ))

    def test_yanlis_imza_gecmez(self):
        self.assertFalse(mw.imza_gecerli(self.GOVDE, _imzala(self.GOVDE, "baska"), GIZ))

    def test_imzasiz_istek_gecmez(self):
        self.assertFalse(mw.imza_gecerli(self.GOVDE, "", GIZ))

    def test_giz_yoksa_HICBIR_imza_gecmez(self):
        # Giz olmadan dogrulama yapilamaz; "dogrulayamadim" = "kabul etme".
        self.assertFalse(mw.imza_gecerli(self.GOVDE, _imzala(self.GOVDE), ""))

    def test_sha256_oneki_zorunlu(self):
        ham = hmac.new(GIZ.encode(), self.GOVDE, hashlib.sha256).hexdigest()
        self.assertFalse(mw.imza_gecerli(self.GOVDE, ham, GIZ))

    def test_govde_degisirse_imza_dusar(self):
        imza = _imzala(self.GOVDE)
        self.assertFalse(mw.imza_gecerli(self.GOVDE + b" ", imza, GIZ))


class DogrulamaElSikismasi(unittest.TestCase):
    def test_dogru_anahtar_challenge_AYNEN_doner(self):
        kod, govde = mw.dogrulama_yaniti(
            {"hub.mode": ["subscribe"], "hub.verify_token": ["abc"],
             "hub.challenge": ["1234567890"]}, "abc")
        self.assertEqual(kod, 200)
        self.assertEqual(govde, "1234567890")

    def test_yanlis_anahtar_403(self):
        kod, _ = mw.dogrulama_yaniti(
            {"hub.mode": ["subscribe"], "hub.verify_token": ["yanlis"],
             "hub.challenge": ["x"]}, "abc")
        self.assertEqual(kod, 403)

    def test_anahtar_tanimsizsa_503(self):
        # Sessizce "dogrulandi" demek, yanlis anahtarla kurulan bir ucun
        # calisiyor gorunup hic olay almamasina yol acardi.
        kod, _ = mw.dogrulama_yaniti(
            {"hub.mode": ["subscribe"], "hub.verify_token": [""],
             "hub.challenge": ["x"]}, "")
        self.assertEqual(kod, 503)

    def test_yanlis_mod_400(self):
        kod, _ = mw.dogrulama_yaniti({"hub.mode": ["unsubscribe"]}, "abc")
        self.assertEqual(kod, 400)


class ReklamReferansiTASINIR(unittest.TestCase):
    """Urunun TEK guvenilir kaynagi. Dusurulurse musteriye hangi urun
    oldugu sorulmak zorunda kalinir."""

    YUK = {"object": "page", "entry": [{"id": "SAYFA1", "messaging": [
        {"sender": {"id": "PSID1"}, "recipient": {"id": "SAYFA1"},
         "timestamp": 1700000000000,
         "message": {"mid": "m1", "text": "fiyatı nedir"},
         "referral": {"ad_id": "120254653497530045", "ref": "vireon",
                      "source": "ADS"}}]}]}

    def test_ad_id_tasiniyor(self):
        [olay] = mw.olaylari_ayristir(self.YUK)
        self.assertEqual(olay["ad_id"], "120254653497530045")
        self.assertEqual(olay["metin"], "fiyatı nedir")
        self.assertEqual(olay["gonderen_id"], "PSID1")

    def test_postback_icindeki_referans_da_okunur(self):
        yuk = {"entry": [{"id": "S", "messaging": [
            {"sender": {"id": "P"}, "postback": {
                "referral": {"ad_id": "999", "source": "ADS"}}}]}]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertEqual(olay["ad_id"], "999")

    def test_referans_yoksa_UYDURULMAZ(self):
        yuk = {"entry": [{"id": "S", "messaging": [
            {"sender": {"id": "P"}, "message": {"mid": "m", "text": "merhaba"}}]}]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertIsNone(olay["ad_id"])

    def test_kendi_mesajimizin_yankisi_ISARETLENIR(self):
        # Isaretlenmezse kendi cevabimiza cevap uretiriz.
        yuk = {"entry": [{"id": "S", "messaging": [
            {"sender": {"id": "S"}, "message": {"mid": "m", "text": "x",
                                                "is_echo": True}}]}]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertTrue(olay["yanki"])

    def test_bos_yuk_cokmez(self):
        self.assertEqual(mw.olaylari_ayristir({}), [])


class WhatsAppMesajlari(unittest.TestCase):
    def test_sablon_hizli_yanit_dugmesi_kaybolmaz(self):
        yuk = {"object": "whatsapp_business_account", "entry": [{
            "changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "12345"},
                "messages": [{"from": "905551112233", "id": "wamid.button",
                              "timestamp": "1720000000", "type": "button",
                              "button": {"text": "Nakit onaylıyorum",
                                         "payload": "COD:99999:CASH"}}],
            }}],
        }]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertEqual(olay["metin"], "Nakit onaylıyorum")
        self.assertEqual(olay["ek"]["button_payload"], "COD:99999:CASH")

    def test_etkilesimli_dugme_metni_kaybolmaz(self):
        yuk = {"object": "whatsapp_business_account", "entry": [{
            "changes": [{"field": "messages", "value": {
                "messages": [{"from": "905551112233", "id": "wamid.interactive",
                              "timestamp": "1720000000", "type": "interactive",
                              "interactive": {"type": "button_reply", "button_reply": {
                                  "title": "Düzeltme / soru", "id": "COD:99999:HELP"}}}],
            }}],
        }]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertEqual(olay["metin"], "Düzeltme / soru")
        self.assertEqual(olay["ek"]["button_payload"], "COD:99999:HELP")

    def test_gelen_mesaj_ayri_kanala_gider(self):
        yuk = {"object": "whatsapp_business_account", "entry": [{
            "id": "2314052356072937", "changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "12345"},
                "messages": [{"from": "905551112233", "id": "wamid.test",
                              "timestamp": "1720000000", "type": "text",
                              "text": {"body": "Merhaba"}}],
                "statuses": [{"id": "baska"}],
            }}],
        }]}
        [olay] = mw.olaylari_ayristir(yuk)
        self.assertEqual(olay["kanal"], "whatsapp")
        self.assertEqual(olay["sayfa_id"], "12345")
        self.assertEqual(olay["gonderen_id"], "905551112233")
        self.assertEqual(olay["mesaj_id"], "wamid.test")
        self.assertEqual(olay["metin"], "Merhaba")
        self.assertEqual(olay["zaman_ms"], 1720000000000)

    def test_teslimat_durumu_mesaj_degildir(self):
        yuk = {"object": "whatsapp_business_account", "entry": [{
            "changes": [{"field": "messages", "value": {
                "statuses": [{"id": "wamid.test", "status": "delivered"}],
            }}],
        }]}
        self.assertEqual(mw.olaylari_ayristir(yuk), [])
        self.assertEqual(mw.teslimat_olaylari(yuk), [{
            "wamid": "wamid.test", "durum": "delivered", "zaman": "", "hata_kodu": "",
        }])

    def test_basarisiz_teslimatta_yalniz_hata_kodu_kaydedilir(self):
        yuk = {"object": "whatsapp_business_account", "entry": [{
            "changes": [{"field": "messages", "value": {"statuses": [{
                "id": "wamid.test", "status": "failed", "recipient_id": "905550000000",
                "errors": [{"code": 131026, "message": "özel hata metni"}],
            }]}}],
        }]}
        olay = mw.teslimat_olaylari(yuk)[0]
        self.assertEqual(olay["hata_kodu"], "131026")
        self.assertNotIn("recipient_id", olay)
        self.assertNotIn("özel hata metni", str(olay))


class KuyrukKAYIP_VERMEZ(unittest.TestCase):
    def test_olaylar_satir_satir_eklenir(self):
        with tempfile.TemporaryDirectory() as gecici:
            kuyruk = Path(gecici) / "alt" / "gelen.jsonl"
            self.assertEqual(mw.kuyruga_yaz([{"a": 1}, {"a": 2}], kuyruk), 2)
            self.assertEqual(mw.kuyruga_yaz([{"a": 3}], kuyruk), 1)
            satirlar = kuyruk.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(satirlar), 3)
            self.assertEqual(json.loads(satirlar[2])["a"], 3)

    def test_her_satirda_alinma_zamani_var(self):
        with tempfile.TemporaryDirectory() as gecici:
            kuyruk = Path(gecici) / "g.jsonl"
            mw.kuyruga_yaz([{"a": 1}], kuyruk)
            self.assertIn("alindi_at", json.loads(kuyruk.read_text(encoding="utf-8")))

    def test_bos_liste_dosya_olusturmaz(self):
        with tempfile.TemporaryDirectory() as gecici:
            kuyruk = Path(gecici) / "g.jsonl"
            self.assertEqual(mw.kuyruga_yaz([], kuyruk), 0)
            self.assertFalse(kuyruk.exists())


class AnahtarOkumaTuzagi(unittest.TestCase):
    def test_deger_icinde_esittir_bozmaz(self):
        # `cut -d= -f2` bu projede 721 karakterlik bir anahtari bir kez bozdu.
        with tempfile.TemporaryDirectory() as gecici:
            env = Path(gecici) / ".env"
            env.write_text("META_APP_SECRET=abc=def==\nBASKA=1\n", encoding="utf-8")
            eski = mw._ENV_DOSYASI
            try:
                mw._ENV_DOSYASI = str(env)
                self.assertEqual(mw._env_oku("META_APP_SECRET"), "abc=def==")
            finally:
                mw._ENV_DOSYASI = eski


if __name__ == "__main__":
    unittest.main()
