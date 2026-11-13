"""Ankara Eczacı Odası nöbet servisi -> o tarihlerde nöbet tutan eczaneler (JSONL).

Her eczane belli aralıkla nöbet tuttuğu için birkaç aylık nöbet listesi
neredeyse tüm AKTİF Ankara eczanelerini, odanın kendi kaydıyla verir
(ad, ilçe, adres, telefon, koordinat). Son nöbet tarihi = eczanenin hâlâ
açık olduğunun kanıtı.
"""
import datetime
import html
import json
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36",
      "X-Requested-With": "XMLHttpRequest"}


def gun(tarih):
    req = urllib.request.Request(f"https://www.aeo.org.tr/getPharmacies/{tarih}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        h = json.loads(r.read().decode("utf-8", "replace")).get("html", "")
    for b in re.split(r'<div class="inline-box"', h)[1:]:
        b = re.sub(r"<svg.*?</svg>", "", b, flags=re.S)
        ilce = (re.search(r'data-district="([^"]*)"', b) or [None, ""])[1]
        konum = re.search(r"query=([\d.]+),([\d.]+)", b)
        tel = (re.search(r'href="tel:(\d+)"', b) or [None, ""])[1]
        satir = [x for x in (html.unescape(s).strip() for s in re.sub(r"<[^>]+>", "\n", b).split("\n"))
                 if x and not x.startswith("data-")]
        ad = next((s for s in satir if "ECZANE" in s.upper()), satir[0] if satir else "")
        adres = satir[satir.index(ad) + 1] if ad in satir and satir.index(ad) + 1 < len(satir) else ""
        yield {"tarih": tarih, "ad": ad, "ilce": html.unescape(ilce), "adres": adres,
               "telefon": tel[-10:], "enlem": float(konum[1]) if konum else None,
               "boylam": float(konum[2]) if konum else None}


def main(cikti, geri=150, ileri=45):
    bugun = datetime.date.today()
    with open(cikti, "w", encoding="utf-8") as f:
        for d in range(-geri, ileri + 1):
            t = (bugun + datetime.timedelta(days=d)).isoformat()
            try:
                kayit = list(gun(t))
            except Exception as e:  # noqa: BLE001
                print(t, "HATA", e, flush=True)
                continue
            for k in kayit:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
            if d % 15 == 0:
                print(t, len(kayit), "nöbetçi", flush=True)
            time.sleep(0.6)


if __name__ == "__main__":
    main(sys.argv[1])
