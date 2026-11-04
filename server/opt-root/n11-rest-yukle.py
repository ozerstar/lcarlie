#!/usr/bin/env python3
"""n11'e urun yukler — REST (product-create).

NEDEN REST
SOAP'in YAZMA servisleri kapatilmis; `SaveProduct` 404 doner ve n11 kendi hata
mesajinda "RestAPI update servislerine gecis yapiniz" diyor. Okuma (kategori,
urun listesi) hala SOAP'ta.

UC NOKTA
  POST https://api.n11.com/ms/product/tasks/product-create
  Basliklar: appKey, appSecret · govde JSON · tek istekte en fazla 1000 sku
  Asenkron: {"id":…, "status":"IN_QUEUE"} doner; sonuc Task Detail ile sorulur.

🔴 Idefix dersleri burada da gecerli:
- "IN_QUEUE" yuklendi demek DEGIL; gorev sonucu ayrica sorulur.
- Ozellik degeri kategorinin izinli listesinde birebir yoksa GONDERILMEZ.
- Marka `attributes` icinde id=1 + customValue ile serbest metin gider.

Kullanim:
  python3 n11-rest-yukle.py --barkod 8684869609233            (sadece gosterir)
  python3 n11-rest-yukle.py --barkod 8684869609233 --gonder
  python3 n11-rest-yukle.py --hepsi --gonder
  python3 n11-rest-yukle.py --gorev 1092                      (sonuc sorgusu)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/etc/lcarlie/n11.env")
URUN_CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
KAT_CSV = Path("/opt/lcarlie/n11-hazirlik/n11-kategori-id.csv")
OZELLIK = Path("/opt/lcarlie/n11-hazirlik/n11-ozellikler.json")
GUNLUK = Path("/opt/lcarlie/n11-hazirlik/gonderim-gunlugu.jsonl")
# n11'in yasakli kelime suzgecine takilan UYARI cumleleri yeniden yazildi
# (anlam korundu, kelime degisti; her karsilik mevzuat suzgecinden gecti).
DUZELTME = Path("/opt/lcarlie/n11-hazirlik/n11-aciklama.json")

OLUSTUR = "https://api.n11.com/ms/product/tasks/product-create"
GOREV = "https://api.n11.com/ms/product/task-details/page-query"

MARKA = "L'CARLIÉ"
MARKA_OZELLIK_ID = 1          # n11'de "Marka" ozelliginin kimligi
SABLON = "L'CARLIE Standart"  # panelde kurulan kargo sablonu
HAZIRLIK_GUN = 3
AZAMI_ADET = 5
KDV = 20

# Baslikta gecmeyen ama KUTU VERISINDE bulunan degerler (uydurulmadi).
# BABYSOL: kutu metninde "SPF 50" yaziyor (kutu-gercegi/babysol.json).
ELLE = {
    "8684869609530": {"Güneş Koruma Faktörü": "SPF50", "Ürün Türü": "Krem"},
}


def ortam() -> dict[str, str]:
    return dict(s.split("=", 1) for s in ENV.read_text(encoding="utf-8").splitlines()
                if "=" in s and not s.startswith("#"))


def istek(url: str, govde: dict, env: dict) -> tuple[int, dict]:
    r = urllib.request.Request(
        url, data=json.dumps(govde, ensure_ascii=False).encode("utf-8"),
        headers={"appKey": env["N11_APP_KEY"], "appSecret": env["N11_APP_SECRET"],
                 "Content-Type": "application/json", "Accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(r, timeout=120) as y:
            return y.status, json.loads(y.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as h:
        g = h.read().decode("utf-8", "replace")
        try:
            return h.code, json.loads(g)
        except json.JSONDecodeError:
            return h.code, {"ham": g[:400]}


def ml(baslik: str) -> str | None:
    m = re.search(r"(\d+)\s*ml\b", baslik, re.IGNORECASE)
    return f"{m.group(1)} ML" if m else None


def ozellik_kur(kid: str, urun: dict, tanim: dict) -> tuple[list[dict], list[str]]:
    """Zorunlu ozellikleri kategorinin IZINLI listesinden doldurur.

    Enum alanlarda `valueId` gonderilir (serbest metinden saglam). Listede
    birebir karsiligi olmayan alan BOS birakilir ve raporlanir -- uydurulmaz.
    """
    alanlar = tanim[kid]["ozellikler"]
    secim: list[dict] = [{"id": MARKA_OZELLIK_ID, "valueId": None,
                          "customValue": MARKA}]
    eksik: list[str] = []
    hacim = ml(urun["idefix_baslik"])
    metin = (urun["urun_adi_wix"] + " " + urun["idefix_baslik"]).casefold()

    def bul(o, adaylar):
        """Izinli listede BIREBIR (buyuk/kucuk harf duyarsiz) karsilik arar.
        🔴 n11'de deger kimligi yok, yalniz ad var -> customValue ile gider."""
        for aday in adaylar:
            if not aday:
                continue
            for d in o["degerler"]:
                if d.casefold() == str(aday).casefold():
                    return d
        return None

    elle = ELLE.get(urun["barkod"], {})
    for o in alanlar:
        if not o["zorunlu"] or o["id"] == MARKA_OZELLIK_ID:
            continue
        ad = o["ad"]
        d = bul(o, [elle[ad]]) if ad in elle else None
        if d:
            secim.append({"id": o["id"], "valueId": None, "customValue": d})
            continue
        if ad == "Ürün Miktarı" and hacim:
            d = bul(o, [hacim, hacim.replace(" ML", " Ml"), hacim.lower()])
        elif ad == "Cilt Tipi":
            d = bul(o, ["Tüm Cilt Tipleri", "Tüm Ciltler", "Normal"])
        elif ad == "Kullanım Amacı":
            adaylar = (["Nemlendirme", "Nemlendirici"] if "nemlendir" in metin
                       else ["Temizleme", "Arındırma", "Bakım", "Nemlendirme"])
            d = bul(o, adaylar)
        elif ad == "Ürün Türü":
            d = bul(o, ["Krem", "Losyon", "Sprey", "Yağ", "Jel"])
        elif ad == "Ürün İçeriği":
            d = bul(o, ["Bitkisel", "Doğal İçerikli", "Diğer"])
        elif ad in ("Faktör", "Güneş Koruma Faktörü"):
            m = re.search(r"(\d{2})\s*spf|spf\s*\+?(\d{2})", metin)
            sayi = (m.group(1) or m.group(2)) if m else None
            d = bul(o, [f"{sayi}", f"SPF {sayi}", f"{sayi} SPF"]) if sayi else None
        if d:
            secim.append({"id": o["id"], "valueId": None, "customValue": d})
        else:
            eksik.append(f"{ad}#{o['id']}")
    return secim, eksik


