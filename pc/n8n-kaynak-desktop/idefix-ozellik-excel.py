#!/usr/bin/env python3
"""Kategori kategori URUN OZELLIGI Excel'leri uretir (toplu guncelleme icin).

Sablon deseni (indirilen ornekten okundu): sheet1 = veri (A: Barkod, B..: ozellik
sutunlari), sheet2 = izinli deger listesi (dogrulama acilir menusu icin).
Yuklemede kategori modalda ayrica secildigi icin dosyadaki dogrulama listesi
onemli degil; onemli olan BASLIK adlari ve hucre METINLERININ kategorinin
izinli deger listesinde birebir bulunmasi.

DOLDURULAN ALANLAR (yalnizca kesin bilinenler)
  Hacim           kutudaki ml degeri (CSV basliklarindan ayiklanir)
  Paket İçi Adet  1 (tekli urun)
  Ürün Formu      urun turunden (krem/sprey/jel/sivi/roll-on -> kategorinin
                  izinli listesinde karsiligi varsa)
Bilinmeyen hicbir alan doldurulmaz; deger listede yoksa o hucre bos kalir.

Yalnizca ENVANTERDEKI (satista/satisa kapali) urunler islenir -- havuzdaki 6
`not_matched` urun panelin toplu yoluna gorunmuyor.
"""
from __future__ import annotations

import csv
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
SABLON = Path("/tmp/t-ozellik.xlsx")
CIKTI = Path("/opt/lcarlie/idefix-hazirlik/ozellik")
OZELLIK_JSON = Path("/tmp/kategori-ozellik.json")   # API'den cekilmis tanimlar
# 🔴 Gruplama KATALOG kategorisine gore yapilir, bizim sectigimize gore DEGIL:
# Idefix ozellikleri urunun katalogtaki kategorisine gore dogruluyor. Katalog
# kategorileri panelin envanter satirlarindan okundu (23.10.2026).
KATALOG_JSON = Path("/tmp/katalog-kategori.json")
AD2ID = {"Nemlendiriciler": "440310605", "Ayak Kremi": "440229053",
         "İntim Bakım Ürünü": "440281091", "Tonik": "440325840",
         "Saç Serum ve Yağı": "440262009", "Yüz Kremi": "440387863",
         "Sinek İlacı ve Kovucu": "880213427", "Yüz Temizleyici": "440322574",
         "Diş Macunu": "440253038", "Bebek Şampuanı": "110124890",
         "Saç Spreyi": "440256031",
         # 23.10.2026: incelemesi biten 6 urunun kategorileri
         "Göz Kremi": "440394057", "Bakım Yağı": "440320571",
         "Masaj, Spa & Wellness": "440246873",
         "Oda Kokusu, Koku Giderici": "880291124"}

# Envanterdeki 30 urun (havuzdaki 6 haric)
# 🔴 Yanlis katalog eslesmesi olan iki barkod ozellik dosyalarina GIRMEZ:
# sayfalari baska urune ait, oraya bizim olcumuz yazilmaz (baslik/aciklama/
# gorsel dosyalarinda da ayni istisna uygulandi).
YANLIS_ESLESME = {"8684869609097", "8684869609301"}

ENVANTER = {
    "8684869609097", "8684869609134", "8684869609110", "8684869609196",
    "8684869609165", "8684869609158", "8684869609141", "8684869609516",
    "8684869609301", "8684869609561", "8684869609073", "8684869609202",
    "8684869609271", "8684869609066", "8684869609554", "8684869609547",
    "8684869609318", "8684869609127", "8684869609295", "8684869609288",
    "8684869609103", "8684869609370", "8684869609363", "8684869609523",
    "8684869609325", "8684869609356", "8684869609530", "8684869609394",
    "8684869609387", "8684869609233",
    # incelemesi 23.10.2026'da biten 6 urun
    "8684869609080", "8684869609172", "8684869609578", "8684869609585",
    "8684869609400", "8684869609608",
}

# Urun formu: baslik/aciklamadan cikan tur -> olasi karsiliklar (kategorinin
# izinli listesinde hangisi varsa o kullanilir)
FORM_ESLEME = [
    (r"roll-?on", ["Roll-On", "Sıvı", "Jel"]),
    (r"sprey", ["Sprey", "Sıvı"]),
    (r"köpü", ["Köpük", "Sıvı"]),
    (r"balm", ["Balm", "Stick", "Krem"]),
    (r"losyon", ["Losyon", "Sıvı", "Krem"]),
    (r"şampuan", ["Şampuan", "Sıvı"]),
    (r"jel", ["Jel"]),
    (r"yağ", ["Yağ", "Sıvı"]),
    (r"krem", ["Krem"]),
    (r"macun", ["Macun", "Krem"]),
]


