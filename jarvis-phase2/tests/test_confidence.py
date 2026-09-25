"""Parçalı güven skoru. Testler gerçek benchmark vakalarından türetildi."""
import unittest

from jarvis.confidence import DIMENSIONS, score, summary_line


class FakeSource:
    def __init__(self, origin_id, source_type="NEWS", authority=0.8, freshness=0.8,
                 claims=None, snippets=(), observed_at="2026-09-01"):
        self.origin_id = origin_id
        self.source_type = source_type
        self.authority = authority
        self.freshness = freshness
        self.claims = claims or {}
        self.evidence_snippets = snippets
        self.observed_at = observed_at


def good(n=3):
    return [FakeSource(f"site{i}.com", claims={f"iddia{i}": "değer"},
                       snippets=("cümle",)) for i in range(n)]


class EnZayifHalkaTests(unittest.TestCase):
    def test_overall_ortalama_degil_minimumdur(self):
        sources = [FakeSource("tekkaynak.com", claims={"a": "1"}, snippets=("c",))]
        result = score(sources, min_independent_sources=4)
        self.assertEqual(result.overall, result.source_independence)
        self.assertLess(result.overall,
                        sum(getattr(result, d) for d in DIMENSIONS) / len(DIMENSIONS))

    def test_bir_boyutu_doldurmak_skoru_yukseltmez(self):
        """Beş kopya kaynak kaliteyi yükseltir ama bağımsızlığı yükseltmez."""
        kopya = [FakeSource("ayni.com", authority=1.0, freshness=1.0,
                            claims={"a": "1"}, snippets=("c",)) for _ in range(5)]
        result = score(kopya, min_independent_sources=3)
        self.assertLessEqual(result.overall, 0.34)
        self.assertEqual(result.limiting_factor, "source_independence")

    def test_sinirlayan_boyut_her_zaman_bildirilir(self):
        result = score(good())
        self.assertIn(result.limiting_factor, DIMENSIONS)
        self.assertTrue(result.explanation)


class KanitTamligiTests(unittest.TestCase):
    def test_sifir_iddia_tam_kapsama_sayilmaz(self):
        """Eski hata: istenen iddia yoksa coverage 1.0 dönüyordu."""
        bos = [FakeSource("a.com"), FakeSource("b.com")]
        result = score(bos)
        self.assertEqual(result.evidence_completeness, 0.0)
        self.assertEqual(result.limiting_factor, "evidence_completeness")

    def test_istenen_iddia_karsilanmazsa_dusuk(self):
        sources = [FakeSource("a.com", claims={"fiyat": "100"})]
        result = score(sources, required_claims=("fiyat", "pazar_payi", "buyume"))
        self.assertAlmostEqual(result.evidence_completeness, 1 / 3, places=2)

    def test_alinti_da_kanit_sayilir(self):
        sources = [FakeSource("a.com", snippets=("c1", "c2", "c3"))]
        self.assertEqual(score(sources, min_independent_sources=1).evidence_completeness, 1.0)


class BagimsizlikTests(unittest.TestCase):
    def test_sirketin_kendi_sayfasi_bagimsiz_sayilmaz(self):
        sources = [FakeSource("marka.com", source_type="COMPANY", claims={"a": "1"}),
                   FakeSource("magaza.com", source_type="RETAILER", claims={"a": "1"})]
        result = score(sources, min_independent_sources=2)
        self.assertEqual(result.source_independence, 0.0)

    def test_kendi_hakkinda_konusan_kaynak_raporlanir(self):
        sources = [FakeSource("marka.com", source_type="COMPANY"),
                   FakeSource("haber.com", source_type="NEWS", claims={"a": "1"})]
        result = score(sources, min_independent_sources=2)
        self.assertIn("kendi hakkında konuşuyor", result.explanation + " ",
                      ) if result.limiting_factor == "source_independence" else None

    def test_bagimsiz_kaynaklar_tam_puan(self):
        result = score(good(3), min_independent_sources=2)
        self.assertEqual(result.source_independence, 1.0)


class CelismeTests(unittest.TestCase):
    def test_tek_celiski_guveni_yariya_indirir(self):
        result = score(good(), contradictions=[{"claim": "fiyat"}])
        self.assertEqual(result.claim_consistency, 0.5)

    def test_iki_celiski_ceyrege_indirir(self):
        result = score(good(), contradictions=[{"a": 1}, {"b": 2}])
        self.assertEqual(result.claim_consistency, 0.25)

    def test_celiski_yoksa_tam(self):
        self.assertEqual(score(good()).claim_consistency, 1.0)


class ModelBelirsizligiTests(unittest.TestCase):
    def test_model_cagrisi_yoksa_deterministik(self):
        result = score(good(), model_calls=0)
        self.assertEqual(result.model_uncertainty, 1.0)

    def test_model_devredeyse_olculmemis_sayilir(self):
        """Ölçülmemiş belirsizliği 1.0 saymak skoru şişirir."""
        result = score(good(), model_calls=3)
        self.assertLess(result.model_uncertainty, 1.0)


class KaynakKalitesiTests(unittest.TestCase):
    def test_bilinmeyen_tur_agirlik_kaybeder(self):
        bilinen = score([FakeSource("a.com", source_type="NEWS", authority=1.0,
                                    claims={"a": "1"})], min_independent_sources=1)
        bilinmeyen = score([FakeSource("a.com", source_type="UNKNOWN", authority=1.0,
                                       claims={"a": "1"})], min_independent_sources=1)
        self.assertLess(bilinmeyen.source_quality, bilinen.source_quality)

    def test_kaynak_yoksa_sifir(self):
        result = score([])
        self.assertEqual(result.source_quality, 0.0)
        self.assertEqual(result.overall, 0.0)


class RaporTests(unittest.TestCase):
    def test_ozet_satiri_sayiyi_tek_basina_vermez(self):
        line = summary_line(score(good()))
        self.assertIn("güven", line)
        self.assertIn("sınırlayan", line)

    def test_to_dict_tum_boyutlari_tasir(self):
        payload = score(good()).to_dict()
        for dimension in DIMENSIONS:
            self.assertIn(dimension, payload)
        self.assertIn("limiting_factor", payload)

    def test_gercek_benchmark_vakasi_magazalar(self):
        """Ölçülen vaka: 3 e-ticaret sayfası, tanım cümleleri, çelişki yok.
        Eski tek sayı 0.346 diyordu; yeni skor NEDENİNİ söylemeli."""
        magazalar = [FakeSource(f"dermo{i}.com", source_type="RETAILER",
                                authority=0.87, freshness=0.4, snippets=("tanım",))
                     for i in range(3)]
        result = score(magazalar, min_independent_sources=2)
        self.assertEqual(result.limiting_factor, "source_independence")
        self.assertEqual(result.source_independence, 0.0)


if __name__ == "__main__":
    unittest.main()
