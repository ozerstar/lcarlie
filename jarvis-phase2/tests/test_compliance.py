"""Kademe 1 mevzuat taraması. Kural kaynağı 03_MEVZUAT_KURALLARI.md (06.09.2026).

Testlerin çoğu belgedeki gerçek vakalardan alındı — özellikle VIREON ihlal kalıbı,
çünkü kelime listesiyle çalışan bir tarayıcının onu kaçırdığı ölçülmüştü.
"""
import unittest

from jarvis.compliance import (BLOCKED, VERIFY, approval_record, deaccent, fold,
                               review, sentences)


def rules(result):
    return {f.rule for f in result.findings}


def matched(result):
    return {f.matched for f in result.findings}


class NesneKuraliTests(unittest.TestCase):
    """Belge §1 — fiil değil, cümlenin nesnesi denetlenir."""

    def test_vireon_ihlal_kalibi_yakalanir(self):
        result = review("Bölgesel bakım jeli dolaşımı destekler.")
        self.assertTrue(result.blocked)
        self.assertIn("yasak nesne — fizyolojik fonksiyon", rules(result))

    def test_yasak_fiil_olmadan_yasak_nesne_yakalanir(self):
        """Kelime listesinin kaçırdığı cümle: temiz fiil, yasak nesne."""
        result = review("Isınma sayesinde bölgeye daha çok kan gider.")
        self.assertTrue(result.blocked)
        self.assertIn("yasak nesne — fizyolojik fonksiyon", rules(result))

    def test_hucre_yenileyici_bloklu(self):
        result = review("Hücre yenileyici etkisiyle öne çıkar.")
        self.assertTrue(result.blocked)

    def test_izinli_nesneli_cumle_bulgu_uretmez(self):
        result = review("Cilt görünümünü destekleyen hafif bir dokusu vardır.")
        self.assertTrue(result.clean)

    def test_azaltir_fiili_tek_basina_bloklu_degil(self):
        """Belge §1: 'azaltır' yasak fiil listesinden çıktı."""
        self.assertTrue(review("Yoğun his azaltır.").clean)

    def test_ama_durum_nesnesiyle_azaltir_bloklu(self):
        result = review("Kızarıklığı azaltır.")
        self.assertTrue(result.blocked)
        self.assertIn("yasak nesne — hastalık veya durum adı", rules(result))


class UyariCumlesiTests(unittest.TestCase):
    """Katalog kılavuzu kural 2 — uyarı cümlesi iddia değildir, silinmez."""

    def test_zorunlu_uyari_bloklanmaz(self):
        result = review("Açık yaralara uygulanmaz.")
        self.assertTrue(result.clean, f"beklenmedik bulgu: {rules(result)}")

    def test_hekime_yonlendirme_bloklanmaz(self):
        self.assertTrue(review("Şikayetiniz sürerse hekime başvurunuz.").clean)


class TurkceKucultmeTests(unittest.TestCase):
    """Türkçe İ/I tuzağı — eşleşme sessizce kaçarsa tarama sahte güven üretir."""

    def test_buyuk_harfli_icermez_yakalanir(self):
        result = review("PARABEN İÇERMEZ.")
        self.assertTrue(result.blocked)
        self.assertIn("'içermez' kalıbı", rules(result))

    def test_aksansiz_yazim_yakalanir(self):
        result = review("Urun dolasimi destekler.")
        self.assertTrue(result.blocked)

    def test_fold_i_harfini_dogru_cevirir(self):
        self.assertEqual(fold("İÇERMEZ"), "içermez")
        self.assertEqual(fold("IŞIK"), "ışık")

    def test_deaccent_turkce_harfleri_duzlestirir(self):
        self.assertEqual(deaccent(fold("dolaşım")), "dolasim")


