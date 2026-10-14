#!/usr/bin/env python3
"""L'CARLIE — BASIN TARAMASI (SearXNG + sendikasyon)

NEDEN AYRI BIR BETIK
itibar-tara.py grounded arama (Gemini) kullaniyor ve o yalnizca ALAN ADI
donduruyor: "ankarakenthaber.com". Tek tek haberleri saymiyor. Sahip
29.09.2026: *"Tum haberleri istiyorum ister ayni olsun ister farkli."*

OLCULEN GERCEK: tek basin bulteni COK SITEYE dagitiliyor. "Ege'nin
maviliklerinde baslayan siradisi bir marka yolculugu" basligi tirnak icinde
aratildiginda 9 ayri sitede cikti. "20+ haber" boyle olusuyor: birkac
bulten, cok site.

YONTEM (iki asama)
  1. KESIF   — marka/kisi varyantlariyla ara, haber sitesi gorunumlu
               sonuclari topla.
  2. SENDIKASYON — bulunan her BASLIGI tirnak icinde tekrar arat; ayni
               metni basan tum siteleri cikar. Ayni haber farkli sitede
               AYRI kayittir; sahip boyle istedi.

🔴 GOOGLE DOGRUDAN SORGULANMAZ. Alti ayri yol bot tespitine takilmisti
(bkz. TikTok ms_token notu). Burada sunucudaki SearXNG kullaniliyor:
google cse + bing + duckduckgo motorlarini birlikte sorguluyor ve bize
JSON donduruyor.

🔴 MEVZUAT DENETIMI ITIBAR-TARA'DAN ODUNC ALINIR. Kelime bazli degil,
Turkce NER ile anlam bazli (Sifa Koprusu Forumu ornegi). Yeniden
yazilmaz -- ayni kapi iki yerde iki turlu davranmasin.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KOK = "/opt/lcarlie/jarvis-phase2"
sys.path.insert(0, KOK)
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

SEARX = os.environ.get("SEARX_URL", "http://127.0.0.1:8888/search")

# --- itibar-tara'dan varyant uretimi ve mevzuat kapisi -----------------------
_spec = importlib.util.spec_from_file_location(
    "itibar", f"{KOK}/scripts/itibar-tara.py")
_it = importlib.util.module_from_spec(_spec)
_argv = sys.argv
sys.argv = ["itibar-tara"]
_spec.loader.exec_module(_it)
sys.argv = _argv

MARKA = list(_it.MARKA_VARYANTLARI)
KISILER = list(_it.KISI_ADLARI)

# --- Haber olmayan alanlar ---------------------------------------------------
# 🔴 Kendi mulklerimiz ve pazaryerleri BASIN DEGILDIR. Bunlari bahis
#    saymak "20 haberimiz var" sayisini sahte sisirir.
HARIC = (
    "lcarlie.shop", "lcarlie.com.tr", "lcarlie.com",
    "instagram.com", "facebook.com", "fb.com", "tiktok.com", "x.com",
    "twitter.com", "linkedin.com", "pinterest.", "youtube.com", "youtu.be",
    "trendyol.com", "hepsiburada.com", "n11.com", "amazon.", "ciceksepeti.",
    "yandex.com", "yandex.com.tr", "google.", "wikipedia.org", "scribd.com",
    "etbis.ticaret.gov.tr", "sikayetvar.com", "eksisozluk.com",
    "gittigidiyor.com", "dolap.com", "shopier.com", "etsy.com",
)


def _haric_mi(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in HARIC)


def alan(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return "?"


# --- SearXNG -----------------------------------------------------------------
def searx(sorgu: str, dil: str = "tr-TR", sayfa: int = 1) -> list[dict]:
    """SearXNG'ye sorar. Hata durumunda BOS DONER ama sessiz kalmaz."""
    veri = urllib.parse.urlencode(
        {"q": sorgu, "format": "json", "language": dil, "pageno": sayfa}).encode()
    try:
        istek = urllib.request.Request(SEARX, data=veri)
        with urllib.request.urlopen(istek, timeout=45) as cevap:
            return json.load(cevap).get("results", []) or []
    except Exception as hata:  # noqa: BLE001
        print(f"  arama hatasi ({sorgu[:40]}): {str(hata)[:80]}", file=sys.stderr)
        return []


def bizimle_ilgili_mi(baslik: str, ozet: str) -> bool:
    """Marka adi baslikta veya ozette geciyor mu? Kisi adi TEK BASINA yetmez.

    🔴 Ad benzerligi tuzagi: "Murat Yildiz" yaygin bir ad ve alakasiz
    haberleri getiriyor (itibar-tara.py'de olculdu). Sirket baglami sart.
    """
    metin = f"{baslik} {ozet}".lower()
    sade = metin.replace("'", "").replace("’", "").replace("`", "")
    for v in MARKA:
        if v.lower().replace("'", "").replace("’", "") in sade:
            return True
    return False


