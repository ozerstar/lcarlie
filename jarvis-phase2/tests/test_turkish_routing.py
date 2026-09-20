"""Türkçe çekimli cümleler doğru yere gidiyor mu? Ağ yok, model yok.

NEDEN BU DOSYA VAR
20.09.2026'da Türkçe çekim tuzağına YEDİ kez düşüldü ve her biri tek tek
düzeltildi. Tek tek düzeltmek yanlış yöntemdi: bu hata sınıfı istisna
fırlatmaz, hata kodu vermez -- sadece eşleşme olmaz ve sistem sessizce
yanlış yere gider. Üretimde haftalarca fark edilmeden durabilir.

Ölçülen gerçek örnekler:
  "sattık"              "satış" dizgisini içermez   -> veri yoluna gitmedi
  "kampanyası hazırla"  "kampanya hazır"ı içermez   -> ajans hiç çalışmadı
  "satışlarımız nasıl gidiyor" "nasıl gidiyor" içerir -> sohbet sanıldı
  "Instagram için gönderi planı" "instagram plan" içermez -> yanlış görev
  "açılış sayfamızın"   "açılış sayfası"nı içermez  -> ajansa ulaşmadı

Buradaki cümleler uydurma değil; aynı isteğin Türkçede doğal yazılışları.
Yeni bir sınıflandırma kuralı eklenirse buraya da çekimli bir örnek eklenir.
"""
import unittest

from jarvis import agency
from webconsole import conversation as conv

AJANS = "AGENCY_REQUEST"
SIRKET = "COMPANY_QUERY"
SOHBET = "SIMPLE_CONVERSATION"
ANALIZ = "ANALYSIS_REQUEST"


class AjansYonlendirmeTests(unittest.TestCase):
    def kontrol(self, cumle, niyet, gorev=None):
        karar = conv.classify(cumle)
        self.assertEqual(niyet, karar.intent, f"{cumle!r} -> {karar.intent}")
        if gorev:
            self.assertEqual(gorev, agency.classify_task(cumle), cumle)

    # --- kampanya: iyelik eki dizgiyi boluyordu
    def test_iyelik_ekli_kampanya_istegi(self):
        self.kontrol("INTIMBLANC kampanyası hazırla", AJANS, agency.TASK_CAMPAIGN)

    def test_cogul_ve_istek_kipi(self):
        self.kontrol("Yeni kampanyalar hazırlayalım", AJANS, agency.TASK_CAMPAIGN)

    def test_farkli_uretim_fiili(self):
        self.kontrol("INTIMBLANC için kampanya kurgula", AJANS, agency.TASK_CAMPAIGN)
        self.kontrol("Bu ürüne kreatif konseptler üret", AJANS, agency.TASK_CAMPAIGN)

    # --- sosyal: araya kelime giriyordu
    def test_araya_kelime_giren_sosyal_plan(self):
        """'instagram plan' kalıbı 'Instagram için gönderi planı'nı görmez."""
        self.kontrol("Instagram için gönderi planı çıkar", AJANS, agency.TASK_SOCIAL)

    def test_iyelik_ekli_sosyal_plan(self):
        self.kontrol("Haftalık sosyal medya planımızı kur", AJANS, agency.TASK_SOCIAL)

    # --- CRO: uretim fiili tasimayabilir
    def test_uretim_fiilsiz_cro_istegi(self):
        """'Dönüşümü artıralım' bir üretim fiili taşımaz ama ajans işidir."""
        self.kontrol("Açılış sayfamızın dönüşümünü artıralım", AJANS, agency.TASK_CRO)


class VeriYonlendirmeTests(unittest.TestCase):
    def test_fiil_cekimli_satis_sorusu(self):
        """'sattık' kelimesi 'satış' dizgisini içermez."""
        self.assertEqual(SIRKET, conv.classify("Geçen ay kaç adet sattık?").intent)

    def test_fiil_cekimli_harcama_sorusu(self):
        self.assertEqual(SIRKET, conv.classify("Reklamlara ne kadar harcadık?").intent)

    def test_selamlasma_kalibi_is_sorusunu_yutmaz(self):
        """'nasıl gidiyor' iş sorusunun İÇİNDE geçebilir."""
        for cumle in ("Satışlarımız nasıl gidiyor?", "Siparişlerimiz nasıl gidiyor?",
                      "Reklamlar nasıl gidiyor?"):
            self.assertEqual(SIRKET, conv.classify(cumle).intent, cumle)

    def test_iyelik_ekli_musteri_sorusu(self):
        self.assertEqual(SIRKET,
                         conv.classify("Müşterilerimizden cevapsız kalan var mı?").intent)


class AsiriTetiklemeTests(unittest.TestCase):
    """Genişletilen kurallar sohbeti veya analizi yutmamalı."""

    def test_saf_selamlasma_sohbette_kalir(self):
        for cumle in ("Merhaba, nasılsın?", "Teşekkürler, görüşürüz",
                      "Günaydın", "Neler yapabilirsin?"):
            self.assertEqual(SOHBET, conv.classify(cumle).intent, cumle)

    def test_kisisel_mesaj_sohbette_kalir(self):
        self.assertEqual(SOHBET, conv.classify("Kafam çok dolu, ne yapmalıyım").intent)

    def test_rapor_sorusu_ajansa_gitmez(self):
        """Üretim fiili yoksa ajans çalışmaz."""
        self.assertNotEqual(AJANS,
                            conv.classify("Kampanyalarımızın harcaması ne kadar?").intent)

    def test_analiz_sorusu_uzman_havuzunda_kalir(self):
        """Bu soru ajansa DEĞİL uzman havuzuna gitmeli; sistem haklı."""
        self.assertEqual(ANALIZ, conv.classify(
            "Reklam performansımızda hangi problemler var, ne test edelim?").intent)


class KaynakTests(unittest.TestCase):
    def test_morfoloji_yoksa_da_calisir(self):
        """Kök eşleşmesi zeyrek olmadan da çalışmalı: testler sistem
        python'unda koşuyor ve orada morfoloji yok."""
        from jarvis import turkish
        if turkish.MORPHOLOGY_AVAILABLE:
            self.skipTest("bu yorumlayıcıda morfoloji var; kapalı hâli ayrıca sınanır")
        self.assertEqual(AJANS, conv.classify("INTIMBLANC kampanyası hazırla").intent)
        self.assertEqual(SIRKET, conv.classify("Geçen ay kaç adet sattık?").intent)


if __name__ == "__main__":
    unittest.main()
