# -*- coding: utf-8 -*-
"""Handler'larin paylastigi ARAYUZ adimlari.

🔴 BU DOSYA VE KARDESLERI, ARAYUZE DOKUNAN TEK YERDIR. CSS secici,
   metin arama, bekleme adimi -- hepsi `handlers/` altinda durur.
   `worker.py` hicbir secici bilmez; ChatGPT'nin gonder dugmesi yarin
   degisirse duzeltilecek yer BURADIR, baska hicbir dosya degil.

🔴 BU KATMAN KIRILGANDIR VE BU BILINEREK YAZILDI. ChatGPT ve Claude
   web arayuzu haber vermeden degisir; ayrica bu arayuzleri
   otomatiklestirmek kullanim sartlarina aykiri OLABILIR. Bu yuzden her
   hedefin bir YEDEK yolu var (bkz. ../yedek.py): secici kirildiginda
   is kaybolmaz, API/ComfyUI/Higgsfield yoluna duser.
"""
from __future__ import annotations

import re
import time

from hatalar import HandlerHatasi, InsanGerekli, ZamanAsimi

# --------------------------------------------------------------------------
# GIRIS / BOT DOGRULAMASI BELIRTILERI
#
# Biri goruldugunde is DURUR ve INSAN_GEREKLI yazilir. Asmaya calisilmaz.
# --------------------------------------------------------------------------
GIRIS_URL_DESENLERI = (
    "/auth/login", "/auth/signin", "accounts.google.com", "auth0.com",
    "/login", "/signin", "challenges.cloudflare.com",
)

GIRIS_METINLERI = (
    "verify you are human", "i am not a robot", "are you a robot",
    "checking if the site connection is secure", "just a moment",
    "log in", "sign in", "oturum ac", "giris yap",
    "welcome back", "continue with google", "enter your email",
    "unusual activity", "olagan disi", "hesabiniz askiya",
    "account has been suspended", "you've reached your limit",
    "usage limit", "limitinize ulastiniz", "rate limit",
)

GIRIS_SECICILERI = (
    "#challenge-running",
    'iframe[src*="challenges.cloudflare.com"]',
    'iframe[title*="recaptcha" i]',
    'iframe[title*="hCaptcha" i]',
)


def insan_gerekli_mi(page) -> str | None:
    """Giris/dogrulama belirtisi varsa SEBEBI dondurur, yoksa None.

    🔴 "log in" gibi genel bir ifade sayfanin herhangi bir yerinde
       gecebilir (altbilgide "Log in" baglantisi gibi). Bu yuzden metin
       taramasi YALNIZ sayfanin govdesi kisaysa (giris sayfalari kisadir)
       ya da secici/URL belirtisi varsa hukum verir. Aksi halde her
       calisan sohbet "giris istendi" sayilirdi.
    """
    try:
        url = (page.url or "").lower()
    except Exception:                                  # noqa: BLE001
        url = ""
    for desen in GIRIS_URL_DESENLERI:
        if desen in url:
            return "giris/dogrulama sayfasina yonlendirildi: %s" % url[:160]

    for secici in GIRIS_SECICILERI:
        try:
            if page.locator(secici).count() > 0:
                return "bot dogrulamasi goruldu (%s)" % secici
        except Exception:                              # noqa: BLE001
            continue

    try:
        govde = (page.locator("body").inner_text(timeout=5000) or "")
    except Exception:                                  # noqa: BLE001
        return None
    dusuk = govde.lower()
    # Kisa govde = muhtemelen giris/engel sayfasi. Uzun govde = calisan uygulama.
    if len(govde.strip()) < 1200:
        for metin in GIRIS_METINLERI:
            if metin in dusuk:
                return "sayfa %r diyor (govde %d karakter)" % (metin, len(govde))
    # Kota/askiya alma uyarilari govde uzun olsa da hukum verir.
    for metin in ("unusual activity", "account has been suspended",
                  "hesabiniz askiya", "usage limit", "limitinize ulastiniz"):
        if metin in dusuk:
            return "hesap/kota uyarisi: %r" % metin
    return None


def kapiyi_gec(page) -> None:
    """Giris/dogrulama varsa isi DURDURUR."""
    sebep = insan_gerekli_mi(page)
    if sebep:
        raise InsanGerekli(sebep)


