"""Is uretici yonlendiricisi: ucretli son care yalniz Gemini kademesi."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import yerel_model  # noqa: E402


class SahteSaglayicilar:
    PROVIDERS = []

    def __init__(self):
        self.cagri = None

    def generate(self, mesajlar, **kw):
        self.cagri = kw
        return {"text": "{}", "provider": "gemini"}


class UcretliYedekTesti(unittest.TestCase):
    def calistir(self, ucretli, **kw):
        prov = SahteSaglayicilar()
        with patch.object(yerel_model, "URLLER", []), \
             patch.dict(os.environ, {"IS_URETICI_UCRETLI": ucretli}):
            uret = yerel_model.yonlendirici(prov)
            return prov, uret([{"role": "user", "content": "x"}], **kw)

    def test_guclu_is_bile_gemini_kademesine_gider(self):
        prov, sonuc = self.calistir("true", kademe="muhakeme", is_anahtari="rakip-sentez")
        self.assertEqual(prov.cagri["kademe"], "hizli")
        self.assertEqual(sonuc["provider"], "gemini")

    def test_kapaliyken_ucretliye_gitmez(self):
        with self.assertRaises(RuntimeError):
            self.calistir("false", is_anahtari="haftalik")


if __name__ == "__main__":
    unittest.main()
