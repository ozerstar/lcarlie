# -*- coding: utf-8 -*-
"""TARAYICI WORKER (PC-1, Windows) — kuyruktaki isi Chrome'da yapar.

    sunucu kuyrugu  --SSH-->  bu worker  -->  Chrome (ayri profil)
                                  |              ChatGPT / Claude
                                  +--SSH-->  sonuc sunucuya

🔴 BU MAKINE DISARIYA ACILMAZ. Port yok, tunel yok, gelen baglanti yok.
   Tek yon var: buradan sunucuya SSH. Sunucudaki anahtar ZORUNLU KOMUT
   ile bagli, yani bu worker'in anahtari kabuk vermez.

🔴 SIFRE VE OTURUM BILGISI KODA YAZILMAZ. ChatGPT ve Claude'a BIR KEZ
   ELLE giris yapilir; oturum Chrome profilinde durur
   (`chrome-profile/`). Worker o profile BAGLANIR, kimlik bilgisi
   gormez, saklamaz, tasimaz.

🔴 SYSTEM OLARAK KOSAMAZ. Windows servisi (session 0) gorunur bir
   masaustu oturumuna sahip degildir; oturum acmis bir kullanicinin
   Chrome profili orada kullanilamaz. Bu yuzden Task Scheduler gorevi
   "oturum acildiginda" ve "yalnizca kullanici oturum acmissa" kosar.
   (Mevcut "Jarvis Metrik" gorevi SYSTEM'dir cunku o yalniz SSH ile
   olcum iter; ikisi AYRI gorev, AYRI anahtar, AYRI gerekce.)

🔴 TEK SEFERDE TEK IS. Hesap kisitlarina takilmamak icin isler arasinda
   10-30 sn rastgele beklenir.

🔴 CAPTCHA ASILMAYA CALISILMAZ. Giris/dogrulama gorulurse is DURUR,
   sunucuya INSAN_GEREKLI yazilir ve ekran goruntusu yuklenir.
"""
from __future__ import annotations

import os
import re
import random
import tempfile
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import handlers                                                  # noqa: E402
from hatalar import HandlerHatasi, InsanGerekli                  # noqa: E402
from kapi import Kapi, KapiHatasi, ortamdan                      # noqa: E402

YOKLAMA_S = 15                 # kuyrugu kac saniyede bir yokla (sartname)
NABIZ_S = 60                   # nabiz araligi (sartname)
ISLER_ARASI_EN_AZ_S = 10       # hesap kisitlarina takilmamak icin
ISLER_ARASI_EN_COK_S = 30
EKRAN_SAKLAMA_GUN = 7          # ekran goruntuleri 7 gun sonra silinir

CDP_PORT = int(os.environ.get("TARAYICI_CDP_PORT", "9222"))
GUNLUK = KOK / "worker.log"
EKRAN_DIZIN = KOK / "ekran"
EN_COK_GUNLUK_BAYT = 4 * 1024 * 1024


def say(mesaj: str) -> None:
    """Gunluge yazar. Windows konsolu cp1254 olabilir; dosya UTF-8."""
    satir = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mesaj)
    try:
        if GUNLUK.exists() and GUNLUK.stat().st_size > EN_COK_GUNLUK_BAYT:
            yedek = GUNLUK.with_suffix(".log.1")
            yedek.unlink(missing_ok=True)
            GUNLUK.rename(yedek)
        with GUNLUK.open("a", encoding="utf-8") as d:
            d.write(satir + "\n")
    except OSError:
        pass
    try:
        print(satir, flush=True)
    except (UnicodeEncodeError, OSError):
        pass


# --------------------------------------------------------------------------
# Chrome
# --------------------------------------------------------------------------
def chrome_yolu() -> Path | None:
    """Chrome'u otomatik bulur.

    🔴 SABIT YOL YAZILMAZ. Bu makinede Chrome
       `C:\\Program Files (x86)\\...` altinda (olculdu 16.10.2026);
       sartnamede yazan `C:\\Program Files\\...` yolu YOKTU. Sabit yol
       yazmak, kurulumun hangi mimaride oldugunu varsaymaktir.
    """
    elle = os.environ.get("TARAYICI_CHROME")
    if elle and Path(elle).is_file():
        return Path(elle)
    adaylar = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome"
        / "Application" / "chrome.exe",
    ]
    for aday in adaylar:
        if aday.is_file():
            return aday
    return None


def tarayiciya_baglan(playwright):
    """Acik Chrome'a CDP ile baglanir.

    Chrome'u worker BASLATMAZ: `start-chrome.ps1` baslatir. Sebebi
    olculdu -- worker Chrome'u her kosuda baslatsaydi, elle acilmis bir
    oturumla ayni profili iki surec kullanmaya calisir ve profil
    kilitlenirdi ("profile is already in use").
    """
    try:
        tarayici = playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:%d" % CDP_PORT, timeout=20000)
    except Exception as hata:                              # noqa: BLE001
        yol = chrome_yolu()
        raise KapiHatasi(
            "Chrome'a baglanilamadi (127.0.0.1:%d). start-chrome.ps1 "
            "calisiyor mu? Chrome: %s. Sebep: %s"
            % (CDP_PORT, yol or "BULUNAMADI", str(hata)[:200])) from None
    if not tarayici.contexts:
        raise KapiHatasi("Chrome baglandi ama hic baglam yok")
    return tarayici