# 🔴 TOHUM: dogrulanmis gercek haber basliklari ve yayin siteleri.
#    Marka sorgusu tek basina bu siteleri getirmiyor (olculdu 29.09.2026):
#    "lcarlie kozmetik" Instagram/Trendyol/Yandex donduruyor, hepsi HARIC
#    listesinde, geriye 0 aday kaliyor. Tohum bilineni garantiye alir;
#    marka sorgulari da kosmaya devam eder, yeni haber bulmayi engellemez.
TOHUM_BASLIKLAR = (
    "L'CARLIE, Dermokozmetik Pazarında Bilim ve Doğayı Yeniden Yorumluyor",
    "Şifa Köprüsü Forumun'da L'CARLİÉ Dikkat Çekti",
    "KET2026'da Lcarlie rüzgarı: Sektöre 39 ürünle dev giriş!",
    "Ege'nin maviliklerinde başlayan sıradışı bir marka yolculuğu",
    "Ege'nin Maviliğinde L'CARLIÉ: Doğallık ve Deneyimi",
)

TOHUM_SITELER = (
    "ankarakenthaber.com", "birlikhabergazetesi.com", "basinpress.com",
    "cilekhabergazetesi.com.tr", "ozelkalite.com",
    "sondakikaturkiyehaberleri.com", "haberci.tr", "mevzuhaber.com",
    "sehiralanya.com.tr", "gunebakishaber.com.tr", "akdenizguncel.com",
    "ozgunmedyaajansi.com.tr", "antalyamanset.com.tr",
)


def kesif() -> dict[str, dict]:
    """1. asama: marka varyantlari + bilinen baslik/site tohumlari."""
    bulunan: dict[str, dict] = {}

    def ekle(r: dict, terim: str, zorla: bool = False) -> None:
        url = r.get("url", "")
        if not url or _haric_mi(url) or url in bulunan:
            return
        baslik = (r.get("title") or "").strip()
        ozet = (r.get("content") or "").strip()
        if not baslik:
            return
        # zorla=True: tohum sorgusu zaten bize ait bir baslik/site soruyor.
        if not zorla and not bizimle_ilgili_mi(baslik, ozet):
            return
        bulunan[url] = {"baslik": baslik, "url": url, "site": alan(url),
                        "ozet": ozet, "terim": terim}

    sorgular = [f"{v} kozmetik" for v in MARKA[:8]]
    sorgular += [
        "L'CARLIE dermokozmetik haber",
        "LCARLIE kozmetik haber",
        "Lcarlie marka haberi",
        "Lemos Medikal kozmetik haber",
        "L'CARLIÉ basın bülteni",
        "Lcarlie dermokozmetik tanıtım",
    ]
    for s in sorgular:
        for r in searx(s):
            ekle(r, "marka")

    # 🔴 Tohum yolu da SUZGECLIDIR. Arama motoru tirnakli basligi bulamayinca
    #    bos donmez, "benzer" sonuc donderir; suzgecsiz birakilinca at yarisi
    #    ve film sitelerine kadar her sey iceri girdi (olculdu 29.09.2026).
    for b in TOHUM_BASLIKLAR:
        hedef = _sadelestir(_cekirdek_baslik(b))
        for r in searx(f'"{b}"'):
            gelen = _sadelestir(r.get("title") or "")
            if not gelen or (hedef not in gelen and gelen not in hedef):
                continue
            ekle(r, "tohum-baslik", zorla=True)

    for d in TOHUM_SITELER:
        for s in (f"site:{d} lcarlie", f"site:{d} carlie"):
            for r in searx(s):
                # Motor `site:` kisitini yok sayabiliyor; alan adi DOGRULANIR.
                a = alan(r.get("url", ""))
                if a != d and not a.endswith("." + d):
                    continue
                ekle(r, "tohum-site", zorla=True)

    print(f"  keşif: {len(bulunan)} aday haber")
    return bulunan


def _sadelestir(s: str) -> str:
    """Karsilastirma icin: kucuk harf, noktalama yok, tek bosluk."""
    ss = s.lower().replace("’", "").replace("'", "").replace("‘", "")
    ss = "".join(c if c.isalnum() or c.isspace() else " " for c in ss)
    return " ".join(ss.split())


def _cekirdek_baslik(b: str) -> str:
    """Site adi ekini at: 'Baslik - Gazete' -> 'Baslik'."""
    c = b.split(" - ")[0].split(" | ")[0].split(" – ")[0].strip()
    return c if len(c) >= 25 else b


