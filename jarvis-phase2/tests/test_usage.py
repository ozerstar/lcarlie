"""Model kullanım defteri. Ağ yok, model yok.

Sınanan asıl davranış: defter PARA UYDURMAZ ve cevabın METNİNİ SAKLAMAZ.

🔴 22.09.2026'da "para hiç yazılmaz" kuralı DEĞİŞTİ: defter artık
sağlayıcının İLAN ETTİĞİ liste fiyatını token sayısıyla çarpıp gösteriyor.
İlke bozulmadı, çünkü:

  * fiyatı tabloda OLMAYAN bir model için rakam ÜRETİLMEZ -- `None` döner
    ve sağlayıcı `fiyati_bilinmeyen` listesine girer. Sıfır yazmak,
    "bedava" demek olurdu ve bu bir yalan olurdu.
  * çıkan rakam ÖLÇÜM DEĞİL; `note` bunu her seferinde söylüyor. Gerçek
    rakam sağlayıcının faturasıdır, bu tablo o faturayı doğrulamak içindir.

Eski test "usd" kelimesini yasaklıyordu; yasak yanlış yere konmuştu --
asıl yasak BİLİNMEYEN fiyata rakam yazmak. Testler ona göre yeniden
yazıldı.
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
    def test_ucretli_cagri_FIYATA_gore_sayilir_bayraga_gore_DEGIL(self):
        """`paid` bayrağı bir MALİYET değil, YÖNLENDİRME bilgisidir.

        Eski sayaç `paid` bayrağına bakıyordu ve "1 ücretli çağrı" diyordu;
        gerçekte 81 çağrının 80'i para harcamıştı (Gemini faturalı ama
        bayrağı False). Sayaç artık gerçek fiyata bakıyor. Bu test o
        ayrımı kilitler: aynı üç çağrı, bayrakla 2 / fiyatla 1 verir.
        """
        # fiyatı tabloda ve SIFIR DEĞİL -> ücretli
        self.usage.record("gemini", "gemini-3.5-flash-lite", False,
                          prompt_tokens=1000, completion_tokens=1000)
        # fiyatı tabloda ve SIFIR -> ücretsiz
        self.usage.record("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free",
                          False, prompt_tokens=1000, completion_tokens=1000)
        # fiyatı tabloda YOK ama `paid` bayrağı True -> ücretli SAYILMAZ
        self.usage.record("claude", "haiku", True,
                          prompt_tokens=1000, completion_tokens=1000)

        ozet = self.usage.summary(1)
        self.assertEqual(3, ozet["total_calls"])
        self.assertEqual(1, ozet["paid_calls"], "sayaç bayrağa geri dönmüş")
        self.assertEqual(1, ozet["ucretsiz_calls"])
        # Bayrak kayboLMAZ, yalnız adı düzeldi: yönlendirme bilgisi olarak durur.
        claude = [k for k in ozet["providers"] if k["provider"] == "claude"][0]
        self.assertTrue(claude["sadece_derin"])

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

    def test_fiyati_BILINMEYEN_model_icin_rakam_URETILMEZ(self):
        """Bilinmeyen fiyata sıfır yazmak "bedava" demektir; bu bir yalandır.

        Asıl korunan kural bu. "claude/haiku" fiyat tablosunda yok (tam ad
        "claude-haiku-4-5-20251001"); eksik eşleşme sessizce 0,00 TL'ye
        dönüşürse maliyet olduğundan düşük görünür.
        """
        self.usage.record("claude", "haiku", True, prompt_tokens=1000,
                          completion_tokens=1000)
        ozet = self.usage.summary(1)
        kutu = [k for k in ozet["providers"] if k["provider"] == "claude"][0]

        self.assertIsNone(kutu["maliyet_usd"], "bilinmeyen fiyata rakam üretildi")
        self.assertIsNone(kutu["maliyet_try"])
        self.assertIn("claude", ozet["fiyati_bilinmeyen"])
        self.assertTrue(kutu["fiyat_notu"], "sebep yazılmamış")

    def test_para_rakami_OLCUM_OLARAK_sunulmaz(self):
        """Rakam liste fiyatından hesaplanır; bunu söylemeyen bir özet yanıltır."""
        self.usage.record("gemini", "gemini-3.5-flash-lite", False,
                          prompt_tokens=1_000_000, completion_tokens=0)
        ozet = self.usage.summary(1)

        # 1M girdi token x 0,30 $/M = 0,30 $. Hesap liste fiyatından gelir.
        self.assertAlmostEqual(0.30, ozet["tahmini_maliyet_usd"], places=4)

        # 🔴 Türkçe nokta tuzağı: "DEĞİL".casefold() birleşik noktalı
        # "i̇" üretir, "değil" ise sade "i". İki taraf da aynı şekilde
        # normalleştirilmezse eşleşme SESSİZCE başarısız olur -- bu testi
        # ilk yazışımda tam buraya düştüm.
        def sadelestir(metin):
            return metin.casefold().replace("i̇", "i")

        not_ = sadelestir(ozet["note"])
        self.assertIn(sadelestir("ÖLÇÜM DEĞİL"), not_,
                      "özet rakamı ölçüm sanılabilir")
        self.assertIn("liste fiyat", not_)
        # Kurun hangi tarihe ait olduğu ve tablonun bayatlığı da görünmeli.
        self.assertIn("gecerlilik", ozet["fiyat_tablosu"])
        self.assertIn("usd_try", ozet["fiyat_tablosu"])

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