class Madde2Tests(unittest.TestCase):
    """Belge §2 — 06.09.2026 eklenenleri."""

    def test_ustunluk_iddiasi_bloklu(self):
        self.assertIn("üstünlük iddiası", rules(review("Türkiye'nin ilk ve en iyi serumu.")))

    def test_icermez_belge_ile_de_kurtarilmaz(self):
        result = review("Silikon içermeyen formül.")
        finding = next(f for f in result.findings if f.rule == "'içermez' kalıbı")
        self.assertEqual(finding.label, BLOCKED)
        self.assertIn("adillik", finding.remedy)

    def test_sure_iddiasi_dogrulama_ister(self):
        result = review("14 günde fark edilir.")
        self.assertIn("süre iddiası", rules(result))
        self.assertEqual(result.verify[0].label, VERIFY)

    def test_yuzde_iddiasi_dogrulama_ister(self):
        self.assertIn("oran/yüzde iddiası", rules(review("Kullanıcıların %92'si memnun.")))

    def test_belge_gerektiren_ifade(self):
        self.assertIn("belge gerektiren ifade",
                      rules(review("Dermatolojik olarak test edilmiştir.")))

    def test_gmp_ustunluk_kurgusunda_isaretlenir(self):
        self.assertIn("GMP/ISO kullanımı", rules(review("GMP sertifikalı tesiste üretilir.")))


class OtoriteVeGorselTests(unittest.TestCase):
    def test_doktor_formulu_isaretlenir(self):
        result = review("Doktor formülü ile geliştirildi.")
        self.assertIn("sağlık çalışanı algısı / otorite transferi", rules(result))
        self.assertIn("m.16/(3)", result.findings[0].basis)

    def test_oncesi_sonrasi_otomatik_guvenli_sayilmaz(self):
        result = review("Öncesi sonrası farkı videoda.")
        finding = next(f for f in result.findings if f.rule == "öncesi/sonrası")
        self.assertEqual(finding.label, VERIFY)
        self.assertIn("retouch", finding.remedy)


class UrunTuzagiTests(unittest.TestCase):
    def test_vireon_bilesen_tuzagi(self):
        result = review("Epimedium özü ile zenginleştirilmiştir.")
        self.assertIn("VIREON/FEMISIA bileşen tuzağı", rules(result))
        self.assertIn("INCI", result.blocked[0].remedy)


class IcerikBeyaniTests(unittest.TestCase):
    """Kılavuz kural 3 — içerik beyanı pazarlama değildir, silinmez.

    Gerçek kutu metinlerinde ölçüldü: bu ayrım yapılmadan 39 üründe onlarca
    yanlış alarm çıkıyor, çünkü INCI listesi yasal zorunluluk olduğu hâlde
    ihlal sayılıyordu.
    """

    def test_inci_listesindeki_bilesen_ihlal_degil(self):
        satir = ("İçindekiler: Saf Su, Haşhaş Yağı, Jojoba Yağı, "
                 "Epimedium Ekstresi, Tribulus Ekstresi")
        result = review(satir)
        self.assertNotIn("VIREON/FEMISIA bileşen tuzağı", rules(result))

    def test_ingilizce_ingredients_satiri_da_muaf(self):
        satir = "Ingredients: Aqua, Epimedium Grandiflorum Leaf Extract, Arginine"
        self.assertNotIn("VIREON/FEMISIA bileşen tuzağı", rules(review(satir)))

    def test_formul_tablosu_satiri_muaf(self):
        self.assertNotIn("VIREON/FEMISIA bileşen tuzağı",
                         rules(review("L-Arginin | L-Arginine | 5.")))

    def test_ama_pazarlama_cumlesinde_anilirsa_bloklu(self):
        """Muafiyet yalnız beyan satırına ait; cümlede anmak hâlâ ihlal."""
        result = review("Epimedium özü ile güçlendirilmiş özel formül.")
        self.assertIn("VIREON/FEMISIA bileşen tuzağı", rules(result))

    def test_tablo_satirindaki_islev_iddiasi_hala_yakalanir(self):
        """Nesne kuralı susmaz: tablo satırı olması iddiayı masum yapmaz."""
        result = review("0 | Isıtıcı, dolaşımı artırıcı")
        self.assertIn("yasak nesne — fizyolojik fonksiyon", rules(result))

    def test_icerik_satirinda_bile_hastalik_adi_bloklu(self):
        result = review("İçindekiler: bitki özleri, egzama bakım kompleksi")
        self.assertTrue(result.blocked)


