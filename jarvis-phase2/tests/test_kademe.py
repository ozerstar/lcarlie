"""Kademe: küçük model cevaplar, doğrulayıcı bakar, tutmazsa güçlü modele çıkar.

Eski hâli yalnız UZUNLUĞA bakıyordu -- 24 karakterden uzun her cevap başarılı
sayılıyordu. Oysa ölçülen kusurlar UZUN cevaplarda yaşandı: uydurma ürün adı,
soruyu tekrar etme, samimi hitap. Bu testler o boşluğu kapalı tutar.
"""
import unittest

from jarvis import answer_guard as g
from jarvis.model_layer import (AdapterState, ModelRouter, TIER_EXTERNAL,
                                TIER_GPU, TIER_LOCAL)

KATALOG = ("VIREON FOR MEN", "INTIMBLANC")


class KusurTespiti(unittest.TestCase):
    def test_bos_cevap(self):
        self.assertEqual(g.kusurlar(""), ["bos"])
        self.assertEqual(g.kusurlar("   "), ["bos"])

    def test_cok_kisa(self):
        self.assertIn("cok_kisa", g.kusurlar("Evet."))

    def test_uydurma_urun(self):
        k = g.kusurlar("FEMISIA FOR WOMEN urunumuz genis kullanim alanina sahiptir.",
                       known_products=KATALOG)
        self.assertIn("uydurma_urun", k)

    def test_katalog_bossa_uydurma_bildirilmez(self):
        """Ürün listesi okunamadığında her adı uydurma saymak, veri yokluğunu
        hataya çevirmek olurdu."""
        k = g.kusurlar("FEMISIA FOR WOMEN urunumuz genis kullanim alanina sahiptir.",
                       known_products=())
        self.assertNotIn("uydurma_urun", k)

    def test_soruyla_baslayan_cevap(self):
        k = g.kusurlar("Fiyat nedir? Fiyat nedir diye soruyorsunuz, cevap asagida.",
                       soru="Fiyat nedir")
        self.assertIn("soruyu_tekrarliyor", k)

    def test_soru_kelimesini_kullanmak_tekrar_degildir(self):
        """Cevabın soruda geçen kelimeleri kullanması normaldir, hatta beklenir."""
        k = g.kusurlar("Fiyati 1.200 TL olup stokta mevcuttur, ayni gun kargolanir.",
                       soru="fiyati nedir")
        self.assertNotIn("soruyu_tekrarliyor", k)

    def test_cok_kisa_soru_tekrar_sayilmaz(self):
        k = g.kusurlar("Peki, su sekilde aciklayabilirim: urun stokta mevcuttur.",
                       soru="peki")
        self.assertNotIn("soruyu_tekrarliyor", k)

    def test_kozmetik_kusurlar(self):
        k = g.kusurlar("Tabii ki! Seninle konusmak guzel \U0001F60A Urun stokta mevcuttur.")
        for beklenen in ("emoji", "samimi_hitap", "bos_acilis"):
            self.assertIn(beklenen, k)

    def test_temiz_cevap(self):
        k = g.kusurlar("VIREON FOR MEN fiyati 1.200 TL, stokta mevcuttur.",
                       known_products=KATALOG)
        self.assertEqual(k, [])


class EsasliKozmetikAyrimi(unittest.TestCase):
    """Emoji için ücretli ikinci çağrı yapmak israftır: formalize() bedava."""

    def test_kozmetik_tek_basina_yukseltmez(self):
        self.assertFalse(g.yukseltilmeli(["emoji", "samimi_hitap", "bos_acilis"]))

    def test_esasli_yukseltir(self):
        for kusur in g.ESASLI:
            with self.subTest(kusur=kusur):
                self.assertTrue(g.yukseltilmeli([kusur]))

    def test_kusursuz_yukseltmez(self):
        self.assertFalse(g.yukseltilmeli([]))

    def test_kumeler_kesismez(self):
        self.assertEqual(set(g.ESASLI) & set(g.KOZMETIK), set())


class _Provider:
    def __init__(self, name, tier, text, state=AdapterState.AVAILABLE):
        self.name, self.tier, self._text, self._state = name, tier, text, state
        self.calls = 0

    def state(self):
        return self._state

    def complete(self, messages, max_tokens):
        self.calls += 1
        return {"text": self._text, "model": self.name}


def _router(gpu_text, dis_durum=AdapterState.AVAILABLE):
    return ModelRouter(
        gpu=_Provider("gpu", TIER_GPU, gpu_text),
        local=_Provider("local", TIER_LOCAL, "yerel cevap"),
        external=_Provider("external", TIER_EXTERNAL,
                           "Guclu modelden gelen tam ve duzgun cevap.", dis_durum))


KANIT = [{"ref": "K1", "text": "VIREON FOR MEN fiyati 1.200 TL."}]


class KademeEntegrasyonu(unittest.TestCase):
    def test_temiz_cevap_yukselmez(self):
        r = _router("VIREON FOR MEN fiyati 1.200 TL, stokta mevcuttur.")
        s = r.synthesize("fiyat", KANIT, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_GPU)
        self.assertEqual(r.external.calls, 0)
        self.assertEqual(s.yukseltme_kusurlari, ())

    def test_uydurma_urun_yukseltir(self):
        r = _router("FEMISIA FOR WOMEN urunumuz genis kullanim alanina sahiptir.")
        s = r.synthesize("urunler", KANIT, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_EXTERNAL)
        self.assertEqual(r.external.calls, 1)
        self.assertIn("uydurma_urun", s.yukseltme_kusurlari)

    def test_cok_kisa_cevap_yukseltir(self):
        r = _router("Evet.")
        s = r.synthesize("fiyat", KANIT, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_EXTERNAL)

    def test_kozmetik_kusur_YUKSELTMEZ(self):
        """Ölçülen israf: emoji yüzünden ikinci ücretli çağrı."""
        r = _router("Tabii ki! Seninle konusmak guzel \U0001F60A Urun stokta mevcuttur.")
        s = r.synthesize("stok", KANIT, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_GPU)
        self.assertEqual(r.external.calls, 0)
        self.assertIn("emoji", s.yukseltme_kusurlari)

    def test_dis_saglayici_yoksa_cokmez(self):
        r = _router("Evet.", dis_durum=AdapterState.UNAVAILABLE)
        s = r.synthesize("fiyat", KANIT, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_GPU)
        self.assertEqual(r.external.calls, 0)
        # Bakılamadı -> None. "Kusur yok" (bos tuple) ile KARISTIRILMAMALI.
        self.assertIsNone(s.yukseltme_kusurlari)

    def test_escalate_true_ise_zaten_disa_gider(self):
        r = _router("Evet.")
        s = r.synthesize("strateji", KANIT, escalate=True, known_products=KATALOG)
        self.assertEqual(s.tier, TIER_EXTERNAL)
        self.assertIsNone(s.yukseltme_kusurlari)


if __name__ == "__main__":
    unittest.main()
