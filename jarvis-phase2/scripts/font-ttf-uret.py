#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Marka fontlarını OTF (CFF) -> TTF (glyf) çevirir.

NEDEN: katalog PDF'i reportlab ile üretiliyor ve reportlab yalnız
TrueType ana hatlarını gömebiliyor; marka fontlarımızın ikisi de OTF/CFF.
Ölçüldü: `TTFont(...otf)` -> TTFError.

ALTERNATIF NEDEN REDDEDILDI: sayfaları Pillow ile 300 DPI raster üretip
PDF'e koymak da mümkündü ve daha kolaydı. Ama 9,5 puntoluk gövde metni
rasterde baskıda YUMUŞAK çıkar ve prepress şartı "font embedding, vector
elements" diyor. "Düşük çözünürlüklü görseli büyütüp print-ready sayma"
kuralının tipografi karşılığı bu.

🔴 DÖNÜŞÜM KAYIPLIDIR AMA ÖLÇÜLEBİLİR. Kübik Bézier eğrileri kuadratiğe
çevrilir; hata payı `EN_COK_HATA` (font birimi) ile sınırlanır. 1000
birimlik em'de 1.0 birim, 10 puntoda 0,01 punto eder -- baskıda
görünmez. Dönüşüm sonrası glif sayısı ve Türkçe kapsama YENİDEN ölçülür;
eşleşmezse dosya yazılmaz.
"""
from __future__ import annotations

from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

KAYNAKLAR = [
    Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar/MonumentExtended-Ultrabold.otf"),
    Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar/MonumentExtended-Regular.otf"),
    Path("/opt/lcarlie/jarvis-phase2/webconsole/static/fonts/Metropolis-Regular.otf"),
    Path("/opt/lcarlie/jarvis-phase2/webconsole/static/fonts/Metropolis-Light.otf"),
    Path("/opt/lcarlie/jarvis-phase2/webconsole/static/fonts/Metropolis-Medium.otf"),
    Path("/opt/lcarlie/jarvis-phase2/webconsole/static/fonts/Metropolis-SemiBold.otf"),
    Path("/opt/lcarlie/jarvis-phase2/webconsole/static/fonts/Metropolis-Bold.otf"),
]
HEDEF = Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar-ttf")
EN_COK_HATA = 1.0          # font birimi
DENEK = "İĞÜŞÖÇıığüşöç—–'’"


def kapsama(font: TTFont) -> set:
    kod = set()
    for tablo in font["cmap"].tables:
        kod |= set(tablo.cmap)
    return kod


def cevir(kaynak: Path, hedef: Path) -> dict:
    otf = TTFont(str(kaynak))
    if otf.sfntVersion != "OTTO":
        raise SystemExit("%s zaten TrueType degil mi? sfntVersion=%s"
                         % (kaynak.name, otf.sfntVersion))
    once_kod = kapsama(otf)
    once_glif = len(otf.getGlyphOrder())

    glyph_set = otf.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = otf.getGlyphOrder()
    glyf.glyphs = {}
    for ad in glyf.glyphOrder:
        kalem = TTGlyphPen(glyph_set)
        glyph_set[ad].draw(Cu2QuPen(kalem, EN_COK_HATA, reverse_direction=True))
        glyf[ad] = kalem.glyph()

    # 🔴 SINIRLAR ONCE HESAPLANIR. maxp.recalc() her glifin xMin/xMax'ini
    # okur; TTGlyphPen bunlari kendiliginden koymuyor ve recalc
    # AttributeError ile duruyordu (olculdu).
    for ad in glyf.glyphOrder:
        glyf[ad].recalcBounds(glyf)

    otf["glyf"] = glyf
    otf["loca"] = newTable("loca")
    # maxp v1.0 TrueType'a ozgu alanlar ister; CFF fontunda bunlar yok ve
    # compile "KeyError: maxZones" ile duruyordu (olculdu). Hepsi sifir:
    # uretilen fontta hinting yok, bu bilincli -- hinting eklemek ayri bir
    # is ve baskida 300 DPI'da farki yok.
    maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    maxp.numGlyphs = len(glyf.glyphOrder)
    maxp.maxZones = 1
    maxp.maxTwilightPoints = 0
    maxp.maxStorage = 0
    maxp.maxFunctionDefs = 0
    maxp.maxInstructionDefs = 0
    maxp.maxStackElements = 0
    maxp.maxSizeOfInstructions = 0
    maxp.maxComponentElements = 0
    otf["maxp"] = maxp
    maxp.recalc(otf)

    post = otf["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = glyf.glyphOrder

    otf["head"].indexToLocFormat = 0
    otf.sfntVersion = "\x00\x01\x00\x00"
    for tablo in ("CFF ", "VORG"):
        if tablo in otf:
            del otf[tablo]

    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_suffix(".ttf.tmp")
    otf.save(str(gecici))

    # 🔴 DOGRULAMA: cevrilen dosya YENIDEN acilip olculur. "Kaydedildi"
    # ile "dogru kaydedildi" ayri seylerdir.
    yeni = TTFont(str(gecici))
    sonra_kod = kapsama(yeni)
    sonra_glif = len(yeni.getGlyphOrder())
    eksik = sorted(c for c in DENEK if ord(c) not in sonra_kod)
    kayip = once_kod - sonra_kod
    if sonra_glif != once_glif or kayip or eksik:
        gecici.unlink(missing_ok=True)
        raise SystemExit(
            "%s: donusum kayipli -- glif %d->%d, kaybolan kod %d, eksik: %s"
            % (kaynak.name, once_glif, sonra_glif, len(kayip), "".join(eksik)))
    gecici.replace(hedef)
    return {"ad": hedef.name, "glif": sonra_glif, "kod": len(sonra_kod),
            "bayt": hedef.stat().st_size}


def main() -> int:
    raporlar = []
    for kaynak in KAYNAKLAR:
        if not kaynak.is_file():
            print("ATLANDI (yok): %s" % kaynak)
            continue
        hedef = HEDEF / (kaynak.stem + ".ttf")
        raporlar.append(cevir(kaynak, hedef))
        r = raporlar[-1]
        print("  %-34s %4d glif · %4d kod noktasi · %d KB"
              % (r["ad"], r["glif"], r["kod"], r["bayt"] // 1024))

    # reportlab gercekten yukleyebiliyor mu -- SONUCA bakilir.
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as RLFont
    for r in raporlar:
        yol = HEDEF / r["ad"]
        pdfmetrics.registerFont(RLFont(yol.stem, str(yol)))
    print("\n%d font cevrildi ve reportlab'a YUKLENDI · %s"
          % (len(raporlar), HEDEF))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
