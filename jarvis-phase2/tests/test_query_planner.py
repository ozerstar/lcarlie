"""Sorgu planlayıcı. Model yok, ağ yok -- doğrulama katmanı sınanır.

Buradaki çöp dizeler uydurma değil: 18 Eylül ölçümünde gerçek modelin
gerçek istek üzerinde ürettiği çıktılardır. Regresyon vakası olarak durur.
"""
import unittest

from jarvis import query_planner as qp

REQUEST = ("Türkiye premium dermokozmetik pazarındaki son gelişmeleri ve rakip "
           "markaların yeni ürün lansmanlarını araştır, önemli fiyat "
           "kampanyalarını da dahil et, bulguları kaynaklarıyla ve birbirinden "
           "bağımsız şekilde döndür")

# Olculen gercek cop cikti: gorev cumlesi, arama sorgusu degil.
OLCULEN_COP = (
    "Türkiye'de premium dermokozmetik pazarındaki son gelişmeleri araştır",
    "Rakip markaların yeni ürün lansmanlarını analiz et",
    "Önemli fiyat kampanyalarını tespit et",
    "Bulguları kaynaklarıyla ve bağımsız olarak döndür",
    "Bağımsız kaynaklardan intimet bakım ürünleri pazarı verilerini topla",
    "Kozmetik ürünlerde yasak iddiaların tespiti ve kaynakları",
)

# Olculen gercek iyi cikti: aranabilir.
OLCULEN_IYI = (
    "dermokozmetik pazari Turkiye 2026",
    "premium dermokozmetik yeni urun lansmani",
    "dermokozmetik fiyat kampanyasi eczane",
    "kozmetik urun etiketi yasak iddia",
    "TİTCK kozmetik iddia mevzuatı",
)


class TalimatTespitiTests(unittest.TestCase):
    def test_olculen_cop_talimat_sayilir(self):
        for cop in OLCULEN_COP:
            with self.subTest(cop=cop):
                self.assertTrue(qp.is_instruction(cop), cop)

    def test_olculen_iyi_talimat_sayilmaz(self):
        for iyi in OLCULEN_IYI:
            with self.subTest(iyi=iyi):
                self.assertFalse(qp.is_instruction(iyi), iyi)

    def test_isim_hali_mesru_sorgu(self):
        """'analiz et' talimat, 'pazar analizi' aranabilir bir terim.

        Ölçüldü: kökü toptan elemek iyi sorguları da eliyordu.
        """
        self.assertTrue(qp.is_instruction("rakip fiyatlarini analiz et"))
        self.assertFalse(qp.is_instruction("intim bakim pazar analizi"))
        self.assertFalse(qp.is_instruction("dermokozmetik urun incelemesi"))
        self.assertFalse(qp.is_instruction("kozmetik pazar arastirmasi raporu"))

    def test_kisa_kok_yanlis_eslesme_yapmaz(self):
        """'ara' kökü 'arasında' ve 'araç'ı yakalamamalı."""
        self.assertFalse(qp.is_instruction("kozmetik pazari 2020 2026 arasinda"))


class DogrulamaTests(unittest.TestCase):
    def test_uzun_cumle_elenir(self):
        uzun = "Turkiye de premium dermokozmetik pazarindaki son gelismeler ve rakipler"
        kabul, elenen = qp.validate([uzun], REQUEST)
        self.assertEqual(kabul, ())
        self.assertIn("kelime", elenen[0]["reason"])

    def test_konudan_sapan_elenir(self):
        kabul, elenen = qp.validate(["istanbul konut fiyatlari"], REQUEST)
        self.assertEqual(kabul, ())
        self.assertEqual(elenen[0]["reason"], "konudan sapmış")

    def test_konuyu_tasiyan_gecer(self):
        kabul, _ = qp.validate(["dermokozmetik pazari Turkiye"], REQUEST)
        self.assertEqual(kabul, ("dermokozmetik pazari Turkiye",))

    def test_tekrar_elenir(self):
        kabul, elenen = qp.validate(
            ["dermokozmetik pazari", "Dermokozmetik  Pazari"], REQUEST)
        self.assertEqual(len(kabul), 1)
        self.assertEqual(elenen[0]["reason"], "tekrar")

    def test_numara_ve_tire_temizlenir(self):
        kabul, _ = qp.validate(
            ["1. dermokozmetik pazari", '- "dermokozmetik lansman"'], REQUEST)
        self.assertEqual(kabul, ("dermokozmetik pazari", "dermokozmetik lansman"))

    def test_eleme_gerekcesi_dondurulur(self):
        """Sessiz eleme, hangi kuralın fazla sert olduğunu ölçülemez yapardı."""
        _, elenen = qp.validate(["kaynaklari dermokozmetik ile getir"], REQUEST)
        self.assertTrue(elenen and elenen[0]["reason"])

    def test_sinir_kelime_sayilari(self):
        self.assertEqual(qp.validate(["dermokozmetik"], REQUEST)[0], ())
        alti = "dermokozmetik pazari turkiye 2026 premium marka"
        self.assertEqual(qp.validate([alti], REQUEST)[0], (alti,))


class PlanTests(unittest.TestCase):
    class SahteRouter:
        def __init__(self, text=None, patlat=False):
            self.text, self.patlat = text, patlat

        def generate(self, messages, max_tokens, escalate=False):
            if self.patlat:
                raise RuntimeError("model yok")
            return {"text": self.text}, "LOCAL_GPU", 1

    def test_model_yoksa_deterministige_duser(self):
        out = qp.plan(REQUEST, None)
        self.assertEqual(out["source"], "deterministic")
        self.assertEqual(out["model_calls"], 0)
        self.assertTrue(out["queries"])

    def test_model_patlarsa_arastirma_durmaz(self):
        out = qp.plan(REQUEST, self.SahteRouter(patlat=True))
        self.assertEqual(out["source"], "deterministic")
        self.assertTrue(out["queries"])
        self.assertIn("başarısız", out["reason"])

    def test_cop_ciktida_deterministige_duser(self):
        out = qp.plan(REQUEST, self.SahteRouter("\n".join(OLCULEN_COP)))
        self.assertEqual(out["source"], "deterministic")
        self.assertEqual(out["queries"], tuple(out["fallback"]))
        self.assertTrue(out["rejected"])

    def test_temiz_ciktida_model_kullanilir(self):
        out = qp.plan(REQUEST, self.SahteRouter(
            "dermokozmetik pazari Turkiye\ndermokozmetik yeni urun lansmani"))
        self.assertEqual(out["source"], "model")
        self.assertEqual(len(out["queries"]), 2)

    def test_yedek_her_zaman_raporlanir(self):
        """Karşılaştırma yapılamazsa iyileştirme ölçülemez."""
        for router in (None, self.SahteRouter("dermokozmetik pazari Turkiye")):
            self.assertTrue(qp.plan(REQUEST, router)["fallback"])

    def test_bos_model_ciktisi_cokmez(self):
        out = qp.plan(REQUEST, self.SahteRouter(""))
        self.assertEqual(out["source"], "deterministic")

    def test_en_fazla_istenen_kadar_sorgu(self):
        out = qp.plan(REQUEST, self.SahteRouter("\n".join(OLCULEN_IYI[:3])),
                      max_queries=2)
        self.assertEqual(len(out["queries"]), 2)


if __name__ == "__main__":
    unittest.main()
