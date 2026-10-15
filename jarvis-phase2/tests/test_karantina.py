# -*- coding: utf-8 -*-
"""Kuyruk yükleyicisinin karantina kapısı.

🔴 BU KAPI OLMADIĞI İÇİN 15.10.2026'da uçtan uca test YAPILAMADI: sentetik
bir mesaj gerçek müşteri mesajı olarak `lcarlie.mesaj`'a yazılacaktı ve
yükleyici 60 saniyede bir koşuyordu. Kapı, veritabanına yazan TEK noktada
duruyor; kaynak ne olursa olsun test kaydı tabloya giremez.

🔴 EN ÖNEMLİ TEST: gövdeden gelen `is_test` iddiası DİNLENMEZ. Webhook
gövdesi istemci kontrolündedir; okunsaydı herkes kendi mesajını "test"
işaretleyip panelden gizleyebilirdi. Bu projede canlıda bir kez yaşandı.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "mky", KOK / "scripts" / "meta-kuyruk-yukle.py")
mky = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mky)


def olay(**ek):
    temel = {"kanal": "whatsapp", "gonderen_id": "905550000000",
             "alici_id": "PN1", "mesaj_id": "wamid.1", "metin": "merhaba",
             "yanki": False, "zaman_ms": 1760000000000, "ad_id": None}
    temel.update(ek)
    return temel


class TrafikSinifi(unittest.TestCase):
    def test_normal_mesaj_production(self):
        self.assertEqual(mky.trafik_sinifi(olay()), "production")

    def test_mesaj_id_onekli_test(self):
        self.assertEqual(mky.trafik_sinifi(olay(mesaj_id="test-wamid-1")), "test")

    def test_gonderen_onekli_test(self):
        self.assertEqual(mky.trafik_sinifi(olay(gonderen_id="test-905550000000")),
                         "test")

    def test_alici_onekli_test(self):
        self.assertEqual(mky.trafik_sinifi(olay(alici_id="test-PN1")), "test")

    def test_buyuk_harf_de_yakalanir(self):
        self.assertEqual(mky.trafik_sinifi(olay(mesaj_id="TEST-wamid-1")), "test")

    def test_ortada_gecen_test_kelimesi_SAYILMAZ(self):
        # "latest-..." veya "contest-..." test trafigi DEGILDIR.
        for mid in ("latest-wamid", "contest-1", "wamid.test-1"):
            with self.subTest(mid=mid):
                self.assertEqual(mky.trafik_sinifi(olay(mesaj_id=mid)),
                                 "production")


class GOVDEDEN_GELEN_IDDIA_DINLENMEZ(unittest.TestCase):
    """🔴 Istemci kendi mesajini 'test' ilan edemez."""

    def test_is_test_alani_okunmaz(self):
        self.assertEqual(mky.trafik_sinifi(olay(is_test=True)), "production")

    def test_traffic_class_alani_okunmaz(self):
        self.assertEqual(mky.trafik_sinifi(olay(traffic_class="test")),
                         "production")

    def test_ek_icindeki_iddia_okunmaz(self):
        self.assertEqual(
            mky.trafik_sinifi(olay(ek={"is_test": True, "traffic_class": "test"})),
            "production")


class KarantinayaYAZILIR_SILINMEZ(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.eski = mky.KARANTINA
        mky.KARANTINA = Path(self.gecici.name) / "karantina.jsonl"

    def tearDown(self):
        mky.KARANTINA = self.eski
        self.gecici.cleanup()

    def test_kayit_dosyaya_yazilir(self):
        mky.karantinaya_yaz(olay(mesaj_id="test-1"), "test- oneki")
        self.assertTrue(mky.KARANTINA.exists())
        k = json.loads(mky.KARANTINA.read_text(encoding="utf-8").strip())
        self.assertEqual(k["mesaj_id"], "test-1")
        self.assertEqual(k["_karantina_sebep"], "test- oneki")
        self.assertIn("_karantina_zaman", k)

    def test_icerik_kaybolmaz(self):
        mky.karantinaya_yaz(olay(mesaj_id="test-1", metin="onemli metin"), "x")
        k = json.loads(mky.KARANTINA.read_text(encoding="utf-8").strip())
        self.assertEqual(k["metin"], "onemli metin")


class YukleKAPIYI_ISLETIR(unittest.TestCase):
    """Kuru kosuda bile test kaydi mesaj sayilmamali."""

    def test_test_kaydi_mesaj_sayilmaz(self):
        sayac = mky.yukle([olay(mesaj_id="test-1")], kuru=True)
        self.assertEqual(sayac["karantina"], 1)
        self.assertEqual(sayac["mesaj"], 0)

    def test_normal_kayit_sayilir(self):
        sayac = mky.yukle([olay()], kuru=True)
        self.assertEqual(sayac["karantina"], 0)
        self.assertEqual(sayac["mesaj"], 1)

    def test_karisik_yuk_ayrilir(self):
        sayac = mky.yukle([olay(mesaj_id="test-1"), olay(mesaj_id="w2"),
                           olay(gonderen_id="test-x")], kuru=True)
        self.assertEqual(sayac["karantina"], 2)
        self.assertEqual(sayac["mesaj"], 1)


if __name__ == "__main__":
    unittest.main()
