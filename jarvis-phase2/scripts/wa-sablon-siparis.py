#!/usr/bin/env python3
"""Sahibe siparis haberi veren UTILITY sablonunu Meta'da kurar.

Bu sablon MUSTERIYE degil, ISLETME SAHIBINE gider. Yine de sablon gerekir:
isletmenin baslattigi her konusma 24 saat penceresi disinda sablon ister.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

AD = "lcarlie_yeni_siparis_v1"
GOVDE = ("🛎️ Yeni sipariş geldi.\n\n"
         "Kanal: {{1}}\n"
         "Sipariş: {{2}}\n"
         "Tutar: {{3}} TL\n"
         "Müşteri: {{4}}\n"
         "Ürünler: {{5}}\n\n"
         "Ayrıntı için Jarvis panelini açabilirsiniz.")
ORNEK = ["Trendyol", "1234567890", "2.100,00", "Ayşe Y. / Ankara",
         "SERALIMBO Gece Bakım Kremi x1"]


def env(anahtar: str) -> str:
    for dosya in ("/etc/lcarlie/jarvis-web.env", "/opt/lcarlie/n8n/.env",
                  "/etc/lcarlie/meta-webhook.env"):
        p = Path(dosya)
        if not p.exists():
            continue
        for satir in p.read_text(encoding="utf-8").splitlines():
            if satir.startswith(anahtar + "="):
                return satir.split("=", 1)[1].strip()
    return ""


def main() -> int:
    jeton, waba = env("META_WHATSAPP_TOKEN"), env("META_WABA_ID")
    if not (jeton and waba):
        print("jeton veya WABA kimligi yok")
        return 1
    govde = json.dumps({
        "name": AD,
        "language": "tr",
        "category": "UTILITY",
        "components": [{
            "type": "BODY",
            "text": GOVDE,
            "example": {"body_text": [ORNEK]},
        }],
    }, ensure_ascii=False).encode("utf-8")
    istek = urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s/message_templates" % waba,
        data=govde, method="POST",
        headers={"Authorization": "Bearer " + jeton,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=60) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        print("kuruldu:", json.dumps(veri, ensure_ascii=False))
        print("🔴 'PENDING' onaylandi demek DEGIL; APPROVED olana kadar "
              "WhatsApp yolu HATA verir, push ve e-posta calismaya devam eder.")
        return 0
    except urllib.error.HTTPError as hata:
        # 🔴 Hata govdesi jeton icerebilir; yalniz kod + kisa mesaj yazilir.
        try:
            detay = json.loads(hata.read().decode("utf-8")).get("error", {})
            print("HTTP %d: %s" % (hata.code, str(detay.get("message"))[:200]))
        except Exception:  # noqa: BLE001
            print("HTTP %d" % hata.code)
        return 1


if __name__ == "__main__":
    sys.exit(main())
