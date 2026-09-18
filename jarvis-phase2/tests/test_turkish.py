"""Turkish layer: the guarantee is that it degrades, never that it is present.

The suite runs on the system interpreter, where zeyrek is not installed, so
these assert the contract on both sides of that line rather than assuming one.
"""
from __future__ import annotations

import unittest

from jarvis import turkish


class TokenisationTests(unittest.TestCase):
    def test_words_are_whole_tokens(self):
        self.assertEqual(["Nasılsın", "bugün"], turkish.words("Nasılsın, bugün?"))

    def test_punctuation_and_digits_survive_sensibly(self):
        self.assertEqual(["Vireon", "fiyatını", "1300", "TL", "yap"],
                         turkish.words("Vireon fiyatını 1300 TL yap."))


class DeasciifierTests(unittest.TestCase):
    def test_returns_input_unchanged_when_unavailable(self):
        result = turkish.deasciify("kampanyayi kapat")
        if turkish.DEASCIIFIER_AVAILABLE:
            self.assertEqual("kampanyayı kapat", result)
        else:
            self.assertEqual("kampanyayi kapat", result)

    def test_text_that_already_has_turkish_letters_is_left_alone(self):
        self.assertEqual("kampanyayı kapat", turkish.deasciify("kampanyayı kapat"))

    def test_empty_input_is_safe(self):
        self.assertEqual("", turkish.deasciify(""))


class MorphologyTests(unittest.TestCase):
    STEMS = frozenset(("yap", "gönder", "kaldır", "artır", "kapat", "yayınla"))

    def test_absence_is_reported_as_none_not_as_false(self):
        """A caller must be able to tell "not a command" from "cannot tell",
        because the first is an answer and the second means fall back."""
        if turkish.MORPHOLOGY_AVAILABLE:
            self.skipTest("morphology present on this interpreter")
        self.assertIsNone(turkish.imperative_stem("yap"))
        self.assertIsNone(turkish.is_imperative_of("yap", self.STEMS))

    def test_imperative_is_separated_from_ability(self):
        if not turkish.MORPHOLOGY_AVAILABLE:
            self.skipTest("morphology not installed on this interpreter")
        self.assertTrue(turkish.is_imperative_of("yap", self.STEMS))
        self.assertTrue(turkish.is_imperative_of("güncelleyin", frozenset(("güncelle",))))
        # the whole point: same stem, not an instruction
        self.assertFalse(turkish.is_imperative_of("yapabiliyoruz", self.STEMS))
        self.assertFalse(turkish.is_imperative_of("kaldırabilir", self.STEMS))
        self.assertFalse(turkish.is_imperative_of("yapmalıyız", self.STEMS))

    def test_a_negative_imperative_is_a_prohibition_not_a_command(self):
        if not turkish.MORPHOLOGY_AVAILABLE:
            self.skipTest("morphology not installed on this interpreter")
        self.assertFalse(turkish.is_imperative_of("yapmayın", self.STEMS))
        self.assertFalse(turkish.is_imperative_of("yayınlama", self.STEMS))

    def test_unrelated_words_are_not_commands(self):
        if not turkish.MORPHOLOGY_AVAILABLE:
            self.skipTest("morphology not installed on this interpreter")
        for word in ("nasılsın", "indirim", "merhaba"):
            self.assertFalse(turkish.is_imperative_of(word, self.STEMS), word)

    def test_status_is_reported(self):
        status = turkish.status()
        self.assertIn("morphology", status)
        self.assertIn("deasciifier", status)


if __name__ == "__main__":
    unittest.main()
