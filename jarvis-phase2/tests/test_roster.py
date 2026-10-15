"""Ekip listesi ve görüşleri. Ağ yok, veritabanı yok, model yok.

Sınanan asıl davranış: verisi olmayan üye SUSMALI, uydurmamalı. Paneli dolu
göstermek için yazılmış bir cümle, boş bir satırdan kötüdür.
"""
import unittest
from unittest.mock import patch

from jarvis import roster


class SahteMemory:
    def __init__(self, veri=None, patlayan=()):
        self.veri = veri or {}
        self.patlayan = set(patlayan)
        self.cagrilar = []

    def _fetch(self, query):
        self.cagrilar.append(query)
        if query in self.patlayan:
            raise RuntimeError("izin yok")

        class Ev:
            records = self.veri.get(query, [])
        return Ev()


SATIS = {
    "sales_orders": [{"olcumde": False, "kanal": "WEB",
                      "ciro_beyan_edilmis_net": 1000}] * 3,
    "sales_items": [{"adet": 2, "satir_ciro_net": 500, "urun_adi": "VIREON (Krem)"},
                    {"adet": 1, "satir_ciro_net": 100, "urun_adi": "HYDRAVIE (Krem)"}],
}
REKLAM = {"advertising_performance": [
    {"pencere": 30, "harcama": 100, "gosterim": 1000, "tiklama": 50,
     "ad_adi": "K7", "kampanya_adi": "Kampanya A", "erisim": 800,
     "ctr_yuzde": 5.0, "commercial_confirmation": "CONFIRMED",
     "etkin_durum": "ACTIVE"},
    {"pencere": 30, "harcama": 50, "gosterim": 2000, "tiklama": 10,
     "ad_adi": "V-K1", "kampanya_adi": "Kampanya B", "erisim": 200,
     "ctr_yuzde": 0.5, "commercial_confirmation": "NONE",
     "meta_gelir_iddiasi": 900, "etkin_durum": "PAUSED"},
]}


class ListeTests(unittest.TestCase):
    def test_her_uyenin_turkce_adi_ve_gorevi_var(self):
        for uye in roster.ROSTER:
            self.assertTrue(uye.name.strip(), uye.key)
            self.assertTrue(uye.job.strip().endswith("."), uye.key)

    def test_kimlikler_benzersiz(self):
        anahtarlar = [u.key for u in roster.ROSTER]
        self.assertEqual(len(anahtarlar), len(set(anahtarlar)))

    def test_ajans_rolleri_de_listede(self):
        ajans = [u for u in roster.ROSTER if u.kind == "agency"]
        self.assertEqual(8, len(ajans))


class DurustlukTests(unittest.TestCase):
    def test_canonical_data_source_is_attached_as_evidence(self):
        class CanonicalMemory(SahteMemory):
            def _fetch(self, query):
                records = self.veri.get(query, [])
                return type("Evidence", (), {"records": records, "source": f"postgres:{query}",
                                             "authority": "CANONICAL_COMPANY_MEMORY"})()

        opinion = roster.opinions(CanonicalMemory(SATIS), only=("ecommerce_sales",))[0]
        self.assertEqual(roster.SPEAKS, opinion["status"])
        self.assertEqual({"postgres:sales_orders", "postgres:sales_items"}, set(opinion["evidence_refs"]))

    def test_one_speaker_failure_does_not_hide_other_members(self):
        def broken(rows):
            raise RuntimeError("not for display")

        with patch.dict(roster.SPEAKERS, {"ecommerce_sales": broken}):
            opinions = roster.opinions(SahteMemory(SATIS), only=("ecommerce_sales", "field_b2b_sales"))
        by_key = {opinion["key"]: opinion for opinion in opinions}
        self.assertEqual(roster.ISLEM_HATASI, by_key["ecommerce_sales"]["status"])
        self.assertEqual("RuntimeError", by_key["ecommerce_sales"]["statement"])
        self.assertEqual(roster.SPEAKS, by_key["field_b2b_sales"]["status"])

    def test_arastirma_uyesi_veriden_konusmaz(self):
        """Dış kaynak gerektiren üye şirket verisinden konuşuyormuş gibi
        yapmamalı."""
        out = roster.opinions(SahteMemory(), only=("market_intelligence",))
        self.assertEqual(roster.NEEDS_RESEARCH, out[0]["status"])

    def test_sentez_uyesi_girdi_bekledigini_soyler(self):
        out = roster.opinions(SahteMemory(), only=("red_team",))
        self.assertEqual(roster.NEEDS_INPUT, out[0]["status"])

    def test_veri_okunamazsa_hangi_sorgu_oldugu_yazilir(self):
        out = roster.opinions(SahteMemory(patlayan=("financial",)),
                              only=("finance",))
        self.assertEqual(roster.NO_DATA, out[0]["status"])
        self.assertIn("financial", out[0]["statement"])

    def test_hicbir_uye_model_cagirmaz(self):
        for kayit in roster.opinions(SahteMemory(SATIS)):
            self.assertEqual(0, kayit["model_calls"])


