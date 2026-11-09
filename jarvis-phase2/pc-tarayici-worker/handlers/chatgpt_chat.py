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
ASISTAN_MESAJI = MESAJ[:2]

ZAMAN_ASIMI_S = 360.0          # yaratıcı istem üretimi uzun sürebilir; 420 sn iş kirası içinde kalır


def calistir(page, is_: dict, zaman_asimi_s: float | None = None) -> dict:
    tavan = float(zaman_asimi_s or ZAMAN_ASIMI_S)

    # Aynı tarayıcı sekmesini ve sohbeti sürdür; yalnız yanlış/boş sayfadaysa yönlen.
    if "chatgpt.com" not in (page.url or ""):
        page.goto(ADRES, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    ortak.kapiyi_gec(page)

    kutu = ortak.ilk_bulunan(page, KUTU)
    onceki = ortak.mesaj_adedi(page, MESAJ)
    onceki_metin = _son_asistan_metin(page)

    ortak.istemi_yaz(page, kutu, is_["istem"])
    ortak.gonder(page, kutu, GONDER)

    # A conversation can virtualize/reuse assistant DOM nodes. Detect the new
    # reply by both message count and last assistant text, then require it to settle.
    import time
    bitis = time.monotonic() + tavan
    son_metin = ""
    son_degisim = 0.0
    while time.monotonic() < bitis:
        sebep = ortak.insan_gerekli_mi(page)
        if sebep:
            from hatalar import InsanGerekli
            raise InsanGerekli(sebep)
        adet = ortak.mesaj_adedi(page, MESAJ)
        metin = _son_asistan_metin(page)
        yeni_yanit = metin and (adet > onceki or metin != onceki_metin)
        if yeni_yanit and metin == son_metin and time.monotonic() - son_degisim >= 3:
            return {"metin": metin, "dosyalar": []}
        if yeni_yanit and metin != son_metin:
            son_metin = metin
            son_degisim = time.monotonic()
        page.wait_for_timeout(700)
    if son_metin:
        raise TimeoutError("GPT yanıtı süre içinde durulmadı; kısmi yanıt teslim edilmedi")
    raise TimeoutError("GPT Work yanıtı süre içinde alınamadı")


def _son_asistan_metin(page) -> str:
    for secici in ASISTAN_MESAJI:
        try:
            loc = page.locator(secici)
            if loc.count():
                return (loc.last.inner_text(timeout=5000) or "").strip()
        except Exception:  # noqa: BLE001 - fall through to the next known message selector
            continue
    return ""
