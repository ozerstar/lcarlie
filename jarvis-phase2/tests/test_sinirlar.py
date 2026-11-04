"""Kısaltma sessiz olmamalı ve teslimin sonucunu atmamalı (04.11 ölçümleri)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from jarvis import sinirlar


class SinirlarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.onceki = os.environ.get("JARVIS_STATE_DIR")
        os.environ["JARVIS_STATE_DIR"] = self.tmp.name
        self.addCleanup(lambda: os.environ.__setitem__("JARVIS_STATE_DIR", self.onceki)
                        if self.onceki is not None else os.environ.pop("JARVIS_STATE_DIR", None))

    def test_sigan_metne_dokunmaz(self):
        self.assertEqual(sinirlar.kisalt("kısa", 100, ne="t"), "kısa")
        self.assertFalse((Path(self.tmp.name) / "kesinti.jsonl").exists())

    def test_kisaltma_sinira_uyar_not_duser_ve_kaydeder(self):
        metin = "\n\n".join(f"Paragraf {i}: " + "x" * 300 for i in range(20))
        k = sinirlar.kisalt(metin, 2000, ne="oneri", isaret="teslim.X")
        self.assertLessEqual(len(k), 2000)
        self.assertIn("kısaltıldı", k)
        self.assertIn("teslim.X", k)
        kayit = [json.loads(x) for x in (Path(self.tmp.name) / "kesinti.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kayit[0]["ne"], "oneri")
        self.assertEqual(kayit[0]["orijinal"], len(metin))

    def test_teslim_ozu_sonucu_ve_karari_korur(self):
        md = ("# Teslim: Karar notu\n- Görev: X\n\n## Özet\nKısa özet.\n\n## İçerik\n"
              + "### 1) Bulgular\n" + "bulgu satırı\n" * 400
              + "### 3) Kasım için 5 karar\n1. Bütçeyi satın alma hedefine çevir\n"
              + "## Kullanılan kanıt\n- K1\n")
        oz = sinirlar.teslim_ozu(md, 1500, ne="kurul.teslim")
        self.assertLessEqual(len(oz), 1500)
        self.assertTrue(oz.startswith("# Teslim: Karar notu"))
        self.assertIn("Kısa özet.", oz)
        self.assertIn("Bütçeyi satın alma hedefine çevir", oz)

    def test_db_sinirlari_veritabanindaki_degerle_ayni(self):
        # core.ai_propose_action REQUEST_HUMAN_REVIEW: length(reason) > 2000 -> RAISE (canlıda okundu 04.11)
        self.assertEqual(sinirlar.DB_SINIR["oneri_sebebi"], 2000)


if __name__ == "__main__":
    unittest.main()