def sendikasyon(adaylar: dict[str, dict]) -> dict[str, dict]:
    """2. asama: her basligi tirnak icinde aratip ayni metni basan tum
    siteleri bul. Ayni haber farkli sitede AYRI kayittir.

    🔴 IKI KAPI (29.09.2026, ilk kosu 151 alakasiz sonuc getirdi):
      1. Yalnizca marka adi BASLIKTA gecen adaylar sendikasyona girer.
         Ozette gecmesi yetmez; ozet sayfanin baska yerinden gelebilir.
      2. Donen sonucun basligi, aranan basligi ICERMELI. Ayni haberin
         kopyasi ayni basligi tasir. Tasimiyorsa o BASKA bir haberdir ve
         arama motoru sadece "benzer" diye dondurmustur.
    """
    yeni: dict[str, dict] = {}
    tohumlar = []
    for a in adaylar.values():
        if len(a["baslik"]) < 25:
            continue
        if not bizimle_ilgili_mi(a["baslik"], ""):   # BASLIKTA gecmeli
            continue
        tohumlar.append(_cekirdek_baslik(a["baslik"]))
    tohumlar = sorted(set(tohumlar))
    print(f"  sendikasyon tohumu: {len(tohumlar)} başlık")

    for cekirdek in tohumlar:
        hedef = _sadelestir(cekirdek)
        if len(hedef) < 25:
            continue
        for r in searx(f'"{cekirdek}"'):
            url = r.get("url", "")
            if not url or _haric_mi(url) or url in adaylar or url in yeni:
                continue
            gelen = _sadelestir(r.get("title") or "")
            # Kopya ayni basligi tasir; iki yonlu bakilir cunku bazi siteler
            # basliga kendi adini ekler, bazilari kisaltir.
            if hedef not in gelen and gelen not in hedef:
                continue
            yeni[url] = {"baslik": (r.get("title") or cekirdek).strip(),
                         "url": url, "site": alan(url),
                         "ozet": (r.get("content") or "").strip(),
                         "terim": "sendikasyon"}
    print(f"  sendikasyon: {len(yeni)} ek kopya")
    return yeni


# --- Veritabani --------------------------------------------------------------
def db_yaz(kayitlar: list[dict], kuru: bool) -> int:
    """core.basin_bahsi'ye yazar. url kolonu DA doldurulur (eski yazici
    bunu bos birakiyordu, bu yuzden hangi haber oldugu izlenemiyordu)."""
    import subprocess

    if not kayitlar:
        return 0
    gorulen: set[tuple[str, str]] = set()
    tekil = []
    for k in kayitlar:
        anahtar = (k["baslik"][:900], k["site"])
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        tekil.append(k)

    def q(x: object) -> str:
        return "'" + str(x or "").replace("'", "''")[:900] + "'"

    satirlar = []
    for k in tekil:
        bayrak = _it.mevzuat_bayraklari(k["baslik"])
        dizi = ("ARRAY[" + ",".join(q(b) for b in bayrak) + "]::text[]"
                if bayrak else "NULL")
        durum = "RISKLI" if bayrak else "TEMIZ"
        satirlar.append(
            f"({q(k['baslik'])},{q(k['site'])},{q(k['url'])},"
            f"{q(k['terim'])},{q(k['ozet'])},{dizi},{q(durum)})")

    sql = (
        "INSERT INTO core.basin_bahsi "
        "(baslik,kaynak_site,url,arama_terimi,ozet,mevzuat_bayragi,mevzuat_durumu) "
        "VALUES " + ",".join(satirlar) +
        " ON CONFLICT (baslik,kaynak_site) DO UPDATE SET "
        "url = COALESCE(EXCLUDED.url, core.basin_bahsi.url), "
        "guncelleme = clock_timestamp();")

    if kuru:
        print(f"  [KURU] {len(tekil)} satır yazılacaktı")
        return 0
    sonuc = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres",
         "psql", "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if sonuc.returncode != 0:
        print(f"  🔴 YAZILAMADI: {sonuc.stderr.strip()[:300]}", file=sys.stderr)
        return 0
    return len(tekil)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yazma, yalnizca goster")
    ap.add_argument("--sendikasyonsuz", action="store_true")
    a = ap.parse_args()

    print(f"marka varyantı: {len(MARKA)} · kişi varyantı: {len(KISILER)}")
    adaylar = kesif()
    if not a.sendikasyonsuz:
        adaylar.update(sendikasyon(adaylar))

    siteler: dict[str, int] = {}
    for k in adaylar.values():
        siteler[k["site"]] = siteler.get(k["site"], 0) + 1
    print(f"\ntoplam bahis: {len(adaylar)} · farklı site: {len(siteler)}")
    for s, n in sorted(siteler.items(), key=lambda x: -x[1]):
        print(f"   {n:>2}  {s}")

    n = db_yaz(list(adaylar.values()), a.kuru)
    print(f"\nveritabanına yazılan: {n}")
    Path("/tmp/basin-bahisler.json").write_text(
        json.dumps(list(adaylar.values()), ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
