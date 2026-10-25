# -*- coding: utf-8 -*-
"""Jarvis taslağı: devir kapısı MODELDEN ÖNCE işler.

🔴 BU TESTİN ASIL İŞİ: devredilmesi gereken bir konuşmada modelin HİÇ
çağrılmadığını kanıtlamak. Çağrılsaydı iki zarar birden olurdu -- uygunsuz
bir taslak üretilir ve her devredilen mesaj için jeton parası yanardı.
"""
import sys
import unittest
from unittest.mock import patch
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


class YeniYonlendirmeTaslaklari(unittest.TestCase):
    def setUp(self):
        self.eski_calistir = GK._calistir

    def tearDown(self):
        GK._calistir = self.eski_calistir

    def test_kargo_durumu_yalniz_dogrulaninca_gonderilebilir(self):
        from jarvis import whatsapp_kargo
        GK._calistir = SahteSorgu("SIPARIS", metin="Kargom nerede?")
        with patch.object(GK, "telefon_bul", return_value="905551234567"), \
             patch.object(whatsapp_kargo, "durum_sor",
                          return_value=("Kargoya verildi.", False)):
            sonuc = GK.taslak(1)
        self.assertEqual(sonuc["sinif"], "KARGO_TAKIP")
        self.assertTrue(sonuc["gonderilebilir"])

    def test_kargo_eslesmezse_insana_devredilir(self):
        from jarvis import whatsapp_kargo
        GK._calistir = SahteSorgu("SIPARIS", metin="Kargom nerede?")
        with patch.object(GK, "telefon_bul", return_value="905551234567"), \
             patch.object(whatsapp_kargo, "durum_sor",
                          return_value=("Doğrulayamadım.", True)):
            sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertFalse(sonuc["gonderilebilir"])

    def test_urun_listesi_yalniz_yayindaki_urunlerden(self):
        def sorgu(sql):
            if "mart.urun_karti" in sql:
                return [{"urun_adi": "BABYSOFT", "wix_yayinda": True, "gorunur": True},
                        {"urun_adi": "GIZLI", "wix_yayinda": False, "gorunur": True}]
            return [{"metin": "hangi ürünler var", "sinif": "ANLASILMADI",
                     "mevzuat": None, "urun": None}]
        GK._calistir = sorgu
        sonuc = GK.taslak(1)
        self.assertEqual(sonuc["sinif"], "KATEGORI")
        self.assertTrue(sonuc["gonderilebilir"])
        self.assertIn("BABYSOFT", sonuc["metin"])
        self.assertNotIn("GIZLI", sonuc["metin"])

    def test_bos_katalog_otomatik_yanit_vermez(self):
        GK._calistir = SahteSorgu("ANLASILMADI", metin="hangi ürünler var")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertFalse(sonuc["gonderilebilir"])

    def test_kisa_selamlamaya_dogal_yanit_verir(self):
        GK._calistir = SahteSorgu("ANLASILMADI", metin="Nbr ben jarvis")
        sonuc = GK.taslak(1)
        self.assertEqual(sonuc["sinif"], "SELAMLAMA")
        self.assertFalse(sonuc["devredilmeli"])
        self.assertTrue(sonuc["gonderilebilir"])
        self.assertIn("nasıl yardımcı olabilirim", sonuc["metin"])

    def test_mevzuat_engelli_selamlama_gonderilmez(self):
        GK._calistir = SahteSorgu("SELAMLAMA", mevzuat="BLOCKED", metin="Nbr")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertFalse(sonuc["gonderilebilir"])

    def test_saglik_ve_sikayet_taslagi_devir_ister(self):
        for sinif, metin, aranan in (
            ("SAGLIK", "Alerjim oldu", "sağlık uzmanına"),
            ("SIKAYET", "Şikayetim var", "özür dileriz"),
            ("ANLASILMADI", "Ne bu şimdi", "biraz açabilir"),
        ):
            with self.subTest(sinif=sinif):
                GK._calistir = SahteSorgu(sinif, metin=metin)
                sonuc = GK.taslak(1)
                self.assertTrue(sonuc["devredilmeli"])
                self.assertIn(aranan, sonuc["metin"])
                self.assertFalse(sonuc["gonderilebilir"])

    def test_odeme_dogrulanmis_urun_sayfasina_gider(self):
        kayit = {"urun_id": "u1", "urun_adi": "BABYSOFT (Losyon)",
                 "slug": "babysoft", "wix_yayinda": True, "gorunur": True,
                 "wix_stok": 3, "wix_satis": 100, "wix_liste": 100,
                 "aciklama_duz": ""}
        def sorgu(sql):
            if "mart.urun_karti" in sql:
                return [kayit]
            return [{"metin": "BABYSOFT nasıl satın alabilirim?",
                     "sinif": "SIPARIS", "mevzuat": None, "urun": None}]
        GK._calistir = sorgu
        sonuc = GK.taslak(1)
        self.assertFalse(sonuc["devredilmeli"])
        self.assertIn("https://www.lcarlie.shop/product-page/babysoft", sonuc["metin"])

    def test_yayinda_olmayan_urun_icin_link_uydurmaz(self):
        kayit = {"urun_id": "u1", "urun_adi": "BABYSOFT (Losyon)",
                 "slug": "babysoft", "wix_yayinda": False, "gorunur": True,
                 "wix_stok": 3, "wix_satis": 100, "wix_liste": 100,
                 "aciklama_duz": ""}
        def sorgu(sql):
            if "mart.urun_karti" in sql:
                return [kayit]
            return [{"metin": "BABYSOFT nasıl satın alabilirim?",
                     "sinif": None, "mevzuat": None, "urun": None}]
        GK._calistir = sorgu
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertNotIn("https://", sonuc["metin"])

    def test_mevzuat_engeli_odeme_linkini_de_kapatir(self):
        GK._calistir = SahteSorgu("ODEME_YONLENDIR", mevzuat="BLOCKED",
                                 metin="Ödeme nasıl yapılır?")
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertFalse(sonuc["uretildi"])
        self.assertEqual(sonuc["metin"], "")

    def test_urun_bilinmiyorsa_odeme_icin_sorar(self):
        GK._calistir = SahteSorgu("ODEME_YONLENDIR", metin="Ödeme nasıl yapılır?")
        sonuc = GK.taslak(1)
        self.assertFalse(sonuc["devredilmeli"])
        self.assertTrue(sonuc["urun_soruluyor"])
        self.assertTrue(sonuc["gonderilebilir"])
        self.assertNotIn("https://", sonuc["metin"])

    def test_yanlis_yazilan_urun_odeme_baglaminda_eslesir(self):
        kayit = {"urun_id": "u1", "urun_adi": "KINESIS + (Sporcu Bakım Kremi)",
                 "slug": "kinesis-plus", "wix_yayinda": True, "gorunur": True,
                 "wix_stok": 3, "wix_satis": 100, "wix_liste": 100,
                 "aciklama_duz": ""}
        def sorgu(sql):
            if "mart.urun_karti" in sql:
                return [kayit]
            return [{"metin": "Kimesis ile ilgileniorm", "sinif": None,
                     "mevzuat": None, "urun": None,
                     "onceki_gelenler": ["Ürünleri nasıl satın alabilirim?"]}]
        GK._calistir = sorgu
        sonuc = GK.taslak(1)
        self.assertEqual(sonuc["sinif"], "ODEME_YONLENDIR")
        self.assertFalse(sonuc["devredilmeli"])
        self.assertIn("product-page/kinesis-plus", sonuc["metin"])

    def test_urun_sozu_odeme_baglami_yokken_devredilir(self):
        GK._calistir = lambda sql: [{"metin": "Kimesis", "sinif": None,
                                     "mevzuat": None, "urun": None,
                                     "onceki_gelenler": []}]
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertNotIn("https://", sonuc["metin"])

    def test_urun_sozu_birkac_tur_onceki_odeme_sorusunu_bulur(self):
        kayit = {"urun_id": "u1", "urun_adi": "KINESIS + (Sporcu Bakım Kremi)",
                 "slug": "kinesis-plus", "wix_yayinda": True, "gorunur": True,
                 "wix_stok": 3, "wix_satis": 100, "wix_liste": 100,
                 "aciklama_duz": ""}
        def sorgu(sql):
            if "mart.urun_karti" in sql:
                return [kayit]
            return [{"metin": "Kimesis", "sinif": None,
                     "mevzuat": None, "urun": None,
                     "onceki_gelenler": ["Kimesis", "Kimesis ile ilgileniorm",
                                          "Ürünleri nasıl satın alabilirim?"]}]
        GK._calistir = sorgu
        sonuc = GK.taslak(1)
        self.assertFalse(sonuc["devredilmeli"])
        self.assertIn("product-page/kinesis-plus", sonuc["metin"])

    def test_olumsuz_urun_mesaji_odeme_linkine_donmez(self):
        GK._calistir = lambda sql: [{"metin": "Kimesis kötü", "sinif": None,
                                     "mevzuat": None, "urun": None,
                                     "onceki_gelenler": ["Nasıl satın alabilirim?"]}]
        sonuc = GK.taslak(1)
        self.assertTrue(sonuc["devredilmeli"])
        self.assertNotIn("https://", sonuc["metin"])


if __name__ == "__main__":
    unittest.main()