# --------------------------------------------------------------------------
# Ekran goruntusu bakimi
# --------------------------------------------------------------------------
def ekranlari_temizle() -> int:
    """7 gunden eski ekran goruntulerini siler."""
    if not EKRAN_DIZIN.is_dir():
        return 0
    esik = datetime.now(timezone.utc) - timedelta(days=EKRAN_SAKLAMA_GUN)
    silinen = 0
    for p in EKRAN_DIZIN.glob("*.png"):
        try:
            if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) < esik:
                p.unlink()
                silinen += 1
        except OSError:
            continue
    return silinen


def ekrani_sakla(is_id: int, ham: bytes | None) -> None:
    """Ekran goruntusunun yerel kopyasi. Sunucudaki kopya ayri."""
    if not ham:
        return
    try:
        EKRAN_DIZIN.mkdir(parents=True, exist_ok=True)
        yol = EKRAN_DIZIN / ("is-%d-%s.png"
                             % (is_id, datetime.now().strftime("%Y%m%dT%H%M%S")))
        yol.write_bytes(ham)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Bir is
# --------------------------------------------------------------------------
def _oturum_anahtari(hedef: str) -> str:
    """Her sağlayıcı için tek sekme/sohbet tut; handler değişince sekme açma."""
    if hedef.startswith("chatgpt_"):
        return "chatgpt"
    if hedef.startswith("claude_"):
        return "claude"
    return hedef


def _mevcut_sohbeti_bul(baglam, anahtar: str):
    alan = "chatgpt.com" if anahtar == "chatgpt" else "claude.ai" if anahtar == "claude" else None
    if not alan:
        return None
    adaylar = [p for p in baglam.pages if not p.is_closed() and alan in (p.url or "")]
    sohbetler = [p for p in adaylar if ("/c/" in p.url if anahtar == "chatgpt" else "/chat/" in p.url)]
    if anahtar == "chatgpt":
        # Same Work conversation across worker restarts; never guess by tab order.
        kayit = KOK / "state" / "chatgpt-last-url.txt"
        try:
            url = kayit.read_text(encoding="utf-8").strip()
        except OSError:
            url = ""
        if re.fullmatch(r"https://chatgpt\.com/c/[A-Za-z0-9-]+/?", url):
            tam_eslesme = next((p for p in sohbetler if (p.url or "").rstrip("/") == url.rstrip("/")), None)
            if tam_eslesme is not None:
                return tam_eslesme
    return (sohbetler or adaylar or [None])[-1]


def _chatgpt_sohbet_kaydet(sayfa, anahtar: str) -> None:
    """Son ChatGPT konuşmasını yeniden başlatmada sürdürebilmek için kaydet."""
    if anahtar != "chatgpt" or sayfa is None or sayfa.is_closed():
        return
    url = sayfa.url or ""
    if not re.fullmatch(r"https://chatgpt\.com/c/[A-Za-z0-9-]+/?", url):
        return
    hedef = KOK / "state" / "chatgpt-last-url.txt"
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = hedef.with_suffix(".tmp")
        gecici.write_text(url, encoding="utf-8")
        gecici.replace(hedef)
    except OSError as e:
        say("ChatGPT sohbet adresi kaydedilemedi: %s" % e)

