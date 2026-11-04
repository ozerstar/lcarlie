#!/usr/bin/env python3
"""Idefix urun yukleyici — CSV'den okur, API'ye gonderir, SONUCU DOGRULAR.

KULLANIM
  idefix-urun-yukle.py            kuru calistirma: govdeyi uretir, GONDERMEZ
  idefix-urun-yukle.py --gonder   gercekten gonderir
  idefix-urun-yukle.py --sadece 8684869609394   tek barkod

🔴 NEDEN SONUC AYRI SORULUR
`POST /pim/pool/{vendorId}/create` HER ZAMAN HTTP 200 ve "status": "created"
doner. Bu "olusturuldu" DEMEK DEGIL, "islenmek uzere alindi" demek. 22.10.2026'da
olculdu: 200 donen gonderim `batch-result`'ta "decline / BRAND_NOT_EXIST" cikti ve
havuza hicbir kayit dusmedi. Bu yuzden gonderim tek basina rapor edilmez;
batchRequestId saklanir, sonuc sorulur, rapor SONUCA gore yazilir.

🔴 KATEGORI BASINA AYRI PARTI
Gonderim kategoriye gore gruplanir -- bir kategorideki hata digerlerini
etkilemesin ve reddedilen grup tek basina tekrarlanabilsin diye.

🔴 BASLIK GERI ALINAMAZ
Idefix'te urun bilgisi API ile guncellenemiyor (yalniz stok-fiyat). Basligi bos
olan urun GONDERILMEZ; placeholder baslik canliya girerse duzeltmesi elle olur.
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
from collections import defaultdict
from pathlib import Path

ENV = Path("/etc/lcarlie/idefix.env")
CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
GUNLUK = Path("/opt/lcarlie/idefix-hazirlik/gonderim-gunlugu.jsonl")
TABAN = "https://merchantapi.idefix.com"

# Idefix tarafi sabitleri -- 22.10.2026'da API'den okundu, uydurulmadi.
KARGO_ID = 84          # Hepsijet (satici kargo profili 174093)
GONDERIM_ADRES = 65271  # shipping, isDefault
IADE_ADRES = 65270      # return, isDefault
TESLIM_GUN = 3


def ortam() -> dict[str, str]:
    d = {}
    for satir in ENV.read_text(encoding="utf-8").splitlines():
        if satir and not satir.startswith("#") and "=" in satir:
            k, v = satir.split("=", 1)
            d[k.strip()] = v.strip()
    return d


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
        govde_metni = h.read().decode("utf-8", "replace")
        try:
            return h.code, json.loads(govde_metni)
        except json.JSONDecodeError:
            return h.code, {"ham": govde_metni[:400]}


def urun_govdesi(s: dict, marka_id: int) -> dict:
    gorseller = [{"url": s[f"gorsel_{i}"]} for i in range(1, 6) if s.get(f"gorsel_{i}")]
    return {
        "barcode": s["barkod"],
        "title": s["idefix_baslik"].strip(),
        "productMainId": s["barkod"],
        "brandId": marka_id,
        "categoryId": int(s["kategori_id"]),
        "inventoryQuantity": int(float(s["stok"] or 0)),
        "vendorStockCode": s["barkod"],
        "description": s["idefix_aciklama"].strip() if s.get("idefix_aciklama") else "",
        "price": float(s["fiyat"]),
        "vatRate": int(float(s["kdv"])),
        "deliveryDuration": TESLIM_GUN,
        "deliveryType": "regular",
        "cargoCompanyId": KARGO_ID,
        "shipmentAddressId": GONDERIM_ADRES,
        "returnAddressId": IADE_ADRES,
        "images": gorseller,
        "attributes": [],
    }


def marka_kimligi(jeton: str, ad: str) -> int | None:
    from urllib.parse import quote
    _, y = cagir(f"/pim/brand?title={quote(ad)}", jeton)
    if isinstance(y, list) and y:
        return int(y[0]["id"])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gonder", action="store_true")
    ap.add_argument("--sadece", default="")
    ap.add_argument("--marka", default="L'CARLIE")
    args = ap.parse_args()

    env = ortam()
    jeton = base64.b64encode(
        f"{env['IDEFIX_API_KEY']}:{env['IDEFIX_API_SECRET']}".encode()).decode()
    satici = env["IDEFIX_SELLER_ID"]

    marka_id = marka_kimligi(jeton, args.marka)
    if marka_id is None:
        print(f"DURDU: '{args.marka}' markasi Idefix listesinde YOK (brandId alinamadi).")
        print("       Marka ekleme talebi onaylanmadan hicbir urun yuklenemez.")
        print("       Olcum: sudo /opt/lcarlie/idefix-marka-kontrol.sh")
        return 2
    print(f"marka: {args.marka} -> brandId {marka_id}")

    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    if args.sadece:
        satirlar = [s for s in satirlar if s["barkod"] == args.sadece]

    basliksiz = [s["urun_adi_wix"] for s in satirlar if not s.get("idefix_baslik", "").strip()]
    if basliksiz:
        print(f"DURDU: {len(basliksiz)} urunun idefix_baslik alani bos.")
        print("       Idefix'te baslik API ile DUZELTILEMEZ; bos basliklar gonderilmez.")
        for a in basliksiz[:5]:
            print("       -", a)
        return 2

    gruplar: dict[str, list[dict]] = defaultdict(list)
    for s in satirlar:
        gruplar[s["kategori_id"]].append(s)
    print(f"urun: {len(satirlar)} · kategori partisi: {len(gruplar)}")

    if not args.gonder:
        ornek = urun_govdesi(satirlar[0], marka_id)
        print("\nKURU CALISTIRMA -- gonderilmedi. Ornek govde:")
        print(json.dumps(ornek, ensure_ascii=False, indent=2)[:900])
        print("\nGondermek icin: --gonder")
        return 0

    sonuclar = []
    for kid, grup in gruplar.items():
        govde = {"products": [urun_govdesi(s, marka_id) for s in grup]}
        kod, yanit = cagir(f"/pim/pool/{satici}/create", jeton, govde)
        parti = (yanit or {}).get("batchRequestId")
        print(f"\nkategori {kid} · {len(grup)} urun -> HTTP {kod} · parti {parti or 'YOK'}")
        if not parti:
            sonuclar.append({"kategori": kid, "durum": "PARTI_YOK", "yanit": yanit})
            continue

        # 200 yeterli DEGIL: gercek sonuc batch-result'ta.
        # Sonuc kararli hale gelince DUR: ya bir red var, ya hepsine referans
        # verilmis. 22.10 olcumu: red 5 saniyede belli oluyor; bekleme merdiveni
        # kisa tutulmazsa 24 parti yarim saat suruyor.
        nihai = None
        for bekle in (5, 10, 20):
            time.sleep(bekle)
            _, b = cagir(f"/pim/pool/{satici}/batch-result/{parti}", jeton)
            urunler = (b or {}).get("products") or []
            if not urunler:
                continue
            nihai = urunler
            if any(u.get("status") == "decline" for u in urunler):
                break
            if all(u.get("reference") for u in urunler):
                break
        for u in nihai or []:
            gerekce = (u.get("failureReasons") or {}).get("message") if isinstance(
                u.get("failureReasons"), dict) else u.get("failureReasons")
            print(f"   {u.get('barcode')} · {u.get('status')} · "
                  f"{gerekce or '-'} · referans {u.get('reference')}")
            sonuclar.append({"kategori": kid, "parti": parti, "barkod": u.get("barcode"),
                             "durum": u.get("status"), "gerekce": gerekce,
                             "referans": u.get("reference")})

    GUNLUK.parent.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open("a", encoding="utf-8") as f:
        for r in sonuclar:
            r["zaman"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    basarili = sum(1 for r in sonuclar if r.get("referans"))
    red = sum(1 for r in sonuclar if r.get("durum") == "decline")
    print(f"\nSONUC: referans alan {basarili} · reddedilen {red} · "
          f"toplam kayit {len(sonuclar)} · gunluk {GUNLUK}")
    return 0 if red == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
