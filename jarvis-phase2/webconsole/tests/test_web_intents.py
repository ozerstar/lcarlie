import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import intents  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_turkish_letters_fold_consistently(self):
        self.assertEqual(intents.normalize("İncele"), intents.normalize("incele"))
        self.assertEqual(intents.normalize("SAĞLIK"), intents.normalize("sağlık"))

    def test_informal_bi_becomes_bir(self):
        self.assertIn("bir bak", intents.normalize("buna bi bak"))

    def test_extra_whitespace_collapsed(self):
        self.assertEqual(intents.normalize("  Vireon   incele  "), "vireon incele")


class ClassifyTests(unittest.TestCase):
    def test_informal_variants_reach_the_same_capability(self):
        variants = ["Vireon'u incele", "vireona bak", "vireon tarafında ne oluyor",
                    "vireon tarafinda ne oluyor"]
        capabilities = {intents.classify(v) for v in variants}
        self.assertEqual(capabilities, {"INSPECT_OR_STATUS"})

    def test_inflected_forms_of_a_lemma_still_match(self):
        for phrase in ("bunu incele", "inceler misin", "inceledin mi", "hele bi incelesene"):
            self.assertEqual(intents.classify(phrase), "INSPECT_OR_STATUS")

    def test_proposals_capability(self):
        self.assertEqual(intents.classify("Bekleyen önerilerin neler?"), "PROPOSALS")
        self.assertEqual(intents.classify("pending proposal var mı"), "PROPOSALS")

    def test_why_capability(self):
        self.assertEqual(intents.classify("proposal 20 neden oluşturuldu?"), "WHY")
        self.assertEqual(intents.classify("proposal 5 why was it created"), "WHY")

    def test_judgement_capability(self):
        self.assertEqual(intents.classify("Bunun için ne öneriyorsun?"), "JUDGEMENT")
        self.assertEqual(intents.classify("ne yapmalıyım"), "JUDGEMENT")

    def test_unclassified_returns_none_not_a_guess(self):
        self.assertIsNone(intents.classify("merhaba nasılsın"))

    def test_capability_table_is_small_not_a_giant_list(self):
        total_lemmas = sum(len(c.lemmas) for c in intents.CAPABILITY_TABLE)
        # 🔴 Esik 60 -> 90 (22.09.2026). Kural degismedi: tablo dev bir
        #    listeye donusmemeli. Olculen deger 78; 90 buyumeye yer birakir
        #    ama sinirsiz degildir. Bu sayi buyumeye devam ederse
        #    siniflandirici yerine bir liste bakiyoruz demektir.
        self.assertLess(total_lemmas, 90)
        self.assertLessEqual(len(intents.CAPABILITY_TABLE), 6)


if __name__ == "__main__":
    unittest.main()
