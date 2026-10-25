import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.image_team import ask


JOB = {"id": "a" * 32, "sha256": "b" * 64,
       "report": {"product_count": 39, "image_count": 195, "problems": []}}


class TeamBriefTest(unittest.TestCase):
    def test_uses_only_pack_evidence(self):
        with patch("jarvis.model_layer.ModelRouter.synthesize", return_value=SimpleNamespace(
                answer="39 ürün ve 195 görsel doğrulandı. Görsel içerik incelenmeli.")) as call:
            result = ask("TASARIM", JOB)
        self.assertTrue(result["model_kullanildi"])
        self.assertEqual([], result["dogrulanmayan_sayilar"])
        self.assertEqual(1, len(call.call_args.args[1]))
        self.assertIn("pikselleri", call.call_args.args[1][0]["summary"])

    def test_unsupported_numeric_claim_is_reported(self):
        with patch("jarvis.model_layer.ModelRouter.synthesize", return_value=SimpleNamespace(
                answer="80 puan verdim.")):
            result = ask("WEB", JOB)
        self.assertEqual(["80"], result["dogrulanmayan_sayilar"])


if __name__ == "__main__":
    unittest.main()
