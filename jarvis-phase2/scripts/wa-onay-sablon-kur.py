#!/usr/bin/env python3
"""Sahibe giden onay şablonunu (lcarlie_onay_bekliyor_v1) Meta'ya kurar.

İki hızlı yanıt düğmesi: "Onayla" / "Reddet". Gönderimde her düğmeye
wa-onay.py öneri kimliği + tek kullanımlık nonce taşıyan yük verir.

Kullanim: wa-onay-sablon-kur.py          (META_WHATSAPP_TOKEN ortamda)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

SURUM = "v21.0"
SABLON_ADI = "lcarlie_onay_bekliyor_v1"
GOVDE = (
    "🔔 Jarvis onayınızı bekliyor.\n\n"
    "Öneri: {{1}}\n"
    "Konu: {{2}}\n"
    "Özet: {{3}}\n\n"
    "Kararınızı aşağıdaki düğmelerle verebilirsiniz. "
    "Ayrıntı için Jarvis paneli: jarvis.lcarlie.shop"
)
ORNEK = ["#167", "KURUL KARARI · AI_OPS", "Model kademe risk matrisini onaylamak"]


def sablon_kur() -> dict:
    bilesenler = [
        {"type": "BODY", "text": GOVDE, "example": {"body_text": [ORNEK]}},
        {"type": "FOOTER", "text": "L’CARLIÉ | Jarvis"},
        {"type": "BUTTONS", "buttons": [
            {"type": "QUICK_REPLY", "text": "Onayla"},
            {"type": "QUICK_REPLY", "text": "Reddet"},
        ]},
    ]
    waba = os.environ.get("META_WABA_ID", "2418585758581265")
    istek = urllib.request.Request(
        f"https://graph.facebook.com/{SURUM}/{waba}/message_templates", method="POST",
        data=urllib.parse.urlencode({
            "name": SABLON_ADI, "language": "tr", "category": "UTILITY",
            "components": json.dumps(bilesenler, ensure_ascii=False)}).encode())
    istek.add_header("Authorization", "Bearer " + os.environ["META_WHATSAPP_TOKEN"])
    try:
        with urllib.request.urlopen(istek, timeout=60) as yanit:
            return json.loads(yanit.read().decode())
    except urllib.error.HTTPError as hata:
        raise SystemExit(f"HTTP {hata.code}: {hata.read().decode()[:900]}") from None


if __name__ == "__main__":
    print(json.dumps(sablon_kur(), ensure_ascii=False, indent=2))
