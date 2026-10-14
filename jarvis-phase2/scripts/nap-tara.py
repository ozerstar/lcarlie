#!/usr/bin/env python3
"""Sitede YANLIS kimlik bilgisi arar (adres · e-posta · telefon).

Sahip beyani 29.09.2026 (core.ayar nap_*):
  adres   : Mehmet Akif Ersoy Mah. 325. Sk. No: 3/117, Yenimahalle / Ankara
  e-posta : info@lcarlie.com.tr

🔴 SAYFA GOVDESI YETMEZ. Elle yapilmis sayfalarin icerigi HtmlComponent
iframe'inin icinde duruyor; sunucudan `filesusr.com` adresine bakmadan
"sayfada yok" denemez. Bu tuzak daha once olculdu.
"""
import re
import urllib.parse
import urllib.request

BASLIK = {"User-Agent": "Mozilla/5.0 (compatible; LcarlieNapBot/1.0)"}

YANLIS = {
    "eposta_tr_siz": re.compile(r"info@lcarlie\.com(?!\.tr)", re.I),
    "cankaya": re.compile(r"[ÇC]ankaya", re.I),
    "universiteler": re.compile(r"[ÜU]niversiteler\s*Mah", re.I),
    "cadde_1636": re.compile(r"1636", re.I),
    "kapi_no_20": re.compile(r"325[^\n]{0,20}\bNo[:\s]*20\b", re.I),
}


def cek(url: str) -> str:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=BASLIK), timeout=25) as c:
            return c.read().decode("utf-8", "ignore")
    except Exception as hata:  # noqa: BLE001
        return f"__HATA__ {hata}"


def main() -> int:
    hm = cek("https://www.lcarlie.shop/pages-sitemap.xml")
    sayfalar = re.findall(r"<loc>([^<]+)</loc>", hm)
    print(f"taranacak sayfa: {len(sayfalar)}")
    bulgu = 0
    for s in sayfalar:
        h = cek(urllib.parse.quote(s, safe=":/"))
        if h.startswith("__HATA__"):
            print(f"  ! {s} -> {h[:60]}")
            continue
        parcalar = [("sayfa", h)]
        for src in set(re.findall(r'src="(https://[^"]*filesusr\.com/html/[^"]+)"', h)):
            parcalar.append(("iframe", cek(src)))
        for nere, metin in parcalar:
            if metin.startswith("__HATA__"):
                continue
            for ad, kalip in YANLIS.items():
                if kalip.search(metin):
                    ornek = kalip.search(metin)
                    bas = max(0, ornek.start() - 60)
                    print(f"  🔴 {s}  [{nere}]  {ad}")
                    print(f"      …{metin[bas:ornek.end() + 60].strip()[:150]}…")
                    bulgu += 1
    print(f"\ntoplam yanlış bulgu: {bulgu}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
