# -*- coding: utf-8 -*-
"""SEO sorusu MODELE DEĞİL VERİYE gider — bekçi testleri.

🔴 NEDEN VAR — GERÇEK ARIZA, ÖLÇÜLDÜ 16.10.2026 00:14
   Sahip "SEO çalışmalarımız ne durumda" diye sordu. Jarvis şöyle cevap
   verdi: *"'bebek kremi', 'ağız bakım', 'dermokozmetik kremler' gibi
   anahtar kelimelerde doğal sıralamada yer alıyoruz."*

   Bu UYDURMAYDI. SEO ekibinin kendi ölçümü aynen şöyle der: *"sıralama
   verisi elimizde YOK, bu yüzden etkisi ölçülemiyor."* Yani Jarvis
   olmayan bir sıralamayı var gibi anlattı — iki kez.

   Sebep üç katmanlıydı ve üçü de burada kilitleniyor:
     1. `classify()` içinde "seo" dalı yoktu
     2. `_domains_of` "seo"yu göremiyordu (3 harf, kök eşiği 4)
     3. bu yüzden `should_use_model()` True dönüp soruyu modele veriyordu

   Bir tanesi gevşerse soru yine modele düşer ve model yine uydurur.
   Bu testler o üç katmanı AYRI AYRI kanıtlar.

Testler ağa çıkmaz, veritabanı istemez: yalnız yönlendirme kararını ölçer.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

# 🔴 DURUM DIZINI, conversation ICE AKTARILMADAN ONCE izole edilir.
#    `conversation_memory` STATE_DIR'i modul yuklenirken BIR KEZ okur;
#    sonra degistirmek ise yaramaz. Izole edilmezse surec uretim sohbet
#    dokumune baglanir -- 20.09.2026'da tam bu yuzden uretim dokumunun
#    369 satiri test fixture'i olmus ve model onlari taklit etmisti.
#    (Ayni koruma `test_conversation.py` basinda da var.)
os.environ.setdefault("JARVIS_STATE_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

import conversation as c  # noqa: E402 - STATE_DIR'den SONRA aktarilmali


class SeoSorusuVeriyeGider(unittest.TestCase):
    """Katman 1: yönlendirme."""

    GERCEK_SORULAR = (
        # Sahibin o sabah yazdığı iki soru, BİREBİR.
        "SEO çalışmalarımız ne durumda",
        "Ne dedin anlamadım seo calışmalarını arttıralım",
        # Aynı konunun başka yazımları
        "seo durumu nedir",
        "arama motoru görünürlüğümüz nasıl",
        "anahtar kelime çakışması var mı",
        "meta açıklamalar tanımlı mı",
        "slug boş olan ürün var mı",
    )

    def test_seo_sorusu_COMPANY_QUERY_olur(self):
        for soru in self.GERCEK_SORULAR:
            with self.subTest(soru=soru):
                karar = c.classify(soru)
                self.assertEqual(karar.intent, c.COMPANY_QUERY,
                                 "SEO sorusu veriye gitmedi: %r" % soru)

    def test_alan_seo_secilir_reklam_DEGIL(self):
        """🔴 "başlık" ve "anahtar kelime" REKLAM köklerinde de var.

        SEO dalı reklam dalından ÖNCE durmazsa SEO sorusu reklam
        verisiyle cevaplanır. Ölçüldü: `advertising` kökleri arasında
        "baslik", "gorsel", "metin" geçiyor.
        """
        for soru in ("SEO başlıkları çok uzun mu",
                     "anahtar kelime dağılımı nasıl",
                     "seo durumu nedir"):
            with self.subTest(soru=soru):
                self.assertEqual(c.classify(soru).domain, "seo")


class ModelKapisiSeoyuGecirmez(unittest.TestCase):
    """Katman 2 ve 3: `_domains_of` görmeli, `should_use_model` kapatmalı."""

    def test_domains_of_seo_yu_GORUR(self):
        """🔴 3 HARF TUZAĞI. Kök taraması `len(w) >= _MIN_ROOT_WORD` (4)
        ile çalışır; "seo" 3 harf olduğu için köke yazılsa SESSİZCE işe
        yaramazdı. Tam kelime kümesi (`_SEO_KELIMELERI`) bu yüzden var --
        "tl" için daha önce çözülmüş olan aynı sorun."""
        self.assertIn("seo", c._domains_of("SEO çalışmalarımız ne durumda"))
        self.assertIn("seo", c._domains_of("seo durumu"))

    def test_should_use_model_seo_sorusunda_KAPALI(self):
        """Asıl arızanın kilidi. Bu True dönerse `route()` içindeki model
        kapısı soruyu COMPANY_QUERY'e yönlendirilmiş OLSA BİLE
        `_synthesize`'a, yani modele gönderir."""
        for soru in ("SEO çalışmalarımız ne durumda",
                     "Ne dedin anlamadım seo calışmalarını arttıralım",
                     "seo durumu nedir"):
            with self.subTest(soru=soru):
                self.assertFalse(c.should_use_model(soru),
                                 "soru modele kaçıyor: %r" % soru)

    def test_SEO_KELIMELERI_tam_kelime_TANIMLI(self):
        """🔴 Tanım bir kez SESSİZCE eklenmeden kaldı (yama imzası yorumdaki
        ada eşleşti) ve `_domains_of` NameError verecek durumdaydı."""
        self.assertTrue(hasattr(c, "_SEO_KELIMELERI"))
        self.assertIn("seo", c._SEO_KELIMELERI)

    def test_seo_alt_dizgi_olarak_eslesmez(self):
        """" seo " boşluklu yazıldı: `_has` boşluklu kalıpta KELİME SINIRI
        arar. Boşluksuz yazılsaydı kelime ortasında eşleşirdi -- "hi "
        kalıbı 20.09.2026'da tam bu yüzden İngilizce iş sorularını sohbet
        saymıştı."""
        for soru in ("bu konseortyum ne", "video montaj nasıl"):
            with self.subTest(soru=soru):
                self.assertNotEqual(c.classify(soru).domain, "seo")


