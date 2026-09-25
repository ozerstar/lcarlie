#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Satış fiyat listesini DOĞRULAR ve bayi fiyatına çevirir.

🔴 LİSTE GÖRSEL OLARAK GELDİ (PDF içinde metin yok, 5 gömülü resim).
Yani veriyi okuyan benim gözüm; göz yanılır. Bu yüzden hiçbir satır
"okudum, doğrudur" diye kabul edilmiyor: listenin KENDİ iskonto mantığı
çıkarılıp her hücre yeniden hesaplanıyor ve tutmayan hücre RAPORLANIYOR.

Listenin mantığı (tutarlı satırlardan çıkarıldı):
    %30 iskontolu KDV dahil  = PSF × 0,70
    %30 iskontolu KDV hariç  = PSF × 0,70 / 1,20
    %40 iskontolu KDV dahil  = PSF × 0,60
    %40 iskontolu KDV hariç  = PSF × 0,60 / 1,20
    Trendyol satış fiyatı    = PSF × 1,15

Yuvarlama listede tam sayıya yapılmış; 1 TL tolerans veriliyor.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

KAP = "lcarlie-postgres"
TOLERANS = 1.0

# (ad, barkod, PSF, %30 hariç, %30 dahil, %40 hariç, %40 dahil, Trendyol)
SATIRLAR = [
    ("BABY RESCUE",      "8684869609363",  900,  525,  630,  450,  540, 1035),
    ("BABYDENT",         "8684869609387", 1100,  642,  770,  550,  660, 1265),
    ("BABYSHOWER",       "8684869609356", 1100,  642,  770,  550,  660, 1265),
    ("BABYSOFT",         "8684869609523", 2100, 1225, 1470, 1050, 1260, 2415),
    ("BABYSOL",          "8684869609530", 1250,  729,  875,  625,  750, 1438),
    ("BRIGHT SMILE",     "8684869609394",  950,  554,  665,  475,  570, 1093),
    ("BUGUARD",          "8684869609301",  900,  525,  630,  450,  540, 1035),
    ("CAL JAW",          "8684869609196", 1100,  642,  770,  550,  660, 1265),
    ("CALMAROS",         "8684869609080", 1850, 1079, 1295,  925, 1110, 2128),
    ("CALMORIS",         "8684869609578", 1100,  642,  770,  550,  660, 1265),
    ("DERMABED",         "8684869609066", 1950, 1138, 1365,  975, 1170, 2243),
    ("DERMACORN",        "8684869609288",  900,  525,  630,  450,  540, 1035),
    ("DERMAGUARD",       "8684869609103", 1200,  700,  840,  600,  720, 1380),
    ("DERMAMOVERA",      "8684869609516", 1950, 1138, 1365,  975, 1170, 2243),
    ("DERMANOVA",        "8684869609073", 2100, 1225, 1470, 1050, 1260, 2415),
    ("DERMARNICA",       "8684869609554", 2100, 1225, 1470, 1050, 1260, 2415),
    ("DERMASTRA",        "8684869609561", 2100, 1225, 1470, 1050, 1260, 2415),
    ("DERMAVASC",        "8684869609271", 2100, 1225, 1470, 1050, 1260, 2415),
    ("EASYCOMB",         "8684869609370", 1020,  595,  714,  510,  612, 1173),
    ("FEMISIA for WOMEN", "8684869609127", 2400, 1400, 1680, 1200, 1440, 2760),
    ("HAIR NOURISHER",   "8684869609158", 1200,  700,  840,  600,  720, 1380),
    ("HYDRAVIE",         "8684869609233", 1200,  700,  840,  600,  720, 1380),
    ("INTIMBLANC",       "8684869609318", 2100, 1225, 1470, 1050, 1260, 2415),
    ("KINESIS +",        "8684869609547", 1950, 1138, 1365,  975, 1170, 2415),
    ("LIFTELLE",         "8684869609141", 2100, 1225, 1470, 1050, 1260, 2415),
    ("LIPVORA",          "8684869609134",  900,  525,  630,  450,  540, 1035),
    ("LUCIDERM",         "8684869609295", 1200,  700,  840,  600,  720, 1380),
    ("MENTHALIS",        "8684869609585", 1100,  642,  840,  650,  660, 1380),
    ("MINISOOTH",        "8684869609325", 1200,  700,  840,  600,  720, 1380),
    ("OPTYWAVE",         "8684869609509", 1100,  642,  770,  550,  660, 1265),
    ("ORAGARDE",         "8684869609165",  900,  525,  630,  450,  540, 1035),
    ("SERALIMBO",        "8684869609202", 2100, 1225, 1470, 1050, 1260, 2415),
    ("SOFTGUARD",        "8684869609301",  950,  554,  665,  475,  570, 1093),
    ("SUNACNEA +30 SPF", "8684869609097", 1200,  700,  840,  600,  720, 1380),
    ("VIREON FOR MEN",   "8684869609110", 2400, 1400, 1680, 1200, 1440, 2760),
]

