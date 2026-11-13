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
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import pazaryeri, haberci  # noqa: E402

SABLON_ON_EK = "lcarlie_kargo_satirli_v2_"
TR = timezone(timedelta(hours=3))
# Satır sonları Meta'da onaylı şablonların sabit metninde bulunur.
# Parametreler tek satırdır; 10 satırın üzeri panelde gösterilir.
SATIR_TAVAN = 10

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
            a = p.get("shipmentAddress") or {}
            cikti.append({
                "kanal": "Trendyol", "no": str(p.get("orderNumber")),
                "kargo": (p.get("cargoProviderName") or "?").replace(" Marketplace", ""),
                "kod": str(p.get("cargoTrackingNumber") or "kod yok"),
                "musteri": ("%s %s" % (p.get("customerFirstName") or "",
                                       p.get("customerLastName") or "")).strip(),
                "urunler": _urunler([{"ad": s.get("productName"), "adet": s.get("quantity")}
                                     for s in p.get("lines") or []]),
                # Etiket alanları (kargo-bekleyen.py): sabah mesajı bunları okumaz.
                "alici": str(a.get("fullName") or "").strip(),
                "adres": " ".join(str(x).strip() for x in (
                    a.get("address1"), a.get("address2"), a.get("neighborhood")) if x),
                "ilce": str(a.get("district") or ""), "il": str(a.get("city") or ""),
                "telefon": str(a.get("phone") or ""),
                "paket_no": str(p.get("shipmentPackageId") or p.get("id") or ""),
                "durum": str(p.get("shipmentPackageStatus") or "")})
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
        a = p.get("shippingAddress") or {}
        cikti.append({
            "kanal": "İdefix", "no": str(p.get("orderNumber")),
            "kargo": p.get("cargoCompany") or "?",
            "kod": str(p.get("cargoTrackingNumber") or p.get("cargoKey") or "kod yok"),
            "musteri": str(p.get("customerContactName") or a.get("fullName") or ""),
            "urunler": _urunler([{"ad": i.get("productName"), "adet": 1}
                                 for i in p.get("items") or []]),
            "alici": str(a.get("fullName") or "").strip(),
            "adres": " ".join(str(x).strip() for x in (
                a.get("address1"), a.get("neighboorhood")) if x),
            "ilce": str(a.get("county") or ""), "il": str(a.get("city") or ""),
            "telefon": str(a.get("phone") or ""),
            "paket_no": str(p.get("id") or ""),
            "durum": str(p.get("statusDescription") or p.get("status") or "")})
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


def tek_mesaj(satirlar: list[dict], okunamayan: list[str], tarih: str) -> tuple[str, list[str]]:
    adetler: dict[str, int] = {}
    for r in satirlar:
        adetler[r["musteri"]] = adetler.get(r["musteri"], 0) + 1
    ogeler = []
    gosterilecek = satirlar if len(satirlar) <= SATIR_TAVAN else satirlar[:SATIR_TAVAN - 1]
    for r in gosterilecek:
        ek = " (aynı alıcı)" if adetler[r["musteri"]] > 1 else ""
        oge = "%s %s · %s · kod %s · %s%s · %s" % (
            r["kanal"], r["no"], r["kargo"], r["kod"], r["musteri"] or "-", ek,
            r["urunler"])
        ogeler.append(oge[:220] + "…" if len(oge) > 220 else oge)
    if len(satirlar) > SATIR_TAVAN:
        ogeler.append("Diğer %d siparişin listesi Jarvis panelinde." %
                      (len(satirlar) - len(gosterilecek)))
    durum = ("⚠️ Okunamayan kanal: " + ", ".join(okunamayan)
             if okunamayan else "Tüm kanallar okundu.")
    return SABLON_ON_EK + str(len(ogeler)), [tarih, str(len(satirlar)), *ogeler, durum]


def _sablon_onayli(sablon: str) -> bool:
    """Meta onayını her sabah doğrula; bekleyen şablonu göndermeye çalışma."""
    from jarvis import whatsapp
    token = whatsapp._env("META_WHATSAPP_TOKEN")
    waba = whatsapp._env("META_WABA_ID")
    if not token or not waba:
        return False
    url = "https://graph.facebook.com/v21.0/%s/message_templates?%s" % (
        waba, urllib.parse.urlencode({"name": sablon, "fields": "name,status"}))
    try:
        istek = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(istek, timeout=15) as yanit:
            veri = json.load(yanit)
        return any(k.get("name") == sablon and k.get("status") == "APPROVED"
                   for k in veri.get("data", []))
    except Exception:  # noqa: BLE001 -- onay sorgusu aksarsa eski şablon kullanılır
        return False


def _eski_sablon_degerleri(degerler: list[str]) -> list[str]:
    """Onay beklerken de yalnız tek bildirim gönder."""
    tarih, toplam, *kalan = degerler
    durum = kalan.pop()
    ogeler = []
    for i, oge in enumerate(kalan, 1):
        aday = " ▸ ".join([*ogeler, "%d) %s" % (i, oge)])
        if len(aday.encode("utf-8")) > 650:
            break
        ogeler.append("%d) %s" % (i, oge))
    metin = " ▸ ".join(ogeler) or "Bekleyen sipariş yok."
    if len(ogeler) < len(kalan):
        metin += " · Kalan siparişler Jarvis panelinde."
    if durum != "Tüm kanallar okundu.":
        metin += " · " + durum
    return [tarih, toplam, metin]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true")
    a = ap.parse_args()
    satirlar, okunamayan = topla()
    tarih = datetime.now(TR).strftime("%d.%m.%Y")
    sablon, degerler = tek_mesaj(satirlar, okunamayan, tarih)
    if not _sablon_onayli(sablon):
        sablon, degerler = "lcarlie_kargo_listesi_v1", _eski_sablon_degerleri(degerler)
    if a.kuru:
        print(sablon, "|", " | ".join(degerler))
        return 1 if okunamayan else 0
    from jarvis import whatsapp
    sonuc = whatsapp.sablon_gonder(haberci.SAHIP_TELEFON, sablon, degerler,
                                   onay_kaynagi="jarvis-otomatik")
    print("gonderildi", sonuc.get("wamid"))
    return 1 if okunamayan else 0


if __name__ == "__main__":
    sys.exit(main())
