"""Ürün bilgi dosyası üreticisi: "Kullanım" bölümü nereden başlar.

24.09.2026'da 36 ürün dosyasının çoğunda `## Kullanım` bölümü cümlenin
ORTASINDAN başlıyordu ("da cildin daha bakımlı...", "a uygundur. Harici
kullanım içindir..."). Sebep tek bir düzenli ifadeydi: desen `Kullanım`
idi ve IGNORECASE ile çekimli geçişlere de takılıyordu --

    "düzenli kullanım|da cildin ..."      -> "da cildin ..."
    "harici kullanım| içindir ..."        -> "içindir ..."

`re.search` ilk eşleşmeyi aldığı için gerçek talimat hiç görülmüyordu.
Hiçbir hata verilmedi; bölüm DOLUYDU, yalnız anlamsızdı -- en sinsi
hata türü. İkinci kusur düz `[:300]` kırpmasıydı: bölüm "formüle
edilmişti" gibi yarım kelimeyle bitiyordu.

Bu testler iki kuralı kilitler:
  1. anahtar kelime çekimli bir kelimenin parçasıysa EŞLEŞMEZ,
  2. çıkan metin kelime/cümle ortasında BİTMEZ.
"""

import importlib.util
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "urun_bilgi_uret", KOK / "tools" / "urun-bilgi-uret.py")
uretici = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uretici)


class KullanimBulma(unittest.TestCase):

    def _bul(self, metin):
        m = uretici.kullanim_bul(metin)
        return m.group(1) if m else None

    # --- eşleşMEMESİ gerekenler (gerçek dosyalardan alındı) -------------
    def test_cekimli_kelime_icinde_ESLESMEZ(self):
        """'kullanımda' bir talimat başlığı değildir."""
        metin = ("Düzenli kullanımda cildin daha bakımlı, dengeli ve pürüzsüz "
                 "algılanan bir görünüm kazanmasına yardımcı olur.")
        self.assertIsNone(self._bul(metin))

    def test_kullanima_uygundur_ESLESMEZ(self):
        metin = "Günlük kullanıma uygundur. Cildi kurutmadan temizlemeye yardımcı olur."
        self.assertIsNone(self._bul(metin))

    def test_harici_kullanim_icindir_ESLESMEZ(self):
        """Bu bir uyarıdır, talimat değil."""
        metin = "Hızla emilen yapısıyla yağlı his bırakmaz. Harici kullanım içindir."
        self.assertIsNone(self._bul(metin))

    def test_talimat_yoksa_BOS_doner(self):
        """Yanlış metin yazmaktansa bölümü hiç yazmamak doğrudur."""
        self.assertIsNone(self._bul("Bu üründe yalnızca genel bir tanıtım metni var."))

    # --- eşleşMESİ gerekenler ------------------------------------------
    def test_iki_nokta_ile_yazilmis_talimat(self):
        metin = ("ÖNE ÇIKAN ÖZELLİKLER bitkisel yağlar. Kullanım: Günde 2 kez "
                 "temiz ve kuru cilde dairesel masaj hareketleriyle uygulanır.")
        self.assertTrue(self._bul(metin).startswith("Günde 2 kez"))

    def test_kullanim_talimati_basligi(self):
        metin = ("Kullanım Talimatı: Temiz cilde sabah ve akşam yaklaşık 20 cm "
                 "mesafeden püskürtünüz.")
        self.assertTrue(self._bul(metin).startswith("Temiz cilde"))

    def test_baslik_gibi_duran_kullanim(self):
        """İki nokta yok ama devamı büyük harfle başlıyor -> yeni cümle."""
        metin = ("Rahatlama hissi sağlar. Kullanım Şakaklara, alına, enseye, "
                 "bileklere veya göğüs bölgesine uygulanır.")
        self.assertTrue(self._bul(metin).startswith("Şakaklara"))

    def test_gercek_talimat_cekimli_gecisin_ARDINDAN_gelse_de_bulunur(self):
        """Asıl kusur buydu: ilk eşleşme yanlış olunca doğrusu hiç görülmüyordu."""
        metin = ("Düzenli kullanımda cilt bakımlı görünür. Günlük kullanıma "
                 "uygundur. Kullanım: Temiz cilde ince bir tabaka halinde "
                 "uygulayınız ve masaj yapınız.")
        self.assertTrue(self._bul(metin).startswith("Temiz cilde"))


class KesmeDavranisi(unittest.TestCase):

    def test_kelime_ortasindan_KESMEZ(self):
        metin = ("Bitkisel yağlar ve mineral içeriklerle formüle edilmiştir ve "
                 "günlük bakım rutinine uygundur.")
        cikti = uretici.cumlede_kes(metin, 45)
        self.assertLessEqual(len(cikti), 45)
        self.assertFalse(cikti.endswith("edilmişti"), "yarım kelimeyle bitti")
        self.assertTrue(metin.startswith(cikti), "metni bozdu")

    def test_cumle_sonunu_tercih_eder(self):
        metin = "Birinci cümle burada. İkinci cümle çok daha uzun ve kesilecek."
        self.assertEqual("Birinci cümle burada.", uretici.cumlede_kes(metin, 40))

    def test_sinira_siginan_metin_aynen_doner(self):
        self.assertEqual("Kısa metin.", uretici.cumlede_kes("Kısa metin.", 300))


class UretilenDosyalar(unittest.TestCase):
    """Üretilmiş dosyalarda bu kusur KALMAMALI.

    Bütçeyi aşan iki dosya (dermastra, sunacnea) tam bu bozuk bölüm
    yüzünden 4200 karakteri geçiyordu ve `company_knowledge` onları
    SESSİZCE atlıyordu -- yani hiçbir zaman getirilemiyorlardı.
    """

    BOZUK_BASLANGICLAR = ("da ", "a ", "sunar", "deneyimi", "sonrası",
                          "konforu", "için uygun", "ına ", "kolaylığı")

    def test_butceyi_asan_dosya_yok(self):
        from jarvis.company_knowledge import _MAX_CHARS, CompanyKnowledge
        k = CompanyKnowledge(KOK / "knowledge")
        asan = {ad: len(d.body) for ad, d in k.documents.items()
                if len(d.body) > _MAX_CHARS}
        self.assertEqual({}, asan, f"{_MAX_CHARS} karakteri aşan dosya getirilemez")


if __name__ == "__main__":
    unittest.main()
