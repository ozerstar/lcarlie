# -*- coding: utf-8 -*-
"""Günlük Instagram paketi: ustalık kuralları, iddia kapısı, uzman kadrosu."""
import importlib.util
import pathlib
import unittest

from jarvis import compliance, ig_ustasi, roster
from jarvis.department_activation import SPEAKERS as DA_SPEAKERS

KOK = pathlib.Path(__file__).resolve().parents[1]


def _betik():
    sp = importlib.util.spec_from_file_location(
        "ig_gunluk_uret", str(KOK / "scripts" / "ig-gunluk-uret.py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


class KancaPuani(unittest.TestCase):
    def test_selamlama_oldurucu(self):
        r = ig_ustasi.kanca_puani("Merhaba arkadaşlar, bugün size bir ürün göstereceğim")
        self.assertLessEqual(r["puan"], 35)
        self.assertTrue(r["kusurlar"])

    def test_iyi_kanca_selamdan_yuksek(self):
        iyi = ig_ustasi.kanca_puani("Kremi yanlış sürüyorsun, suç sende değil")["puan"]
        kotu = ig_ustasi.kanca_puani("Bu videoda yeni ürünümüzü tanıtıyoruz")["puan"]
        self.assertGreater(iyi, kotu)
        self.assertGreaterEqual(iyi, 55)

    def test_urun_adiyla_acilis_kusur(self):
        r = ig_ustasi.kanca_puani("VIREON ile tanışın", "VIREON (Erkek Bakım)")
        self.assertTrue(any("Ürün adıyla" in k for k in r["kusurlar"]))

    def test_kancada_hashtag_kusur(self):
        self.assertTrue(ig_ustasi.kanca_puani("Üç adımda rutin #bakım")["kusurlar"])


class IddiaKapisi(unittest.TestCase):
    def test_serbest_iddia_yakalanir(self):
        self.assertTrue(ig_ustasi.serbest_iddia("Cildine nem kazandırır ve korur."))

    def test_referans_icindeki_iddia_sayilmaz(self):
        self.assertEqual(ig_ustasi.serbest_iddia("Akşam rutininde {S2} Sonra bekle."), [])

    def test_masum_kelimeler_iddia_degil(self):
        for m in ("Sağlam bir kapak.", "Eve giderken yanına al.", "Korku yok."):
            self.assertEqual(ig_ustasi.serbest_iddia(m), [], m)

    def test_yasak_formuller_listede_yok(self):
        ad = " ".join(f["ad"].lower() for f in ig_ustasi.FORMULLER.values())
        for yasak in ("önce", "sonra", "istatistik", "en iyi", "sonuç"):
            self.assertNotIn(yasak, ad)

    def test_genisletme_aynen_ve_eksik_referans(self):
        b = _betik()
        metin, eksik = b.genislet("A {S1} B {S9}", ["Cümle bir."])
        self.assertEqual(metin, "A Cümle bir. B ")
        self.assertEqual(eksik, ["{S9}"])


class YasakNesne(unittest.TestCase):
    """30.10.2026 ilk pakette compliance'tan KAÇAN gerçek cümleler."""

    def test_ilk_paketin_kacaklari_yakalanir(self):
        for cumle in ("Sızlayan bacaklar, gece çorap + bu krem ile rahat uyku.",
                      "Cilt nemliyken emilim daha iyi olur.",
                      "Gün boyu baskıdan sonra bacaklar dinlenir.",
                      "Sabah: fark gör", "Sonuç: fark"):
            self.assertTrue(ig_ustasi.yasak_nesne(cumle), cumle)

    def test_izinli_nesneler_gecer(self):
        for cumle in ("Dokusu hafif, kokusu belirgin.", "Akşam rutininde iki dakika.",
                      "İşe yarayan bir adım: nemli cilde uygula.",
                      "Yaratıcı bir ritüel."):
            self.assertEqual(ig_ustasi.yasak_nesne(cumle), [], cumle)

    def test_zorunlu_uyari_muaf(self):
        uyari = "Açık yaralara uygulanmamalıdır."
        self.assertEqual(ig_ustasi.yasak_nesne("Kullanım: " + uyari, (uyari,)), [])
        self.assertTrue(ig_ustasi.yasak_nesne("Yaraya iyi gelir."))

    def test_referans_icindeki_cumle_aranmaz(self):
        self.assertEqual(ig_ustasi.yasak_nesne("{S3}"), [])

    def test_dikis_izi_duzeltilir(self):
        self.assertEqual(ig_ustasi.noktalama_duzelt("kullanılır.. Diz ., baldır"),
                         "kullanılır. Diz. baldır")


class CaptionDenetimi(unittest.TestCase):
    def test_link_ve_uzun_ilk_satir(self):
        notlar = ig_ustasi.caption_denetle("x" * 130 + "\nhttps://lcarlie.shop", [], 5)
        self.assertEqual(len(notlar), 2)

    def test_hashtag_tavani_denetciden(self):
        cok = ["#a%d" % i for i in range(compliance.HASHTAG_CAP + 1)]
        self.assertTrue(ig_ustasi.caption_denetle("kısa", cok, compliance.HASHTAG_CAP))

    def test_yz_kokusu(self):
        self.assertTrue(ig_ustasi.koku_bul("Keşfetmeye hazır mısınız? Eşsiz bir deneyim."))

    def test_insanlastir_uzun_tire(self):
        self.assertNotIn("—", ig_ustasi.insanlastir("Doku — hafif"))


class UzmanKadrosu(unittest.TestCase):
    def test_direktor_instagram_basinda(self):
        self.assertEqual(roster.DEPARTMAN_SORUMLUSU["INSTAGRAM"], "ig_icerik_direktoru")
        self.assertEqual(roster.UYE_DEPARTMAN["ig_icerik_direktoru"], "INSTAGRAM")
        self.assertEqual(roster.eslenmeyen_uyeler(), ())

    def test_direktor_veriden_konusur(self):
        satir = {"gun": "2026-10-30", "urun_slug": "vireon", "uzman_karari": "DUZELT",
                 "denetim": "TEMIZ", "durum": "ONERI", "kanca_puani": 70}
        s = DA_SPEAKERS["ig_icerik_direktoru"]({"ig_gunluk_paket": [satir] * 5})
        self.assertIn("5 içerik", s)
        self.assertIn("yayın yapılmadı", s)

    def test_direktor_bos_veride_uydurmaz(self):
        s = DA_SPEAKERS["ig_icerik_direktoru"]({"ig_gunluk_paket": []})
        self.assertIn("yok", s)


if __name__ == "__main__":
    unittest.main()
