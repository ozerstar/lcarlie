#!/usr/bin/env python3
"""Hepsiburada SIT (test ortami) entegrasyon test senaryosu.

Hepsiburada canli API anahtarini, test ortaminda kullanilacak modelin
adimlari calistirildiktan sonra verir (SSS #12, #29). Bu betik o adimlari
SIRAYLA calistirir ve her istek/yanitin kaydini tutar; kayit, canli ortam
talebine kanit olarak eklenir.

  hb-sit-test.py listeleme|siparis|katalog|hepsi

Kimlik: /etc/lcarlie/hepsiburada-test.env (02.11.2026 mpentegrasyontestaccount
maili). Yalniz -sit ucuna gider; canli magazaya dokunmaz.
"""
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ENV = "/etc/lcarlie/hepsiburada-test.env"
KAYIT = Path("/opt/lcarlie/jarvis-phase2/state/hb-sit")
LISTING = "https://listing-external-sit.hepsiburada.com"
OMS = "https://oms-external-sit.hepsiburada.com"
STUB = "https://oms-stub-external-sit.hepsiburada.com"
MPOP = "https://mpop-sit.hepsiburada.com"


def env() -> dict:
    e = {}
    with open(ENV, encoding="utf-8") as f:
        for s in f:
            if "=" in s and not s.startswith("#"):
                k, v = s.rstrip("\n").split("=", 1)
                e[k] = v
    return e


E = env()
M = E["HB_TEST_MERCHANT_ID"]
YETKI = "Basic " + base64.b64encode(("%s:%s" % (M, E["HB_TEST_SECRET"])).encode()).decode()
GUNLUK: list[dict] = []


def istek(adim: str, yontem: str, url: str, govde=None, *, beklenen=(200, 201, 202, 204),
          tur: str = "application/json", ham: bytes | None = None):
    basliklar = {"Authorization": YETKI, "User-Agent": E["HB_TEST_USER_AGENT"],
                 "Accept": "application/json"}
    veri = ham
    if govde is not None:
        veri = json.dumps(govde, ensure_ascii=False).encode()
    if veri is not None:
        basliklar["Content-Type"] = tur
    r = urllib.request.Request(url, data=veri, method=yontem, headers=basliklar)
    try:
        with urllib.request.urlopen(r, timeout=40) as y:
            kod, metin, bas = y.status, y.read().decode("utf-8", "replace"), dict(y.headers)
    except urllib.error.HTTPError as h:
        kod, metin, bas = h.code, h.read().decode("utf-8", "replace"), dict(h.headers)
    try:
        cevap = json.loads(metin) if metin.strip() else None
    except ValueError:
        cevap = metin[:2000]
    basarili = kod in beklenen
    GUNLUK.append(dict(zaman=datetime.now(timezone.utc).isoformat(), adim=adim, yontem=yontem,
                       url=url.replace(M, "{merchantId}"), istek=govde if ham is None else "<dosya>",
                       http=kod, yanit=cevap, correlation_id=bas.get("x-correlation-id"),
                       basarili=basarili))
    print("%s %-48s %s %s" % ("✓" if basarili else "✗", adim, kod,
                              json.dumps(cevap, ensure_ascii=False)[:160]))
    return kod, cevap


def bekle_yukleme(adim: str, tur: str, kimlik: str) -> dict | None:
    for _ in range(12):
        time.sleep(5)
        _, c = istek(adim, "GET", "%s/listings/merchantid/%s/%s/id/%s" % (LISTING, M, tur, kimlik))
        if isinstance(c, dict) and c.get("status") in ("Done", "Failed"):
            return c
    return None