class KonusuzArastirmaAratilmaz(unittest.TestCase):
    """🔴 "Araştır ve optimize et" -> TDK'dan "optimize" kelimesinin tanımı.

    Ölçüldü 16.10.2026 00:15. Mesaj ham haliyle arama sorgusu oldu; önceki
    turun konusu taşınmadığı için geriye yalnız FİİL kaldı ve fiil
    aratıldı. Konu tahmin edilmez, SORULUR.
    """

    def test_fiil_yalniz_mesaj_SORULUR(self):
        for soru in ("Arastır ve optimize et", "araştır", "araştır ve incele",
                     "hemen araştır", "araştır bunları"):
            with self.subTest(soru=soru):
                self.assertEqual(c.classify(soru).intent,
                                 c.RESEARCH_SUBJECT_MISSING,
                                 "konusuz istek aratıldı: %r" % soru)

    def test_konusu_OLAN_istek_arastirilir(self):
        """Konu varsa davranış DEĞİŞMEZ -- düzeltme araştırmayı kısmaz."""
        for soru in ("rakip fiyatlarını araştır",
                     "Seo ekibi bunları arastırsın",
                     "kozmetik pazarını araştır"):
            with self.subTest(soru=soru):
                self.assertEqual(c.classify(soru).intent, c.RESEARCH_REQUEST,
                                 "konulu istek engellendi: %r" % soru)

    def test_konusuz_istek_MODELE_GITMEZ(self):
        """Yeni niyet `route()` içinde model kapısından ÖNCE karşılanır;
        altına konsaydı soru yine modele düşer ve model konuyu
        uydurabilirdi."""
        kaynak = c.__file__
        with open(kaynak, encoding="utf-8") as dosya:
            metin = dosya.read()
        once = metin.index("RESEARCH_SUBJECT_MISSING:")
        model_kapisi = metin.index("and should_use_model(message)")
        self.assertLess(once, model_kapisi,
                        "konusuz arastirma dali model kapisinin ALTINDA")


class UydurmaNinKAYNAGI(unittest.TestCase):
    """Cevabın kendisi deterministik olmak ZORUNDA."""

    def test_seo_cevabi_roster_konusmacilarini_kullanir(self):
        """🔴 Cevap yeniden YAZILMAZ. `jarvis.roster` SEO konuşmacıları
        zaten `urun_seo`'dan deterministik cümle üretiyor ve panelin EKİP
        panosu aynen onları gösteriyor. İkinci bir biçimlendirici, aynı
        şeyin iki tanımı olurdu."""
        self.assertTrue(hasattr(c, "_seo_answer"))
        with open(c.__file__, encoding="utf-8") as dosya:
            govde = dosya.read()
        bolum = govde[govde.index("def _seo_answer"):govde.index("def _company(")]
        self.assertIn("roster.SPEAKERS", bolum,
                      "SEO cevabi roster konusmacilarini kullanmiyor")
        for yasak in ("synthesize", "generate(", "ModelRouter"):
            self.assertNotIn(yasak, bolum,
                             "SEO cevap yolunda model izi: %r" % yasak)


if __name__ == "__main__":
    unittest.main()
