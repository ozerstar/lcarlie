#!/usr/bin/env python3
"""L'CARLIE siparis teyidi WhatsApp sablonunu Meta'ya kurar (gorsel baslikli).

IMAGE baslikli sablon olusturmak icin ornek gorselin "header_handle"i gerekir;
bu handle yalnizca Resumable Upload API'den alinir (link kabul edilmez).
Gonderim aninda baslik gorseli her urun icin ayri verilebilir -- handle sadece
Meta'nin incelemede gorecegi ornektir.

Kullanim: wa-sablon-olustur.py <ornek-gorsel.jpg>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SURUM = "v21.0"
UYGULAMA = "2243528976504995"
SABLON_ADI = "lcarlie_siparis_teyidi_v1"

GOVDE = (
    "Sayın {{1}},\n\n"
    "L’CARLIÉ ritüeline hoş geldiniz. Bize gösterdiğiniz güven için teşekkür ederiz.\n\n"
    "{{2}} numaralı siparişiniz tarafımıza ulaştı ve özenle hazırlanmak üzere alındı.\n\n"
    "Ürünler: {{3}}\n"
    "Tutar: {{4}} TL\n"
    "Teslimat adresi: {{5}}\n"
    "Telefon: {{6}}\n\n"
    "Gönderinizin ilk seferde doğru kapıya ulaşabilmesi için adres bilgilerinizi "
    "onaylamanızı rica ederiz. Bir düzeltme gerekiyorsa bu mesaja yazmanız yeterlidir; "
    "ekibimiz en kısa sürede dönüş yapar."
)

ORNEK = ["Ayşe Yılmaz", "10039", "DERMANOVA x1", "2.100,00",
         "Örnek Sokak No:1 Daire:3, Çankaya / Ankara", "+905320000000"]


def _jeton() -> str:
    for ad in ("META_WHATSAPP_TOKEN", "META_SYSTEM_TOKEN"):
        deger = os.environ.get(ad)
        if deger:
            return deger
    raise SystemExit("jeton yok")


def _uygulama_jetonu() -> str:
    """Resumable Upload uygulama dugumunde calisir; sistem kullanicisi jetonu
    orada "nonexisting field (uploads)" verir. Uygulama jetonu gerekir."""
    gizli = os.environ.get("META_APP_SECRET", "")
    if not gizli:
        raise SystemExit("META_APP_SECRET yok")
    return f"{UYGULAMA}|{gizli}"


def _cagir(adres: str, veri=None, basliklar=None, ham=None, *, uygulama=False) -> dict:
    # 🔴 data=None urllib'de GET demektir; bos govdeli POST b"" olmali.
    # Aksi halde /uploads "nonexisting field (uploads)" der (GET yok).
    govde = ham if ham is not None else urllib.parse.urlencode(veri or {}).encode()
    istek = urllib.request.Request(adres, data=govde, method="POST")
    istek.add_header("Authorization",
                     ("OAuth " + _uygulama_jetonu()) if uygulama
                     else ("Bearer " + _jeton()))
    for anahtar, deger in (basliklar or {}).items():
        istek.add_header(anahtar, deger)
    try:
        with urllib.request.urlopen(istek, timeout=120) as yanit:
            return json.loads(yanit.read().decode())
    except urllib.error.HTTPError as hata:
        govde = hata.read().decode()
        raise SystemExit(f"HTTP {hata.code}: {govde[:900]}") from None


def handle_al(yol: Path) -> str:
    """Resumable Upload: once oturum acilir, sonra dosya tek parca gonderilir."""
    oturum = _cagir(
        f"https://graph.facebook.com/{SURUM}/{UYGULAMA}/uploads?"
        + urllib.parse.urlencode({"file_length": yol.stat().st_size,
                                  "file_type": "image/jpeg",
                                  "file_name": yol.name}),
        veri={}, uygulama=True)
    kimlik = oturum["id"]
    sonuc = _cagir(f"https://graph.facebook.com/{SURUM}/{kimlik}",
                   basliklar={"file_offset": "0",
                              "Content-Type": "application/octet-stream"},
                   ham=yol.read_bytes(), uygulama=True)
    return sonuc["h"]


def sablon_kur(handle: str) -> dict:
    bilesenler = [
        {"type": "HEADER", "format": "IMAGE",
         "example": {"header_handle": [handle]}},
        {"type": "BODY", "text": GOVDE,
         "example": {"body_text": [ORNEK]}},
        {"type": "FOOTER", "text": "L’CARLIÉ | Sipariş teyidi"},
        {"type": "BUTTONS", "buttons": [
            {"type": "QUICK_REPLY", "text": "Adresim doğru"},
            {"type": "QUICK_REPLY", "text": "Adresimi düzelteceğim"},
        ]},
    ]
    waba = os.environ.get("META_WABA_ID", "2418585758581265")
    return _cagir(
        f"https://graph.facebook.com/{SURUM}/{waba}/message_templates",
        veri={"name": SABLON_ADI, "language": "tr", "category": "UTILITY",
              "components": json.dumps(bilesenler, ensure_ascii=False)})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    h = handle_al(Path(sys.argv[1]))
    print("handle alindi:", h[:28], "...")
    print(json.dumps(sablon_kur(h), ensure_ascii=False, indent=2))