# ------------------------------------------------------------------ LISTELEME
def listeleme() -> list[dict]:
    L = "%s/listings/merchantid/%s" % (LISTING, M)
    _, c = istek("Listing bilgilerini çekme", "GET", L + "?offset=0&limit=50")
    ornek = (c or {}).get("listings", [])[:2]
    sku = [x["hepsiburadaSku"] for x in ornek]
    istek("Listing sorgu (hbSku)", "GET", L + "?offset=0&limit=10&hbSkuList=" + ",".join(sku))
    istek("Komisyon bilgisi sorgulama", "GET",
          "%s/commissions/merchantid/%s?skuList=%s" % (LISTING, M, ",".join(sku)))

    govde = [dict(hepsiburadaSku=x["hepsiburadaSku"], merchantSku=x["merchantSku"],
                  price="%d,90" % (150 + 70 * i), availableStock=25, dispatchTime=2,
                  cargoCompany1="Aras Kargo", cargoCompany2="", cargoCompany3="",
                  maximumPurchasableQuantity=0) for i, x in enumerate(ornek)]
    _, c = istek("Listing bilgilerini güncelleme (envanter)", "POST", L + "/inventory-uploads", govde)
    if isinstance(c, dict) and c.get("id"):
        bekle_yukleme("Listing güncelleme işlem kontrolü (envanter)", "inventory-uploads", c["id"])

    _, c = istek("Fiyat güncelleme", "POST", L + "/price-uploads",
                 [dict(hepsiburadaSku=x["hepsiburadaSku"], merchantSku=x["merchantSku"],
                       price="%d,50" % (160 + 70 * i)) for i, x in enumerate(ornek)])
    if isinstance(c, dict) and c.get("id"):
        bekle_yukleme("Fiyat güncelleme işlem kontrolü", "price-uploads", c["id"])
    _, c = istek("Stok güncelleme", "POST", L + "/stock-uploads",
                 [dict(hepsiburadaSku=x["hepsiburadaSku"], merchantSku=x["merchantSku"],
                       availableStock=30) for x in ornek])
    if isinstance(c, dict) and c.get("id"):
        bekle_yukleme("Stok güncelleme işlem kontrolü", "stock-uploads", c["id"])

    s = sku[0]
    istek("Listing satışa kapatma", "POST", "%s/sku/%s/deactivate" % (L, s))
    istek("Listing satışa açma", "POST", "%s/sku/%s/activate" % (L, s))
    istek("Buybox bilgilerini listeleme", "GET",
          "%s/buybox-orders/merchantid/%s?skuList=%s" % (LISTING, M, ",".join(sku)))
    _, c = istek("Listing doğrulama (satışta mı)", "GET", L + "?offset=0&limit=10&hbSkuList=" + ",".join(sku))
    return [dict(sku=x["hepsiburadaSku"], merchantSku=x["merchantSku"], price=x["price"])
            for x in (c or {}).get("listings", [])]


