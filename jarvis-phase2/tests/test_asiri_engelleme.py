# -*- coding: utf-8 -*-
"""Aşırı engelleme testleri — 28.09.2026 denetimi.

Buradaki cümlelerin TAMAMI onaylı kutu metinlerinden (`kutu.json`,
kaynak türü `onayli_kutu_metni`) birebir alınmıştır. Ambalajın üstünde
basılı olan bir cümleyi motor engelliyorsa kural yanlıştır.

Ölçüm (düzeltme öncesi): 39 üründe 77 bulgu, 66'sı yanlış.
"""
import unittest

from jarvis.compliance import BLOCKED, VERIFY, review


def _bulgular(metin, kural_parcasi=None, etiket=None):
    b = review(metin).findings
    if kural_parcasi:
        b = [x for x in b if kural_parcasi in x.rule]
    if etiket:
        b = [x for x in b if x.label == etiket]
    return b


class ZorunluMetinEngellenemez(unittest.TestCase):
    """Kanunen yazmak zorunda olduğumuz metin engellenemez."""

    def test_istenmeyen_etki_uyarisi_engellenmez(self):
        # BUGUARD / uyarılar -- zorunlu istenmeyen etki uyarısı
        m = ("Kızarıklık, kaşıntı veya tahriş halinde kullanımı bırakınız "
             "ve doktora başvurunuz.")
        self.assertEqual([], _bulgular(m, "hastalık veya durum adı"))

    def test_uyari_kalibi_iddiayi_aklamaz(self):
        # Kaçak yolu kapalı: fayda cümlesine uyarı eklemek muafiyet vermez.
        m = ("Egzamayı geçirir, şikâyet halinde doktora başvurunuz.")
        self.assertTrue(_bulgular(m, etiket=BLOCKED))

    def test_inci_listesi_engellenmez(self):
        # VIREON / inci -- beyanı zorunlu içerik listesi
        m = ("Saf Su, Haşhaş Yağı, Hodan Yağı, Jojoba Yağı, Üzüm Çekirdeği "
             "Yağı, Tarçın Kabuk Yağı, Zencefil Yağı, Nioli Yağı, Karabiber "
             "Yağı, Epimedium Ekstresi, L-Arginine, Tokoferol.")
        self.assertEqual([], _bulgular(m, "bileşen tuzağı"))

    def test_bilesen_cumlede_anilirsa_engellenir(self):
        # Kaçak yolu kapalı: pazarlama cümlesinde anmak ihlaldir.
        m = "Epimedium ekstresi sayesinde etkisini hemen gösterir."
        self.assertTrue(_bulgular(m, "bileşen tuzağı", BLOCKED))

    def test_raf_omru_sure_iddiasi_degildir(self):
        # 36 üründe aynı satır -- zorunlu etiket unsuru
        m = "24 ay – serin ve kuru yerde, doğrudan güneş ışığından uzakta saklayınız."
        self.assertEqual([], _bulgular(m, "süre"))

    def test_kullanim_talimati_sure_iddiasi_degildir(self):
        # INTIMBLANC / kullanım ve CALMORIS / uyarılar
        for m in ("Uygulama sonrası en az 6 saat boyunca suyla temas ettirmeyiniz.",
                  "Fototoksik bileşenler içerir; uygulama sonrası en az 12 saat "
                  "direkt güneş ışığından kaçının."):
            with self.subTest(m=m[:40]):
                self.assertEqual([], _bulgular(m, "süre"))

    def test_etkiye_bagli_sure_hala_isaretlenir(self):
        m = "7 günde cilt görünümü belirgin şekilde pürüzsüzleşir."
        self.assertTrue(_bulgular(m, "süre", VERIFY))

    def test_formulasyon_yuzdesi_oran_iddiasi_degildir(self):
        # DERMAGUARD / tanım -- formül tablosunun % sütunu
        m = ("İçerik INCI % Oranı Shea Butter 20% Sweet Almond Oil 10% "
             "Aloe Vera 10% Glycerin 2%")
        self.assertEqual([], _bulgular(m, "oran"))

    def test_zorunlu_gunes_ibaresi_oran_iddiasi_degildir(self):
        m = "Güneş koruyucu ürünler %100 koruma sağlamaz."
        self.assertEqual([], _bulgular(m, "oran"))


