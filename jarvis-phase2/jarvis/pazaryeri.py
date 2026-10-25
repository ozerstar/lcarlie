"""Pazaryeri siparis okuyuculari. Her kanal AYNI sozlesmeyi doner.

🔴 SOZLESME -- bu dosyanin tek kritik kurali:
    - adapter BIR LISTE dondurduyse: o kanalda su an bu siparisler VAR.
      Bos liste = "siparis yok" demektir ve DOGRU bilgidir.
    - adapter YUKSELDIYSE (raise): o kanalda ne oldugunu BILMIYORUZ.
    Bu ikisi birbirine KARISTIRILAMAZ. Karistirilirsa, calismayan bir
    kanal "siparis yok" gibi gorunur ve siparis sessizce kacirilir.

KanalKapali HATA DEGILDIR: kimlik bilgisi henuz girilmemis kanal demektir.
Nobetci onu "bilinmiyor" diye gosterir, alarm uretmez.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ZAMAN_ASIMI = 45
N8N_ENV = os.environ.get("N8N_ENV_FILE", "/opt/lcarlie/n8n/.env")


class KanalKapali(RuntimeError):
    """Kanal henuz baglanmadi (kimlik yok). Hata degil, eksik kurulum."""


@dataclass
class Siparis:
    kanal: str
    siparis_no: str
    durum: str
    paket_no: str | None = None
    zaman: datetime | None = None
    tutar: float | None = None
    musteri_ad: str = ""
    sehir: str = ""
    kalemler: list[dict] = field(default_factory=list)
    ham: dict = field(default_factory=dict)

    @property
    def ozet(self) -> str:
        kalem = ", ".join(str(k.get("ad", ""))[:40] for k in self.kalemler[:3])
        if len(self.kalemler) > 3:
            kalem += " (+%d)" % (len(self.kalemler) - 3)
        return kalem or "kalem bilgisi yok"


# --------------------------------------------------------------- yardimcilar
def env_oku(yol: str) -> dict[str, str]:
    p = Path(yol)
    if not p.exists():
        raise KanalKapali("%s yok" % yol)
    return dict(s.split("=", 1) for s in p.read_text(encoding="utf-8").splitlines()
                if "=" in s and not s.lstrip().startswith("#"))


def _n8n_env(anahtar: str) -> str:
    dogrudan = os.environ.get(anahtar)
    if dogrudan:
        return dogrudan.strip()
    for satir in Path(N8N_ENV).read_text(encoding="utf-8").splitlines():
        if satir.startswith(anahtar + "="):
            return satir.split("=", 1)[1].strip()
    return ""


def _istek(url: str, basliklar: dict[str, str], *, govde: bytes | None = None,
           yontem: str = "GET") -> bytes:
    r = urllib.request.Request(url, data=govde, headers=basliklar, method=yontem)
    try:
        with urllib.request.urlopen(r, timeout=ZAMAN_ASIMI) as y:
            return y.read()
    except urllib.error.HTTPError as h:
        # 🔴 Govde anahtar icerebilir; yalniz kod ve kisa metin disari cikar.
        ozet = h.read().decode("utf-8", "replace")[:200].replace("\n", " ")
        raise RuntimeError("HTTP %d: %s" % (h.code, ozet)) from None


def _ms_zaman(deger: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(deger) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso_zaman(deger: Any) -> datetime | None:
    if not deger:
        return None
    metin = str(deger).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(metin)
    except ValueError:
        pass
    for bicim in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(metin, bicim).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ TRENDYOL
def trendyol(sayfa_boyu: int = 200) -> list[Siparis]:
    e = env_oku("/etc/lcarlie/trendyol.env")
    sid = e["TRENDYOL_SELLER_ID"]
    cift = "%s:%s" % (e["TRENDYOL_API_KEY"], e["TRENDYOL_API_SECRET"])
    yetki = base64.b64encode(cift.encode()).decode()
    url = ("https://apigw.trendyol.com/integration/order/sellers/%s/orders"
           "?size=%d&orderByField=PackageLastModifiedDate"
           "&orderByDirection=DESC" % (sid, sayfa_boyu))
    veri = json.loads(_istek(url, {
        "Authorization": "Basic " + yetki,
        "User-Agent": "%s - SelfIntegration" % sid,
        "Content-Type": "application/json"}))
    cikti = []
    for p in veri.get("content") or []:
        ad = "%s %s" % (p.get("customerFirstName") or "", p.get("customerLastName") or "")
        cikti.append(Siparis(
            kanal="trendyol",
            siparis_no=str(p.get("orderNumber") or p.get("id") or ""),
            paket_no=str(p.get("id") or "") or None,
            durum=str(p.get("shipmentPackageStatus") or p.get("status") or "?"),
            zaman=_ms_zaman(p.get("orderDate")),
            tutar=p.get("grossAmount"),
            musteri_ad=ad.strip(),
            sehir=str((p.get("shipmentAddress") or {}).get("city") or ""),
            kalemler=[{"ad": s.get("productName"), "adet": s.get("quantity"),
                       "barkod": s.get("barcode")} for s in (p.get("lines") or [])],
            ham={k: p.get(k) for k in ("id", "orderNumber", "status",
                                       "shipmentPackageStatus", "cargoProviderName")}))
    return cikti


# ----------------------------------------------------------------------- N11
# 🔴 n11'in YAZMA servisleri REST'e tasindi ama OKUMA hala SOAP'ta.
#    product-create REST, OrderList SOAP -- ikisi ayni anda dogru.
_N11_SOAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
    ' xmlns:sch="http://www.n11.com/ws/schemas"><s:Body>'
    "<sch:OrderListRequest>"
    "<auth><appKey>{k}</appKey><appSecret>{s}</appSecret></auth>"
    "<searchData><sortForUpdateDate>true</sortForUpdateDate></searchData>"
    "<pagingData><currentPage>0</currentPage><pageSize>{n}</pageSize></pagingData>"
    "</sch:OrderListRequest></s:Body></s:Envelope>"
)


def _yerel(etiket: str) -> str:
    return etiket.rsplit("}", 1)[-1]


def _cocuk(dugum, ad: str, varsayilan: str = "") -> str:
    for c in dugum.iter():
        if _yerel(c.tag) == ad and c.text:
            return c.text.strip()
    return varsayilan


def n11(sayfa_boyu: int = 100) -> list[Siparis]:
    e = env_oku("/etc/lcarlie/n11.env")
    govde = _N11_SOAP.format(k=e["N11_APP_KEY"], s=e["N11_APP_SECRET"],
                             n=sayfa_boyu).encode("utf-8")
    ham = _istek("https://api.n11.com/ws/orderService/",
                 {"Content-Type": "text/xml;charset=UTF-8", "SOAPAction": ""},
                 govde=govde, yontem="POST")
    kok = ET.fromstring(ham)
    durum = _cocuk(kok, "status")
    if durum and durum != "success":
        raise RuntimeError("n11: " + _cocuk(kok, "errorMessage", "bilinmeyen hata")[:160])
    cikti = []
    for s in kok.iter():
        if _yerel(s.tag) != "order":
            continue
        kalemler = [{"ad": _cocuk(k, "productName"),
                     "adet": _cocuk(k, "quantity"),
                     "barkod": _cocuk(k, "productSellerCode")}
                    for k in s.iter() if _yerel(k.tag) == "orderItem"]
        tutar = _cocuk(s, "totalAmount", "0")
        cikti.append(Siparis(
            kanal="n11",
            siparis_no=_cocuk(s, "orderNumber") or _cocuk(s, "id"),
            durum=_cocuk(s, "status", "?"),
            zaman=_iso_zaman(_cocuk(s, "createDate")),
            tutar=float(tutar or 0) or None,
            musteri_ad=_cocuk(s, "fullName"),
            sehir=_cocuk(s, "city"),
            kalemler=kalemler,
            ham={"id": _cocuk(s, "id"), "status": _cocuk(s, "status")}))
    return cikti


# --------------------------------------------------------------- HEPSIBURADA
def hepsiburada(sayfa_boyu: int = 100) -> list[Siparis]:
    e = env_oku("/etc/lcarlie/hepsiburada.env")
    mid = e.get("HB_MERCHANT_ID", "")
    kul, sif = e.get("HB_API_USERNAME", ""), e.get("HB_API_PASSWORD", "")
    if not (mid and kul and sif):
        raise KanalKapali("HB_MERCHANT_ID / HB_API_USERNAME / HB_API_PASSWORD eksik")
    yetki = base64.b64encode(("%s:%s" % (kul, sif)).encode()).decode()
    url = ("https://oms-external.hepsiburada.com/orders/merchantid/%s"
           "?limit=%d&offset=0" % (mid, sayfa_boyu))
    veri = json.loads(_istek(url, {"Authorization": "Basic " + yetki,
                                   "User-Agent": mid,
                                   "Accept": "application/json"}))
    kayitlar = veri.get("items") if isinstance(veri, dict) else veri
    cikti = []
    for p in kayitlar or []:
        fiyat = p.get("totalPrice")
        cikti.append(Siparis(
            kanal="hepsiburada",
            siparis_no=str(p.get("orderNumber") or p.get("orderId") or ""),
            paket_no=str(p.get("packageNumber") or "") or None,
            durum=str(p.get("status") or "?"),
            zaman=_iso_zaman(p.get("orderDate") or p.get("createdDate")),
            tutar=fiyat.get("amount") if isinstance(fiyat, dict) else fiyat,
            musteri_ad=str((p.get("customer") or {}).get("name") or ""),
            sehir=str((p.get("shippingAddress") or {}).get("city") or ""),
            kalemler=[{"ad": i.get("productName"), "adet": i.get("quantity"),
                       "barkod": i.get("merchantSku")} for i in (p.get("items") or [])],
            ham={"orderNumber": p.get("orderNumber"), "status": p.get("status")}))
    return cikti


# -------------------------------------------------------------------- IDEFIX
def idefix(sayfa_boyu: int = 100) -> list[Siparis]:
    # 🔴 Idefix'in siparis ucu HENUZ BILINMIYOR. `oms/...` yollari
    #    omsapi.idefix.com/api/shipment/connect/... altina gidiyor ama
    #    denenen 13 yolun hepsi 404 verdi (25.10.2026). Tahminle yol
    #    uydurulmaz; Idefix destege soruldu.
    env_oku("/etc/lcarlie/idefix.env")          # kimlik duruyor mu
    raise KanalKapali("Idefix siparis ucu belirlenmedi (destek talebi acik)")


# --------------------------------------------------------------- CICEKSEPETI
def ciceksepeti(sayfa_boyu: int = 100) -> list[Siparis]:
    e = env_oku("/etc/lcarlie/ciceksepeti.env")
    anahtar = e.get("CICEKSEPETI_API_KEY", "")
    if not anahtar:
        raise KanalKapali("CICEKSEPETI_API_KEY yok")
    govde = json.dumps({"pageSize": sayfa_boyu, "page": 1}).encode()
    veri = json.loads(_istek("https://apis.ciceksepeti.com/api/v1/Order/GetOrders",
                             {"x-api-key": anahtar,
                              "Content-Type": "application/json"},
                             govde=govde, yontem="POST"))
    cikti = []
    for p in (veri.get("orders") or veri.get("data") or []):
        cikti.append(Siparis(
            kanal="ciceksepeti",
            siparis_no=str(p.get("orderCode") or p.get("orderId") or ""),
            durum=str(p.get("orderStatus") or p.get("status") or "?"),
            zaman=_iso_zaman(p.get("orderCreateDate")),
            tutar=p.get("totalPrice"),
            musteri_ad=str(p.get("receiverName") or ""),
            sehir=str(p.get("city") or ""),
            kalemler=[{"ad": i.get("productName"), "adet": i.get("quantity"),
                       "barkod": i.get("barcode")} for i in (p.get("items") or [])],
            ham={"orderCode": p.get("orderCode"), "status": p.get("orderStatus")}))
    return cikti


# ------------------------------------------------------------------ PAZARAMA
def pazarama(sayfa_boyu: int = 100) -> list[Siparis]:
    e = env_oku("/etc/lcarlie/pazarama.env")
    kimlik = e.get("PAZARAMA_CLIENT_ID", "")
    sir = e.get("PAZARAMA_CLIENT_SECRET", "")
    if not (kimlik and sir):
        raise KanalKapali("PAZARAMA_CLIENT_ID / PAZARAMA_CLIENT_SECRET yok")
    yetki = base64.b64encode(("%s:%s" % (kimlik, sir)).encode()).decode()
    jeton_yanit = json.loads(_istek(
        "https://isortagimapi.pazarama.com/api/token",
        {"Authorization": "Basic " + yetki,
         "Content-Type": "application/x-www-form-urlencoded"},
        govde=b"grant_type=client_credentials&scope=merchantgatewayapi.fullaccess",
        yontem="POST"))
    jeton = (jeton_yanit.get("data") or {}).get("accessToken")
    if not jeton:
        raise RuntimeError("Pazarama jetonu alinamadi")
    veri = json.loads(_istek(
        "https://isortagimapi.pazarama.com/order/getOrdersForApi?Size=%d" % sayfa_boyu,
        {"Authorization": "Bearer " + str(jeton), "Accept": "application/json"}))
    cikti = []
    for p in ((veri.get("data") or {}).get("orders") or []):
        cikti.append(Siparis(
            kanal="pazarama",
            siparis_no=str(p.get("orderNumber") or ""),
            durum=str(p.get("orderStatus") or "?"),
            zaman=_iso_zaman(p.get("orderDate")),
            tutar=p.get("totalAmount"),
            musteri_ad=str(p.get("customerName") or ""),
            sehir=str(p.get("city") or ""),
            kalemler=[{"ad": i.get("productName"), "adet": i.get("quantity"),
                       "barkod": i.get("barcode")} for i in (p.get("items") or [])],
            ham={"orderNumber": p.get("orderNumber")}))
    return cikti


# ----------------------------------------------------------------------- WIX
def wix(adet: int = 50) -> list[Siparis]:
    anahtar, site = _n8n_env("WIX_API_KEY"), _n8n_env("WIX_SITE_ID")
    if not (anahtar and site):
        raise KanalKapali("WIX_API_KEY / WIX_SITE_ID yok")
    sirala = '[{"dateCreated": "desc"}]'
    govde = json.dumps({"query": {"paging": {"limit": adet, "offset": 0},
                                  "sort": sirala}}).encode()
    veri = json.loads(_istek("https://www.wixapis.com/stores/v2/orders/query",
                             {"Authorization": anahtar, "wix-site-id": site,
                              "Content-Type": "application/json"},
                             govde=govde, yontem="POST"))
    cikti = []
    for p in veri.get("orders") or []:
        # 🔴 paymentMethod KOKTE YOK, billingInfo icinde. Kokte arayan
        #    "odeme yontemi bos" sanir.
        fatura = p.get("billingInfo") or {}
        sevk = (p.get("shippingInfo") or {}).get("shipmentDetails") or {}
        adres = sevk.get("address") or {}
        ad = "%s %s" % (fatura.get("firstName") or "", fatura.get("lastName") or "")
        toplam = str((p.get("totals") or {}).get("total") or 0)
        cikti.append(Siparis(
            kanal="wix",
            siparis_no=str(p.get("number") or p.get("id") or ""),
            durum=str(p.get("paymentStatus") or "?"),
            zaman=_iso_zaman(p.get("dateCreated")),
            tutar=float(toplam or 0) or None,
            musteri_ad=ad.strip(),
            sehir=str(adres.get("city") or ""),
            kalemler=[{"ad": i.get("name"), "adet": i.get("quantity"),
                       "barkod": i.get("sku")} for i in (p.get("lineItems") or [])],
            ham={"id": p.get("id"), "paymentMethod": fatura.get("paymentMethod"),
                 "fulfillmentStatus": p.get("fulfillmentStatus")}))
    return cikti


KANALLAR: dict[str, Callable[[], list[Siparis]]] = {
    "wix": wix,
    "trendyol": trendyol,
    "n11": n11,
    "hepsiburada": hepsiburada,
    "idefix": idefix,
    "ciceksepeti": ciceksepeti,
    "pazarama": pazarama,
}
