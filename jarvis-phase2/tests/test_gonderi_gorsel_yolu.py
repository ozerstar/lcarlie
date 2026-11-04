"""Üretilen görsel adresi: Türkçe harfli ad URL'den kodlu gelir (04.11: hepsi 404 veriyordu)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webconsole"))

import katalog  # noqa: E402


class GonderiGorselYoluTest(unittest.TestCase):
    def test_kodlu_turkce_ad_bulunur_kacis_reddedilir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "l-carlié-mat-çantası-kare-20261103T073946.jpg").write_bytes(b"x")
            with mock.patch.object(katalog, "GONDERI_DIZIN", Path(d)):
                yol = katalog.gonderi_gorsel_yolu("l-carli%C3%A9-mat-%C3%A7antas%C4%B1-kare-20261103T073946.jpg")
                self.assertTrue(yol.is_file())
                with self.assertRaises(katalog.KatalogHatasi):
                    katalog.gonderi_gorsel_yolu("%2E%2E%2Fsecret.jpg")


if __name__ == "__main__":
    unittest.main()