# --------------------------------------------------------------------------
# YAZMA
# --------------------------------------------------------------------------
def ilk_bulunan(page, seciciler: tuple[str, ...], zaman_asimi_ms: int = 20000):
    """Verilen secicilerden GORUNUR olan ilkini dondurur.

    Tek secici yerine liste: arayuz degistiginde hepsi birden kirilmaz.
    Hicbiri bulunmazsa HANGILERININ denendigi hataya yazilir -- "bulunamadi"
    demek, hangi secicinin bayatladigini saklamak olurdu.
    """
    bitis = time.time() + zaman_asimi_ms / 1000.0
    while time.time() < bitis:
        for secici in seciciler:
            try:
                loc = page.locator(secici).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:                          # noqa: BLE001
                continue
        page.wait_for_timeout(400)
    raise HandlerHatasi("arayuz ogesi bulunamadi; denenen seciciler: %s"
                        % " | ".join(seciciler))


def istemi_yaz(page, kutu, istem: str) -> None:
    """İstemi yazar. Satir sonu GONDERMEZ (Enter mesaji yollar).

    🔴 Cok satirli istemde `fill()`/`type()` ile ham satir sonu yazmak,
       ChatGPT ve Claude'da mesaji YARIM gonderir: ilk Enter gonder
       dugmesi gibi davranir. Satir sonlari bosluga cevrilir ve
       paragraflar iki boslukla ayrilir.
    """
    tek_satir = re.sub(r"[\r\n]+", "  ", istem).strip()
    kutu.click()
    page.wait_for_timeout(200)
    try:
        kutu.fill("")
    except Exception:                                  # noqa: BLE001
        pass
    kutu.type(tek_satir, delay=8)
    page.wait_for_timeout(300)


def gonder(page, kutu, gonder_seciciler: tuple[str, ...]) -> None:
    """Gonder dugmesine basar; yoksa Ctrl+Enter ile gonderir."""
    try:
        dugme = ilk_bulunan(page, gonder_seciciler, zaman_asimi_ms=6000)
        dugme.click()
        return
    except HandlerHatasi:
        pass
    # Dugme bulunamadiysa klavye: Enter bu iki arayuzde de gonderir.
    kutu.press("Enter")


# --------------------------------------------------------------------------
# YANITI BEKLEME
# --------------------------------------------------------------------------
def yanit_bekle(page, mesaj_seciciler: tuple[str, ...],
                baslangic_adedi: int, tavan_s: float,
                durulma_s: float = 2.5) -> str:
    """Yeni bir yanit gelip DURULANA kadar bekler, metnini dondurur.

    🔴 "Yanit geldi" ile "yanit bitti" ayri seylerdir. Akarak yazilan bir
       cevabin ilk harfini gorup almak, yarim metin kaydetmek olurdu.
       Bu yuzden metin `durulma_s` boyunca DEGISMEYENE kadar beklenir.

    🔴 Tavan dolarsa ZamanAsimi -- eldeki yarim metin "sonuc" sayilmaz.
    """
    bitis = time.time() + tavan_s
    son_metin = ""
    son_degisim = None

    while time.time() < bitis:
        # Giris/dogrulama yanit beklerken de cikabilir (oturum dustu).
        sebep = insan_gerekli_mi(page)
        if sebep:
            raise InsanGerekli(sebep)

        metin = ""
        for secici in mesaj_seciciler:
            try:
                loc = page.locator(secici)
                adet = loc.count()
                if adet > baslangic_adedi:
                    metin = (loc.nth(adet - 1).inner_text(timeout=5000) or "").strip()
                    if metin:
                        break
            except Exception:                          # noqa: BLE001
                continue

        if metin and metin == son_metin:
            if son_degisim and (time.time() - son_degisim) >= durulma_s:
                return metin
        elif metin:
            son_metin = metin
            son_degisim = time.time()

        page.wait_for_timeout(700)

    if son_metin:
        raise ZamanAsimi(
            "yanit %.0f sn icinde durulmadi (%d karakter geldi, yarim sayildi)"
            % (tavan_s, len(son_metin)))
    raise ZamanAsimi("yanit %.0f sn icinde hic gelmedi" % tavan_s)


def mesaj_adedi(page, mesaj_seciciler: tuple[str, ...]) -> int:
    """Gondermeden ONCEki yanit adedi. Yeni yaniti bundan ayirt ederiz."""
    for secici in mesaj_seciciler:
        try:
            adet = page.locator(secici).count()
            if adet:
                return adet
        except Exception:                              # noqa: BLE001
            continue
    return 0


def ekran(page) -> bytes | None:
    """Her iste bir ekran goruntusu. Hata ayiklamanin tek gorsel kaniti."""
    try:
        return page.screenshot(type="png", full_page=False)
    except Exception:                                  # noqa: BLE001
        return None
