#!/usr/bin/env python3
"""36 urunu n11'in GERCEK kategori kimliklerine esler.

Kimlikler API'den alindi (CategoryService, 24.10.2026) -- public siteden
tahmin edilmedi. Satici agaci public siteden DAHA DERIN cikti; ornegin
"Vucut Nemlendiriciler" yaprak degil, altinda "Vucut Kremi & Losyon" var.
Bu yuzden dunki site tabanli esleme burada yaprak kimlikleriyle yenilendi.

🔴 Hicbir urun tahminle yerlestirilmez. Karsiligi bulunmayan urun BOS kalir.
"""
from __future__ import annotations

import csv
from pathlib import Path

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CIKTI = Path("/opt/lcarlie/n11-hazirlik")

# n11 yaprak kategorileri (API'den, id -> okunur yol)
YAPRAK = {
    1002662: "Cilt Bakımı > Yüz Bakımı > Yüz Kremi",
    1002653: "Cilt Bakımı > Yüz Bakımı > Yüz Temizleyici",
    1002660: "Cilt Bakımı > Yüz Bakımı > Tonik",
    1002655: "Cilt Bakımı > Yüz Bakımı > Göz Kremi",
    1002654: "Cilt Bakımı > Yüz Bakımı > Dudak Bakımı",
    1189211: "Cilt Bakımı > Yüz Bakımı > Cilt Bakım Yağı",
    1002642: "Cilt Bakımı > Vücut Bakımı > Vücut Nemlendiriciler > Vücut Kremi & Losyon",
    1002647: "Cilt Bakımı > Vücut Bakımı > Vücut Sıkılaştırıcı",
    1002646: "Cilt Bakımı > Vücut Bakımı > Vücut Çatlak Kremi",
    1258211: "Cilt Bakımı > El, Ayak, Tırnak > Ayak Bakımı > Ayak Kremi",
    1258212: "Cilt Bakımı > El, Ayak, Tırnak > Ayak Bakımı > Nasır & Mantar Önleyici",
    1252203: "Cilt Bakımı > Güneş & Bronzluk > Güneş Kremleri",
    1000021: "Bebek Bakım & Sağlık > Bebek Bakım > Bebek Güneş Kremi",
    1000023: "Bebek Bakım & Sağlık > Bebek Bakım > Bebek Losyonu",
    1000024: "Bebek Bakım & Sağlık > Bebek Bakım > Pişik Kremi",
    1000019: "Bebek Bakım & Sağlık > Bebek Bakım > Bebek Bakım Ürünleri Diğer",
    1002592: "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Şampuan",
    1002590: "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Saç Bakım Yağı",
    1002586: "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Saç Losyonu",
    1259207: "Ağız & Diş Bakımı > Diş Macunu",
    1259201: "Ağız & Diş Bakımı > Ağız Temizleme & Gargara",
    1002550: "Kadın Bakım Ürünleri > Genital Ürünler > Genital Bölge Temizleme",
    1002508: "Erkek Bakım Ürünleri > Erkek Cilt Bakımı",
    1252200: "Parfüm & Deodorant > Vücut Spreyi",
}

