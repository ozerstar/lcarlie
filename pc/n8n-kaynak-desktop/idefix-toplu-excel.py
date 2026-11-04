#!/usr/bin/env python3
"""Idefix toplu guncelleme Excel'lerini uretir (baslik / aciklama).

NEDEN BU YOL
Panelde her urun icin ayri "Urun Bilgisi Guncelleme" modali var ama otomasyonla
surulmesi kirilgan (menu sayfanin ustune sabitleniyor, JS click modali acmiyor).
Panelin KENDI toplu yolu ayni talebi uretiyor: Envanter > urunleri sec >
"Toplu Urun Bilgisi Guncelle" > alan sec > Ornek Excel > doldur > yukle.

Sablon sutunlari (indirilen dosyadan okundu):
  productDescription.xlsx -> Barkod | Urun Aciklamasi
  productName.xlsx        -> bos geldi; ayni desenle Barkod | Urun Adi

Hucreler INLINE STRING olarak yazilir (sharedStrings'e dokunmadan), boylece
uzun HTML aciklamalar kacis sorunu cikarmaz.

🔴 DISARIDA BIRAKILANLAR
- Yanlis eslesen iki urun (SUNACNEA 8684869609097, BUGUARD 8684869609301):
  katalog sayfalari baska urune ait; bizim metnimiz oraya YAZILMAZ.
- Aciklamasi panelden tek tek zaten gonderilmis dortlu: HYDRAVIE, VIREON,
  LIPVORA, LIFTELLE (tekrar gonderilirse ayni talep ikilenir).
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CIKTI = Path("/opt/lcarlie/idefix-hazirlik")

YANLIS_ESLESME = {"8684869609097", "8684869609301"}
ACIKLAMA_GONDERILDI = {"8684869609233", "8684869609110", "8684869609134", "8684869609141"}

# Katalogta eslesen 30 urun (pool/list'ten alindi); havuzdaki 6 not_matched
# urun bu listede YOK -- onlarin sayfasi henuz olusmadi.
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


def xlsx_yaz(sablon: Path, hedef: Path, baslik: tuple[str, str],
             satirlar: list[tuple[str, str]]) -> None:
    kaynak = zipfile.ZipFile(sablon)
    parcalar = {ad: kaynak.read(ad) for ad in kaynak.namelist()}
    kaynak.close()

    hucreler = []
    tum = [baslik] + satirlar
    for i, (a, b) in enumerate(tum, start=1):
        hucreler.append(
            f'<row r="{i}">'
            f'<c r="A{i}" t="inlineStr"><is><t xml:space="preserve">{escape(a)}</t></is></c>'
            f'<c r="B{i}" t="inlineStr"><is><t xml:space="preserve">{escape(b)}</t></is></c>'
            f'</row>')
    sheet = parcalar["xl/worksheets/sheet1.xml"].decode("utf-8")
    sheet = re.sub(r'<dimension ref="[^"]*"/>',
                   f'<dimension ref="A1:B{len(tum)}"/>', sheet)
    yeni = "<sheetData>" + "".join(hucreler) + "</sheetData>"
    if "<sheetData>" in sheet:
        sheet = re.sub(r"<sheetData>.*?</sheetData>", yeni, sheet, flags=re.S)
    else:
        sheet = re.sub(r"<sheetData\s*/>", yeni, sheet)
    assert "inlineStr" in sheet, "satirlar yazilamadi"
    parcalar["xl/worksheets/sheet1.xml"] = sheet.encode("utf-8")

    hedef.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, veri in parcalar.items():
            z.writestr(ad, veri)

    # Geri oku ve dogrula
    k = zipfile.ZipFile(hedef)
    s = k.read("xl/worksheets/sheet1.xml").decode("utf-8")
    bulunan = len(re.findall(r'<row r="\d+">', s))
    print(f"  {hedef.name}: {bulunan} satir ({bulunan-1} urun), "
          f"{hedef.stat().st_size} bayt")
    assert bulunan == len(tum), f"satir sayisi tutmadi: {bulunan} != {len(tum)}"


def main() -> int:
    veri = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    acik, bas = [], []
    for b, x in veri.items():
        if b not in ESLESEN or b in YANLIS_ESLESME:
            continue
        if b not in ACIKLAMA_GONDERILDI:
            acik.append((b, x["idefix_aciklama"]))
        bas.append((b, x["idefix_baslik"]))

    print("uretiliyor:")
    xlsx_yaz(Path("/tmp/t-productDescription.xlsx"),
             CIKTI / "toplu-aciklama.xlsx",
             ("Barkod", "Ürün Açıklaması"), acik)
    xlsx_yaz(Path("/tmp/t-productName.xlsx"),
             CIKTI / "toplu-baslik.xlsx",
             ("Barkod", "Ürün Adı"), bas)

    print(f"\naciklama gonderilecek : {len(acik)} urun")
    print(f"baslik gonderilecek   : {len(bas)} urun")
    print(f"disarida birakilan    : yanlis eslesme {len(YANLIS_ESLESME)}, "
          f"aciklamasi zaten gonderilen {len(ACIKLAMA_GONDERILDI)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
