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


YENI_SOHBET = "[YENI_SOHBET]"   # blog hattı: uzun metin, ayrı sekme + yeni sohbet
UZUN_ZAMAN_ASIMI_S = 1500.0     # 1.300+ kelimelik yazı/çeviri; kira 1800 sn (tarayici-kapi)
DURDUR = ('button[data-testid="stop-button"]', 'button[aria-label*="Stop" i]',
          'button[aria-label*="Durdur" i]')


def calistir(page, is_: dict, zaman_asimi_s: float | None = None) -> dict:
    istem = is_["istem"]
    if not istem.startswith(YENI_SOHBET):
        return _uret(page, is_, float(zaman_asimi_s or ZAMAN_ASIMI_S), uzun=False)
    # 25.11.2026: blog yazısı/çevirisi Gemini yerine burada üretilir. Görsel
    # işlerinin sürdürdüğü sohbet kirlenmesin diye ayrı sekmede YENİ sohbet
    # açılır ve iş bitince sekme kapatılır.
    yeni = page.context.new_page()
    try:
        yeni.goto(ADRES, wait_until="domcontentloaded", timeout=60000)
        return _uret(yeni, dict(is_, istem=istem[len(YENI_SOHBET):].strip()),
                     float(zaman_asimi_s or UZUN_ZAMAN_ASIMI_S), uzun=True)
    finally:
        try:
            yeni.close()
        except Exception:  # noqa: BLE001
            pass


def _uret(page, is_: dict, tavan: float, uzun: bool) -> dict:

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
        if yeni_yanit and metin == son_metin and time.monotonic() - son_degisim >= (10 if uzun else 3):
            # Uzun işte düşünme/arama sırasında metin 10 sn'den uzun durabilir:
            # durdur düğmesi görünürken yanıt bitmiş sayılmaz.
            if not uzun or not _uretiyor_mu(page):
                return {"metin": (_son_kod_blogu(page) or metin) if uzun else metin, "dosyalar": []}
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
                metin = (loc.last.inner_text(timeout=5000) or "").strip()
                if metin:
                    return metin
        except Exception:  # noqa: BLE001 - fall through to the next known message selector
            continue

    # The current ChatGPT Work UI no longer exposes these message selectors in
    # some layouts. Read the rendered conversation text as a fallback so Jarvis
    # can still capture a visible GPT answer without interacting with the UI.
    try:
        govde = (page.locator("body").inner_text(timeout=5000) or "").strip()
    except Exception:  # noqa: BLE001
        return ""

    baslangiclar = ("ChatGPT dedi:", "ChatGPT said:", "ChatGPT:")
    bas = max((govde.rfind(x) for x in baslangiclar), default=-1)
    if bas < 0:
        return ""
    metin = govde[bas:]
    for bitis in ("\nDüzenle\n", "\nSon yanıt\n", "\nKopyala\n", "\nPaylaş\n"):
        konum = metin.find(bitis)
        if konum >= 0:
            metin = metin[:konum]
    return metin.split(":", 1)[-1].strip()


def _uretiyor_mu(page) -> bool:
    for secici in DURDUR:
        try:
            loc = page.locator(secici)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _son_kod_blogu(page) -> str:
    """Son asistan mesajındaki en uzun kod bloğu (JSON/HTML işlenmeden, ham)."""
    try:
        mesaj = page.locator(ASISTAN_MESAJI[0]).last
        bloklar = mesaj.locator("pre code")
        if not bloklar.count():
            bloklar = mesaj.locator("pre")
        metinler = [(bloklar.nth(i).inner_text(timeout=5000) or "").strip() for i in range(bloklar.count())]
        return max(metinler, key=len) if metinler else ""
    except Exception:  # noqa: BLE001
        return ""
