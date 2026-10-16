# -*- coding: utf-8 -*-
"""chatgpt_image — ChatGPT web arayuzunde gorsel uretir ve indirir.

ARAYUZE DOKUNAN TEK YER BURASI.

🔴 GORSEL, TARAYICININ KENDI OTURUMUYLA INDIRILIR. `page.request.get`
   sayfanin cerezlerini tasir; `urllib` ile indirmek 403 doner cunku
   gorsel URL'leri oturuma baglidir. Ayrica Chrome'un indirme klasorune
   dusurmek yerine BELLEGE alinir: diskte dolasan dosya aramak, hangi
   indirmenin hangi ise ait oldugunu tahmin etmek demekti.

🔴 SAYFA INDIRME DUGMESI KULLANILMAZ. Indirme olayini yakalamak,
   Chrome'un indirme dizinine ve adlandirmasina bagimlilik yaratir.
"""
from __future__ import annotations

import re

from handlers import ortak
from hatalar import HandlerHatasi, ZamanAsimi

ADRES = "https://chatgpt.com/"

KUTU = (
    "#prompt-textarea",
    'div[contenteditable="true"]#prompt-textarea',
    'div[contenteditable="true"]',
)

GONDER = (
    'button[data-testid="send-button"]',
    'button[aria-label*="Send prompt" i]',
)

MESAJ = (
    'div[data-message-author-role="assistant"]',
    "div.agent-turn",
)

# Uretilen gorselin kendisi. Avatar/simge gorsellerini DISLAMAK icin
# kaynak adresi desenle suzulur.
GORSEL = (
    'div[data-message-author-role="assistant"] img[src*="oaiusercontent"]',
    'div[data-message-author-role="assistant"] img[src*="files.oaiusercontent"]',
    'div[data-message-author-role="assistant"] img[alt*="Generated" i]',
    'div[data-message-author-role="assistant"] img[src^="blob:"]',
)

# Avatar/ikon kaynaklari: bunlar uretilmis gorsel DEGIL.
GORSEL_DISLANAN = re.compile(
    r"(avatar|profile|favicon|logo|sprite|\.svg(\?|$)|data:image/svg)", re.I)

ZAMAN_ASIMI_S = 300.0          # gorsel: 5 dk (sartname)
EN_AZ_GORSEL_BAYT = 8 * 1024   # 8 KB altindaki sey uretilmis gorsel degildir


def _gorsel_adresleri(page) -> list[str]:
    adresler: list[str] = []
    for secici in GORSEL:
        try:
            loc = page.locator(secici)
            for i in range(loc.count()):
                src = loc.nth(i).get_attribute("src") or ""
                if src and not GORSEL_DISLANAN.search(src) and src not in adresler:
                    adresler.append(src)
        except Exception:                              # noqa: BLE001
            continue
    return adresler


def _indir(page, adres: str) -> bytes | None:
    """Gorseli sayfanin oturumuyla indirir."""
    if adres.startswith("blob:"):
        # blob: adresi ag uzerinden alinamaz; sayfa icinde base64'e cevrilir.
        try:
            veri = page.evaluate(
                """async (url) => {
                    const r = await fetch(url);
                    const b = await r.blob();
                    const buf = await b.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let s = '';
                    for (let i = 0; i < bytes.length; i++) {
                        s += String.fromCharCode(bytes[i]);
                    }
                    return btoa(s);
                }""", adres)
        except Exception:                              # noqa: BLE001
            return None
        if not veri:
            return None
        import base64
        try:
            return base64.b64decode(veri)
        except Exception:                              # noqa: BLE001
            return None
    try:
        yanit = page.request.get(adres, timeout=90000)
        if not yanit.ok:
            return None
        return yanit.body()
    except Exception:                                  # noqa: BLE001
        return None


def calistir(page, is_: dict, zaman_asimi_s: float | None = None) -> dict:
    import time
    tavan = float(zaman_asimi_s or ZAMAN_ASIMI_S)
    bitis = time.time() + tavan

    page.goto(ADRES, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    ortak.kapiyi_gec(page)

    kutu = ortak.ilk_bulunan(page, KUTU)
    onceki = ortak.mesaj_adedi(page, MESAJ)
    onceki_gorsel = set(_gorsel_adresleri(page))

    ortak.istemi_yaz(page, kutu, is_["istem"])
    ortak.gonder(page, kutu, GONDER)

    # Gorsel uretimi metinden cok daha uzun surer; mesaj sayisi artsa bile
    # gorsel henuz gelmemis olabilir. Bu yuzden METNI degil GORSELI bekleriz.
    yeni: list[str] = []
    while time.time() < bitis:
        sebep = ortak.insan_gerekli_mi(page)
        if sebep:
            from hatalar import InsanGerekli
            raise InsanGerekli(sebep)
        yeni = [a for a in _gorsel_adresleri(page) if a not in onceki_gorsel]
        if yeni:
            # Gorsel DOM'a girdi; akmasi bitsin diye kisa bir durulma.
            page.wait_for_timeout(2500)
            yeni = [a for a in _gorsel_adresleri(page) if a not in onceki_gorsel]
            break
        page.wait_for_timeout(1500)

    if not yeni:
        # 🔴 Metin geldi ama gorsel gelmediyse bu BASARI DEGILDIR.
        #    ChatGPT "uretemiyorum" ya da "politikaya aykiri" diye metin
        #    donmus olabilir; o metin hataya yazilir ki sebep gorunsun.
        try:
            aciklama = ortak.yanit_bekle(page, MESAJ, onceki, 10.0, durulma_s=1.0)
        except (ZamanAsimi, HandlerHatasi):
            aciklama = ""
        raise HandlerHatasi(
            "gorsel uretilmedi (%.0f sn beklendi)%s"
            % (tavan, (" — arayuzun yanitı: " + aciklama[:300]) if aciklama else ""))

    dosyalar: list[tuple[str, bytes]] = []
    for sira, adres in enumerate(yeni[:4], start=1):
        ham = _indir(page, adres)
        if not ham or len(ham) < EN_AZ_GORSEL_BAYT:
            continue
        dosyalar.append(("gorsel-%d.png" % sira, ham))

    if not dosyalar:
        raise HandlerHatasi(
            "gorsel DOM'da goruldu (%d adet) ama indirilemedi ya da "
            "%d bayttan kucuk geldi" % (len(yeni), EN_AZ_GORSEL_BAYT))

    # Yanindaki metin varsa alinir, ama yokluğu hata DEGILDIR.
    try:
        metin = ortak.yanit_bekle(page, MESAJ, onceki, 15.0, durulma_s=1.0)
    except (ZamanAsimi, HandlerHatasi):
        metin = ""
    return {"metin": metin, "dosyalar": dosyalar}
