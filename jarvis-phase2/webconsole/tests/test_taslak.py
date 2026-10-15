# -*- coding: utf-8 -*-
"""Jarvis taslağı: devir kapısı MODELDEN ÖNCE işler.

🔴 BU TESTİN ASIL İŞİ: devredilmesi gereken bir konuşmada modelin HİÇ
çağrılmadığını kanıtlamak. Çağrılsaydı iki zarar birden olurdu -- uygunsuz
bir taslak üretilir ve her devredilen mesaj için jeton parası yanardı.
"""
import sys
import unittest
from pathlib import Path

# Bu dosya webconsole/tests/ icinde; proje koku UC seviye yukarida.
KOK = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import gelen_kutusu as GK  # noqa: E402
from jarvis import satis_dialog  # noqa: E402


class SahteSorgu:
    """`_calistir` yerine gecer: son gelen mesaji ve urun kayitlarini verir."""

    def __init__(self, sinif, urun=None, mevzuat=None, metin="Fiyati nedir"):
        self.sinif, self.urun, self.mevzuat = sinif, urun, mevzuat
        self.metin = metin

    def __call__(self, sql):
        if "mart.urun_karti" in sql:
            return []
        return [{"metin": self.metin, "sinif": self.sinif,
                 "mevzuat": self.mevzuat, "urun": self.urun}]


class ModelCagrisiSAYACI:
    def __init__(self):
        self.cagri = 0

    def __call__(self, *a, **kw):
        self.cagri += 1
        return satis_dialog.Cevap(metin="sahte", soru_tipi="FIYAT", urun=None,
                                  yaklasim="", gonderilebilir=True)


class DevirKapisiMODELDEN_ONCE(unittest.TestCase):
    def setUp(self):
        self.eski_calistir = GK._calistir
        self.eski_uret = satis_dialog.cevap_uret
        self.sayac = ModelCagrisiSAYACI()
        satis_dialog.cevap_uret = self.sayac

    def tearDown(self):
        GK._calistir = self.eski_calistir
        satis_dialog.cevap_uret = self.eski_uret

    def test_saglik_mesajinda_model_CAGRILMAZ(self):
        GK._calistir = SahteSorgu("SAGLIK")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 0, "devredilen konusmada model cagrilmis")

    def test_siparis_mesajinda_model_CAGRILMAZ(self):
        GK._calistir = SahteSorgu("SIPARIS")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 0)

    def test_iddia_sorusunda_model_CAGRILMAZ(self):
        GK._calistir = SahteSorgu("IDDIA_SORUSU")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 0)

    def test_mevzuat_bloke_mesajinda_model_CAGRILMAZ(self):
        GK._calistir = SahteSorgu("FIYAT", mevzuat="BLOCKED")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 0)

    def test_tanimsiz_sinifta_model_CAGRILMAZ(self):
        # 🔴 sinif bossa taslak() mesaji ANINDA siniflandirir -- dogru
        # davranis, cunku siniflandirici 5 dakikada bir kosuyor ve yeni
        # gelen mesaj henuz islenmemis olabilir. Bu yuzden metin de
        # taninmayan bir sey olmali; ilk halinde "Fiyati nedir" yazdigim
        # icin test FIYAT bekliyordu ve kendi beklentim yanlisti.
        GK._calistir = SahteSorgu(None, metin="Ne bu simdi")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 0)

    def test_fiyat_sorusunda_model_CAGRILIR(self):
        GK._calistir = SahteSorgu("FIYAT")
        sonuc = GK.taslak(1)
        self.assertFalse(sonuc["devredilmeli"])
        self.assertEqual(self.sayac.cagri, 1)
        self.assertTrue(sonuc["urun_soruluyor"],
                        "urun bilinmiyorken once urun sorulmali")


class TaslakGONDERMEZ(unittest.TestCase):
    """🔴 taslak() disariya hicbir yol acmamali."""

    def test_kaynakta_gonderme_cagrisi_YOK(self):
        kaynak = (KOK / "webconsole" / "gelen_kutusu.py").read_text(encoding="utf-8")
        bas = kaynak.index("def taslak(")
        govde = kaynak[bas:]
        self.assertNotIn("whatsapp.gonder", govde,
                         "taslak() gonderme cagiriyor")
        self.assertNotIn("cevap_gonder", govde)


if __name__ == "__main__":
    unittest.main()
