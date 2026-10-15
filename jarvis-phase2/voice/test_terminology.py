import unittest

from terminology import NAMES, whisper_options


class TerminologyTests(unittest.TestCase):
    def test_reviewed_names_are_passed_as_context_and_hotwords(self):
        options = whisper_options()
        self.assertEqual(set(options), {"initial_prompt", "hotwords"})
        for name in ("Jarvis", "L'CARLIE", "HYDRAVIE", "BABYSOFT"):
            self.assertIn(name, NAMES)
            self.assertIn(name, options["initial_prompt"])
            self.assertIn(name, options["hotwords"])


if __name__ == "__main__":
    unittest.main()
