#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bayi fiyat tablosunu Wix PSF'inden HESAPLAYARAK doldurur.

SAHİBİN KARARI (25.09.2026): "Wix'teki ana fiyatları alarak tabloları
doldurabilirsin %'lerle."

Bu, otoriteyi değiştirir. Önceki yükleme basılı listeyi kaynak sayıyor,
hesapla tutmayan hücreyi `celiskili` işaretleyip fiyatı gizliyordu.
Artık kaynak Wix'teki satış fiyatı (PSF); kademeler listenin kendi
iskonto mantığıyla HESAPLANIR. Basılı listedeki dört sapma böylece
kapanır -- düzeltilmiş olmaz, YERİNE hesap konur; ikisi aynı şey değil,
o yüzden sapmalar rapora yazılıp saklanır.

    %30 KDV dahil = PSF x 0,70      %40 KDV dahil = PSF x 0,60
    %30 KDV hariç = PSF x 0,70/1,2  %40 KDV hariç = PSF x 0,60/1,2
    Trendyol      = PSF x 1,15

🔴 YUVARLAMA VARSAYIM DEĞİL, KANITTIR. Kural (tam TL'ye, yarımı yukarı)
basılı listenin ÇELİŞKİSİZ hücrelerine uygulanır; hepsini birebir
üretmiyorsa betik YAZMADAN durur. Aksi halde "hesap" dediğim şey,
listeyi yeniden yazmaktan ibaret olurdu.
"""
from __future__ import annotations

import json
import subprocess
from decimal import Decimal, ROUND_HALF_UP

KAP = "lcarlie-postgres"
KAYNAK = "Wix PSF + liste iskonto mantigi (sahip karari 25.09.2026)"

# (sutun, etiket, carpan, bolen)
KADEMELER = [
    ("isk30_haric", "%30 KDV hariç", Decimal("0.70"), Decimal("1.2")),
    ("isk30_dahil", "%30 KDV dahil", Decimal("0.70"), Decimal("1")),
    ("isk40_haric", "%40 KDV hariç", Decimal("0.60"), Decimal("1.2")),
    ("isk40_dahil", "%40 KDV dahil", Decimal("0.60"), Decimal("1")),
    ("trendyol",    "Trendyol",      Decimal("1.15"), Decimal("1")),
]

# Barkod şüpheleri fiyattan AYRI tutulur: barkod belirsizliği depoyu
# ilgilendirir, sahada söylenecek fiyatı değil.
BARKOD_NOTU = {
    "optywave": "Fiyat listesinde 8684869609509, Wix ve katalogda "
                "8684869609172. Ad ve PSF birebir ayni; ayni urun sayildi, "
                "barkod teyit edilmeli.",
    "buguard": "BUGUARD ve SOFTGUARD ana veride AYNI barkodu tasiyor "
               "(8684869609301). Wix hatasi degil, kaynak veride. "
               "Eslesme ada gore yapildi.",
    "softguard": "BUGUARD ve SOFTGUARD ana veride AYNI barkodu tasiyor "
                 "(8684869609301). Wix hatasi degil, kaynak veride. "
                 "Eslesme ada gore yapildi.",
}


def kademe(psf: Decimal, carpan: Decimal, bolen: Decimal) -> int:
    """Tam TL'ye yuvarla, yarımı yukarı."""
    return int((psf * carpan / bolen).quantize(Decimal("1"),
                                               rounding=ROUND_HALF_UP))


def calistir(sql: str, degiskenler: dict | None = None) -> list:
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in (degiskenler or {}).items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=120, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:500])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def main() -> int:
    mevcut = {r["urun_slug"]: r for r in calistir(
        "SELECT row_to_json(t) FROM (SELECT * FROM core.urun_bayi_fiyat) t;")}
    wix = calistir("""SELECT row_to_json(t) FROM (
      SELECT slug, sku, ad, fiyat FROM raw.wix_urun
       WHERE slug IS NOT NULL AND fiyat IS NOT NULL ORDER BY slug) t;""")
    if not wix:
        raise SystemExit("DURDU: Wix urun fiyati okunamadi")

    # -- 1. YUVARLAMA KURALINI KANITLA ------------------------------------
    # Yalniz FIYAT celiskisi olmayan satirlarin basili hucreleri.
    sinanan = tutan = 0
    kirik = []
    for s in wix:
        m = mevcut.get(s["slug"])
        if not m or m.get("celiskili") or m.get("psf") is None:
            continue
        psf = Decimal(str(m["psf"]))
        for sutun, etiket, carpan, bolen in KADEMELER:
            basili = m.get(sutun)
            if basili is None:
                continue
            sinanan += 1
            if int(Decimal(str(basili))) == kademe(psf, carpan, bolen):
                tutan += 1
            else:
                kirik.append("%s %s: basili %s, kural %d"
                             % (s["slug"], etiket, basili,
                                kademe(psf, carpan, bolen)))
    print("YUVARLAMA KURALI: %d/%d basili hucre birebir uretildi"
          % (tutan, sinanan))
    if kirik:
        print("KURAL TUTMUYOR -- hicbir sey yazilmadi:")
        for k in kirik[:12]:
            print("   " + k)
        return 2
    if sinanan < 100:
        print("DURDU: yalniz %d hucre sinandi, kural kanitlanmis "
              "sayilmaz" % sinanan)
        return 2

    # -- 2. HESAPLA, FARKLARI RAPORLA, YAZ --------------------------------
    degisen, yeni, sapma = [], [], []
    for s in wix:
        slug, psf = s["slug"], Decimal(str(s["fiyat"]))
        m = mevcut.get(slug)
        hesap = {sutun: kademe(psf, carpan, bolen)
                 for sutun, _e, carpan, bolen in KADEMELER}

        if m is None:
            yeni.append((slug, int(psf)))
        else:
            if m.get("psf") is not None and Decimal(str(m["psf"])) != psf:
                sapma.append("%s PSF: tabloda %s, Wix %s"
                             % (slug, m["psf"], psf))
            for sutun, etiket, _c, _b in KADEMELER:
                basili = m.get(sutun)
                if basili is not None and int(Decimal(str(basili))) != hesap[sutun]:
                    sapma.append("%s %s: basili %s -> hesap %d"
                                 % (slug, etiket, int(Decimal(str(basili))),
                                    hesap[sutun]))
            if any(m.get(c) is None or int(Decimal(str(m[c]))) != hesap[c]
                   for c, _e, _x, _y in KADEMELER):
                degisen.append(slug)

        barkod = (m or {}).get("barkod") or s.get("sku")
        bnot = BARKOD_NOTU.get(slug)
        calistir("""
          INSERT INTO core.urun_bayi_fiyat
            (urun_slug, barkod, psf, psf_kaynagi,
             isk30_haric, isk30_dahil, isk40_haric, isk40_dahil, trendyol,
             bayi_fiyat, celiskili, celiski_notu,
             barkod_celiskili, barkod_notu, kaynak, giren)
          VALUES (:'slug', NULLIF(:'barkod',''), %d, 'Wix satis fiyati',
                  %d, %d, %d, %d, %d,
                  %d, false, NULL,
                  %s, NULLIF(:'bnot',''), :'kaynak', 'wix-hesap')
          ON CONFLICT (urun_slug) DO UPDATE SET
            barkod = EXCLUDED.barkod, psf = EXCLUDED.psf,
            psf_kaynagi = EXCLUDED.psf_kaynagi,
            isk30_haric = EXCLUDED.isk30_haric,
            isk30_dahil = EXCLUDED.isk30_dahil,
            isk40_haric = EXCLUDED.isk40_haric,
            isk40_dahil = EXCLUDED.isk40_dahil,
            trendyol = EXCLUDED.trendyol, bayi_fiyat = EXCLUDED.bayi_fiyat,
            celiskili = false, celiski_notu = NULL,
            barkod_celiskili = EXCLUDED.barkod_celiskili,
            barkod_notu = EXCLUDED.barkod_notu,
            kaynak = EXCLUDED.kaynak, giren = EXCLUDED.giren,
            girildi = now();""" % (
            int(psf), hesap["isk30_haric"], hesap["isk30_dahil"],
            hesap["isk40_haric"], hesap["isk40_dahil"], hesap["trendyol"],
            hesap["isk40_haric"],          # bayi_fiyat = en dusuk kademe
            "true" if bnot else "false"),
            {"slug": slug, "barkod": barkod or "", "bnot": bnot or "",
             "kaynak": KAYNAK})

    # -- 3. OLC -----------------------------------------------------------
    if sapma:
        print("\nBASILI LISTEDEN SAPAN HUCRELER (hesap gecerli sayildi):")
        for x in sapma:
            print("   " + x)
    if yeni:
        print("\nYENI SATIR: " + ", ".join("%s (%d TL)" % y for y in yeni))

    ozet = calistir("""SELECT row_to_json(t) FROM (
      SELECT count(*) AS toplam,
             count(psf) AS psf_dolu,
             count(*) FILTER (WHERE celiskili) AS fiyat_celiskili,
             count(*) FILTER (WHERE barkod_celiskili) AS barkod_celiskili,
             count(*) FILTER (WHERE isk40_dahil IS NOT NULL)
               AS kademe_dolu FROM mart.bayi_fiyat_gecerli) t;""")[0]
    print("\ntabloda: %s urun - PSF %s - kademe %s - fiyat celiskisi %s - "
          "barkod suphesi %s"
          % (ozet["toplam"], ozet["psf_dolu"], ozet["kademe_dolu"],
             ozet["fiyat_celiskili"], ozet["barkod_celiskili"]))

    eksik = calistir("""SELECT row_to_json(t) FROM (
      SELECT DISTINCT w.slug FROM raw.wix_urun w
       WHERE w.slug IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM mart.bayi_fiyat_gecerli b
                          WHERE b.urun_slug = w.slug
                            AND b.isk40_dahil IS NOT NULL)
       ORDER BY 1) t;""")
    if eksik:
        print("KADEME FIYATI OLMAYAN URUN: %s"
              % ", ".join(e["slug"] for e in eksik))
    else:
        print("kademe fiyati olmayan urun YOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