def isi_yap(playwright, kapi: Kapi, is_: dict, sayfa_havuzu: dict | None = None) -> str:
    """Tek isi bastan sona yurutur. Sonuc durumunu dondurur."""
    from handlers import ortak

    is_id = int(is_["is_id"])
    jeton = is_["kira_jetonu"]
    hedef = is_["hedef"]
    say("is %d basladi (%s, deneme %s)" % (is_id, hedef, is_.get("deneme")))

    sayfa = None
    goruntusu: bytes | None = None
    sayfa_havuzu = sayfa_havuzu if sayfa_havuzu is not None else {}
    oturum = _oturum_anahtari(hedef)
    try:
        modul = handlers.getir(hedef)
        onbellek = sayfa_havuzu.get(oturum)
        if onbellek:
            tarayici, sayfa = onbellek
            if sayfa.is_closed():
                sayfa = None
        if sayfa is None:
            tarayici = tarayiciya_baglan(playwright)
            baglam = tarayici.contexts[0]
            sayfa = _mevcut_sohbeti_bul(baglam, oturum)
            if sayfa is None:
                sayfa = baglam.new_page()
            sayfa_havuzu[oturum] = (tarayici, sayfa)
        # Girdi dosyalari kullanicinin Chrome oturumuna aktarilmak uzere
        # yalnizca bu is boyunca gecici dosyalara yazilir.
        with tempfile.TemporaryDirectory(prefix="jarvis-browser-job-") as gecici:
            yerel_girdiler = []
            for sira, _ in enumerate(is_.get("girdi_dosyalari") or []):
                ad, ham = kapi.girdi(is_id, sira)
                yol = Path(gecici) / Path(ad).name
                yol.write_bytes(ham)
                yerel_girdiler.append(str(yol))
            is_["local_input_files"] = yerel_girdiler
            sonuc = modul.calistir(sayfa, is_)
        goruntusu = ortak.ekran(sayfa)
        ekrani_sakla(is_id, goruntusu)

        metin = (sonuc.get("metin") or "").strip()
        dosyalar = sonuc.get("dosyalar") or []
        if not metin and not dosyalar:
            # Bos sonuc basari sayilmaz; sunucudaki CHECK de reddeder.
            raise HandlerHatasi("handler bos sonuc dondurdu")

        kapi.bitir(is_id, jeton, metin, dosyalar, goruntusu)
        say("is %d BITTI (%d karakter, %d dosya)"
            % (is_id, len(metin), len(dosyalar)))
        return "BITTI"

    except InsanGerekli as hata:
        # 🔴 TERMINAL. Yeniden denenmez; dogrulama asilmaya calisilmaz.
        if sayfa is not None and goruntusu is None:
            goruntusu = ortak.ekran(sayfa)
            ekrani_sakla(is_id, goruntusu)
        say("is %d INSAN_GEREKLI: %s" % (is_id, hata))
        try:
            kapi.insan(is_id, jeton, str(hata), goruntusu)
        except KapiHatasi as k:
            say("  insan durumu YAZILAMADI: %s" % k)
        return "INSAN_GEREKLI"

    except Exception as hata:                              # noqa: BLE001
        if sayfa is not None and goruntusu is None:
            goruntusu = ortak.ekran(sayfa)
            ekrani_sakla(is_id, goruntusu)
        sebep = "%s: %s" % (type(hata).__name__, str(hata)[:400])
        say("is %d HATA: %s" % (is_id, sebep))
        say(traceback.format_exc(limit=4))
        try:
            kapi.hata(is_id, jeton, sebep, goruntusu)
        except KapiHatasi as k:
            say("  hata durumu YAZILAMADI: %s" % k)
        return "HATA"

    finally:
        # Hedef sekmesi ve konuşma açık kalır; yeniden başlatmada GPT adresini sürdür.
        _chatgpt_sohbet_kaydet(sayfa, oturum)


# --------------------------------------------------------------------------
# Dongu
# --------------------------------------------------------------------------
def nabiz_ayrintisi(son_is: str | None, chrome_acik: bool) -> dict:
    return {"chrome": "acik" if chrome_acik else "KAPALI",
            "son_is": son_is or "-",
            "pid": os.getpid(),
            "surum": "1"}


def main() -> int:
    worker = os.environ.get("TARAYICI_WORKER_ADI", "pc1-chrome")
    try:
        kapi = ortamdan()
    except KapiHatasi as hata:
        say("KURULUM EKSIK: %s" % hata)
        return 2

    from playwright.sync_api import sync_playwright

    say("worker acildi (%s), Chrome: %s" % (worker, chrome_yolu() or "BULUNAMADI"))
    silinen = ekranlari_temizle()
    if silinen:
        say("%d eski ekran goruntusu silindi" % silinen)

    son_nabiz = 0.0
    son_temizlik = time.time()
    son_is: str | None = None
    sayfa_havuzu: dict = {}

    with sync_playwright() as playwright:
        while True:
            # --- nabiz ---
            if time.time() - son_nabiz >= NABIZ_S:
                chrome_acik = True
                try:
                    tarayiciya_baglan(playwright)
                except KapiHatasi:
                    chrome_acik = False
                try:
                    kapi.nabiz(worker, nabiz_ayrintisi(son_is, chrome_acik))
                    son_nabiz = time.time()
                except KapiHatasi as hata:
                    # Nabiz atilamadiysa sunucu bunu BAYAT olarak gorur ve
                    # panelde "worker'dan haber eski" der. Dogru davranis.
                    say("nabiz atilamadi: %s" % hata)
                    son_nabiz = time.time()

            # --- gunluk bakim ---
            if time.time() - son_temizlik > 6 * 3600:
                ekranlari_temizle()
                son_temizlik = time.time()

            # --- is al ---
            try:
                is_ = kapi.al(worker)
            except KapiHatasi as hata:
                say("kuyruk okunamadi: %s" % hata)
                time.sleep(YOKLAMA_S)
                continue

            if not is_:
                time.sleep(YOKLAMA_S)
                continue

            son_is = isi_yap(playwright, kapi, is_, sayfa_havuzu)

            # 🔴 TEK SEFERDE TEK IS + isler arasi rastgele bekleme.
            bekle = random.uniform(ISLER_ARASI_EN_AZ_S, ISLER_ARASI_EN_COK_S)
            say("sonraki is icin %.0f sn bekleniyor" % bekle)
            time.sleep(bekle)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say("worker elle durduruldu")
        raise SystemExit(0) from None
