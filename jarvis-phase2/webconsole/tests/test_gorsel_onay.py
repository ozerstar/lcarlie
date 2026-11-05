"""Görsel onayları: yalnız Jarvis'in ürettiği görseller sorulur, ret nedensiz kaydedilmez."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gorsel_onay  # noqa: E402


class Adaylar(unittest.TestCase):
    def setUp(self):
        self.kok = Path(tempfile.mkdtemp())
        self.tar, self.kre, ig = self.kok / "tarayici", self.kok / "kreatif", self.kok / "ig"
        (self.tar / "tarayici-21-dosyalar").mkdir(parents=True)
        for ad in ("gorsel-1.png", "ekran-21.png"):
            (self.tar / "tarayici-21-dosyalar" / ad).write_bytes(b"x")
        (self.tar / "tarayici-21.json").write_text(json.dumps({"slug": "tarayici-21", "is_id": 21, "hedef": "chatgpt_image",
            "istem": "IMAGE 1", "dosyalar": ["gorsel-1.png", "ekran-21.png", "EKSIK:gorsel-2.png"]}), encoding="utf-8")
        (self.kre / "hydravie-1-gorseller" / "etiket-kontrol").mkdir(parents=True)
        (self.kre / "hydravie-1-gorseller" / "01-4x5.jpg").write_bytes(b"x")
        (self.kre / "hydravie-1-gorseller" / "etiket-kontrol" / "01.jpg").write_bytes(b"x")
        ig.mkdir()
        (ig / "jarvis-gpt-web-vireon-12.jpg").write_bytes(b"x")
        (ig / "babysoft-reels-1.jpg").write_bytes(b"x")
        self.yama = mock.patch.object(gorsel_onay, "IG_DIR", ig)
        self.yama.start()

    def tearDown(self):
        self.yama.stop()

    def test_yalniz_uretilen_gorseller_sorulur(self):
        anahtarlar = set(gorsel_onay._adaylar(self.tar, self.kre))
        self.assertEqual(anahtarlar, {"tarayici/tarayici-21-dosyalar/gorsel-1.png",
                                      "kreatif/hydravie-1-gorseller/01-4x5.jpg",
                                      "gonderi-gorsel/jarvis-gpt-web-vireon-12.jpg"})

    def test_bilinmeyen_gorsel_ve_nedensiz_ret_reddedilir(self):
        with self.assertRaises(gorsel_onay.OnayHatasi):
            gorsel_onay.karar_ver("ozer", {"anahtar": "../../etc/passwd", "karar": "BEGENDI"}, self.tar, self.kre)
        with self.assertRaises(gorsel_onay.OnayHatasi):
            gorsel_onay.karar_ver("ozer", {"anahtar": "kreatif/hydravie-1-gorseller/01-4x5.jpg", "karar": "BEGENMEDI"},
                                  self.tar, self.kre)
        with self.assertRaises(gorsel_onay.OnayHatasi):
            gorsel_onay.karar_ver("ozer", {"anahtar": "kreatif/hydravie-1-gorseller/01-4x5.jpg", "karar": "BEGENMEDI",
                                           "nedenler": ["uydurma neden"]}, self.tar, self.kre)

    def test_gecerli_ret_kaydedilir(self):
        cur = mock.MagicMock()
        baglanti = mock.MagicMock()
        baglanti.__enter__.return_value.cursor.return_value.__enter__.return_value = cur
        with mock.patch.object(gorsel_onay, "_connect", return_value=baglanti):
            sonuc = gorsel_onay.karar_ver("ozer", {"anahtar": "kreatif/hydravie-1-gorseller/01-4x5.jpg", "karar": "BEGENMEDI",
                                                   "nedenler": ["Logo veya yazı hatalı"], "yorum": " logo  bulanık "}, self.tar, self.kre)
        self.assertEqual(sonuc["karar"], "BEGENMEDI")
        parametreler = cur.execute.call_args[0][1]
        self.assertEqual(parametreler[0], "kreatif")
        self.assertEqual(parametreler[4], ["Logo veya yazı hatalı"])
        self.assertEqual(parametreler[5], "logo bulanık")


if __name__ == "__main__":
    unittest.main()