SUTUNLAR = [
    ("%30 KDV hariç", lambda p: p * 0.70 / 1.20),
    ("%30 KDV dahil", lambda p: p * 0.70),
    ("%40 KDV hariç", lambda p: p * 0.60 / 1.20),
    ("%40 KDV dahil", lambda p: p * 0.60),
    ("Trendyol",      lambda p: p * 1.15),
]


def oku(sql: str) -> list:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input="\\set ON_ERROR_STOP on\n" + sql, capture_output=True,
        text=True, timeout=60, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def main() -> int:
    print("LISTE: %d satir" % len(SATIRLAR))

    # 1) HESAP DENETIMI
    hatali = []
    for satir in SATIRLAR:
        ad, barkod, psf = satir[0], satir[1], satir[2]
        for i, (etiket, hesap) in enumerate(SUTUNLAR):
            listede = satir[3 + i]
            olmasi = hesap(psf)
            if abs(listede - olmasi) > TOLERANS:
                hatali.append((ad, etiket, listede, round(olmasi)))

    if hatali:
        print("\n🔴 HESAP TUTMAYAN HUCRE: %d" % len(hatali))
        for ad, etiket, listede, olmasi in hatali:
            fark = (listede - olmasi) / olmasi * 100.0
            print("   %-18s %-14s listede %5d · olmasi gereken %5d  (%%%+.1f)"
                  % (ad, etiket, listede, olmasi, fark))
    else:
        print("\nhesap denetimi: TUM HUCRELER TUTUYOR")

    # 2) BARKOD CAKISMASI
    barkodlar = {}
    for satir in SATIRLAR:
        barkodlar.setdefault(satir[1], []).append(satir[0])
    cakisan = {b: a for b, a in barkodlar.items() if len(a) > 1}
    if cakisan:
        print("\n🔴 AYNI BARKOD:")
        for b, adlar in cakisan.items():
            print("   %s -> %s" % (b, " + ".join(adlar)))

    # 3) KATALOGLA ESLESME
    kayitlar = oku("""SELECT row_to_json(t) FROM (
      SELECT slug, sku, ad, wix_satis FROM (
        SELECT w.slug, w.sku, w.ad, k.wix_satis
          FROM raw.wix_urun w
          LEFT JOIN mart.urun_karti k ON k.sku = w.sku AND k.urun_adi = w.ad
      ) q) t;""")
    kat_barkod = {}
    for k in kayitlar:
        kat_barkod.setdefault(k["sku"], []).append(k)

    eslesen, eslesmeyen, fiyat_farki = [], [], []
    for satir in SATIRLAR:
        ad, barkod, psf = satir[0], satir[1], satir[2]
        adaylar = kat_barkod.get(barkod, [])
        if len(adaylar) == 1:
            sec = adaylar[0]
        else:
            # Barkod cakisiyorsa ADA gore ayir.
            sec = next((a for a in adaylar
                        if ad.split("(")[0].strip().upper()
                        in (a["ad"] or "").upper()), None)
        if sec is None:
            eslesmeyen.append((ad, barkod))
            continue
        eslesen.append((ad, sec["slug"], psf, sec.get("wix_satis")))
        w = sec.get("wix_satis")
        if w is not None and abs(float(w) - psf) > 1:
            fiyat_farki.append((sec["slug"], psf, float(w)))

    print("\nESLESME: %d/%d" % (len(eslesen), len(SATIRLAR)))
    if eslesmeyen:
        print("🔴 KATALOGDA BULUNAMAYAN:")
        for ad, b in eslesmeyen:
            print("   %-20s %s" % (ad, b))

    kat_slug = {k["slug"] for k in kayitlar}
    listede_yok = sorted(kat_slug - {e[1] for e in eslesen})
    if listede_yok:
        print("\n🔴 KATALOGDA VAR, FIYAT LISTESINDE YOK:")
        for s in listede_yok:
            u = next(k for k in kayitlar if k["slug"] == s)
            print("   %-28s %-16s Wix %s TL"
                  % (s, u["sku"], u.get("wix_satis")))

    if fiyat_farki:
        print("\n⚠ PSF ile WIX FIYATI FARKLI:")
        for s, psf, w in fiyat_farki:
            print("   %-28s liste %5d · Wix %5.0f" % (s, psf, w))
    else:
        print("\nPSF ile Wix fiyati: TUM ESLESENLERDE AYNI")

    Path("/tmp/fiyat-eslesme.json").write_text(
        json.dumps({"eslesen": eslesen, "hatali_hucre": hatali,
                    "listede_yok": listede_yok}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