class GorusTests(unittest.TestCase):
    def test_satis_gercek_rakami_verir(self):
        out = roster.opinions(SahteMemory(SATIS), only=("ecommerce_sales",))
        self.assertIn("3 adet", out[0]["statement"])
        self.assertIn("600", out[0]["statement"])

    def test_olcum_penceresi_sifir_gostermez(self):
        """Ölçüm dışı satış 'satış yok' gibi okunmamalı."""
        metin = roster.opinions(SahteMemory(SATIS),
                                only=("ecommerce_sales",))[0]["statement"]
        self.assertIn("satışlar yine de gerçek", metin)

    def test_en_cok_ciro_yapan_urun_adlandirilir(self):
        metin = roster.opinions(SahteMemory(SATIS),
                                only=("ecommerce_sales",))[0]["statement"]
        self.assertIn("VIREON", metin)

    def test_kreatif_en_iyi_ve_en_kotuyu_karsilastirir(self):
        metin = roster.opinions(SahteMemory(REKLAM),
                                only=("creative_intelligence",))[0]["statement"]
        self.assertIn("K7", metin)
        self.assertIn("V-K1", metin)

    def test_olcum_uzmani_dogrulama_oranini_soyler(self):
        metin = roster.opinions(SahteMemory(REKLAM),
                                only=("data_measurement",))[0]["statement"]
        self.assertIn("1", metin)
        self.assertIn("iddia", metin)

    def test_ayni_veriyi_okuyan_uyeler_farkli_sey_soyler(self):
        """Dört üye aynı görünümü okur ama aynı cümleyi kurmamalı."""
        kimler = ("meta_performance", "creative_intelligence",
                  "social_media", "data_measurement")
        cumleler = [o["statement"] for o in
                    roster.opinions(SahteMemory(REKLAM), only=kimler)]
        self.assertEqual(len(cumleler), len(set(cumleler)))

    def test_bos_veride_cokmez(self):
        for kayit in roster.opinions(SahteMemory({})):
            self.assertTrue(kayit["statement"].strip())


class YeniBirimTests(unittest.TestCase):
    def test_yeni_birimler_rol_ve_sorumlu_sahibi(self):
        codes = ("CS", "CUSTOMER_INT", "EXPERIMENT", "DECISION_MEM",
                 "INSTAGRAM", "INVENTORY", "UGC", "RND")
        for code in codes:
            members = roster.departman_uyeleri()[code]
            self.assertEqual(1, len(members), code)
            self.assertEqual(members[0], roster.departman_sorumlusu(code))
            self.assertIn(members[0].key, roster.SPEAKERS)
        self.assertEqual((), roster.eslenmeyen_uyeler())

    def test_kaynak_bossa_aktif_gorunmez(self):
        for key in ("musteri_hizmetleri", "musteri_istihbarati", "deney_izleme",
                    "karar_hafizasi", "instagram_olcum", "stok_kapsama",
                    "video_brief", "yeni_urun_on_arastirma"):
            opinion = roster.opinions(SahteMemory(), only=(key,))[0]
            self.assertEqual(roster.NO_DATA, opinion["status"], key)

    def test_musteri_hizmetleri_yanit_gondermez(self):
        opinion = roster.opinions(SahteMemory({
            "crm_unanswered": [{"bekleme_saat": 6}],
            "urun_bilgi": [{"urun_adi": "Örnek"}],
        }), only=("musteri_hizmetleri",))[0]
        self.assertEqual(roster.SPEAKS, opinion["status"])
        self.assertIn("1 yanıtsız", opinion["statement"])
        self.assertIn("Yanıt gönderilmedi", opinion["statement"])

    def test_stok_wix_ile_fiziksel_envanteri_ayirir(self):
        opinion = roster.opinions(SahteMemory({"urun_bilgi": [
            {"wix_stok": 0}, {"wix_stok": None}, {"wix_stok": 3},
        ]}), only=("stok_kapsama",))[0]
        self.assertIn("1 ürünün Wix stok değeri yok", opinion["statement"])
        self.assertIn("fiziksel depo", opinion["statement"])

    def test_instagram_erisim_olmadan_oran_iddia_etmez(self):
        opinion = roster.opinions(SahteMemory({"content_performance": [
            {"etkilesim": 18, "bicim": "reels"},
        ]}), only=("instagram_olcum",))[0]
        self.assertIn("18 etkileşim", opinion["statement"])
        self.assertIn("oranı hesaplanmadı", opinion["statement"])


if __name__ == "__main__":
    unittest.main()
