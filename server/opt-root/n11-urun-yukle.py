#!/usr/bin/env python3
"""n11'e urun gonderir (SaveProduct).

ONCE TEK URUN. n11'in yaniti neyin eksik oldugunu kesin soyluyor; marka ve
kargo sablonu engelleri hakkinda tahmin yurutmek yerine SERVISE SORULUR.

🔴 Idefix dersleri burada da gecerli:
- Yanit "success" demeden hicbir sey yuklenmis sayilmaz; ayrica
  ProductApprovalStatus ile dogrulanir.
- Ozellik degeri kategorinin izinli listesinde BIREBIR yoksa yazilmaz.

Kullanim:
  python3 n11-urun-yukle.py --barkod 8684869609233          (sadece gosterir)
  python3 n11-urun-yukle.py --barkod 8684869609233 --gonder (gercekten gonderir)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ENV = Path("/etc/lcarlie/n11.env")
URUN_CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
KAT_CSV = Path("/opt/lcarlie/n11-hazirlik/n11-kategori-id.csv")
OZELLIK = Path("/opt/lcarlie/n11-hazirlik/n11-ozellikler.json")
# 🔴 .wsdl adresine POST her serviste calismiyor; dogru adres WSDL icindeki
# <soap:address location="..."> degeri (ShipmentService'te de ayni tuzak).
UC = "https://api.n11.com/ws/productService/"

MARKA = "L'CARLIÉ"
HAZIRLIK_GUN = 3
PARA_TL = 1          # currencyType: 1 = TL

# Urun basina, kategorinin izinli listesinden SECILMIS degerler.
# Bos birakilan alan = listede birebir karsiligi bulunamadi.
ELLE_OZELLIK = {
    "8684869609233": {"Kullanım Amacı": "Nemlendirme",
                      "Cilt Tipi": "Tüm Cilt Tipleri",
                      "Ürün Miktarı": "50 ML"},
}


def ortam() -> dict[str, str]:
    return dict(s.split("=", 1) for s in ENV.read_text(encoding="utf-8").splitlines()
                if "=" in s and not s.startswith("#"))


def cagir(xml: str) -> str:
    r = urllib.request.Request(UC, data=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml;charset=UTF-8", "SOAPAction": ""})
    with urllib.request.urlopen(r, timeout=120) as y:
        return y.read().decode("utf-8", "replace")


def govde_kur(u: dict, kid: str, ozellik: dict[str, str], K: str, S: str) -> str:
    gorseller = "".join(
        f"<image><url>{escape(u[f'gorsel_{i}'])}</url><order>{i}</order></image>"
        for i in range(1, 6) if u.get(f"gorsel_{i}"))
    oz = "".join(f"<attribute><name>{escape(a)}</name>"
                 f"<value>{escape(d)}</value></attribute>"
                 for a, d in ozellik.items() if d)
    fiyat = float(u["fiyat"])
    stok = int(float(u["stok"] or 0))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:sch="http://www.n11.com/ws/schemas">
 <s:Body><sch:SaveProductRequest>
  <auth><appKey>{K}</appKey><appSecret>{S}</appSecret></auth>
  <product>
   <productSellerCode>{escape(u['barkod'])}</productSellerCode>
   <title>{escape(u['idefix_baslik'])}</title>
   <subtitle>{escape(u['idefix_baslik'][:60])}</subtitle>
   <description><![CDATA[{u['idefix_aciklama']}]]></description>
   <category><id>{kid}</id></category>
   <price>{fiyat:.2f}</price>
   <currencyType>{PARA_TL}</currencyType>
   <images>{gorseller}</images>
   <domestic>true</domestic>
   <approvalStatus>Active</approvalStatus>
   <attributes>{oz}</attributes>
   <productionDate></productionDate>
   <expirationDate></expirationDate>
   <productCondition>1</productCondition>
   <preparingDay>{HAZIRLIK_GUN}</preparingDay>
   <shipmentTemplate></shipmentTemplate>
   <stockItems>
    <stockItem>
     <bundle>false</bundle>
     <gtin>{escape(u['barkod'])}</gtin>
     <quantity>{stok}</quantity>
     <sellerStockCode>{escape(u['barkod'])}</sellerStockCode>
    </stockItem>
   </stockItems>
  </product>
 </sch:SaveProductRequest></s:Body></s:Envelope>'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--barkod", required=True)
    ap.add_argument("--gonder", action="store_true")
    a = ap.parse_args()

    env = ortam()
    K, S = env["N11_APP_KEY"], env["N11_APP_SECRET"]
    urun = {x["barkod"]: x for x in csv.DictReader(
        URUN_CSV.open(encoding="utf-8-sig"), delimiter=";")}[a.barkod]
    kat = {x["barkod"]: x for x in csv.DictReader(
        KAT_CSV.open(encoding="utf-8-sig"), delimiter=";")}[a.barkod]
    kid = kat["n11_kategori_id"]
    if not kid:
        print("bu urunun n11 kategorisi yok, gonderilemez")
        return 1

    tanim = json.loads(OZELLIK.read_text(encoding="utf-8"))[kid]
    zorunlu = [o["ad"] for o in tanim["ozellikler"] if o["zorunlu"]]
    ozellik = {"Marka": MARKA}
    ozellik.update(ELLE_OZELLIK.get(a.barkod, {}))
    eksik = [z for z in zorunlu if not ozellik.get(z)]

    print(f"urun      : {urun['urun_adi_wix'][:46]}")
    print(f"kategori  : {kid} · {kat['n11_kategori']}")
    print(f"fiyat/stok: {urun['fiyat']} TL · {urun['stok']} adet")
    print(f"gorsel    : {sum(1 for i in range(1,6) if urun.get(f'gorsel_{i}'))}")
    print(f"aciklama  : {len(urun['idefix_aciklama'])} karakter")
    print("ozellikler:")
    for k, v in ozellik.items():
        print(f"   {k:<18} {v}")
    if eksik:
        print(f"🔴 doldurulamayan ZORUNLU alan: {', '.join(eksik)}")

    if not a.gonder:
        print("\n(--gonder verilmedi, gonderilmedi)")
        return 0

    y = cagir(govde_kur(urun, kid, ozellik, K, S))
    durum = re.search(r"<status>(.*?)</status>", y)
    print(f"\ndurum: {durum.group(1) if durum else '?'}")
    for h in re.findall(r"<errorMessage>(.*?)</errorMessage>", y, re.S):
        print("hata :", h.strip())
    for h in re.findall(r"<errorCode>(.*?)</errorCode>", y, re.S):
        print("kod  :", h.strip())
    pid = re.search(r"<id>(\d+)</id>", y)
    if pid:
        print("urun id:", pid.group(1))
    if not durum:
        print("ham yanit:", y[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
