# -*- coding: utf-8 -*-
"""Panel okunurluğu — yazıyla değil testle korunur.

Sahip 26.09.2026: "yazılar okunmuyor anlaşılmıyor kalite çok düştü."
Ölçüldü ve haklı çıktı; iki kusur birden vardı.

🔴 KONTRAST. `--ivory-4` = %22 opaklık, neredeyse siyah zeminde **1,9:1**.
Eşik 4,5:1. O metin zor okunmuyordu, GÖRÜNMÜYORDU. `--ivory-3` (3,7:1) ve
`--gold-dim` (3,33:1) de eşiğin altındaydı.

🔴 YAZI BOYUTU. 400 bildirimin 141'i 13px'in altında; biri 8,4px, onu 9px.

Bu testin varlık sebebi, bunların geri gelme biçimi: kimse "okunmaz
metin ekleyeyim" demiyor. Yeni bir kart yazarken 10px'lik bir dipnot
koyuyor, `--ivory-4` soluk durduğu için onu seçiyor ve panel bir tık
daha okunmaz hale geliyor. Tek tek fark edilmiyor, toplamı fark ediliyor.

Bu ayrıca kendi kusurumdu: üretilen görsellerde 4,5:1'i zorunlu tutan
kodu yazarken (gorsel-kompozit.py EN_AZ_KONTRAST) panelin kendisine
1,9:1 metin koydum.
"""
import re
import unittest
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent
       / "webconsole" / "static" / "app.css")

EN_AZ_KONTRAST = 4.5
EN_KUCUK_YAZI = 11.0

# Metnin uzerine bindigi zeminler. En ACIK olani en zor vaka: kontrast
# orada olculur, cunku metin en cok orada kaybolur.
ZEMINLER = {
    "--ink-0": "#08080a",
    "--ink-1": "#0d0d10",
    "--ink-2": "#131317",
    "--ink-3": "#191920",
}

# Govde/etiket metninde kullanilan jetonlar. Yalniz suslemede kullanilan
# cizgi ve zemin jetonlari burada DEGIL -- cizgiye kontrast esigi
# uygulamak, olcmedigin bir seyi olcuyormus gibi yapmaktir.
METIN_JETONLARI = ("--ivory", "--ivory-2", "--ivory-3", "--ivory-4",
                   "--gold", "--gold-dim")


def _kanal(v: float) -> float:
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def parlaklik(rgb) -> float:
    r, g, b = (_kanal(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(on, arka) -> float:
    a, b = parlaklik(on), parlaklik(arka)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def bindir(on, alfa, arka):
    """Yarı saydam metnin zemin üstündeki gerçek rengi."""
    return tuple(round(arka[i] + alfa * (on[i] - arka[i])) for i in range(3))


def jetonlari_oku(metin: str) -> dict:
    cikti = {}
    for ad, deger in re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", metin):
        deger = deger.strip()
        m = re.match(r"#([0-9a-fA-F]{6})$", deger)
        if m:
            cikti[ad] = (hex_rgb(deger), 1.0)
            continue
        m = re.match(r"rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\s*\)$",
                     deger)
        if m:
            cikti[ad] = ((int(m.group(1)), int(m.group(2)), int(m.group(3))),
                         float(m.group(4)))
    return cikti


class TestKontrast(unittest.TestCase):
    def setUp(self):
        self.jetonlar = jetonlari_oku(CSS.read_text(encoding="utf-8"))

    def test_jetonlar_okunabildi(self):
        # Olcum harness'i sessizce bos donmesin: once okuyucunun
        # calistigi kanitlanir, sonra olcum yapilir.
        self.assertGreater(len(self.jetonlar), 10, self.jetonlar)
        for ad in METIN_JETONLARI:
            self.assertIn(ad, self.jetonlar, ad)

    def test_metin_jetonlari_esigi_gecer(self):
        # En acik zemin en zor vaka.
        arka = hex_rgb(ZEMINLER["--ink-3"])
        dusuk = []
        for ad in METIN_JETONLARI:
            renk, alfa = self.jetonlar[ad]
            oran = kontrast(bindir(renk, alfa, arka), arka)
            if oran < EN_AZ_KONTRAST:
                dusuk.append("%s = %.2f:1" % (ad, oran))
        self.assertEqual(dusuk, [],
                         "esik %.1f:1 -- panelde okunmayan metin rengi: %s"
                         % (EN_AZ_KONTRAST, ", ".join(dusuk)))

    def test_rampa_ayirt_edilebilir(self):
        # Hepsini beyaza yaklastirip esigi gecmek cozum degil: hiyerarsi
        # kaybolur. Basamaklar arasinda gercek fark kalmali.
        arka = hex_rgb(ZEMINLER["--ink-1"])
        oranlar = []
        for ad in ("--ivory", "--ivory-2", "--ivory-3", "--ivory-4"):
            renk, alfa = self.jetonlar[ad]
            oranlar.append(kontrast(bindir(renk, alfa, arka), arka))
        for once, sonra in zip(oranlar, oranlar[1:], strict=False):
            self.assertGreater(once, sonra * 1.2,
                               "ivory rampasinda basamaklar birbirine cok "
                               "yakin: %s" % [round(o, 2) for o in oranlar])

    def test_olcum_gercekten_calisiyor(self):
        # Bilinen deger: siyah uzerine beyaz 21:1.
        self.assertAlmostEqual(kontrast((255, 255, 255), (0, 0, 0)), 21.0,
                               places=1)
        # Ve eski kusurlu deger gercekten kaliyordu mu: %22 opaklik.
        arka = hex_rgb("#0d0d10")
        eski = kontrast(bindir((242, 239, 233), 0.22, arka), arka)
        self.assertLess(eski, 2.5,
                        "eski --ivory-4 degeri esigi gecmis gorunuyor; "
                        "olcum yanlis olabilir")


class TestYaziBoyutu(unittest.TestCase):
    def test_taban_boyut(self):
        metin = CSS.read_text(encoding="utf-8")
        kucukler = []
        for deger in re.findall(r"font-size:\s*([0-9]+(?:\.[0-9]+)?)px", metin):
            if float(deger) < EN_KUCUK_YAZI:
                kucukler.append(deger + "px")
        self.assertEqual(sorted(set(kucukler)), [],
                         "panelde %spx altinda yazi var: %s"
                         % (EN_KUCUK_YAZI, sorted(set(kucukler))))

    def test_olcum_bir_sey_buluyor(self):
        metin = CSS.read_text(encoding="utf-8")
        hepsi = re.findall(r"font-size:\s*([0-9.]+)px", metin)
        self.assertGreater(len(hepsi), 100,
                           "font-size taramasi calismiyor gibi: %d" % len(hepsi))


if __name__ == "__main__":
    unittest.main()