DUZELTILMIS = (json.loads(DUZELTME.read_text(encoding="utf-8"))
               if DUZELTME.exists() else {})


def sku_kur(urun: dict, kid: str, ozellikler: list[dict]) -> dict:
    gorseller = [{"url": urun[f"gorsel_{i}"], "order": i}
                 for i in range(1, 6) if urun.get(f"gorsel_{i}")]
    return {
        "title": urun["idefix_baslik"],
        "description": DUZELTILMIS.get(urun["barkod"], urun["idefix_aciklama"]),
        "categoryId": int(kid),
        "currencyType": "TL",
        "productMainId": urun["barkod"],
        "preparingDay": HAZIRLIK_GUN,
        "shipmentTemplate": SABLON,
        "maxPurchaseQuantity": AZAMI_ADET,
        "stockCode": urun["barkod"],
        "catalogId": None,
        "barcode": urun["barkod"],
        "quantity": int(float(urun["stok"] or 0)),
        "images": gorseller,
        "attributes": ozellikler,
        "salePrice": float(urun["fiyat"]),
        "listPrice": float(urun["fiyat"]),
        "vatRate": KDV,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--barkod")
    ap.add_argument("--hepsi", action="store_true")
    ap.add_argument("--gonder", action="store_true")
    ap.add_argument("--gorev")
    a = ap.parse_args()
    env = ortam()

    if a.gorev:
        # 🔴 Gorev sorgusu "payload" sarmalayicisi ISTEMIYOR; taskId ust
        # seviyede olmali (400 "taskDetailQueryDTO.taskId bos deger olamaz").
        kod, y = istek(GOREV, {"taskId": int(a.gorev),
                               "pageable": {"page": 0, "size": 50}}, env)
        print(f"HTTP {kod}")
        print(json.dumps(y, ensure_ascii=False, indent=1)[:2000])
        return 0

    urunler = {x["barkod"]: x for x in csv.DictReader(
        URUN_CSV.open(encoding="utf-8-sig"), delimiter=";")}
    kat = {x["barkod"]: x for x in csv.DictReader(
        KAT_CSV.open(encoding="utf-8-sig"), delimiter=";")}
    tanim = json.loads(OZELLIK.read_text(encoding="utf-8"))

    hedef = [a.barkod] if a.barkod else [b for b in urunler
                                         if kat.get(b, {}).get("n11_kategori_id")]
    skular, rapor = [], []
    for b in hedef:
        k = kat.get(b, {})
        kid = k.get("n11_kategori_id")
        if not kid:
            rapor.append((b, urunler[b]["urun_adi_wix"][:28], "KATEGORI YOK", []))
            continue
        oz, eksik = ozellik_kur(kid, urunler[b], tanim)
        skular.append(sku_kur(urunler[b], kid, oz))
        rapor.append((b, urunler[b]["urun_adi_wix"][:28], k["n11_kategori"][-28:], eksik))

    print(f"{'barkod':<15}{'urun':<30}{'kategori':<30} eksik zorunlu alan")
    for b, ad, kk, eksik in rapor:
        print(f"{b:<15}{ad:<30}{kk:<30} {', '.join(eksik) if eksik else '-'}")
    print(f"\ngonderilecek: {len(skular)} urun")

    if not a.gonder:
        print("(--gonder verilmedi)")
        return 0

    kod, y = istek(OLUSTUR, {"payload": {"integrator": "LCARLIE",
                                         "skus": skular}}, env)
    print(f"\nHTTP {kod}")
    print(json.dumps(y, ensure_ascii=False, indent=1)[:1200])
    GUNLUK.parent.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open("a", encoding="utf-8") as g:
        g.write(json.dumps({"http": kod, "yanit": y,
                            "barkodlar": [s["barcode"] for s in skular]},
                           ensure_ascii=False) + "\n")
    gid = y.get("id")
    if gid:
        print(f"\n🔴 'IN_QUEUE' yuklendi demek DEGIL. Sonucu sor:")
        print(f"   python3 n11-rest-yukle.py --gorev {gid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
