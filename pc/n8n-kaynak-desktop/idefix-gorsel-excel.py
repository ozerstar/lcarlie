#!/usr/bin/env python3
"""Idefix toplu GORSEL EKLEME Excel'i (Barkod | Gorsel 1..8).

Sablon: https://statics.idefix.com/mpstatics/excelfile/addingProductVisuals.xlsx
Sutunlar indirilen dosyadan okundu: Barkod, Gorsel 1 ... Gorsel 8.

Bizde urun basina 5 gorsel var (Kontrollu V2 TRENDYOL seti, 1200x1800),
`https://n8n.lcarlie.shop/urun-gorsel/<barkod>-01..05.jpg` adresinden HTTPS
ile servis ediliyor. Idefix "SSL sertifikali HTTPS adres" sart kosuyor ve
barkod basina en fazla 8 gorsel kabul ediyor.

🔴 Bu dosya gorsel EKLER, MC/Lc.İmeeke'nin gorsellerini SILMEZ. Silme ayri bir
talep tipi (`deleted_image`) ve toplu modalda yok; urun urun acilmasi gerekir.

Disarida: SUNACNEA ve BUGUARD (yanlis katalog eslesmesi) ve havuzdaki 6
not_matched urun (sayfalari henuz olusmadi).
"""
from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
SABLON = Path("/tmp/t-gorsel.xlsx")
HEDEF = Path("/opt/lcarlie/idefix-hazirlik/toplu-gorsel.xlsx")

YANLIS_ESLESME = {"8684869609097", "8684869609301"}
ESLESEN = {
    "8684869609097", "8684869609134", "8684869609110", "8684869609196",
    "8684869609165", "8684869609158", "8684869609141", "8684869609516",
    "8684869609301", "8684869609561", "8684869609073", "8684869609202",
    "8684869609271", "8684869609066", "8684869609554", "8684869609547",
    "8684869609318", "8684869609127", "8684869609295", "8684869609288",
    "8684869609103", "8684869609370", "8684869609363", "8684869609523",
    "8684869609325", "8684869609356", "8684869609530", "8684869609394",
    "8684869609387", "8684869609233",
}
SUTUN = "ABCDEFGHI"


def main() -> int:
    veri = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    basliklar = ["Barkod"] + [f"Görsel {i}" for i in range(1, 9)]
    satirlar = []
    for b, x in veri.items():
        if b not in ESLESEN or b in YANLIS_ESLESME:
            continue
        g = [x.get(f"gorsel_{i}", "") for i in range(1, 6)]
        g = [u for u in g if u]
        if not g:
            print("GORSELI YOK, atlandi:", x["urun_adi_wix"])
            continue
        satirlar.append([b] + g + [""] * (8 - len(g)))

    kaynak = zipfile.ZipFile(SABLON)
    parcalar = {ad: kaynak.read(ad) for ad in kaynak.namelist()}
    kaynak.close()

    hucreler = []
    for i, satir in enumerate([basliklar] + satirlar, start=1):
        p = [f'<row r="{i}">']
        for j, deger in enumerate(satir):
            if deger == "":
                continue
            p.append(f'<c r="{SUTUN[j]}{i}" t="inlineStr"><is>'
                     f'<t xml:space="preserve">{escape(str(deger))}</t></is></c>')
        p.append("</row>")
        hucreler.append("".join(p))

    sheet = parcalar["xl/worksheets/sheet1.xml"].decode("utf-8")
    sheet = re.sub(r'<dimension ref="[^"]*"/>',
                   f'<dimension ref="A1:I{len(satirlar)+1}"/>', sheet)
    yeni = "<sheetData>" + "".join(hucreler) + "</sheetData>"
    sheet = (re.sub(r"<sheetData>.*?</sheetData>", yeni, sheet, flags=re.S)
             if "<sheetData>" in sheet else re.sub(r"<sheetData\s*/>", yeni, sheet))
    assert "inlineStr" in sheet
    parcalar["xl/worksheets/sheet1.xml"] = sheet.encode("utf-8")

    with zipfile.ZipFile(HEDEF, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, deger in parcalar.items():
            z.writestr(ad, deger)

    k = zipfile.ZipFile(HEDEF)
    s = k.read("xl/worksheets/sheet1.xml").decode("utf-8")
    satir_sayisi = len(re.findall(r'<row r="\d+">', s))
    url_sayisi = len(re.findall(r"urun-gorsel/", s))
    print(f"{HEDEF.name}: {satir_sayisi} satir ({satir_sayisi-1} urun), "
          f"{url_sayisi} gorsel adresi, {HEDEF.stat().st_size} bayt")
    assert satir_sayisi == len(satirlar) + 1
    assert url_sayisi == sum(len([u for u in r[1:] if u]) for r in satirlar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
