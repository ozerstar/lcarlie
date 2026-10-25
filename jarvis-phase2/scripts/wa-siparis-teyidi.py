#!/usr/bin/env python3
"""Sipariş teyidi WhatsApp şablonunu gönderir (kapıda ödeme DIŞI siparişler).

İki kaynak:
  --siparis 10039     raw.wix_order'dan okur (gerçek sipariş)
  --elle ...          alanları komuttan alır (deneme/düzeltme)

Gönderim `jarvis.whatsapp.sablon_gonder` üzerinden gider: beş kapı burada
değil ORADA işler. Bu betik yalnız değerleri hazırlar.

🔴 Varsayılan KURU KOŞU. Gerçekten göndermek için --gonder gerekir ve
`JARVIS_WHATSAPP_GONDER=1` açık olmalıdır.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import whatsapp  # noqa: E402

SABLON = "lcarlie_siparis_teyidi_v1"
KAPIDA = {"Çevrim Dışı Ödemeler", "Офлайн-оплата"}
GORSEL_KOK = "https://n8n.lcarlie.shop/urun-gorsel/teyit/"

ONIZLEME = (
    "Sayın {0},\n\nL’CARLIÉ ritüeline hoş geldiniz. Bize gösterdiğiniz güven "
    "için teşekkür ederiz.\n\n{1} numaralı siparişiniz tarafımıza ulaştı ve "
    "özenle hazırlanmak üzere alındı.\n\nÜrünler: {2}\nTutar: {3} TL\n"
    "Teslimat adresi: {4}\nTelefon: {5}\n\nGönderinizin ilk seferde doğru "
    "kapıya ulaşabilmesi için adres bilgilerinizi onaylamanızı rica ederiz. "
    "Bir düzeltme gerekiyorsa bu mesaja yazmanız yeterlidir; ekibimiz en kısa "
    "sürede dönüş yapar."
)


def _sql(sorgu: str) -> str:
    return subprocess.run(
        ["docker", "exec", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-t", "-A", "-c", sorgu],
        capture_output=True, text=True, check=True).stdout.strip()


def _tutar(deger) -> str:
    return f"{float(deger):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def siparisten(numara: str) -> dict:
    """Gerçek siparişi okur. Kapıda ödemeliyse BU şablon gönderilmez."""
    ham = _sql("select row_to_json(x) from (select odeme_yontemi, odeme_durumu, "
               "teslimat_durumu, arsivlendi, toplam, ham from raw.wix_order "
               "where siparis_no = %d) x" % int(numara))
    if not ham:
        raise SystemExit("siparis bulunamadi: " + numara)
    kayit = json.loads(ham)
    if kayit["odeme_yontemi"] in KAPIDA:
        raise SystemExit("bu siparis KAPIDA ODEMELI -- kapida odeme sablonu kullanilir")
    if kayit.get("arsivlendi") or kayit["teslimat_durumu"] in {"CANCELED", "CANCELLED"}:
        raise SystemExit("siparis arsivli veya iptal")
    govde = kayit["ham"]
    adres = (((govde.get("shippingInfo") or {}).get("shipmentDetails") or {})
             .get("address") or {})
    alici = govde.get("buyerInfo") or {}
    kalemler = govde.get("lineItems") or []
    return {
        "ad": (adres.get("fullName") or alici.get("firstName") or "").strip(),
        "no": str(numara),
        "urunler": ", ".join(
            "%s x%s" % (str(k.get("name") or "").split("(")[0].strip(),
                        k.get("quantity") or 1) for k in kalemler),
        "tutar": _tutar(kayit["toplam"]),
        "adres": ", ".join(p for p in (adres.get("addressLine1"),
                                       adres.get("city")) if p),
        "telefon": str(adres.get("phone") or alici.get("phone") or "").strip(),
        "urun_anahtar": str((kalemler[0].get("name") if kalemler else "")).split("(")[0].strip(),
    }


def main() -> None:
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--siparis")
    ayristirici.add_argument("--telefon")
    ayristirici.add_argument("--ad")
    ayristirici.add_argument("--no")
    ayristirici.add_argument("--urunler")
    ayristirici.add_argument("--tutar")
    ayristirici.add_argument("--adres")
    ayristirici.add_argument("--gorsel", help="baslik gorseli dosya adi (teyit/ altinda)")
    ayristirici.add_argument("--gonder", action="store_true",
                             help="KURU KOSUYU KAPAT -- gercek mesaj gider")
    arg = ayristirici.parse_args()

    if arg.siparis:
        veri = siparisten(arg.siparis)
        telefon = arg.telefon or veri["telefon"]
    else:
        eksik = [a for a in ("telefon", "ad", "no", "urunler", "tutar", "adres")
                 if not getattr(arg, a)]
        if eksik:
            raise SystemExit("eksik alan: " + ", ".join(eksik))
        veri = {"ad": arg.ad, "no": arg.no, "urunler": arg.urunler,
                "tutar": arg.tutar, "adres": arg.adres, "telefon": arg.telefon,
                "urun_anahtar": arg.urunler.split("x")[0].strip()}
        telefon = arg.telefon

    degerler = [veri["ad"], veri["no"], veri["urunler"], veri["tutar"],
                veri["adres"], veri["telefon"]]
    gorsel = GORSEL_KOK + (arg.gorsel or
                           veri["urun_anahtar"].split()[0].lower() + ".jpg")
    onizleme = ONIZLEME.format(*degerler)

    print(onizleme)
    print("\nbaslik gorseli:", gorsel)
    sonuc = whatsapp.sablon_gonder(
        telefon, SABLON, degerler, onay_kaynagi=whatsapp.ONAY_INSAN,
        baslik_gorsel=gorsel, onizleme=onizleme, kuru=not arg.gonder)
    print(json.dumps({k: v for k, v in sonuc.items() if k != "onizleme"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
