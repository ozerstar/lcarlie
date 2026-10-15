import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mesaj-siniflandir.py"
SPEC = importlib.util.spec_from_file_location("mesaj_siniflandir_script", SCRIPT)
classifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classifier)


class PsqlOutputTests(unittest.TestCase):
    def test_json_text_with_unicode_line_separator_is_one_record(self):
        records = [
            {"id": 1, "metin": "ilk satır\u2028ikinci satır"},
            {"id": 2, "metin": "başka mesaj"},
        ]
        output = "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"
        result = subprocess.CompletedProcess([], 0, stdout=output, stderr="")
        with patch.object(classifier.subprocess, "run", return_value=result):
            self.assertEqual(records, classifier.oku(False))


if __name__ == "__main__":
    unittest.main()
