"""Imla kapisi: gercek hatayi yakalar, mesru kelimeyi yakalamaz."""
from tests import betik_yolu
import importlib.util
import sys
import shutil
import subprocess
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("kb", betik_yolu("kreatif-brief.py"))
kb = importlib.util.module_from_spec(spec)
sys.argv = ["kb"]
spec.loader.exec_module(kb)

YAKALANMALI = [
    ("nazik bakımlaşır", "bakımlaşır"),
    ("Aaa kızlar şunayem değil mi", "şunayem"),
    ("saç titleri akademisi", "titleri"),
]
YAKALANMAMALI = [
    "Tarak daha rahat geçiyor",
    "Durulama gerektirmez",
    "EASYCOMB saç bakım spreyi",
    "Cildim sabah daha bakımlı görünüyor",
    "Nemli veya kuru saça 15-20 cm mesafeden püskürtünüz",
    "Aloe vera ve jojoba yağı içerir",
    "Günlük bakım rutinime ekledim",
]

import unittest as _unittest


class DenetimSonucu(_unittest.TestCase):
    """Keep real dictionary validation distinct from the portable parser test."""

    @_unittest.skipUnless(shutil.which("hunspell"), "hunspell integration unavailable")
    def test_butun_denetimler_gecti(self):
        for cumle, beklenen in YAKALANMALI:
            with self.subTest(cumle=cumle):
                self.assertIn(beklenen, kb.imla_denetimi([cumle]))
        for cumle in YAKALANMAMALI:
            with self.subTest(cumle=cumle):
                self.assertEqual(kb.imla_denetimi([cumle]), [])

    def test_hunspell_output_filter_contract(self):
        output = "bakımlaşır\nşunayem\ntitleri\nEASYCOMB\ndan\nbakımlaşır\n"
        result = subprocess.CompletedProcess([], 0, output.encode(), b"")
        with patch("shutil.which", return_value="/test/hunspell"), \
                patch("subprocess.run", return_value=result) as run:
            self.assertEqual(kb.imla_denetimi(["sample"]),
                             ["bakımlaşır", "şunayem", "titleri"])
            self.assertEqual(run.call_args.args[0][:4],
                             ["hunspell", "-d", "tr_TR", "-l"])

    def test_unavailable_checker_is_not_a_linguistic_pass(self):
        with patch("shutil.which", return_value=None), patch("subprocess.run") as run:
            self.assertEqual(kb.imla_denetimi(["bakımlaşır"]), [])
            run.assert_not_called()


if __name__ == "__main__":
    _unittest.main()