# ------------------------------------------------------------------- SIPARIS
def test_siparisi(urunler: list[dict]) -> str:
    # Ayni saniyede iki siparis ayni numarayi aliyordu (stub 409 dondu);
    # numara yalniz rakam kabul ediyor ("LC" + 10 hane gecti, hex harf reddedildi).
    no = "LC%010d" % (time.time_ns() // 1000 % 10**10)
    satirlar = [dict(Sku=u["sku"], MerchantId=M, Quantity=1,
                     Price=dict(Amount=float(u["price"] or 100), Currency="TRY"), Vat=0,
                     TotalPrice=dict(Amount=float(u["price"] or 100), Currency="TRY"),
                     CargoCompanyId=1, DeliveryOptionId=1) for u in urunler]
    istek("Test için sipariş oluşturma", "POST", "%s/orders/merchantId/%s" % (STUB, M), dict(
        OrderNumber=no, OrderDate=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        Customer=dict(CustomerId=str(uuid.uuid4()), Name="Test Musteri"),
        DeliveryAddress=dict(AddressId=str(uuid.uuid4()), Name="LEMOS Test", AddressDetail="Test adresi",
                             Email="test@lcarlie.com.tr", CountryCode="TR", PhoneNumber="905000000000",
                             AlternatePhoneNumber="905000000000", Town="Cankaya", District="Kizilay",
                             City="Ankara"),
        LineItems=satirlar))
    return no


def siparis(urunler: list[dict]):
    O = "%s/orders/merchantid/%s" % (OMS, M)
    no1 = test_siparisi(urunler)
    no2 = test_siparisi(urunler[:1])  # iptal senaryosu icin ayri siparis
    kalemler = []
    for _ in range(12):
        time.sleep(5)
        _, c = istek("Ödemesi tamamlanmış siparişleri listeleme", "GET", O + "?offset=0&limit=50")
        kalemler = [k for k in (c or {}).get("items", []) if k.get("orderNumber") in (no1, no2)]
        if len({k["orderNumber"] for k in kalemler}) == 2:
            break
    istek("Ödemesi beklenen siparişleri listeleme", "GET",
          "%s/orders/merchantid/%s/paymentawaiting?offset=0&limit=10" % (OMS, M))
    k1 = [k for k in kalemler if k["orderNumber"] == no1]
    k2 = [k for k in kalemler if k["orderNumber"] == no2]
    if not k1:
        print("Test siparişi listelenmedi; sipariş adımları durdu.")
        return

    # Paketleme
    istek("Aynı pakete konulabilecek kalemleri listeleme", "GET",
          "%s/lineitems/merchantid/%s/packageablewith/lineitemid/%s" % (OMS, M, k1[0]["id"]),
          beklenen=(200, 404))
    _, c = istek("Kalem veya kalemleri paketleme", "POST", "%s/packages/merchantid/%s" % (OMS, M), dict(
        parcelQuantity=1, deci=1,
        lineItemRequests=[dict(id=k["id"], quantity=k["quantity"]) for k in k1]))
    paket = (c or {}).get("packageNumber") if isinstance(c, dict) else None
    time.sleep(5)
    istek("Paket bilgilerini listeleme", "GET", "%s/packages/merchantid/%s?limit=10&offset=0" % (OMS, M))
    istek("Siparişe ait detay listeleme", "GET", "%s/orders/merchantid/%s/ordernumber/%s" % (OMS, M, no1))
    if paket:
        P = "%s/packages/merchantid/%s/packagenumber/%s" % (OMS, M, paket)
        istek("Paket bozma", "POST", P + "/unpack")
        istek("Bozulan paket bilgilerini listeleme", "GET",
              "%s/packages/merchantid/%s/status/unpacked?offset=0&limit=10" % (OMS, M))
        # Bozulan kalem yeniden paketlenir: canli akista da bu sira izlenir.
        time.sleep(5)
        _, c = istek("Yeniden paketleme", "POST", "%s/packages/merchantid/%s" % (OMS, M), dict(
            parcelQuantity=1, deci=1,
            lineItemRequests=[dict(id=k["id"], quantity=k["quantity"]) for k in k1]))
        paket = (c or {}).get("packageNumber") if isinstance(c, dict) else paket
        P = "%s/packages/merchantid/%s/packagenumber/%s" % (OMS, M, paket)
        istek("Paket için kargo bilgilerini listeleme", "GET", P)
        istek("Paketin geçebileceği kargo firmaları", "GET", P + "/changablecargocompanies")
        istek("Paketli siparişin kargo firmasını değiştirme", "PUT", P + "/changecargocompany",
              dict(cargoCompanyShortName="AR"))
        istek("Kargo değişikliği doğrulama", "GET", P)
        # Test faturasi: herkese acik ornek PDF (Content-Type application/pdf).
        istek("Fatura linki gönderme", "PUT", P + "/invoice",
              dict(invoiceLink="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"))
        istek("Fatura durumu (hasInvoice)", "GET",
              "%s/orders/merchantid/%s/ordernumber/%s" % (OMS, M, no1))
    if k2:
        istek("İptal bilgisi gönderme", "POST",
              "%s/lineitems/merchantid/%s/id/%s/cancelbymerchant" % (OMS, M, k2[0]["id"]),
              dict(reasonId=12))
        istek("İptal sipariş bilgilerini listeleme", "GET",
              "%s/orders/merchantid/%s/cancelled?offset=0&limit=10" % (OMS, M))
    istek("Kargoya verilen siparişleri listeleme", "GET",
          "%s/packages/merchantid/%s/shipped?offset=0&limit=10" % (OMS, M), beklenen=(200, 404))
    istek("Teslim edilen siparişleri listeleme", "GET",
          "%s/packages/merchantid/%s/delivered?offset=0&limit=10" % (OMS, M), beklenen=(200, 404))
    istek("Teslim edilemeyen siparişleri listeleme", "GET",
          "%s/packages/merchantid/%s/undelivered?offset=0&limit=10" % (OMS, M), beklenen=(200, 404))


# ------------------------------------------------------------------- KATALOG
# Gonderilen urun: LUCIDERM, Trendyol'da yayindaki bilgilerle (ad, aciklama,
# gorsel, INCI'den secilen icerikler, kullanim uyarilari). Etki yalniz
# "Temizleyici": akne/leke gibi iddia secenekleri bilerek secilmedi.
# Test ortaminda urun "Incelenecek"te kalir; onaylayan ekip yok (SSS #29).
URUN = KAYIT / "urun-luciderm.json"
KATEGORI = 32010908  # Kozmetik > Cilt Bakimi > Yuz Bakimi > Temizleyiciler ve Tonikler > Kopuk


def katalog():
    istek("Kategori bilgilerini alma", "GET", MPOP + "/product/api/categories/get-all-categories"
          "?leaf=true&status=ACTIVE&available=true&page=0&size=5&version=1")
    istek("Kategori özelliklerini alma", "GET", "%s/product/api/categories/%d/attributes" % (MPOP, KATEGORI))
    for ozellik in ("0000031", "hacim", "00004O7K", "turu"):
        istek("Özellik değerini alma (%s)" % ozellik, "GET",
              "%s/product/api/categories/%d/attribute/%s/values?page=0&size=100&version=4"
              % (MPOP, KATEGORI, ozellik))
    if not URUN.exists():
        print("Ürün dosyası yok (%s); yükleme atlandı." % URUN)
        return
    urun = json.loads(URUN.read_text(encoding="utf-8"))
    for u in urun:
        u["merchant"] = M
    sinir = uuid.uuid4().hex
    ham = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"urunler.json\"\r\n"
            "Content-Type: application/json\r\n\r\n" % sinir).encode()
           + json.dumps(urun, ensure_ascii=False).encode() + ("\r\n--%s--\r\n" % sinir).encode())
    _, c = istek("Ürün bilgisi gönderme", "POST", MPOP + "/product/api/products/import",
                 ham=ham, tur="multipart/form-data; boundary=" + sinir)
    takip = ((c or {}).get("data") or {}).get("trackingId") if isinstance(c, dict) else None
    if takip:
        for _ in range(8):
            time.sleep(8)
            _, d = istek("Ürün durumu sorgulama", "GET",
                         "%s/product/api/products/status/%s?page=0&size=10&version=1" % (MPOP, takip))
            if isinstance(d, dict) and all(x.get("importStatus") not in ("WAITING", "IN_PROGRESS", None)
                                           for x in d.get("data") or [{}]):
                break
    istek("Statü bazlı ürün bilgisi çekme", "GET",
          "%s/product/api/products/all-products-of-merchant/%s?page=0&size=5" % (MPOP, M))


ADIMLAR = {"listeleme": listeleme, "siparis": None, "katalog": katalog}


def main() -> int:
    hedef = sys.argv[1] if len(sys.argv) > 1 else "hepsi"
    KAYIT.mkdir(parents=True, exist_ok=True)
    try:
        urunler = []
        if hedef in ("listeleme", "siparis", "hepsi"):
            urunler = listeleme()
        if hedef in ("siparis", "hepsi"):
            siparis([u for u in urunler if u["price"]][:2])
        if hedef in ("katalog", "hepsi"):
            katalog()
    finally:
        yol = KAYIT / ("%s-%s.json" % (hedef, datetime.now().strftime("%Y%m%d-%H%M%S")))
        yol.write_text(json.dumps(GUNLUK, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = sum(1 for g in GUNLUK if g["basarili"])
        print("\n%d/%d adım başarılı · kayıt: %s" % (ok, len(GUNLUK), yol))
    return 0


if __name__ == "__main__":
    sys.exit(main())
