"""Model kullanım defteri. Ağ yok, model yok.

Sınanan asıl davranış: defter PARA TAHMİN ETMEZ ve cevabın METNİNİ
SAKLAMAZ. Birim fiyat zamanla değişir; koda sabit fiyat yazmak bir gün
sessizce yanlış rakam göstermek olurdu.
"""
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class UsageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["JARVIS_STATE_DIR"] = self._tmp.name
        from jarvis import usage
        self.usage = importlib.reload(usage)

    def tearDown(self):
        self._tmp.cleanup()

    # --- kayit
    def test_cagri_deftere_yazilir(self):
        self.usage.record("gemini", "flash", False, prompt_tokens=10,
                          completion_tokens=20, elapsed_s=0.5)
        self.assertEqual(1, self.usage.summary(1)["total_calls"])

    def test_metin_kaydedilmez(self):
        """Defter maliyet kaydıdır, konuşma arşivi değil."""
        self.usage.record("claude", "haiku", True, prompt_tokens=5,
                          completion_tokens=5)
        satir = json.loads(Path(self.usage.LEDGER).read_text(encoding="utf-8")
                           .splitlines()[0])
        for yasak in ("text", "answer", "content", "messages", "prompt"):
            self.assertNotIn(yasak, satir)

    def test_anahtar_kaydedilmez(self):
        self.usage.record("openai", "gpt", True)
        icerik = Path(self.usage.LEDGER).read_text(encoding="utf-8")
        for onek in ("sk-", "AIza", "gsk_"):
            self.assertNotIn(onek, icerik)

    # --- ozet
    def test_ucretli_cagri_ayri_sayilir(self):
        self.usage.record("gemini", "flash", False)
        self.usage.record("claude", "haiku", True)
        self.usage.record("openai", "gpt", True)
        ozet = self.usage.summary(1)
        self.assertEqual(3, ozet["total_calls"])
        self.assertEqual(2, ozet["paid_calls"])

    def test_token_toplanir(self):
        for _ in range(3):
            self.usage.record("gemini", "flash", False, prompt_tokens=10,
                              completion_tokens=5)
        kutu = self.usage.summary(1)["providers"][0]
        self.assertEqual(30, kutu["prompt_tokens"])
        self.assertEqual(15, kutu["completion_tokens"])

    def test_token_gelmeyen_cagri_kapsamada_gorunur(self):
        """Eksik veri tam veri gibi okunmamalı."""
        self.usage.record("x", "m", False, prompt_tokens=10, completion_tokens=5)
        self.usage.record("x", "m", False)   # token yok
        self.assertEqual("1/2", self.usage.summary(1)["providers"][0]["token_coverage"])

    def test_basarisiz_cagri_isaretlenir(self):
        self.usage.record("groq", "m", False, ok=False, error="HTTP 403")
        self.assertEqual(1, self.usage.summary(1)["providers"][0]["failed"])

    def test_para_tahmin_edilmez(self):
        """Birim fiyat zamanla değişir; sabit fiyat yazmak yanlış rakam üretir."""
        self.usage.record("claude", "haiku", True, prompt_tokens=1000,
                          completion_tokens=1000)
        ozet = self.usage.summary(1)
        icerik = json.dumps(ozet, ensure_ascii=False)
        for para in ("usd", "cost", "$", "tutar", "ücret_tl"):
            self.assertNotIn(para, icerik.casefold())
        self.assertIn("para tahmin etmez", ozet["note"].casefold())

    # --- dayaniklilik
    def test_eski_kayit_pencere_disinda_sayilmaz(self):
        import time
        self.usage.record("eski", "m", False)
        satirlar = Path(self.usage.LEDGER).read_text(encoding="utf-8").splitlines()
        kayit = json.loads(satirlar[0])
        kayit["at"] = time.time() - 30 * 86400
        Path(self.usage.LEDGER).write_text(
            json.dumps(kayit, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(0, self.usage.summary(days=7)["total_calls"])

    def test_bozuk_satir_ozeti_cokertmez(self):
        Path(self.usage.LEDGER).parent.mkdir(parents=True, exist_ok=True)
        Path(self.usage.LEDGER).write_text("{bozuk\n", encoding="utf-8")
        self.usage.record("gemini", "flash", False)
        self.assertEqual(1, self.usage.summary(1)["total_calls"])

    def test_defter_yoksa_ozet_bos_doner(self):
        self.assertEqual(0, self.usage.summary(1)["total_calls"])

    def test_yazma_hatasi_cagriyi_durdurmaz(self):
        """Maliyet kaydı tutulamıyor diye Jarvis susmamalı."""
        self.usage.LEDGER = Path("/olmayan/dizin/defter.jsonl")
        self.usage.record("gemini", "flash", False)   # istisna fırlatmamalı


if __name__ == "__main__":
    unittest.main()
