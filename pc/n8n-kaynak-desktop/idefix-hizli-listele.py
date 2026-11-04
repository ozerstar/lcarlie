#!/usr/bin/env python3
"""Idefix HIZLI URUN ESLESTIRME — katalogta zaten var olan barkoda satici olarak baglanir.

NE KONTROL EDERIZ, NE ETMEYIZ
Bu uc yalniz sunlari aliyor: barcode, title, price, comparePrice,
inventoryQuantity, vendorStockCode. **Gorsel, aciklama ve marka katalog
kaydindan gelir** -- yani MC'nin kaydindan. "Sonra degistiririz" bu yolda
bizim elimizde degil; baslik alani gonderiliyor ama sayfada bizim basligimizin
mi yoksa katalogunkinin mi gorundugu ANCAK DENEYEREK anlasilir. Bu betik
tam da onu olcmek icin tek urunle calistirilir.

Kullanim:
  idefix-hizli-listele.py 8684869609233            # kuru calistirma
  idefix-hizli-listele.py 8684869609233 --gonder   # gercekten listeler
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/etc/lcarlie/idefix.env")
CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
GUNLUK = Path("/opt/lcarlie/idefix-hazirlik/hizli-listeleme-gunlugu.jsonl")
TABAN = "https://merchantapi.idefix.com"


def ortam() -> dict[str, str]:
    return dict(
        satir.split("=", 1) for satir in ENV.read_text(encoding="utf-8").splitlines()
        if satir and not satir.startswith("#") and "=" in satir)


def cagir(yol: str, jeton: str, govde: dict | None = None):
    istek = urllib.request.Request(
        TABAN + yol,
        data=json.dumps(govde).encode("utf-8") if govde is not None else None,
        headers={"X-API-KEY": jeton, "Accept": "application/json",
                 "Content-Type": "application/json"},
        method="POST" if govde is not None else "GET")
    try:
        with urllib.request.urlopen(istek, timeout=90) as y:
            return y.status, json.loads(y.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as h:
        g = h.read().decode("utf-8", "replace")
        try:
            return h.code, json.loads(g)
        except json.JSONDecodeError:
            return h.code, {"ham": g[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("barkod", nargs="?", default="",
                    help="tek barkod; --hepsi ile birlikte verilmez")
    ap.add_argument("--hepsi", action="store_true",
                    help="pool/create'te BRAND_FAILED_TO_MATCH ile reddedilen "
                         "tum barkodlari gonderir (zaten listelenmis olanlar haric)")
    ap.add_argument("--gonder", action="store_true")
    ap.add_argument("--fiyat", type=float, default=0.0,
                    help="verilmezse CSV'deki Wix fiyati kullanilir")
    args = ap.parse_args()

    env = ortam()
    jeton = base64.b64encode(
        (env["IDEFIX_API_KEY"] + ":" + env["IDEFIX_API_SECRET"]).encode()).decode()
    satici = env["IDEFIX_SELLER_ID"]

    satirlar = {s["barkod"]: s for s in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    if args.hepsi:
        # Katalogta zaten kayitli oldugu icin pool/create'te reddedilenler
        gunluk = Path("/opt/lcarlie/idefix-hazirlik/gonderim-gunlugu.jsonl")
        hedef = []
        for satir in gunluk.read_text(encoding="utf-8").splitlines():
            r = json.loads(satir)
            if r.get("durum") == "decline" and "CATALOG_BRAND" in (r.get("gerekce") or ""):
                if r["barkod"] not in hedef:
                    hedef.append(r["barkod"])
        # Daha once hizli listelenmis olanlari tekrar gonderme
        hlog = GUNLUK
        if hlog.exists():
            yapilmis = {json.loads(x)["barkod"] for x in
                        hlog.read_text(encoding="utf-8").splitlines() if x.strip()}
            hedef = [b for b in hedef if b not in yapilmis]
    else:
        hedef = [args.barkod] if args.barkod else []
    if not hedef:
        print("gonderilecek barkod yok")
        return 1

    oge = []
    for b in hedef:
        s = satirlar.get(b)
        if not s:
            print("CSV'de yok:", b)
            return 1
        fiyat = args.fiyat or float(s["fiyat"])
        oge.append({"title": s["idefix_baslik"], "barcode": b, "price": fiyat,
                    "comparePrice": fiyat,
                    "inventoryQuantity": int(float(s["stok"] or 0)),
                    "vendorStockCode": b})
        print(f"  {b} · {fiyat:>7.0f} TL · {s['idefix_baslik'][:52]}")
    govde = {"items": oge}
    print(f"toplam {len(oge)} urun")

    if not args.gonder:
        print()
        print(json.dumps(govde, ensure_ascii=False, indent=2))
        print("\nGondermek icin: --gonder")
        return 0

    kod, yanit = cagir(f"/pim/catalog/{satici}/fast-listing", jeton, govde)
    parti = (yanit or {}).get("batchRequestId")
    print(f"\nHTTP {kod} · parti {parti or 'YOK'} · durum {(yanit or {}).get('status')}")

    # 200 yeterli degil (pool/create'te olculdu): sonuc ayrica sorulur.
    nihai = None
    if parti:
        for bekle in (5, 10, 20):
            time.sleep(bekle)
            _, b = cagir(f"/pim/catalog/{satici}/batch-result/{parti}", jeton)
            if not b or not (b.get("items") or b.get("products")):
                _, b = cagir(f"/pim/pool/{satici}/batch-result/{parti}", jeton)
            oge = (b or {}).get("items") or (b or {}).get("products") or []
            if oge:
                nihai = oge
                if any(o.get("status") in ("decline", "failed") for o in oge):
                    break
                if all(o.get("productId") for o in oge):
                    break
    for o in nihai or []:
        print(f"   {o.get('barcode')} · {o.get('status')} · productId "
              f"{o.get('productId')} · {o.get('failureReasons') or '-'}")

    GUNLUK.parent.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open("a", encoding="utf-8") as f:
        for b in hedef:
            f.write(json.dumps({"zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                "barkod": b, "parti": parti,
                                "sonuc": nihai}, ensure_ascii=False) + "\n")
    print(f"\ngunluk: {GUNLUK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
