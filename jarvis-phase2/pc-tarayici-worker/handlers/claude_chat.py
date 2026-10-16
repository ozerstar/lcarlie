# -*- coding: utf-8 -*-
"""claude_chat — Claude web arayuzunde metin uretir.

ARAYUZE DOKUNAN TEK YER BURASI. Secici bayatlarsa duzeltilecek dosya bu.
Her secici bir LISTE: arayuz degisince hepsi birden kirilmasin.
"""
from __future__ import annotations

from handlers import ortak

ADRES = "https://claude.ai/new"

# Yazma kutusu. Claude bir contenteditable div kullanir.
KUTU = (
    'div[contenteditable="true"][translate="no"]',
    'div.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"]',
    'textarea[placeholder*="Claude" i]',
)

GONDER = (
    'button[aria-label="Send message"]',
    'button[aria-label*="Send" i]',
    'button[type="submit"]:has(svg)',
)

# Asistan mesajlari.
MESAJ = (
    'div[data-testid="assistant-message"]',
    "div.font-claude-message",
    'div[data-is-streaming="false"] div.font-claude-response',
    'div[class*="font-claude"]',
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
