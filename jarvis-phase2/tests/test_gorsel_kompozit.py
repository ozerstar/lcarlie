# -*- coding: utf-8 -*-
"""Gönderi görseli motorunun sözleşmesi.

🔴 BU DOSYANIN HER SINAMASI ÖLÇÜLMÜŞ BİR KUSURA KARŞILIK GELİYOR
(25.09.2026'da beşi de yaşandı):

  1. rembg maskesinde ürünün GÖVDESİ tam opak değildi (%17,4'ü 255, %51'i
     250-254) ve yapıştırmada iç pikseller arka planla harmanlanıyordu.
  2. Doğrulama eşiği >=250 yazılmıştı; harmanlanan pikselleri "korunmalı"
     sayıyor ve yanıltıyordu.
  3. Yazı perdesi üründen SONRA çiziliyor, bulanıklığı ürünü kirletiyordu.
  4. Metropolis'te `·` ve `₺` glifleri YOK; Pillow sessizce kutu basıyordu.
  5. Ürün sabit oranla büyütülüyor, uzun başlıkta yazıyla ÇAKIŞIYORDU.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_sp = importlib.util.spec_from_file_location(
    "gorsel_kompozit", str(KOK / "scripts" / "gorsel-kompozit.py"))
gk = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(gk)

from PIL import Image  # noqa: E402

_URUN_VAR = gk.GORSEL.is_dir() and any(gk.GORSEL.glob("*.webp"))
_FONT_VAR = (gk.FONT_DIZIN / gk.FONTLAR["bold"]).is_file()


class MaskeGovdesiTamOpakOlur(unittest.TestCase):
    """Yarı saydam gövde, yapıştırmada ürün pikselini değiştirir."""

    def test_govde_255_yapilir(self):
        im = Image.new("RGBA", (4, 4), (10, 20, 30, 252))
        sert = gk.maskeyi_sertlestir(im)
        self.assertEqual(set(sert.split()[-1].getdata()), {255})

    def test_fon_0_yapilir(self):
        im = Image.new("RGBA", (4, 4), (10, 20, 30, 5))
        self.assertEqual(set(gk.maskeyi_sertlestir(im).split()[-1].getdata()), {0})

    def test_gercek_kenar_yumusak_kalir(self):
        # 8 ile 250 arasi GERCEK gecistir; sertlestirilirse kenar makasla
        # kesilmis gorunur.
        im = Image.new("RGBA", (4, 4), (10, 20, 30, 128))
        self.assertEqual(set(gk.maskeyi_sertlestir(im).split()[-1].getdata()), {128})

    def test_renk_kanallari_degismez(self):
        im = Image.new("RGBA", (4, 4), (10, 20, 30, 252))
        sert = gk.maskeyi_sertlestir(im)
        self.assertEqual(sert.split()[0].getdata()[0], 10)
        self.assertEqual(sert.split()[1].getdata()[0], 20)
        self.assertEqual(sert.split()[2].getdata()[0], 30)


@unittest.skipUnless(_FONT_VAR, "marka fontu bulunamadi")
class EksikGlifKutuBasmaz(unittest.TestCase):
    """Pillow eksik glif yerine .notdef kutusu çizer ve HATA VERMEZ."""

    def test_metropoliste_olmayan_karakterler_degistirilir(self):
        # Olculdu: Metropolis'in bes agirliginda da yok.
        for ham, beklenen in (("a·b", "a–b"), ("1.950 ₺", "1.950 TL"),
                              ("x•y", "x–y")):
            self.assertEqual(gk.metin_guvenli(ham, "bold"), beklenen)

    def test_lira_isareti_kutu_basmaz(self):
        self.assertNotIn("₺", gk.metin_guvenli("Fiyat 2.400 ₺", "bold"))

    def test_turkce_karakterler_korunur(self):
        metin = "İĞÜŞÖÇ ığüşöç"
        self.assertEqual(gk.metin_guvenli(metin, "bold"), metin)

    def test_karsiligi_olmayan_eksik_karakter_reddedilir(self):
        # Uydurma bir karakter: tabloda yok, fontta yok -> uretim durur.
        with self.assertRaises(gk.GorselHatasi):
            gk.metin_guvenli("normal 字 metin", "bold")


class KontrastOlculur(unittest.TestCase):
    def test_siyah_beyaz_en_yuksek(self):
        self.assertAlmostEqual(gk.kontrast((0, 0, 0), (255, 255, 255)), 21.0, places=1)

    def test_ayni_renk_birdir(self):
        self.assertAlmostEqual(gk.kontrast((120, 120, 120), (120, 120, 120)), 1.0)

    def test_esik_wcag_aa(self):
        self.assertGreaterEqual(gk.EN_AZ_KONTRAST, 4.5)


@unittest.skipUnless(_URUN_VAR and _FONT_VAR, "urun gorseli ya da font yok")
class UrunPikseliKorunur(unittest.TestCase):
    """Sözün kanıtı: ürün bölgesi kaynak kesimle BİREBİR aynı olmalı."""

    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp(prefix="gorsel-test-"))
        adaylar = sorted({p.name.rsplit("-", 1)[0]
                          for p in gk.GORSEL.glob("*.webp")})
        cls.slug = adaylar[0] if adaylar else None

    def test_her_bicimde_birebir(self):
        for bicim in ("KARE", "AKIS", "REELS"):
            r = gk.uret(self.slug, bicim=bicim,
                        baslik="Uzun bir baslik satiri daha da uzun olsun",
                        alt="Alt satir da epeyce uzun bir metin olabilir",
                        cikti_dizin=self.dizin)
            self.assertEqual(r["birebir_oran"], 1.0,
                             "%s: urun pikselleri degismis" % bicim)
            self.assertEqual(r["ssim"], 1.0)
            self.assertEqual(tuple(r["boyut"]), gk.BICIMLER[bicim])

    def test_yazi_urunle_cakismaz(self):
        # Uzun baslik urunu kucultmeli, ustune binmemeli.
        r = gk.uret(self.slug, bicim="KARE",
                    baslik="Cok uzun bir baslik iki hatta uc satira yayilsin diye",
                    alt="Ve alt satir da uzun olsun ki yer daralsin",
                    cikti_dizin=self.dizin)
        self.assertEqual(r["birebir_oran"], 1.0)

    def test_kontrast_raporlanir(self):
        r = gk.uret(self.slug, bicim="AKIS", baslik="Baslik", alt="Alt",
                    cikti_dizin=self.dizin)
        self.assertIsNotNone(r["kontrast_orani"])
        self.assertGreaterEqual(r["kontrast_orani"], gk.EN_AZ_KONTRAST)

    def test_rapor_katmanlari_yazar(self):
        r = gk.uret(self.slug, bicim="KARE", cikti_dizin=self.dizin)
        self.assertTrue(any("gercek fotograf" in k for k in r["katmanlar"]))


class BicimlerInstagramOlculeriyle(unittest.TestCase):
    def test_olculer(self):
        self.assertEqual(gk.BICIMLER["REELS"], (1080, 1920))
        self.assertEqual(gk.BICIMLER["KARE"], (1080, 1080))
        self.assertEqual(gk.BICIMLER["AKIS"], (1080, 1350))

    def test_her_bicimin_urun_orani_var(self):
        for b in gk.BICIMLER:
            self.assertIn(b, gk.URUN_YUKSEKLIK_ORANI)


class YerlesimSanatYonetimindenGelir(unittest.TestCase):
    """Merkez kilidi bir sanat yonetimi kusuruydu: secilen konsept
    'urun sag-altta, negatif alan sol-ustte' diyordu, motor ortaliyordu."""

    def test_gecersiz_yerlesim_reddedilir(self):
        with self.assertRaises(gk.GorselHatasi):
            gk.uret("x", yerlesim_adi="ortalarda")

    def test_gecersiz_isik_reddedilir(self):
        with self.assertRaises(gk.GorselHatasi):
            gk.uret("x", isik="arkadan")

    def test_yerlesim_oranlari_tanimli(self):
        self.assertEqual(gk.YERLESIMLER["merkez"], 0.50)
        self.assertGreater(gk.YERLESIMLER["sag"], 0.5)
        self.assertLess(gk.YERLESIMLER["sol"], 0.5)


class IsikYonuOlculur(unittest.TestCase):
    """Sabit yon varsaymak golgeyi sahnenin isigina ters dusurur ve
    kompozit 'yapistirilmis' gorunur."""

    def _sahne(self, sol_parlak: bool):
        im = Image.new("RGB", (400, 400), (30, 30, 30))
        parlak = Image.new("RGB", (150, 400), (220, 220, 220))
        im.paste(parlak, (0, 0) if sol_parlak else (250, 0))
        return im

    def test_soldan_isik(self):
        self.assertEqual(
            gk.isik_yonu_olc(self._sahne(True), (160, 100, 240, 300)), "sol")

    def test_sagdan_isik(self):
        self.assertEqual(
            gk.isik_yonu_olc(self._sahne(False), (160, 100, 240, 300)), "sag")

    def test_fark_kucukse_ust_varsayilir(self):
        duz = Image.new("RGB", (400, 400), (120, 120, 120))
        self.assertEqual(gk.isik_yonu_olc(duz, (160, 100, 240, 300)), "ust")


@unittest.skipUnless(_URUN_VAR and _FONT_VAR, "urun gorseli ya da font yok")
class YerlesimVePikselBirlikteCalisir(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp(prefix="gorsel-yerlesim-"))
        adaylar = sorted({p.name.rsplit("-", 1)[0]
                          for p in gk.GORSEL.glob("*.webp")})
        cls.slug = adaylar[0] if adaylar else None

    def test_her_yerlesimde_urun_pikseli_korunur(self):
        for yer in ("sol", "merkez", "sag", "sag_ucta"):
            r = gk.uret(self.slug, bicim="AKIS", baslik="Baslik", alt="Alt",
                        yerlesim_adi=yer, cikti_dizin=self.dizin)
            self.assertEqual(r["birebir_oran"], 1.0, yer)
            self.assertEqual(r["yerlesim"], yer)

    def test_yerlesim_konumu_degistirir(self):
        sol = gk.uret(self.slug, yerlesim_adi="sol", cikti_dizin=self.dizin)
        sag = gk.uret(self.slug, yerlesim_adi="sag", cikti_dizin=self.dizin)
        self.assertLess(sol["urun_kutusu"]["sol"], sag["urun_kutusu"]["sol"])

    def test_urun_tuvalin_disina_tasmaz(self):
        for yer in gk.YERLESIMLER:
            r = gk.uret(self.slug, yerlesim_adi=yer, cikti_dizin=self.dizin)
            self.assertGreaterEqual(r["urun_kutusu"]["sol"], 0)
            self.assertLessEqual(r["urun_kutusu"]["sag"], r["boyut"][0])

    def test_isik_yonu_raporlanir(self):
        r = gk.uret(self.slug, cikti_dizin=self.dizin)
        self.assertIn(r["isik_yonu"], ("sol", "sag", "ust"))
        self.assertEqual(r["isik_kaynagi"], "olculdu")


if __name__ == "__main__":
    unittest.main()
