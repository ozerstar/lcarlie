#!/usr/bin/env python3
"""36 urunu n11 kategori agacina esler ve inceleme dosyasi uretir.

KATEGORI AGACI NEREDEN GELDI
n11 API'si anahtarsiz hicbir sey vermiyor ("Authentication failed"), panel de
uyelik onayina kadar kilitli. Bu yuzden agac www.n11.com'un KENDI kategori
menusunden okundu (23.10.2026, Chrome). Asagidaki yollar birebir siteden
alinmadir, uydurulmamistir.

🔴 KESIN DEGIL: Buradaki eslemeler n11'in SATICI panelindeki kategori
listesiyle birebir ayni olmayabilir; public site agaci ile satici agaci
genelde ortusur ama panel acildiginda TEKRAR DOGRULANMALI. Ayrica her
kategorinin zorunlu ozellikleri (Marka, Hacim, Cilt Tipi ...) yalniz panelden
veya API'den okunabiliyor -- bu dosyada ozellik YOK.

EMIN OLMADIKLARIM bos birakilir ve raporda ayri listelenir; tahminle
doldurulmaz.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CIKTI = Path("/opt/lcarlie/n11-hazirlik")

# www.n11.com kategori menusunden okunan yapraklar (23.10.2026)
AGAC = {
    "yuz-nemlendirici":   "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Yüz Kremi",
    "cilt-temizleyici":   "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Yüz Temizleyici",
    "tonik":              "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Tonik",
    "goz-kremi":          "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Göz Kremi",
    "dudak-bakimi":       "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Dudak Bakımı",
    "cilt-bakim-yagi":    "Kozmetik & Kişisel Bakım > Cilt Bakımı > Yüz Bakımı > Cilt Bakım Yağı",
    "vucut-nemlendirici": "Kozmetik & Kişisel Bakım > Cilt Bakımı > Vücut Bakımı > Vücut Nemlendiriciler",
    "vucut-sikilastirici": "Kozmetik & Kişisel Bakım > Cilt Bakımı > Vücut Bakımı > Vücut Sıkılaştırıcı & Şekillendirici",
    "ayak-bakimi":        "Kozmetik & Kişisel Bakım > Cilt Bakımı > El, Ayak, Tırnak > Ayak Bakımı",
    "gunes-kremleri":     "Kozmetik & Kişisel Bakım > Cilt Bakımı > Güneş & Bronzluk > Güneş Kremleri",
    "bebek-losyon":       "Bebek Bakım & Sağlık > Bebek Bakım Ürünleri > Bebek Losyonu",
    "bebek-pisik":        "Bebek Bakım & Sağlık > Bebek Bakım Ürünleri > Pişik Kremi",
    "bebek-gunes":        "Bebek Bakım & Sağlık > Bebek Bakım Ürünleri > Bebek Güneş Kremi",
    "bebek-yagi":         "Bebek Bakım & Sağlık > Bebek Bakım Ürünleri > Bebek Yağı",
    "bebek-diger":        "Bebek Bakım & Sağlık > Bebek Bakım Ürünleri > Bebek Bakım Ürünleri Diğer",
    "dis-macunu":         "Ağız & Diş Bakımı > Diş Macunu",
    "gargara":            "Ağız & Diş Bakımı > Ağız Temizleme & Gargara",
    "sac-yag":            "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Saç Bakım Yağı",
    "sampuan":            "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Şampuan",
    "sac-losyon":         "Saç Bakım & Şekillendirme > Saç Bakımı & Şampuan > Saç Losyonu",
    "genital":            "Kadın Bakım Ürünleri > Genital Ürünler",
    "erkek-cilt":         "Erkek Bakım Ürünleri > Erkek Cilt Bakımı",
    "vucut-spreyi":       "Parfüm & Deodorant > Vücut Spreyi",
}

# Urun adindaki anahtar kelimeye gore esleme. Sira onemli: ustteki once bakar.
KURALLAR: list[tuple[str, str]] = [
    (r"pişik|pisik|minisooth",        "bebek-pisik"),
    (r"babysol|bebek.*güneş",         "bebek-gunes"),
    (r"babysoft|bebek vücut losyon",  "bebek-losyon"),
    (r"babyshower|bebek.*şampuan",    "sampuan"),
    (r"babydent",                     "dis-macunu"),
    (r"baby ?rescue",                 "bebek-diger"),
    (r"diş macunu|bright smile",      "dis-macunu"),
    (r"ağız bakım|oragarde|gargara",  "gargara"),
    (r"saç bakım yağı|hair nourish",  "sac-yag"),
    (r"easycomb",                     "sac-losyon"),
    (r"göz çevresi|göz kremi|optywave", "goz-kremi"),
    (r"dudak|lipvora",                "dudak-bakimi"),
    (r"tonik|calmaros",               "tonik"),
    (r"temizleme köpüğü|luciderm",    "cilt-temizleyici"),
    (r"güneş kremi|sunacnea|spf",     "gunes-kremleri"),
    (r"göğüs|dekolte|liftelle",       "vucut-sikilastirici"),
    (r"gerilme|elastikiyet|dermastra", "vucut-sikilastirici"),
    (r"ayak|tırnak|dermaguard",       "ayak-bakimi"),
    (r"sertleş|nasır|dermacorn",      "ayak-bakimi"),
    (r"intim|hassas bölge|intimblanc", "genital"),
    (r"erkek|vireon",                 "erkek-cilt"),
    (r"roll-?on.*yağ|calmoris|menthalis", "cilt-bakim-yagi"),
    (r"nemlendirici yüz kremi|hydravie", "yuz-nemlendirici"),
    (r"gece bakım kremi|seralimbo",   "yuz-nemlendirici"),
    # Genel vucut kremleri en sona: yukaridakilere uymayan kremler
    (r"krem|losyon|bakım kremi",      "vucut-nemlendirici"),
]

# 🔴 Kurallarin karar veremedigi, INSAN kararina birakilanlar
# Kural disi, ELLE verilen eslemeler (gerekcesiyle)
ELLE = {
    # Urun adi zaten "Kadinlara Ozel Bitkisel Intim Bakim Kremi" diyor;
    # INTIMBLANC ile ayni yaprak.
    "8684869609127": "genital",
    # Bitkisel VUCUT SPREYI -> n11'de bunun tam karsiligi var.
    "8684869609301": "vucut-spreyi",
    # Isinma etkili masaj kremi; n11 kozmetik agacinda masaj yapragi yok,
    # krem oldugu icin vucut nemlendirici. (Idefix'te de ayni karar verildi.)
    "8684869609400": "vucut-nemlendirici",
    # Gece cene bakim roll-on'u: yuze uygulanan bakim urunu.
    "8684869609196": "yuz-nemlendirici",
}

# 🔴 Gercekten INSAN karari bekleyen
SUPHELI = {
    "8684869609608": "SOFTGUARD tekstil/yatak-doşemelik bakim spreyi — KOZMETIK "
                     "DEGIL. n11'in kozmetik agacinda yapragi yok; Ev & Yasam "
                     "tarafinda uygun yaprak panelden secilmeli.",
}


def esle(ad: str, baslik: str) -> str | None:
    metin = (ad + " " + baslik).casefold()
    for desen, anahtar in KURALLAR:
        if re.search(desen, metin):
            return anahtar
    return None


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    veri = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))

    satirlar, bosta = [], []
    for u in veri:
        b = u["barkod"]
        ad = (u.get("urun_adi_wix") or "").split("|")[0].strip()
        if b in SUPHELI:
            satirlar.append({"barkod": b, "urun": ad, "n11_kategori": "",
                             "durum": "INSAN KARARI", "not": SUPHELI[b]})
            bosta.append((ad, SUPHELI[b]))
            continue
        anahtar = ELLE.get(b) or esle(ad, u.get("idefix_baslik") or "")
        if not anahtar:
            satirlar.append({"barkod": b, "urun": ad, "n11_kategori": "",
                             "durum": "ESLESMEDI", "not": "kural tutmadi"})
            bosta.append((ad, "kural tutmadi"))
            continue
        satirlar.append({"barkod": b, "urun": ad,
                         "n11_kategori": AGAC[anahtar],
                         "durum": "ESLESTI", "not": anahtar})

    with (CIKTI / "n11-kategori.csv").open("w", encoding="utf-8-sig", newline="") as y:
        w = csv.DictWriter(y, fieldnames=list(satirlar[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(satirlar)

    eslesen = [s for s in satirlar if s["durum"] == "ESLESTI"]
    dagilim: dict[str, int] = {}
    for s in eslesen:
        dagilim[s["n11_kategori"]] = dagilim.get(s["n11_kategori"], 0) + 1

    md = ["# n11 kategori eşlemesi", "",
          f"**{len(eslesen)}/{len(satirlar)} ürün eşleşti**, "
          f"{len(satirlar)-len(eslesen)} ürün insan kararı bekliyor.", "",
          "Ağaç www.n11.com'un kendi kategori menüsünden okundu (23.10.2026). ",
          "🔴 Satıcı panelindeki ağaçla birebir aynı olmayabilir; panel açılınca ",
          "doğrulanmalı. Zorunlu ürün özellikleri bu dosyada YOK — onlar yalnız ",
          "panelden/API'den okunabiliyor.", "",
          "## Kategori dağılımı", "", "| n11 kategorisi | Ürün |", "|---|---|"]
    for k, n in sorted(dagilim.items(), key=lambda t: -t[1]):
        md.append(f"| {k} | {n} |")
    md += ["", "## Ürün ürün", "", "| Barkod | Ürün | n11 kategorisi |", "|---|---|---|"]
    for s in satirlar:
        md.append(f"| {s['barkod']} | {s['urun']} | "
                  f"{s['n11_kategori'] or '**' + s['durum'] + '**'} |")
    if bosta:
        md += ["", "## Karar bekleyenler", ""]
        for ad, neden in bosta:
            md.append(f"- **{ad}** — {neden}")
    (CIKTI / "N11-KATEGORI.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"eslesen: {len(eslesen)}/{len(satirlar)}")
    for k, n in sorted(dagilim.items(), key=lambda t: -t[1]):
        print(f"  {n:>2}  {k}")
    if bosta:
        print("\nkarar bekleyen:")
        for ad, neden in bosta:
            print(f"  {ad:<34} {neden[:60]}")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
