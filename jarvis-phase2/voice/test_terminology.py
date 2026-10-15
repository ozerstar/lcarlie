import unittest

from terminology import NAMES, normalize_transcript, whisper_options


class TerminologyTests(unittest.TestCase):
    def test_reviewed_names_are_passed_as_context_and_hotwords(self):
        options = whisper_options()
        self.assertEqual(set(options), {"initial_prompt", "hotwords"})
        for name in ("Jarvis", "L'CARLIE", "HYDRAVIE", "BABYSOFT"):
            self.assertIn(name, NAMES)
            self.assertIn(name, options["initial_prompt"])
            self.assertIn(name, options["hotwords"])

    def test_only_observed_distinctive_variants_are_corrected(self):
        self.assertEqual(
            normalize_transcript("Lecerle için HIDRAVU satışlarını göster."),
            "L'CARLIE için HYDRAVIE satışlarını göster.",
        )
        self.assertEqual(
            normalize_transcript("Hızlı kargo ve hidrolik pompa hakkında konuş."),
            "Hızlı kargo ve hidrolik pompa hakkında konuş.",
        )


if __name__ == "__main__":
    unittest.main()
