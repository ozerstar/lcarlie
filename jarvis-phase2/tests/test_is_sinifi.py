"""İş sınıfı kapısının testleri.

Bu testlerin varlık sebebi ÖLÇÜLMÜŞ bir boşluk: eski kelime listesi
"Bu krem hangi ürünle birlikte kullanılır?" sorusunu yakalamıyordu ve soru
küçük modele düşüyordu. İlk test o vakayı sabitler; kapı bir daha o deliği
açarsa test kırılır.
"""
import unittest

from jarvis import is_sinifi as s
from jarvis.model_layer import needs_escalation


class OlculenBosluk(unittest.TestCase):
    """Eski kapının kaçırdığı gerçek vaka. Bu test gerilemeyi yakalar."""

    def test_hangi_urunle_kullanilir_guclu_modele_gider(self):
        soru = "Bu krem hangi ürünle birlikte kullanılır?"
        self.assertEqual(s.siniflandir(soru), s.KARAR_GIRDISI)
        self.assertTrue(needs_escalation(soru),
                        "ölçülen boşluk geri geldi: soru küçük modele düşüyor")

    def test_eski_kelime_listesi_hala_calisiyor(self):
        for soru in ("fiyat stratejisi ne olmalı", "bu bulguya karşı çık",
                     "iki seçeneği kıyasla", "risk analizi yap"):
            with self.subTest(soru=soru):
                self.assertTrue(needs_escalation(soru))


class SiniflandirmaTests(unittest.TestCase):
    def test_yayin_adayi(self):
        for soru in ("INTIMBLANC için reklam metni yaz", "bir caption öner",
                     "ürün açıklaması yaz", "blog yazısı hazırla"):
            with self.subTest(soru=soru):
                self.assertEqual(s.siniflandir(soru), s.YAYIN_ADAYI)

    def test_olgu_sorusuna_model_sorulmaz(self):
        for soru in ("kaç ürün var", "stok ne durumda", "barkod nedir"):
            with self.subTest(soru=soru):
                sinif = s.siniflandir(soru)
                self.assertEqual(sinif, s.OLGU)
                self.assertFalse(s.model_gerekir(sinif))
                self.assertFalse(needs_escalation(soru))

    def test_mekanik_is_kucuk_modelde_kalir(self):
        for soru in ("merhaba", "teşekkürler", "tamam"):
            with self.subTest(soru=soru):
                self.assertEqual(s.siniflandir(soru), s.MEKANIK)
                self.assertFalse(needs_escalation(soru))

    def test_uzun_istek_karar_girdisidir(self):
        uzun = "a" * (s._KARAR_KARAKTER + 1)
        self.assertEqual(s.siniflandir(uzun), s.KARAR_GIRDISI)

    def test_bos_mesaj_cokmez(self):
        for bos in ("", "   ", None):
            with self.subTest(bos=bos):
                self.assertEqual(s.siniflandir(bos), s.MEKANIK)


class BeyanTahmindenUstundur(unittest.TestCase):
    def test_amac_metni_ezer(self):
        # Metin "merhaba" (mekanik görünür) ama çağıran reklam metni üretiyor.
        self.assertEqual(s.siniflandir("merhaba", amac="reklam_metni"),
                         s.YAYIN_ADAYI)

    def test_taninmayan_amac_guvenli_tarafa_duser(self):
        """Bilinmeyen iş ucuz kademeye DEĞİL, güçlü modele gider."""
        sinif = s.siniflandir("merhaba", amac="hic_bilinmeyen_bir_is")
        self.assertEqual(sinif, s.KARAR_GIRDISI)
        self.assertTrue(s.guclu_model_gerekir(sinif))

    def test_amac_buyuk_harf_ve_bosluk_toleransli(self):
        self.assertEqual(s.siniflandir("x", amac="Reklam Metni"), s.YAYIN_ADAYI)


class MevzuatKapisi(unittest.TestCase):
    def test_disari_cikabilen_metin_mevzuattan_gecer(self):
        self.assertTrue(s.mevzuat_zorunlu(s.MUSTERIYE))
        self.assertTrue(s.mevzuat_zorunlu(s.YAYIN_ADAYI))

    def test_ic_metin_mevzuat_zorunlu_degil(self):
        for sinif in (s.KARAR_GIRDISI, s.OLGU, s.MEKANIK):
            with self.subTest(sinif=sinif):
                self.assertFalse(s.mevzuat_zorunlu(sinif))


class TurkceEslesme(unittest.TestCase):
    """Türkçe i/ı ayrımı sessizce boş eşleşme üretir -- ölçülmüş tuzak."""

    def test_noktasiz_i_ile_yazilan_terim_de_yakalanir(self):
        self.assertEqual(s.siniflandir("rakipleri arastir"), s.KARAR_GIRDISI)
        self.assertEqual(s.siniflandir("rakipleri araştır"), s.KARAR_GIRDISI)

    def test_buyuk_harf_fark_etmez(self):
        self.assertEqual(s.siniflandir("RAKİP ANALİZİ"), s.KARAR_GIRDISI)


class SinifKumeleriTutarli(unittest.TestCase):
    def test_guclu_model_kumesi_olguyu_icermez(self):
        """OLGU'ya model hiç sorulmaz; güçlü model kümesinde olamaz."""
        self.assertNotIn(s.OLGU, s.GUCLU_MODEL)

    def test_her_sinif_tanimli(self):
        for sinif in s.GUCLU_MODEL | s.MEVZUAT_ZORUNLU:
            self.assertIn(sinif, s.SINIFLAR)


if __name__ == "__main__":
    unittest.main()
