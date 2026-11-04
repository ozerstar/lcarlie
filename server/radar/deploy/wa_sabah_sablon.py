#!/usr/bin/env python3
"""Radar sabah ozeti WhatsApp sablonunu Meta'ya kurar (yalniz metin, 5 degisken). Sahip onayi: 31.10.2026."""
import json, os, urllib.parse, urllib.request, urllib.error
SURUM = "v21.0"
AD = "lcarlie_sabah_ozeti_v1"
GOVDE = ("☀️ L’CARLIÉ sabah özeti — {{1}}\n"
         "Rakip radarı: {{2}}\n"
         "Müşteri adayları: {{3}}\n"
         "Onayınızı bekleyen: {{4}}\n"
         "Satış: {{5}}\n"
         "Ayrıntılar Jarvis panelinde, Radar bölümünde.")
ORNEK = ["31.10.2026", "2 yeni aday: Örnek Marka (78), Diğer Marka (64)", "3 yeni eczane/klinik adayı",
         "1 mesaj taslağı, 12 aday marka", "Trendyol: 2 sipariş"]
jeton = os.environ.get("META_WHATSAPP_TOKEN") or os.environ.get("META_SYSTEM_TOKEN")
waba = os.environ.get("META_WABA_ID")
assert jeton and waba, "jeton/WABA yok"
bilesen = [{"type": "BODY", "text": GOVDE, "example": {"body_text": [ORNEK]}},
           {"type": "FOOTER", "text": "L’CARLIÉ | Jarvis Radar"}]
veri = urllib.parse.urlencode({"name": AD, "language": "tr", "category": "UTILITY",
                               "components": json.dumps(bilesen, ensure_ascii=False)}).encode()
istek = urllib.request.Request(f"https://graph.facebook.com/{SURUM}/{waba}/message_templates", data=veri, method="POST")
istek.add_header("Authorization", "Bearer " + jeton)
try:
    with urllib.request.urlopen(istek, timeout=60) as y:
        print(y.read().decode())
except urllib.error.HTTPError as h:
    print("HTTP", h.code, h.read().decode()[:900])
