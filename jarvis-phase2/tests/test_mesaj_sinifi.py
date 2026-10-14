# -*- coding: utf-8 -*-
"""Müşteri mesajı sınıflandırmasının testleri.

Bu testler devir kapısının GİRDİSİNİ kilitler. Sınıf kayarsa kapı yanlış
karar verir: şikâyet Jarvis'e cevaplatılır ya da basit bir fiyat sorusu
gereksiz yere sahibe düşer.
"""
import unittest

from jarvis import devir, mesaj_sinifi as M


class JarvisinCevaplayabilecekleri(unittest.TestCase):
    def test_fiyat(self):
        for m in ("Fiyatı nedir?", "fiyat", "Kaç para", "Ne kadar tutuyor",
                  "kaç TL", "Ücreti ne kadar"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.FIYAT)

    def test_icerik(self):
        for m in ("İçindekiler nelerdir?", "içeriği ne", "paraben var mı",
                  "Krem formunda mı", "doğal mı"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.ICERIK)

    def test_kullanim(self):
        for m in ("Nasıl kullanılır", "Nereye sürülür", "Günde kaç kez"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.KULLANIM)

    def test_selamlama_ve_tesekkur(self):
        self.assertEqual(M.siniflandir("Merhaba"), M.SELAMLAMA)
        self.assertEqual(M.siniflandir("Teşekkürler"), M.TESEKKUR)

    def test_hepsi_beyaz_listede(self):
        for sinif in (M.FIYAT, M.ICERIK, M.KULLANIM, M.KARGO, M.SELAMLAMA,
                      M.TESEKKUR):
            with self.subTest(sinif=sinif):
                self.assertIn(sinif, devir.JARVIS_SINIFLARI)


class SahibeGidenler(unittest.TestCase):
    def test_saglik_ve_sikayet(self):
        for m in ("Alerjim var", "Cildim kızardı", "Yan etkisi var mı",
                  "Hamileyim kullanabilir miyim", "Doktora sordum",
                  "Bana yaramadı", "Yaram var"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.SAGLIK)

    def test_siparis_ve_islem(self):
        for m in ("Sipariş nasıl verilir?", "İade etmek istiyorum",
                  "Kargom gelmedi", "Kapıda ödeme var mı"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.SIPARIS)

    def test_hicbiri_beyaz_listede_DEGIL(self):
        for sinif in (M.SAGLIK, M.SIPARIS, M.IDDIA_SORUSU, M.ANLASILMADI):
            with self.subTest(sinif=sinif):
                self.assertNotIn(sinif, devir.JARVIS_SINIFLARI)


class IddiaSorusuAYRIDIR(unittest.TestCase):
    """🔴 Eski 540 etiketlemede bu sınıf YOKTU. 'Neye faydası var' SAGLIK,
    'Etkisi ne kadar sürede' TESEKKUR etiketlenmişti. Ürünün etkisini
    soran mesajın cevabı bir mevzuat iddiası üretir."""

    def test_etki_sorulari(self):
        for m in ("Ne işe yarar", "Faydası ne", "Etkisi var mı",
                  "İyi gelir mi", "Kaç günde etki eder", "Kalıcı mı"):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.IDDIA_SORUSU)

    def test_iddia_sahibe_devredilir_ve_SEBEBI_dogru(self):
        gerek, sebep = devir.devir_gerekir(M.IDDIA_SORUSU, urun_bilindi=True)
        self.assertTrue(gerek)
        self.assertEqual(sebep, devir.IDDIA)
        self.assertIn("iddia", devir.sebep_aciklamasi(sebep).lower())


class KelimeOrtasindaESLESMEZ(unittest.TestCase):
    """🔴 ÖLÇÜLMÜŞ TUZAK. 'ne işe yarar' SAGLIK çıkıyordu çünkü 'yarar'
    içinde 'yara' kökü geçiyor. Aynı sınıf hata bu projede daha önce
    'hi ' kalıbının kelime ortasında eşleşmesiyle yaşandı."""

    def test_yarar_saglik_DEGIL(self):
        self.assertEqual(M.siniflandir("Ne işe yarar"), M.IDDIA_SORUSU)
        self.assertEqual(M.siniflandir("Yararlı mı"), M.IDDIA_SORUSU)

    def test_yara_hala_saglik(self):
        self.assertEqual(M.siniflandir("Yaram var"), M.SAGLIK)
        self.assertEqual(M.siniflandir("Yarası iyileşir mi"), M.SAGLIK)

    def test_tam_kelime_kokleri_ortada_eslesmez(self):
        # "tamam" TAM_KELIME; "tamamlayici" onu tetiklememeli.
        self.assertNotEqual(M.siniflandir("Tamamlayıcı ürün var mı"), M.TESEKKUR)


class EminDegilseDEVREDER(unittest.TestCase):
    def test_bos_mesaj(self):
        for m in ("", "   ", None):
            with self.subTest(m=m):
                self.assertEqual(M.siniflandir(m), M.ANLASILMADI)

    def test_tanimsiz_mesaj(self):
        self.assertEqual(M.siniflandir("Ne bu"), M.ANLASILMADI)

    def test_anlasilmadi_sahibe_gider(self):
        gerek, _ = devir.devir_gerekir(M.ANLASILMADI, urun_bilindi=True)
        self.assertTrue(gerek)


class TurkceBuyukHarfTuzagi(unittest.TestCase):
    """🔴 Türkçe yerelde 'I'.lower() noktasız 'ı' üretir ve hiçbir şeyle
    eşleşmez. Bu proje bu tuzağa daha önce düştü."""

    def test_buyuk_harfli_mesaj_ayni_siniflanir(self):
        self.assertEqual(M.siniflandir("FİYATI NEDİR"), M.FIYAT)
        self.assertEqual(M.siniflandir("İÇİNDEKİLER NELERDİR"), M.ICERIK)

    def test_aksansiz_yazim_da_yakalanir(self):
        self.assertEqual(M.siniflandir("fiyati nedir"), M.FIYAT)
        self.assertEqual(M.siniflandir("icindekiler nelerdir"), M.ICERIK)


if __name__ == "__main__":
    unittest.main()