class NesnesiIzinliCumleEngellenemez(unittest.TestCase):
    """Belgenin kendi kuralı: nesne izinliyse cümle geçer."""

    def test_gorunum_nesnesi_engellenmez(self):
        # DERMASTRA / tanım -- nesne tam olarak "görünüm"
        m = ("L'CARLIE Dermastra, beyaz çatlak görünümünün azalmasına ve cildin "
             "yenilenme sürecine destek olmak amacıyla geliştirilmiştir.")
        self.assertEqual([], _bulgular(m, "hastalık veya durum adı"))

    def test_temizlik_izinli_nesnedir(self):
        # BRIGHT SMILE / tanım -- kozmetiğin kanundaki birincil işlevi
        m = ("Bambu kaynaklı aktif karbon sayesinde diş yüzeyindeki lekeleri "
             "nazikçe temizlemeye destek olur.")
        self.assertEqual([], _bulgular(m, "hastalık veya durum adı"))

    def test_selulit_gorunumu_engellenmez(self):
        m = "Selülit görünümünün azalmasına yardımcı olur."
        self.assertEqual([], _bulgular(m, "hastalık veya durum adı"))

    def test_ciddi_hastalik_gorunumle_aklanmaz(self):
        # Kaçak yolu kapalı: "görünümü" eklemek tıbbi terimi kozmetik yapmaz.
        for m in ("Egzama görünümünü azaltır.", "Sedef görünümünü giderir.",
                  "Mantar görünümünü yok eder."):
            with self.subTest(m=m):
                self.assertTrue(_bulgular(m, etiket=BLOCKED))


class AlanAdiIddiaDegildir(unittest.TestCase):
    """Sahip kararı 28.09.2026: alan adı kullanımı ve cilt tipi tanımı
    iddia değildir; uygulama bölgesini tarif eder."""

    def test_kas_bolgesi_alan_adidir(self):
        # DORSIVIA / tanım
        m = ("Düzenli kullanımda bel, sırt ve kas bölgelerinin bakımına "
             "katkıda bulunur.")
        self.assertEqual([], _bulgular(m, "fizyolojik fonksiyon"))

    def test_kas_islevi_hala_engellenir(self):
        # Kaçak yolu kapalı: işlev iddiası alan adı değildir.
        for m in ("Kasları gevşetir.", "Kas gevşemesine yardımcı olur.",
                  "Kas dokusunu onarır."):
            with self.subTest(m=m):
                self.assertTrue(_bulgular(m, "fizyolojik fonksiyon", BLOCKED))


class KullanimDeyimiUstunlukDegildir(unittest.TestCase):

    def test_en_iyi_sonuc_icin_engellenmez(self):
        # BABYRESCUE / kullanım
        m = ("En iyi sonuç için uygulama öncesinde bölgenin kuru olmasına "
             "özen gösteriniz.")
        self.assertEqual([], _bulgular(m, "üstünlük"))

    def test_gercek_ustunluk_iddiasi_engellenir(self):
        for m in ("Türkiye'nin en iyi nemlendiricisi.", "Pazarın lideri.",
                  "Rakipsiz formül."):
            with self.subTest(m=m):
                self.assertTrue(_bulgular(m, "üstünlük", BLOCKED))


class UretimOrtamiSaglikCalisaniDegildir(unittest.TestCase):
    """Sahip kararı 27.09.2026: kimyagerler de beyaz giyer, kozmetik
    laboratuvarda üretilir. Otorite transferi, sağlık mesleği çağrışımı
    eşlik ettiğinde doğar."""

    def test_uretim_ortami_tek_basina_isaretlenmez(self):
        for m in ("Ürünlerimiz beyaz önlüklü kimyagerler tarafından "
                  "laboratuvarda üretilir.",
                  "Formülasyon kendi laboratuvarımızda geliştirilir."):
            with self.subTest(m=m[:40]):
                self.assertEqual([], _bulgular(m, "otorite transferi"))

    def test_saglik_meslegi_cagrisimi_isaretlenir(self):
        for m in ("Doktor tavsiyesiyle geliştirildi.",
                  "Eczacı önerisiyle kullanın.",
                  "Beyaz önlüklü doktorumuz tedaviyi anlatıyor."):
            with self.subTest(m=m[:40]):
                self.assertTrue(_bulgular(m, "otorite transferi", VERIFY))


if __name__ == "__main__":
    unittest.main()