class GunesKoruyucuTests(unittest.TestCase):
    """Belge §5 — zorunlu ibare seti."""

    def test_eksik_zorunlu_ibareler_raporlanir(self):
        result = review("SUNACNEA SPF 30 günlük güneş koruyucu.")
        eksik = [f for f in result.findings if f.rule == "güneş koruyucu zorunlu ibare eksik"]
        self.assertEqual(len(eksik), 4)

    def test_tam_ibare_seti_bulgu_uretmez(self):
        text = ("SPF 30 günlük güneş koruyucu. Yeterli miktarda uygulanmaması korumayı "
                "önemli ölçüde düşürür. Aşırı güneş maruziyeti sağlık tehdididir. "
                "Bebek ve küçük çocuklar doğrudan güneşe maruz bırakılmamalıdır. "
                "Hiçbir ürün %100 koruma sağlamaz.")
        eksik = [f for f in review(text).findings
                 if f.rule == "güneş koruyucu zorunlu ibare eksik"]
        self.assertEqual(eksik, [])

    def test_gunes_koruyucu_olmayan_metinde_ibare_aranmaz(self):
        result = review("Hafif dokulu nemlendirici.")
        self.assertTrue(result.clean)


class HashtagTests(unittest.TestCase):
    """Belge §6."""

    def test_hastalik_etiketi_bloklu(self):
        result = review("Günlük rutin #akne #bakim")
        self.assertIn("hastalık/semptom etiketi", rules(result))

    def test_tavan_asilirsa_dogrulama(self):
        result = review("metin #a #b #c #d #e #f")
        self.assertIn("hashtag tavanı", rules(result))

    def test_tavan_altinda_bulgu_yok(self):
        self.assertTrue(review("metin #bakim #cilt").clean)


class CiktiSozlesmesiTests(unittest.TestCase):
    """Tarayıcı asla 'uygun' demez — bu sınıf o sınırı sabitler."""

    def test_temiz_metin_bile_insan_onayi_ister(self):
        payload = review("Hafif dokulu bir üründür.").to_dict()
        self.assertTrue(payload["clean_tier1"])
        self.assertTrue(payload["approval_required"])

    def test_yalnizca_blocked_ve_verify_uretilir(self):
        text = ("Dolaşımı destekler. 14 günde sonuç. Paraben içermez. "
                "Doktor formülü. #akne")
        for finding in review(text).findings:
            self.assertIn(finding.label, (BLOCKED, VERIFY))

    def test_her_bulgu_dayanak_tasir(self):
        for finding in review("Egzamayı tedavi eder.").findings:
            self.assertTrue(finding.basis)
            self.assertTrue(finding.remedy)

    def test_kural_kaynagi_raporlanir(self):
        self.assertIn("03_MEVZUAT_KURALLARI", review("metin").rules_source)

    def test_ayni_bulgu_tekrarlanmaz(self):
        result = review("Dolaşımı destekler. Dolaşımı destekler.")
        keys = [(f.rule, f.matched, f.sentence) for f in result.findings]
        self.assertEqual(len(keys), len(set(keys)))


class OnayKaydiTests(unittest.TestCase):
    """Belge §9 — kayıt, tarama sonucunun yerine geçmez."""

    def test_insan_alanlari_bos_birakilir(self):
        record = approval_record("IC-001", "SUNACNEA", "reel",
                                 review("Hafif dokulu ürün.", checked_at="2026-09-19"))
        self.assertEqual(record["onaylayan"], "INSAN DOLDURUR")
        self.assertEqual(record["iddianin_dayandigi_belge"], "INSAN DOLDURUR")

    def test_bloklu_metin_yayin_durumu(self):
        record = approval_record("IC-002", "VIREON", "katalog",
                                 review("Dolaşımı destekler."))
        self.assertEqual(record["yayin_durumu"], "BLOCKED")

    def test_temiz_metin_bile_pending_kalir(self):
        record = approval_record("IC-003", "LIFTELLE", "site",
                                 review("Hafif dokulu ürün."))
        self.assertEqual(record["yayin_durumu"], "PENDING_HUMAN_REVIEW")


class CumleAyirmaTests(unittest.TestCase):
    def test_cumleler_ayrilir(self):
        self.assertEqual(len(sentences("Bir. İki! Üç?")), 3)

    def test_bos_metin_cokmez(self):
        self.assertTrue(review("").clean)


if __name__ == "__main__":
    unittest.main()
