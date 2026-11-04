#!/usr/bin/env python3
"""Trendyol'daki urun ACIKLAMA ve GORSELLERINI bizim kaynagimizla degistirir.

NEDEN
Trendyol'daki 34 urunumuzun metinleri bizim degil: AI ile uretilmis pazarlama
metni. Sadece uslup sorunu da degil -- 25.10.2026'da olculdu, HYDRAVIE'nin
Trendyol aciklamasi "Ceramide destekli" diyor; bizim formulde seramid YOK
(niasinamid, bakuchiol, nar cekirdegi, aynisefa, papatya). Yani yanlis icerik
beyani yayinda.

KAYNAK (uydurma yok)
  /opt/lcarlie/idefix-hazirlik/urunler.csv
    idefix_baslik   : mevzuattan gecmis baslik
    idefix_aciklama : Wix'teki onayli metinden AYIKLANMIS, denetlenmis HTML
  Gorseller: https://n8n.lcarlie.shop/urun-gorsel/<barkod>-0N.jpg

🔴 UC KAPI
 1. Her metin `compliance.review`den gecer. hb-icerik-yaz.py'deki IKI ISTISNA
    aynen uygulanir (uyari cumlesi iddia degildir; zorunlu ibare yalniz
    gunes urunlerinde beklenir). Bulgu varsa urun GONDERILMEZ.
 2. Her gorsel adresi gonderimden ONCE HTTP ile yoklanir. Ulasilamayan
    gorsel gonderilmez -- Trendyol kirik adresi sessizce yutabilir.
 3. SUPHELI barkodlar listesindeki urunlere DOKUNULMAZ (asagida gerekceli).

BASLIK neden varsayilan olarak gonderilmiyor
Baslik degisikligi urunu yeniden onaya dusurur ve o sure satisi etkileyebilir.
Sahip isterse `--baslik-da` ile acilir.

Kullanim:
  trendyol-icerik-guncelle.py                      (kuru kosu, rapor)
  trendyol-icerik-guncelle.py --barkod 8684869609233
  trendyol-icerik-guncelle.py --gonder
  trendyol-icerik-guncelle.py --gonder --baslik-da
  trendyol-icerik-guncelle.py --toplu <batchRequestId>
"""
from __future__ import annotations

import argparse
import base64
import csv
import html as h
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path("/opt/lcarlie/jarvis-phase2")
sys.path.insert(0, str(KOK))

from jarvis import compliance  # noqa: E402

ENV = Path("/etc/lcarlie/trendyol.env")
CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
ONAYLI = Path("/tmp/ty-onayli.json")
GUNLUK = Path("/opt/lcarlie/trendyol-hazirlik/gonderim-gunlugu.jsonl")
GORSEL_KOK = "https://n8n.lcarlie.shop/urun-gorsel"
AZAMI_GORSEL = 5

# idefix/hb betikleriyle ayni kume: zorunlu uyari ibaresi beklenen urunler
GUNES = {"8684869609097", "8684869609530"}

# 🔴 DOKUNULMAYACAKLAR -- kimlik uyusmazligi var, once sahip karar vermeli.
SUPHELI = {
    "8684869609301": "Bu barkod bizde BUGUARD; Trendyol'daki ilan "
                     "'SoftGuard Akar Spreyi' basligiyla duruyor. Hangi urun "
                     "oldugu netlesmeden metin yazmak yanlisi buyutur.",
}


def ortam() -> dict[str, str]:
    return dict(s.split("=", 1) for s in ENV.read_text(encoding="utf-8").splitlines()
                if "=" in s and not s.startswith("#"))


def basliklar(e: dict[str, str]) -> dict[str, str]:
    cift = "%s:%s" % (e["TRENDYOL_API_KEY"], e["TRENDYOL_API_SECRET"])
    return {"Authorization": "Basic " + base64.b64encode(cift.encode()).decode(),
            "User-Agent": "%s - SelfIntegration" % e["TRENDYOL_SELLER_ID"],
            "Content-Type": "application/json"}