def hacim(baslik: str) -> str:
    m = re.search(r"(\d+)\s*ml\b", baslik, re.IGNORECASE)
    return f"{m.group(1)} ml" if m else ""


def form_adayi(metin: str) -> list[str]:
    k = metin.casefold().replace("İ", "i")
    for desen, adaylar in FORM_ESLEME:
        if re.search(desen, k):
            return adaylar
    return []


def yaz(hedef: Path, basliklar: list[str], satirlar: list[list[str]]) -> int:
    kaynak = zipfile.ZipFile(SABLON)
    parcalar = {a: kaynak.read(a) for a in kaynak.namelist()}
    kaynak.close()
    sutun = "ABCDEFGHIJ"
    hucreler = []
    for i, satir in enumerate([basliklar] + satirlar, start=1):
        p = [f'<row r="{i}">']
        for j, d in enumerate(satir):
            if not d:
                continue
            p.append(f'<c r="{sutun[j]}{i}" t="inlineStr"><is>'
                     f'<t xml:space="preserve">{escape(str(d))}</t></is></c>')
        p.append("</row>")
        hucreler.append("".join(p))
    s = parcalar["xl/worksheets/sheet1.xml"].decode("utf-8")
    s = re.sub(r'<dimension ref="[^"]*"/>',
               f'<dimension ref="A1:{sutun[len(basliklar)-1]}{len(satirlar)+1}"/>', s)
    yeni = "<sheetData>" + "".join(hucreler) + "</sheetData>"
    s = (re.sub(r"<sheetData>.*?</sheetData>", yeni, s, flags=re.S)
         if "<sheetData>" in s else re.sub(r"<sheetData\s*/>", yeni, s))
    parcalar["xl/worksheets/sheet1.xml"] = s.encode("utf-8")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
        for a, d in parcalar.items():
            z.writestr(a, d)
    return len(satirlar)


def main() -> int:
    tanim = json.loads(OZELLIK_JSON.read_text(encoding="utf-8"))
    veri = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))

    katalog = json.loads(KATALOG_JSON.read_text(encoding="utf-8"))
    gruplar: dict[str, list[dict]] = {}
    for x in veri:
        if x["barkod"] in YANLIS_ESLESME:
            continue
        ad = katalog.get(x["barkod"])
        if not ad:
            continue
        kid = AD2ID.get(ad)
        if not kid:
            print("kategori kimligi yok:", ad)
            continue
        gruplar.setdefault(kid, []).append(x)

    ozet = []
    for kid, urunler in sorted(gruplar.items(), key=lambda t: -len(t[1])):
        alanlar = tanim.get(kid, {})
        kullanilacak, basliklar = [], ["Barkod"]
        # 🔴 Hacim alaninin adi kategoriye gore degisiyor: Oda Kokusu
        # kategorisinde "Boyut/Ebat". Ayni ml degeri oraya da yazilir.
        for ad in ("Hacim", "Boyut/Ebat", "Paket İçi Adet", "Ürün Formu"):
            if ad in alanlar:
                kullanilacak.append(ad)
                basliklar.append(ad)
        atlanan = []
        if not kullanilacak:
            ozet.append((kid, len(urunler), 0, "doldurulabilir alan yok"))
            continue

        satirlar, dolu, atlanan = [], 0, []
        for u in urunler:
            satir = [u["barkod"]]
            for ad in kullanilacak:
                izinli = alanlar[ad]
                deger = ""
                if ad in ("Hacim", "Boyut/Ebat"):
                    h = hacim(u["idefix_baslik"])
                    deger = h if h in izinli else ""
                elif ad == "Paket İçi Adet":
                    deger = "1" if "1" in izinli else ""
                elif ad == "Ürün Formu":
                    for aday in form_adayi(u["idefix_baslik"]):
                        if aday in izinli:
                            deger = aday
                            break
                satir.append(deger)
                if deger:
                    dolu += 1
            # 🔴 Tum hucreleri bos olan satir GONDERILMEZ: Idefix bunu
            # "Geçersiz özellik verisi" diye reddediyor (22.10'da BABY RESCUE
            # 5 ml listede olmadigi icin bos satirla gitti ve reddedildi).
            if any(d for d in satir[1:]):
                satirlar.append(satir)
            else:
                atlanan.append(u["urun_adi_wix"])

        dosya = CIKTI / f"ozellik-{kid}.xlsx"
        n = yaz(dosya, basliklar, satirlar)
        ozet.append((kid, n, dolu, " · ".join(kullanilacak)
                     + (f"  | atlanan: {len(atlanan)}" if atlanan else "")))

    print(f"{'kategori':<12} {'urun':>4} {'dolu':>5}  alanlar")
    for kid, n, dolu, alan in ozet:
        print(f"{kid:<12} {n:>4} {dolu:>5}  {alan}")
    print(f"\ndosyalar: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
