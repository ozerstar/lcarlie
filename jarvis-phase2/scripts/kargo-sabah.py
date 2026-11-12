#!/usr/bin/env python3
"""Her sabah o gün kargoya verilecek siparişleri sahibe WhatsApp'tan yollar.

Sahip 12.11.2026: *"her sabah bana o gün kargoya verilecek malzemelerin
listesini whatsapp'tan göndereceksin. Kargo kodu, kargo adı, müşteri adı ve
ürünler."*

Kaynak her kanalın kendi API'si (veritabanındaki `ham` kırpılmış, kargo kodu
yok). "Kargoya verilecek" = paket oluşmuş ama henüz kargoya çıkmamış:
  · Trendyol  shipmentPackageStatus Created / Picking / Invoiced
  · İdefix    gönderilmemiş durumlar (kod = cargoKey, kargoya verilen anahtar)
  · Wix       ödenmiş + NOT_FULFILLED (kod Basit Kargo'dan aranır)
  · n11       kapanmamış durumlar

🔴 Okunamayan kanal mesajda AYRICA yazılır. "Sipariş yok" ile "soramadım"
   karışırsa kaçan paket sessizce kaybolur ([[durum ayrımı kapısı]]).

Kullanım: kargo-sabah.py [--kuru]   (--kuru: göndermez, ekrana basar)
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import pazaryeri, haberci  # noqa: E402

SABLON = "lcarlie_kargo_listesi_v1"
TR = timezone(timedelta(hours=3))
# Şablon parametresi tek satır olmalı; gövde 1024 karakteri aşamaz.
PARCA_TAVAN = 850

GITMIS = ("shipped", "deliver", "cancel", "return", "refund", "in_cargo",
          "completed", "teslim", "iptal", "iade", "kargoda")


def _gitmis_mi(durum: str) -> bool:
    d = (durum or "").lower()
    return any(k in d for k in GITMIS)


def _urunler(kalemler) -> str:
    # Yalnız ürün kodu (ilk kelime): başlıktaki "SPF", "akne" gibi kelimeler
    # mevzuat kapısına takılır ve sabah listesi hiç gitmez.
    parca = []
    for k in kalemler:
        kod = (str(k.get("ad") or "").split() or ["-"])[0].upper()
        parca.append("%s x%s" % (kod, k.get("adet") or 1))
    return ", ".join(parca) or "-"


def trendyol() -> list[dict]:
    e = pazaryeri.env_oku("/etc/lcarlie/trendyol.env")
    sid = e["TRENDYOL_SELLER_ID"]
    yetki = base64.b64encode(("%s:%s" % (e["TRENDYOL_API_KEY"],
                                         e["TRENDYOL_API_SECRET"])).encode()).decode()
    cikti = []
    for durum in ("Created", "Picking", "Invoiced"):
        url = ("https://apigw.trendyol.com/integration/order/sellers/%s/orders"
               "?status=%s&size=200" % (sid, durum))
        veri = json.loads(pazaryeri._istek(url, {
            "Authorization": "Basic " + yetki,
            "User-Agent": "%s - SelfIntegration" % sid}))
        for p in veri.get("content") or []:
            cikti.append({
                "kanal": "Trendyol", "no": str(p.get("orderNumber")),
                "kargo": (p.get("cargoProviderName") or "?").replace(" Marketplace", ""),
                "kod": str(p.get("cargoTrackingNumber") or "kod yok"),
                "musteri": ("%s %s" % (p.get("customerFirstName") or "",
                                       p.get("customerLastName") or "")).strip(),
                "urunler": _urunler([{"ad": s.get("productName"), "adet": s.get("quantity")}
                                     for s in p.get("lines") or []])})
    return cikti


def idefix() -> list[dict]:
    e = pazaryeri.env_oku("/etc/lcarlie/idefix.env")
    jeton = base64.b64encode((e["IDEFIX_API_KEY"].strip() + ":" +
                              e["IDEFIX_API_SECRET"].strip()).encode()).decode()
    vendor = urllib.parse.quote(e["IDEFIX_SELLER_ID"].strip(), safe="")
    veri = json.loads(pazaryeri._istek(
        "https://merchantapi.idefix.com/oms/%s/list?page=1&limit=100" % vendor,
        {"X-API-KEY": jeton, "Accept": "application/json"}))
    cikti = []
    for p in veri.get("items") or []:
        if _gitmis_mi(str(p.get("status"))):
            continue
        cikti.append({
            "kanal": "İdefix", "no": str(p.get("orderNumber")),
            "kargo": p.get("cargoCompany") or "?",
            "kod": str(p.get("cargoTrackingNumber") or p.get("cargoKey") or "kod yok"),
            "musteri": str(p.get("customerContactName") or
                           (p.get("shippingAddress") or {}).get("fullName") or ""),
            "urunler": _urunler([{"ad": i.get("productName"), "adet": 1}
                                 for i in p.get("items") or []])})
    return cikti


def _basitkargo_kod(siparis_no: str) -> tuple[str, str]:
    try:
        from jarvis.basitkargo import Kargo
        sonuc = Kargo().cagir("search_shipments", {"keyword": siparis_no, "size": 5})
        for k in (sonuc.get("items") or []):
            kod = k.get("barcode") or k.get("trackingCode") or k.get("handlerShipmentCode")
            if kod:
                return str(kod), str(k.get("handlerName") or k.get("handler") or "Basit Kargo")
    except Exception:  # noqa: BLE001 -- kod bulunamazsa satır yine yazılır
        pass
    return "kargo kaydı yok", "-"


def wix() -> list[dict]:
    cikti = []
    for s in pazaryeri.wix(50):
        if s.durum != "PAID" or (s.ham or {}).get("fulfillmentStatus") != "NOT_FULFILLED":
            continue
        kod, kargo = _basitkargo_kod(s.siparis_no)
        cikti.append({"kanal": "Wix", "no": s.siparis_no, "kargo": kargo, "kod": kod,
                      "musteri": s.musteri_ad, "urunler": _urunler(s.kalemler)})
    return cikti


def n11() -> list[dict]:
    cikti = []
    for s in pazaryeri.n11():
        if _gitmis_mi(s.durum):
            continue
        cikti.append({"kanal": "n11", "no": s.siparis_no, "kargo": "?", "kod": "kod yok",
                      "musteri": s.musteri_ad, "urunler": _urunler(s.kalemler)})
    return cikti


KANALLAR = {"Trendyol": trendyol, "İdefix": idefix, "Wix": wix, "n11": n11}


def topla() -> tuple[list[dict], list[str]]:
    satirlar, okunamayan = [], []
    for ad, islev in KANALLAR.items():
        try:
            satirlar.extend(islev())
        except pazaryeri.KanalKapali:
            continue  # kimlik hiç girilmemiş kanal (HB yalnız e-posta yolunda)
        except Exception as hata:  # noqa: BLE001
            okunamayan.append("%s (%s)" % (ad, type(hata).__name__))
    # Aynı alıcıya giden paketler yan yana dursun: tek koliye konabilir.
    satirlar.sort(key=lambda r: (r["kanal"], r["musteri"], r["no"]))
    return satirlar, okunamayan


def parcala(satirlar: list[dict], okunamayan: list[str]) -> list[str]:
    adetler: dict[str, int] = {}
    for r in satirlar:
        adetler[r["musteri"]] = adetler.get(r["musteri"], 0) + 1
    ogeler = []
    for i, r in enumerate(satirlar, 1):
        ek = " (aynı alıcı)" if adetler[r["musteri"]] > 1 else ""
        ogeler.append("%d) %s %s · %s · kod %s · %s%s · %s" % (
            i, r["kanal"], r["no"], r["kargo"], r["kod"], r["musteri"] or "-", ek,
            r["urunler"]))
    if not ogeler:
        ogeler = ["Bekleyen sipariş yok."]
    if okunamayan:
        ogeler.append("⚠️ Okunamayan kanal: " + ", ".join(okunamayan))
    parcalar, simdi = [], ""
    for o in ogeler:
        aday = (simdi + " ▸ " + o) if simdi else o
        if len(aday) > PARCA_TAVAN and simdi:
            parcalar.append(simdi)
            simdi = o
        else:
            simdi = aday
    parcalar.append(simdi)
    return parcalar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true")
    a = ap.parse_args()
    satirlar, okunamayan = topla()
    tarih = datetime.now(TR).strftime("%d.%m.%Y")
    parcalar = parcala(satirlar, okunamayan)
    for n, parca in enumerate(parcalar, 1):
        baslik = tarih if len(parcalar) == 1 else "%s (%d/%d)" % (tarih, n, len(parcalar))
        degerler = [baslik, str(len(satirlar)), parca]
        if a.kuru:
            print(" | ".join(degerler))
            continue
        from jarvis import whatsapp
        sonuc = whatsapp.sablon_gonder(haberci.SAHIP_TELEFON, SABLON, degerler,
                                       onay_kaynagi="jarvis-otomatik")
        print("gonderildi", n, sonuc.get("wamid"))
    return 1 if okunamayan else 0


if __name__ == "__main__":
    sys.exit(main())