def kucult(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def duz(html_metin: str) -> str:
    return re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", html_metin))).strip()


def denetle(barkod: str, metin: str) -> list[str]:
    """hb-icerik-yaz.py ile BIREBIR ayni kapi. Iki istisna:
    - Uyari/olumsuz cumle bir IDDIA degildir (…maz, …meyin, …kaçının).
    - 'zorunlu ibare' kurali yalniz gunes urunlerinde anlamlidir."""
    bulgu = []
    for f in compliance.review(metin).findings:
        cumle = f.sentence or ""
        if re.search(r"(ma(z|yın|malı)|mez|meyin|durunuz|önerilir|kaçın)", kucult(cumle)):
            continue
        if "zorunlu ibare" in f.rule and barkod not in GUNES:
            continue
        bulgu.append("%s -> '%s'" % (f.rule, f.matched))
    return bulgu


def gorsel_yokla(url: str) -> bool:
    istek = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(istek, timeout=20) as y:
            return y.status == 200 and "image" in (y.headers.get("Content-Type") or "")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return False


def gorseller(barkod: str) -> list[str]:
    bulunan = []
    for i in range(1, AZAMI_GORSEL + 1):
        u = "%s/%s-%02d.jpg" % (GORSEL_KOK, barkod, i)
        if gorsel_yokla(u):
            bulunan.append(u)
    return bulunan


def ty_icerik_kimlikleri() -> dict[str, dict]:
    ty = json.loads(ONAYLI.read_text(encoding="utf-8"))
    esleme: dict[str, dict] = {}
    for u in ty:
        for v in u.get("variants") or []:
            if v.get("barcode"):
                esleme[str(v["barcode"])] = u
    return esleme


def istek_at(url: str, govde: dict, bas: dict[str, str]) -> tuple[int, dict]:
    r = urllib.request.Request(url, data=json.dumps(govde, ensure_ascii=False).encode("utf-8"),
                               headers=bas, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=120) as y:
            return y.status, json.loads(y.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as hata:
        g = hata.read().decode("utf-8", "replace")
        try:
            return hata.code, json.loads(g)
        except json.JSONDecodeError:
            return hata.code, {"ham": g[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--barkod")
    ap.add_argument("--gonder", action="store_true")
    ap.add_argument("--baslik-da", action="store_true")
    ap.add_argument("--toplu")
    a = ap.parse_args()

    e = ortam()
    sid = e["TRENDYOL_SELLER_ID"]
    bas = basliklar(e)
    K = "https://apigw.trendyol.com/integration/product/sellers/%s/products" % sid

    if a.toplu:
        u = "%s/batch-requests/%s" % (K, a.toplu)
        r = urllib.request.Request(u, headers=bas)
        try:
            with urllib.request.urlopen(r, timeout=60) as y:
                d = json.loads(y.read().decode())
        except urllib.error.HTTPError as hata:
            print("HTTP %d: %s" % (hata.code, hata.read().decode("utf-8", "replace")[:300]))
            return 1
        print("durum: %s  toplam: %s" % (d.get("status"), d.get("itemCount")))
        for i in d.get("items") or []:
            print("  %-12s %s" % (i.get("status"),
                                  (i.get("failureReasons") or [""])[0]))
        return 0

    bizim = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}
    ty = ty_icerik_kimlikleri()

    hedefler = [a.barkod] if a.barkod else list(bizim)
    kalemler, rapor = [], []
    for b in hedefler:
        s = bizim.get(b)
        if not s:
            rapor.append((b, "-", "BIZDE YOK", ""))
            continue
        ad = s["urun_adi_wix"].split("|")[0].strip()[:26]
        if b in SUPHELI:
            rapor.append((b, ad, "SUPHELI, ATLANDI", SUPHELI[b][:60]))
            continue
        urun = ty.get(b)
        if not urun:
            rapor.append((b, ad, "TRENDYOLDA YOK", ""))
            continue
        baslik, aciklama = s["idefix_baslik"], s["idefix_aciklama"]
        bulgu = denetle(b, baslik + ". " + duz(aciklama))
        if bulgu:
            rapor.append((b, ad, "MEVZUAT BULGUSU", "; ".join(bulgu)[:60]))
            continue
        gorsel = gorseller(b)
        if not gorsel:
            rapor.append((b, ad, "GORSEL ULASILMADI", GORSEL_KOK))
            continue
        kalem = {"contentId": urun["contentId"],
                 "description": aciklama,
                 "images": [{"url": g} for g in gorsel]}
        if a.baslik_da:
            kalem["title"] = baslik
        kalemler.append(kalem)
        rapor.append((b, ad, "HAZIR", "%d gorsel · %d karakter"
                      % (len(gorsel), len(aciklama))))

    print("%-15s %-27s %-18s %s" % ("barkod", "urun", "durum", "not"))
    for r in rapor:
        print("%-15s %-27s %-18s %s" % r)
    print("\ngonderilecek: %d urun · baslik %s"
          % (len(kalemler), "DAHIL" if a.baslik_da else "HARIC"))

    if not a.gonder:
        print("(--gonder verilmedi, hicbir sey degistirilmedi)")
        return 0

    kod, y = istek_at("%s/content-bulk-update" % K, {"items": kalemler}, bas)
    print("\nHTTP %d" % kod)
    print(json.dumps(y, ensure_ascii=False)[:600])
    GUNLUK.parent.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open("a", encoding="utf-8") as g:
        g.write(json.dumps({"http": kod, "yanit": y,
                            "contentIdler": [k["contentId"] for k in kalemler]},
                           ensure_ascii=False) + "\n")
    toplu = y.get("batchRequestId")
    if toplu:
        print("\n🔴 Yanit alinmasi 'guncellendi' demek DEGIL. Sonucu sor:")
        print("   trendyol-icerik-guncelle.py --toplu %s" % toplu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
