#!/usr/bin/env python3
"""Idefix "Urun Denetim Bilgileri" toplu guncelleme Excel'ini uretir.

SABLON (indirilen dosyadan okundu, 23.10.2026)
  https://statics.idefix.com/mpstatics/excelfile/urun-denetim-bilgileri-guncelleme.xlsx
  A Barkod | B Menşei | C Üretici Bilgisi
  D İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı
  E CE Uygunluk Sembolü | F Kullanım Talimatı / Uyarıları Görseli
  G Paket Görseli (Ön) | H Paket Görseli (Arka)
  I Ürün Bilgi Formu Görseli | J Enerji Sınıfı Görseli
  K Enerji ve Besin Değerleri Görseli
  sheet2 = ulke listesi (dogrulama acilir menusu)

🔴 BU ALANLAR YASAL. Hicbiri tahminle doldurulmaz. Kaynaklar:

  Menşei          = "Türkiye"
                    DAYANAK: ambalajin yasal blogunda "Made in TÜRKİYE"
                    yaziyor (06 TASARIM-BASKI/ambalaj/ML BUYUK KUTU
                    sayfa goruntusu, 10 ml kutu).

  Yetkili Temsilci= LEMOS MEDİKAL ... A.Ş. + adres
                    DAYANAK: ayni yasal blok "Responsible Person/Sorumlu Kişi".
                    🔴 ADRES CELISKISI: kutuda ESKI adres basili
                    (Üniversiteler Mah. 1636. Cad. No: 1/54 Çankaya/Ankara),
                    resmi adres ise artik Yenimahalle. Asagida GUNCEL adres
                    kullanilir; karar sahibin.

  Üretici Bilgisi = BOS BIRAKILIR.
                    Kutuda uretici YAZMIYOR, yalnizca sorumlu kisi var.
                    Sirketin 7 sertifikasinin kapsami "kozmetik urunlerinin
                    ALIMI VE SATISI" -- yani LEMOS uretici degil. Buraya LEMOS
                    yazmak gercege aykiri olur. Sahip fason ureticiyi
                    bildirene kadar bos kalir.

  CE              = BOS. Kozmetik urunler CE isaretine tabi degildir.

  F-K gorseller   = BOS. Bu gorseller (kullanim/uyari, paket on-arka, urun
                    bilgi formu) henuz HTTPS adresinde yayinlanmadi.
"""
from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
SABLON = Path("/tmp/urun-denetim-bilgileri-guncelleme.xlsx")
HEDEF = Path("/opt/lcarlie/idefix-hazirlik/toplu-denetim.xlsx")

MENSEI = "Türkiye"
TEMSILCI = ("LEMOS MEDİKAL SAĞLIK VE İŞ GÜVENLİĞİ İNŞAAT GIDA TURİZM SANAYİ VE "
            "TİCARET A.Ş. · Mehmet Akif Ersoy Mah. 325. Sk. No:3/117 "
            "Yenimahalle/Ankara · lcarlie.com.tr")

# 23.10.2026 15:xx -- havuzdaki 6 urun ONAYLANDI ve envantere dustu; artik
# 36'sinin 36'si da panelin toplu yoluna gorunuyor.
ENVANTER = {
    "8684869609097", "8684869609134", "8684869609110", "8684869609196",
    "8684869609165", "8684869609158", "8684869609141", "8684869609516",
    "8684869609301", "8684869609561", "8684869609073", "8684869609202",
    "8684869609271", "8684869609066", "8684869609554", "8684869609547",
    "8684869609318", "8684869609127", "8684869609295", "8684869609288",
    "8684869609103", "8684869609370", "8684869609363", "8684869609523",
    "8684869609325", "8684869609356", "8684869609530", "8684869609394",
    "8684869609387", "8684869609233",
    # inceleme bitince eklenen 6 urun
    "8684869609080", "8684869609172", "8684869609578", "8684869609585",
    "8684869609400", "8684869609608",
}

BASLIKLAR = ["Barkod", "Menşei", "Üretici Bilgisi",
             "İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı",
             "CE Uygunluk Sembolü", "Kullanım Talimatı / Uyarıları Görseli",
             "Paket Görseli (Ön)", "Paket Görseli (Arka)",
             "Ürün Bilgi Formu Görseli", "Enerji Sınıfı Görseli",
             "Enerji ve Besin Değerleri Görseli"]
SUTUN = "ABCDEFGHIJK"


def main() -> int:
    veri = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    satirlar = []
    for b in veri:
        if b not in ENVANTER:
            continue
        satirlar.append([b, MENSEI, "", TEMSILCI, "", "", "", "", "", "", ""])

    kaynak = zipfile.ZipFile(SABLON)
    parcalar = {a: kaynak.read(a) for a in kaynak.namelist()}
    kaynak.close()

    hucreler = []
    for i, satir in enumerate([BASLIKLAR] + satirlar, start=1):
        p = [f'<row r="{i}">']
        for j, d in enumerate(satir):
            if not d:
                continue
            p.append(f'<c r="{SUTUN[j]}{i}" t="inlineStr"><is>'
                     f'<t xml:space="preserve">{escape(str(d))}</t></is></c>')
        p.append("</row>")
        hucreler.append("".join(p))

    s = parcalar["xl/worksheets/sheet1.xml"].decode("utf-8")
    s = re.sub(r'<dimension ref="[^"]*"/>',
               f'<dimension ref="A1:K{len(satirlar)+1}"/>', s)
    yeni = "<sheetData>" + "".join(hucreler) + "</sheetData>"
    s = (re.sub(r"<sheetData>.*?</sheetData>", yeni, s, flags=re.S)
         if "<sheetData>" in s else re.sub(r"<sheetData\s*/>", yeni, s))
    assert "inlineStr" in s, "satirlar yazilamadi"
    parcalar["xl/worksheets/sheet1.xml"] = s.encode("utf-8")

    with zipfile.ZipFile(HEDEF, "w", zipfile.ZIP_DEFLATED) as z:
        for a, d in parcalar.items():
            z.writestr(a, d)

    k = zipfile.ZipFile(HEDEF)
    g = k.read("xl/worksheets/sheet1.xml").decode("utf-8")
    n = len(re.findall(r'<row r="\d+">', g))
    print(f"{HEDEF.name}: {n} satir ({n-1} urun), {HEDEF.stat().st_size} bayt")
    print(f"  Menşei       : {MENSEI}")
    print(f"  Temsilci     : {TEMSILCI[:60]}...")
    print("  Üretici      : BOS (kutuda yazmiyor, sahip bildirecek)")
    print("  CE           : BOS (kozmetikte gecerli degil)")
    print("  F-K gorseller: BOS (henuz yayinlanmadi)")
    assert n == len(satirlar) + 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
