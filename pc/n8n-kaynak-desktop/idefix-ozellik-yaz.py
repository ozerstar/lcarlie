#!/usr/bin/env python3
"""Havuzdaki (not_matched) urunlere URUN OZELLIGI yazar.

NEDEN API
Bu 6 urun katalogta karsiligi olmayan, BIZE ait havuz kayitlari. Ozellikleri
`pool/create` govdesindeki `attributes` ile gider; panelin toplu ozellik yolu
kategori kategori Excel istiyor ve bunlar zaten panelde "Incelenecek"te.

🔴 TEKRAR GONDERIM TESTI
Ayni barkodla create cagrisinin havuzda IKIZ kayit olusturup olusturmadigi
bilinmiyordu. Bu yuzden once TEK urunle denenir ve havuz sayisi karsilastirilir
(`--dene`). Sayi artarsa durulur.

DEGERLER UYDURULMAZ
Her attributeValueId `/pim/category-attribute/{kategori}` listesinden secildi ve
urunun kendi verisiyle dogrulandi (hacim kutudan, tur urun tanimindan, koku
INCI'den). Bilinmeyen alan (orn. SOFTGUARD'in rengi) BOS BIRAKILIR.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/etc/lcarlie/idefix.env")
CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
TABAN = "https://merchantapi.idefix.com"

KARGO_ID = 84
GONDERIM_ADRES = 65271
IADE_ADRES = 65270
TESLIM_GUN = 3
NO_BRAND = 20031592

# barkod -> [(attributeId, attributeValueId, "aciklama")]
OZELLIK = {
    # SOFTGUARD · Oda Kokusu/Koku Giderici (880291124)
    "8684869609608": [
        (189, 1043, "Paket İçi Adet = 1"),
        (222, 1790243, "Boyut/Ebat = 100 ml (kutu)"),
        (174, 1699206, "Türü = Kumaş ve Oda Spreyi (ürün tanımı)"),
        (2395, 1696320, "Koku Tipi = Lavanta (INCI: lavanta suyu)"),
    ],
    # CALMAROS · Tonik (440325840)
    "8684869609080": [
        (189, 1043, "Paket İçi Adet = 1"),
        (13, 181080, "Hacim = 200 ml (kutu)"),
    ],
    # OPTYWAVE · Göz Kremi (440394057)
    "8684869609172": [
        (13, 1698761, "Hacim = 10 ml (kutu)"),
        (30, 1697506, "Ürün Formu = Sıvı (roll-on yağ)"),
        (3256, 1793583, "Yaşlanma Karşıtı = Hayır (iddia yok)"),
        (17, 105630, "SPF = Korumasız (üründe SPF yok)"),
    ],
    # CALMORIS · Bakım Yağı (440320571)
    "8684869609578": [(13, 1698761, "Hacim = 10 ml (kutu)")],
    # MENTHALIS · Bakım Yağı (440320571)
    "8684869609585": [(13, 1698761, "Hacim = 10 ml (kutu)")],
    # DORSIVIA · kategorisi hizmet kategorisi (Süre/Kişi Sayısı/Masaj Tipi) --
    # krem icin uygun ozellik YOK, bilerek bos birakildi.
    "8684869609400": [],
}


def ortam() -> dict[str, str]:
    return dict(s.split("=", 1) for s in ENV.read_text(encoding="utf-8").splitlines()
                if s and not s.startswith("#") and "=" in s)


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
            return h.code, {"ham": g[:300]}


def havuz_sayisi(jeton: str, satici: str) -> int:
    _, d = cagir(f"/pim/pool/{satici}/list?page=1&limit=100", jeton)
    return len((d or {}).get("products") or [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dene", default="", help="tek barkod ile sinama")
    ap.add_argument("--gonder", action="store_true")
    args = ap.parse_args()

    env = ortam()
    jeton = base64.b64encode(
        (env["IDEFIX_API_KEY"] + ":" + env["IDEFIX_API_SECRET"]).encode()).decode()
    satici = env["IDEFIX_SELLER_ID"]
    veri = {x["barkod"]: x for x in csv.DictReader(
        CSV.open(encoding="utf-8-sig"), delimiter=";")}

    hedef = [args.dene] if args.dene else [b for b, o in OZELLIK.items() if o]

    once = havuz_sayisi(jeton, satici)
    print(f"havuz (once): {once}")

    for b in hedef:
        o = OZELLIK.get(b) or []
        s = veri[b]
        if not o:
            print(f"{b} · ozellik tanimli degil, atlandi")
            continue
        gorseller = [{"url": s[f"gorsel_{i}"]} for i in range(1, 6) if s.get(f"gorsel_{i}")]
        govde = {"products": [{
            "barcode": b,
            "title": s["idefix_baslik"],
            "productMainId": b,
            "brandId": NO_BRAND,
            "categoryId": int(s["kategori_id"]),
            "inventoryQuantity": int(float(s["stok"] or 0)),
            "vendorStockCode": b,
            "description": s["idefix_aciklama"],
            "price": float(s["fiyat"]),
            "vatRate": int(float(s["kdv"])),
            "deliveryDuration": TESLIM_GUN,
            "deliveryType": "regular",
            "cargoCompanyId": KARGO_ID,
            "shipmentAddressId": GONDERIM_ADRES,
            "returnAddressId": IADE_ADRES,
            "images": gorseller,
            "attributes": [{"attributeId": a, "attributeValueId": v,
                            "customAttributeValue": None} for a, v, _ in o],
        }]}
        print(f"\n{b} · {s['urun_adi_wix'][:34]} · {len(o)} ozellik")
        for _, _, aciklama in o:
            print(f"    {aciklama}")
        if not args.gonder:
            continue
        kod, yanit = cagir(f"/pim/pool/{satici}/create", jeton, govde)
        parti = (yanit or {}).get("batchRequestId")
        print(f"    HTTP {kod} · parti {parti}")
        if parti:
            for bekle in (5, 10):
                time.sleep(bekle)
                _, r = cagir(f"/pim/pool/{satici}/batch-result/{parti}", jeton)
                u = (r or {}).get("products") or []
                if u:
                    for x in u:
                        gerekce = x.get("failureReasons")
                        print(f"    sonuc: {x.get('status')} · ozellik "
                              f"{len(x.get('attributes') or [])} · {gerekce or '-'}")
                    break
        time.sleep(2)

    if args.gonder:
        time.sleep(5)
        sonra = havuz_sayisi(jeton, satici)
        print(f"\nhavuz (sonra): {sonra} · {'IKIZLENMEDI' if sonra == once else 'DIKKAT: SAYI DEGISTI'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