# barkod -> n11 yaprak kimligi. Her satirin gerekcesi yanindadir.
ESLEME: dict[str, int] = {
    "8684869609233": 1002662,   # HYDRAVIE nemlendirici yuz kremi
    "8684869609202": 1002662,   # SERALIMBO gece bakim kremi (yuz)
    "8684869609196": 1002662,   # CALJAW gece cene bakim roll-on (yuze uygulanir)
    "8684869609295": 1002653,   # LUCIDERM yuz temizleme kopugu
    "8684869609080": 1002660,   # CALMAROS tonik sprey
    "8684869609172": 1002655,   # OPTYWAVE goz cevresi roll-on
    "8684869609134": 1002654,   # LIPVORA dudak balmi
    "8684869609578": 1189211,   # CALMORIS aromatik bakim yagi roll-on
    "8684869609585": 1189211,   # MENTHALIS bitki yaglari roll-on
    "8684869609073": 1002642,   # DERMANOVA bitkisel cilt bakim kremi
    "8684869609271": 1002642,   # DERMAVASC bacak ve vucut bakim kremi
    "8684869609554": 1002642,   # DERMARNICA arnika ozlu bakim kremi
    "8684869609516": 1002642,   # DERMAMOVERA masaj ve bakim kremi
    "8684869609547": 1002642,   # KINESIS+ sporcu bakim kremi
    "8684869609400": 1002642,   # DORSIVIA isinma etkili masaj kremi
    "8684869609066": 1002642,   # DERMABED bariyer ve koruyucu krem
    "8684869609141": 1002647,   # LIFTELLE gogus/dekolte sikilastirici
    "8684869609561": 1002646,   # DERMASTRA gerilme bolgeleri -> catlak kremi
    "8684869609103": 1258211,   # DERMAGUARD ayak ve tirnak bakim kremi
    "8684869609288": 1258212,   # DERMACORN sertlesmis bolge -> nasir onleyici
    "8684869609097": 1252203,   # SUNACNEA +30 SPF gunes kremi
    "8684869609530": 1000021,   # BABYSOL bebek gunes kremi
    "8684869609523": 1000023,   # BABYSOFT bebek vucut losyonu
    "8684869609325": 1000024,   # MINISOOTH bebek pisik kremi
    "8684869609363": 1000019,   # BABY RESCUE anlik yatistirici
    "8684869609356": 1002592,   # BABYSHOWER sampuan
    "8684869609158": 1002590,   # HAIR NOURISHER sac bakim yagi
    "8684869609370": 1002586,   # EASYCOMB sac acici -> sac losyonu
    "8684869609387": 1259207,   # BABYDENT dis bakim jeli
    "8684869609394": 1259207,   # BRIGHT SMILE dis macunu
    "8684869609165": 1259201,   # ORAGARDE agiz bakim spreyi
    "8684869609318": 1002550,   # INTIMBLANC hassas bolge
    "8684869609127": 1002550,   # FEMISIA intim bakim kremi
    "8684869609110": 1002508,   # VIREON FOR MEN erkek bakim kremi
    "8684869609301": 1252200,   # BUGUARD bitkisel vucut spreyi
}

# 🔴 Karsiligi bulunamayan: kozmetik agacinda yeri yok
ACIKTA = {
    "8684869609608": "SOFTGUARD tekstil/yatak-doşemelik bakim spreyi — n11'in "
                     "kozmetik, bebek, agiz-dis, sac ve parfum dallarinda "
                     "karsiligi YOK. Ev & Yasam / Temizlik tarafinda aranmali.",
}


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    veri = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    satir, acikta = [], []
    for b, u in veri.items():
        ad = (u.get("urun_adi_wix") or "").split("|")[0].strip()
        kid = ESLEME.get(b)
        if not kid:
            satir.append({"barkod": b, "urun": ad, "n11_kategori_id": "",
                          "n11_kategori": "", "durum": "ACIKTA"})
            acikta.append((ad, ACIKTA.get(b, "esleme tanimlanmadi")))
            continue
        satir.append({"barkod": b, "urun": ad, "n11_kategori_id": kid,
                      "n11_kategori": YAPRAK[kid], "durum": "HAZIR"})

    with (CIKTI / "n11-kategori-id.csv").open("w", encoding="utf-8-sig", newline="") as y:
        w = csv.DictWriter(y, fieldnames=list(satir[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(satir)

    hazir = [s for s in satir if s["durum"] == "HAZIR"]
    dagilim: dict[str, int] = {}
    for s in hazir:
        dagilim[s["n11_kategori"]] = dagilim.get(s["n11_kategori"], 0) + 1

    print(f"hazir: {len(hazir)}/{len(satir)}")
    for k, n in sorted(dagilim.items(), key=lambda t: -t[1]):
        print(f"  {n:>2}  {k}")
    if acikta:
        print("\nacikta:")
        for ad, neden in acikta:
            print(f"  {ad} — {neden[:70]}")
    print(f"\nkullanilan farkli kategori: {len(dagilim)}")
    print(f"yazildi: {CIKTI / 'n11-kategori-id.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
