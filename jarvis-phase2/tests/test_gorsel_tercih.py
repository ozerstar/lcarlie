"""Beğenilmeyen görsel nedenleri yeni ChatGPT görsel istemine girer (sahip 05.11.2026)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis import gorsel_tercih, tarayici  # noqa: E402

SATIRLAR = [{"tur": "neden", "metin": "Yapay / plastik görünüyor", "adet": 4},
            {"tur": "neden", "metin": "Logo veya yazı hatalı", "adet": 2},
            {"tur": "yorum", "metin": "şişe   beyaz değil krem çıkmış", "adet": 1}]


class KacinilacaklarMetni(unittest.TestCase):
    def test_nedenler_ve_yorumlar_bloga_girer(self):
        blok = gorsel_tercih.kacinilacaklar_metni(SATIRLAR)
        self.assertIn("do NOT repeat", blok)
        self.assertIn("- Yapay / plastik görünüyor (4 kez)", blok)
        self.assertIn('"şişe beyaz değil krem çıkmış"', blok)

    def test_veri_yoksa_bos(self):
        self.assertEqual(gorsel_tercih.kacinilacaklar_metni([]), "")

    def test_blok_siniri_asmaz(self):
        uzun = [{"tur": "yorum", "metin": "x" * 220, "adet": 1}] * 30
        self.assertLessEqual(len(gorsel_tercih.kacinilacaklar_metni(uzun)), gorsel_tercih.EN_COK_BLOK)

    def test_okuma_hatasi_uretimi_durdurmaz(self):
        with mock.patch.object(gorsel_tercih, "db_run", side_effect=OSError("docker yok")):
            self.assertEqual(gorsel_tercih.kacinilacaklar_metni(), "")


class IstemeEklenir(unittest.TestCase):
    def _ekle(self, hedef, istem="Create a premium skincare image of the product."):
        with mock.patch("jarvis.gorsel_tercih.kacinilacaklar_metni", return_value="OWNER'S IMAGE FEEDBACK — x"), \
             mock.patch.object(tarayici, "_psql", return_value=["7"]) as psql, \
             mock.patch.object(tarayici, "_girdi_dogrula", return_value=[]):
            tarayici.enqueue_browser_task(istem, hedef, idempotency_key="test:gorsel:0001")
        return psql.call_args.kwargs["degiskenler"]["istem"]

    def test_gorsel_isine_eklenir(self):
        self.assertIn("OWNER'S IMAGE FEEDBACK", self._ekle("chatgpt_image"))

    def test_sohbet_isine_eklenmez(self):
        self.assertNotIn("OWNER'S IMAGE FEEDBACK", self._ekle("claude_chat"))

    def test_ust_siniri_asmaz(self):
        istem = "y" * (tarayici.EN_COK_ISTEM - 100)
        self.assertLessEqual(len(self._ekle("chatgpt_image", istem)), tarayici.EN_COK_ISTEM)


if __name__ == "__main__":
    unittest.main()
