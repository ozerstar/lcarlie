# -*- coding: utf-8 -*-
"""chatgpt_chat — ChatGPT web arayuzunde metin uretir.

ARAYUZE DOKUNAN TEK YER BURASI.
"""
from __future__ import annotations

from handlers import ortak

ADRES = "https://chatgpt.com/"

KUTU = (
    "#prompt-textarea",
    'div[contenteditable="true"]#prompt-textarea',
    'textarea[data-id="root"]',
    'div[contenteditable="true"]',
)

GONDER = (
    'button[data-testid="send-button"]',
    'button[aria-label*="Send prompt" i]',
    'button[aria-label*="Mesaj gonder" i]',
)

MESAJ = (
    'div[data-message-author-role="assistant"]',
    "div.agent-turn",
    'article[data-testid^="conversation-turn"]',
)

ZAMAN_ASIMI_S = 180.0          # sohbet: 3 dk (sartname)


def calistir(page, is_: dict, zaman_asimi_s: float | None = None) -> dict:
    tavan = float(zaman_asimi_s or ZAMAN_ASIMI_S)

    page.goto(ADRES, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    ortak.kapiyi_gec(page)

    kutu = ortak.ilk_bulunan(page, KUTU)
    onceki = ortak.mesaj_adedi(page, MESAJ)

    ortak.istemi_yaz(page, kutu, is_["istem"])
    ortak.gonder(page, kutu, GONDER)

    metin = ortak.yanit_bekle(page, MESAJ, onceki, tavan)
    return {"metin": metin, "dosyalar": []}
