#!/usr/bin/env python3
"""L'CARLIE - SITE NOBETI

NEDEN VAR
Siteyi kimse olcmuyordu. 22.09.2026'da ilk bakista cikan sey bunu
ozetliyor: lcarlie.com.tr bir <meta http-equiv="refresh"> sayfasi
donduruyor ve HTTP **200** diyor. Durum koduna bakan her izleme "site
saglikli" der; oysa arama motorlari meta-refresh'i 301 gibi saymaz,
yani o alan adinin butun SEO degeri bosa gidiyor. Sessiz ariza sinifi.

NE YAPAR
Sitemap'ten gercek URL'leri okur (yeni urun sayfalari elle eklenmeden
kapsama girsin diye), her birini olcer ve ONCEKI KOSUYLA karsilastirir.
Bulgular state/findings.jsonl'e yazilir; panel zaten oradan okuyor.

🔴 HICBIR SEY YAZMAZ, HICBIR SEY ONARMAZ. Yalniz okur ve raporlar.
   Onarim ayri bir zincir (CodingExecutor -> onay kuyrugu) ve insan
   onayindan gecer.

🔴 SESSIZ BASARISIZLIK YOK. Siteye hic ulasilamazsa bu da bir BULGUDUR;
   "kontrol calisti, sorun bulunmadi" ile "kontrol calisamadi" ayri
   seylerdir ve ayri raporlanir.

🔴 YALNIZ STANDART KUTUPHANE. Yeni bagimlilik eklenmez.

Kullanim:
  site-nobeti.py                 Olc, karsilastir, bulgulari yaz
  site-nobeti.py --rapor         Insan icin okunur ozet, bulgu YAZMAZ
  site-nobeti.py --taban-sifirla Temel cizgiyi bu kosuyla yeniden kur
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TABAN_URL = os.environ.get("LCARLIE_SITE", "https://www.lcarlie.shop")
# 🔴 .com.tr bilerek listede: yonlendirmesi bozuk ve bunu gormek istiyoruz.
EK_ADRESLER = tuple(
    u for u in os.environ.get("LCARLIE_SITE_EK", "https://www.lcarlie.com.tr/").split(",") if u
)
KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
DURUM_DIZIN = KOK / "state" / "site-nobeti"
TABAN_DOSYA = DURUM_DIZIN / "taban.json"
BULGU_DOSYA = KOK / "state" / "findings.jsonl"

# 🔴 PANEL DE IZLENIR. Sitemap'i yok, hedefler acikca yazilir.
#    Her hedefin bir ISARETI var: dosya sunuluyor ama ICI BOS/BOZUK
#    olabilir ve HTTP 200 bunu gizler. 20.09.2026'da EKIP sekmesi tam
#    boyle kayboldu: ekran yazilmisti, iki haritaya kaydedilmemisti;
#    sayfa 200 donuyordu ve tiklama hicbir sey yapmiyordu.
#
#    Giris YAPILMAZ, parola kullanilmaz: yalnizca acikta sunulan uclar.
PANEL_TABAN = os.environ.get("LCARLIE_PANEL", "https://jarvis.lcarlie.shop")
PANEL_HEDEFLER = (
    ("/",            "statApprovals", 8000),
    ("/app.js",      "function setView", 100000),
    ("/app.css",     ".proposal-card", 40000),
    ("/api/session", "authenticated", 0),
)

ZAMAN_ASIMI = int(os.environ.get("SITE_NOBETI_ZAMAN_ASIMI", "25"))
AZAMI_URL = int(os.environ.get("SITE_NOBETI_AZAMI_URL", "40"))
AJAN = "LCARLIE-site-nobeti/1.0 (+izleme; yalniz okur)"

# Gerileme esikleri. Olculmus degerlerden secildi: ana sayfa 851 KB ve
# 0,55 sn. Esikler gurultu uretmeyecek kadar genis, gercek bir cokusu
# kacirmayacak kadar dar.
BOYUT_DUSUS_ORANI = 0.40   # %40'tan fazla kuculme
SURE_ARTIS_KATI = 2.5      # 2,5 kattan fazla yavaslama
SERTIFIKA_UYARI_GUN = 21
# Ag hatasinda (yanit hic gelmedi) bu kadar saniye bekleyip bir kez daha olculur.
YENIDEN_DENE_SN = float(os.environ.get("SITE_NOBETI_YENIDEN_DENE_SN", "5"))

# 🔴 05.11.2026: sunucunun kendi DNS'i 06:57'de birkac saniye coktu; 8 blog
#    sayfasi "ULASILAMADI · KRITIK" diye sahibe gitti. Site acikti. Ad
#    cozumleme hatasi OLCUMU YAPAN tarafin sorunudur, sitenin degil:
#    ayri sinyal (site_olcum), sahibe is acmaz, temel cizgiyi bozmaz.
DNS_HATASI = re.compile(r"name resolution|Name or service not known|nodename nor servname|"
                        r"getaddrinfo|No address associated", re.I)


def ag_hatasi_dns_mi(hata: str | None) -> bool:
    return bool(hata) and bool(DNS_HATASI.search(hata))


def _sade_hata(hata: str) -> str:
    """Teknik hata metnini sahibin okuyacagi cumleye cevirir."""
    if ag_hatasi_dns_mi(hata):
        return "sunucumuz site adresini çözemedi (DNS)"
    if re.search(r"timed? ?out|zaman", hata, re.I):
        return "sayfa 25 saniye içinde yanıt vermedi"
    if re.search(r"refused|reset|aborted", hata, re.I):
        return "bağlantı karşı taraftan kesildi"
    if re.search(r"SSL|certificate|sertifika", hata, re.I):
        return "güvenli bağlantı (SSL) kurulamadı"
    return "sayfaya bağlanılamadı"


# --------------------------------------------------------------------------
# olcum
# --------------------------------------------------------------------------
def _iste(url: str) -> dict:
    """Yanit hic gelmediyse (DNS, baglanti) bir kez daha dener."""
    sonuc = _iste_bir(url)
    if sonuc.get("hata") and YENIDEN_DENE_SN >= 0:
        time.sleep(YENIDEN_DENE_SN)
        ikinci = _iste_bir(url)
        ikinci["ilk_hata"] = sonuc["hata"]
        return ikinci
    return sonuc


def _iste_bir(url: str) -> dict:
    """Tek bir adresi olcer. Yonlendirmeleri ELLE takip eder.

    urllib varsayilan olarak yonlendirmeyi sessizce izler; o zaman kac
    adim atildigi ve 301 mi 302 mi oldugu GORUNMEZ olur. Oysa
    yonlendirmenin TURU bu isin merkezinde: meta-refresh ile 301 arasindaki
    fark, .com.tr alan adinin SEO degerini kaybetmesi demek.
    """
    sonuc = {"url": url, "zincir": [], "meta_refresh": None}
    su_an = url
    bas = time.monotonic()
    for _ in range(6):
        istek = urllib.request.Request(_kodla(su_an), headers={"User-Agent": AJAN})
        acici = urllib.request.build_opener(_YonlendirmeYok)
        try:
            with acici.open(istek, timeout=ZAMAN_ASIMI) as cevap:
                govde = cevap.read(400_000)
                sonuc.update(durum=cevap.status, son_url=su_an,
                             boyut=len(govde), basliklar=dict(cevap.headers))
                break
        except _Yonlendirildi as y:
            sonuc["zincir"].append({"url": su_an, "durum": y.kod, "hedef": y.konum})
            su_an = y.konum
            continue
        except urllib.error.HTTPError as e:
            sonuc.update(durum=e.code, son_url=su_an, boyut=0, basliklar=dict(e.headers))
            govde = b""
            break
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
            sonuc.update(hata=f"{type(e).__name__}: {e}", durum=None, son_url=su_an)
            sonuc["sure"] = round(time.monotonic() - bas, 3)
            return sonuc
    else:
        sonuc.update(hata="yonlendirme dongusu (6 adim asildi)", durum=None, son_url=su_an)
        sonuc["sure"] = round(time.monotonic() - bas, 3)
        return sonuc

    sonuc["sure"] = round(time.monotonic() - bas, 3)
    metin = govde.decode("utf-8", errors="replace")
    sonuc["govde"] = metin
    sonuc["baslik"] = _ilk(r"<title[^>]*>(.*?)</title>", metin)
    sonuc["aciklama"] = _ilk(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', metin)
    sonuc["canonical"] = _ilk(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']', metin)
    # noindex iki yerden gelebilir: meta etiketi ya da X-Robots-Tag basligi.
    meta_robots = _ilk(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'](.*?)["\']', metin) or ""
    baslik_robots = str(sonuc.get("basliklar", {}).get("X-Robots-Tag", ""))
    sonuc["noindex"] = "noindex" in (meta_robots + " " + baslik_robots).lower()
    # 🔴 Asil yakalanmasi gereken: 200 donen ama aslinda yonlendiren sayfa.
    mr = _ilk(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'](.*?)["\']', metin)
    if mr:
        sonuc["meta_refresh"] = mr.strip()
    return sonuc


def _kodla(url: str) -> str:
    """ASCII disi adresleri istege uygun hale getirir.

    Sitemap Turkce karakterli urun adresleri iceriyor; urllib istek
    satirini ascii ile kodladigi icin bunlar UnicodeEncodeError atiyordu.
    Yol ve sorgu yuzde kodlanir, alan adi IDNA'ya cevrilir.

    🔴 '%' guvenli birakilir: aksi halde zaten kodlanmis bir adres
       ikinci kez kodlanir ('%20' -> '%2520') ve adres bozulur.
    """
    parca = urllib.parse.urlsplit(url)
    try:
        host = parca.hostname.encode("idna").decode("ascii") if parca.hostname else ""
    except (UnicodeError, AttributeError):
        host = parca.hostname or ""
    if parca.port:
        host = f"{host}:{parca.port}"
    return urllib.parse.urlunsplit((
        parca.scheme,
        host,
        urllib.parse.quote(parca.path, safe="/%~:@!$&'()*+,;="),
        urllib.parse.quote(parca.query, safe="=&%~:@!$'()*+,;/?"),
        "",
    ))


class _Yonlendirildi(Exception):
    def __init__(self, kod: int, konum: str):
        self.kod, self.konum = kod, konum


class _YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Yonlendirildi(code, newurl)


def _ilk(desen: str, metin: str) -> str | None:
    m = re.search(desen, metin, re.I | re.S)
    return m.group(1).strip() if m else None


def _sertifika_gun(host: str) -> int | None:
    """Sertifikanin bitimine kac gun kaldi. Olculemezse None -- TAHMIN YOK."""
    try:
        baglam = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=ZAMAN_ASIMI) as ham:
            with baglam.wrap_socket(ham, server_hostname=host) as s:
                bitis = s.getpeercert().get("notAfter")
        son = dt.datetime.strptime(bitis, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
        return (son - dt.datetime.now(dt.timezone.utc)).days
    except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
        return None


def _sitemap_urlleri(taban: str) -> list[str]:
    """Sitemap'ten gercek adresleri okur; index ise alt haritalari gezer.

    Elle URL listesi tutmak, yeni urun sayfalarinin kapsam disinda
    kalmasi demekti - ve kapsam disinda kalan sayfa, bozuldugunda
    gorunmez.
    """
    adresler: list[str] = []
    yigin = [f"{taban}/sitemap.xml"]
    gorulen = set()
    while yigin and len(adresler) < AZAMI_URL * 3:
        sm = yigin.pop(0)
        if sm in gorulen:
            continue
        gorulen.add(sm)
        try:
            istek = urllib.request.Request(_kodla(sm), headers={"User-Agent": AJAN})
            with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as cevap:
                xml = cevap.read(2_000_000).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
            continue
        loclar = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        if "<sitemapindex" in xml:
            yigin.extend(loclar)
        else:
            adresler.extend(loclar)
    # Ana sayfa her zaman ilk sirada; kalanlar deterministik siralanir ki
    # kosular arasi karsilastirma anlamli olsun.
    benzersiz = sorted(set(adresler))
    onde = [f"{taban}/"]
    return onde + [u for u in benzersiz if u not in onde][: AZAMI_URL - 1]


# --------------------------------------------------------------------------
# degerlendirme
# --------------------------------------------------------------------------
def _bulgular(olcum: dict, taban: dict | None) -> list[tuple[str, str, str, dict]]:
    """(onem, signal_code, sebep, kanit) listesi dondurur."""
    b: list[tuple[str, str, str, dict]] = []
    url = olcum["url"]
    kisa = url.replace(TABAN_URL, "").replace("https://", "") or "/"

    if olcum.get("hata"):
        if ag_hatasi_dns_mi(olcum["hata"]):
            b.append(("WARNING", "site_olcum",
                      f"{kisa} sayfası ölçülemedi: {_sade_hata(olcum['hata'])}. "
                      f"Bu, sitenin kapalı olduğunu göstermez; sorun ölçümü yapan sunucuda.",
                      {"url": url, "hata": olcum["hata"]}))
            return b
        b.append(("CRITICAL", "site_erisim",
                  f"{kisa} sayfası açılmadı: {_sade_hata(olcum['hata'])}. "
                  f"İki deneme de başarısız oldu.",
                  {"url": url, "hata": olcum["hata"]}))
        return b

    durum = olcum.get("durum")
    if durum is None or durum >= 400:
        b.append(("CRITICAL", "site_erisim",
                  f"{kisa} sayfası HTTP {durum} hatası veriyor; müşteri bu sayfayı açamaz.",
                  {"url": url, "durum": durum}))
        return b

    if olcum.get("meta_refresh") is not None:
        b.append(("WARNING", "site_seo",
                  f"{kisa} açılıyor ama ziyaretçiyi sayfa içi bir yönlendirmeyle (meta-refresh) "
                  f"başka adrese gönderiyor ({olcum['meta_refresh'][:80]}). Google bunu kalıcı "
                  f"yönlendirme (301) saymaz; bu adresin arama değeri yeni adrese geçmiyor.",
                  {"url": url, "meta_refresh": olcum["meta_refresh"]}))

    if olcum.get("noindex"):
        b.append(("CRITICAL", "site_seo",
                  f"{kisa} sayfası Google'a kapalı (noindex): arama sonuçlarında hiç çıkmaz.",
                  {"url": url}))

    if not (olcum.get("baslik") or "").strip():
        b.append(("WARNING", "site_seo", f"{kisa} sayfasının başlığı (title) boş; Google'da başlıksız görünür.", {"url": url}))
    if not (olcum.get("aciklama") or "").strip():
        b.append(("INFO", "site_seo", f"{kisa} sayfasının açıklaması (meta description) yok.", {"url": url}))

    if taban:
        # Onceki olcum yapilamadiysa (durum None) karsilastirilacak bir sey yoktur.
        if taban.get("durum") is not None and taban.get("durum") != durum:
            b.append(("WARNING", "site_gerileme",
                      f"{kisa} sayfasının yanıt kodu değişti: önce {taban.get('durum')}, şimdi {durum}.",
                      {"url": url, "onceki": taban.get("durum"), "simdi": durum}))
        eski_boyut, yeni_boyut = taban.get("boyut") or 0, olcum.get("boyut") or 0
        if eski_boyut > 5000 and yeni_boyut < eski_boyut * (1 - BOYUT_DUSUS_ORANI):
            b.append(("WARNING", "site_gerileme",
                      f"{kisa} sayfası önceki ölçüme göre %{round((1 - yeni_boyut / eski_boyut) * 100)} küçüldü "
                      f"({eski_boyut} → {yeni_boyut} bayt). Sayfa eksik yükleniyor olabilir.",
                      {"url": url, "onceki_boyut": eski_boyut, "boyut": yeni_boyut}))
        eski_sure, yeni_sure = taban.get("sure") or 0, olcum.get("sure") or 0
        if eski_sure > 0.2 and yeni_sure > eski_sure * SURE_ARTIS_KATI:
            b.append(("INFO", "site_gerileme",
                      f"{kisa} sayfası yavaşladı: {eski_sure} sn → {yeni_sure} sn.",
                      {"url": url, "onceki_sure": eski_sure, "sure": yeni_sure}))
        if taban.get("baslik") and olcum.get("baslik") and taban["baslik"] != olcum["baslik"]:
            b.append(("INFO", "site_gerileme",
                      f"{kisa} sayfasının başlığı değişti: “{taban['baslik'][:50]}” → "
                      f"“{olcum['baslik'][:50]}”",
                      {"url": url, "onceki": taban["baslik"], "simdi": olcum["baslik"]}))
    return b


def _panel_bulgulari() -> list[tuple]:
    """Panelin ayakta VE butun oldugunu olcer.

    Durum kodu yetmez: bir dosya sunulup ici bos ya da kirpilmis olabilir.
    Her hedef icin hem bir ISARET metni hem de asgari boyut aranir.
    """
    b: list[tuple] = []
    for yol, isaret, asgari in PANEL_HEDEFLER:
        url = PANEL_TABAN + yol
        o = _iste(url)
        if o.get("hata"):
            if ag_hatasi_dns_mi(o["hata"]):
                b.append((url, "WARNING", "site_olcum",
                          f"Jarvis paneli ({yol}) ölçülemedi: {_sade_hata(o['hata'])}. "
                          f"Bu, panelin kapalı olduğunu göstermez.",
                          {"url": url, "hata": o["hata"]}))
                continue
            b.append((url, "CRITICAL", "panel_erisim",
                      f"Jarvis paneli ({yol}) açılmadı: {_sade_hata(o['hata'])}. "
                      f"İki deneme de başarısız oldu.",
                      {"url": url, "hata": o["hata"]}))
            continue
        durum = o.get("durum")
        if durum is None or durum >= 400:
            b.append((url, "CRITICAL", "panel_erisim",
                      f"Jarvis paneli ({yol}) HTTP {durum} hatası veriyor.",
                      {"url": url, "durum": durum}))
            continue
        govde = o.get("govde") or ""
        boyut = o.get("boyut") or 0
        if isaret and isaret not in govde:
            # 🔴 Sunuluyor ama ICI BEKLENEN SEY DEGIL. 200 bunu gizler.
            b.append((url, "CRITICAL", "panel_butunluk",
                      f"Jarvis paneli ({yol}) açılıyor ama içinde beklenen bölüm yok "
                      f"(aranan: {isaret}). Dosya boş, eksik ya da yanlış sürüm olabilir.",
                      {"url": url, "aranan": isaret, "boyut": boyut}))
        elif asgari and boyut < asgari:
            b.append((url, "WARNING", "panel_butunluk",
                      f"Jarvis paneli ({yol}) beklenenden küçük: {boyut} bayt "
                      f"(en az {asgari} olmalı). Dosya eksik olabilir.",
                      {"url": url, "boyut": boyut, "asgari": asgari}))
    return b


def _bulgu_yaz(kayitlar: list[dict]) -> None:
    BULGU_DOSYA.parent.mkdir(parents=True, exist_ok=True)
    with BULGU_DOSYA.open("a", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")


def _son_bulgular() -> dict[str, dict]:
    try:
        lines = BULGU_DOSYA.read_text(encoding="utf-8").splitlines()[-1000:]
    except OSError:
        return {}
    latest = {}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("signature"):
            latest[row["signature"]] = row
    return latest


def _acik_http_adresleri() -> list[str]:
    host = urllib.parse.urlsplit(TABAN_URL).netloc
    urls = []
    for signature, row in _son_bulgular().items():
        if row.get("status") == "RESOLVED" or row.get("signal_code") not in ("site_erisim", "site_olcum"):
            continue
        if not (re.search(r"HTTP [45]\d\d", str(row.get("reason", "")))
                or (row.get("evidence") or {}).get("hata")):
            continue
        url = (row.get("evidence") or {}).get("url") or signature.split(":", 1)[-1]
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme == "https" and parsed.netloc == host:
            urls.append(url)
    return list(dict.fromkeys(urls))


def _kapanan_http_bulgulari(olcumler: dict, bulgular: list) -> list[dict]:
    active = {f"{kod}:{url}" for url, _onem, kod, _sebep, _kanit in bulgular}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    closed = []
    for signature, row in _son_bulgular().items():
        if row.get("status") == "RESOLVED" or signature in active:
            continue
        if row.get("signal_code") not in ("site_erisim", "site_olcum"):
            continue
        if not (re.search(r"HTTP [45]\d\d", str(row.get("reason", "")))
                or (row.get("evidence") or {}).get("hata")):
            continue
        url = (row.get("evidence") or {}).get("url") or signature.split(":", 1)[-1]
        measurement = olcumler.get(url, {})
        code = measurement.get("durum")
        if isinstance(code, int) and 200 <= code < 300:
            closed.append({"observed_at": now, "signature": signature,
                "signal_code": row.get("signal_code"), "severity": "INFO", "status": "RESOLVED",
                "reason": f"Önceki sorun kapandı: sayfa yeniden ölçüldü ve açılıyor (HTTP {code}).",
                "evidence": {"url": url, "durum": code},
                "note": "Yalnız başarılı yeniden ölçümle kapatıldı."})
    return closed


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="L'CARLIE site nobeti")
    ap.add_argument("--rapor", action="store_true", help="insan icin ozet; bulgu YAZMAZ")
    ap.add_argument("--taban-sifirla", action="store_true", help="temel cizgiyi yeniden kur")
    a = ap.parse_args()

    DURUM_DIZIN.mkdir(parents=True, exist_ok=True)
    try:
        taban = json.loads(TABAN_DOSYA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        taban = {}
    ilk_kosu = not taban

    adresler = _sitemap_urlleri(TABAN_URL)
    if len(adresler) <= 1:
        # 🔴 Sitemap okunamadi. Bu SESSIZCE gecilmez: kapsam cokmus demektir.
        kayit = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "signature": "site_kapsam:sitemap_okunamadi",
                 "reason": "Site haritası (sitemap) okunamadı; nöbet bu kez yalnız ana "
                           "sayfayı ölçebildi. Diğer sayfalar kontrol edilmedi.",
                 "evidence": {"taban": TABAN_URL, "bulunan_adres": len(adresler)},
                 "signal_code": "site_erisim", "severity": "WARNING",
                 "note": "site-nobeti.py · yalniz okur"}
        if not a.rapor:
            _bulgu_yaz([kayit])
        print("UYARI: sitemap okunamadi, kapsam 1 adrese dustu", file=sys.stderr)
    adresler = list(dict.fromkeys(_acik_http_adresleri() + list(adresler)))[:AZAMI_URL] + list(EK_ADRESLER)

    olcumler, tum_bulgular = {}, []
    for url in adresler:
        o = _iste(url)
        olcumler[url] = {k: o.get(k) for k in
                         ("durum", "boyut", "sure", "baslik", "noindex", "meta_refresh")}
        tum_bulgular.extend((url, *x) for x in _bulgular(o, taban.get(url)))

    # Panel de izlenir: siteyi olcup paneli olcmemek, olcumu yapan seyin
    # kendisini kor birakmak olurdu.
    tum_bulgular.extend(_panel_bulgulari())

    host = TABAN_URL.split("//", 1)[-1].split("/", 1)[0]
    gun = _sertifika_gun(host)
    if gun is not None and gun < SERTIFIKA_UYARI_GUN:
        tum_bulgular.append((TABAN_URL, "WARNING", "site_erisim",
                             f"Sitenin güvenlik sertifikası (SSL) {gun} gün sonra bitiyor.", {"host": host, "gun": gun}))

    # --- rapor ---------------------------------------------------------
    print(f"=== SITE NOBETI · {TABAN_URL} · {len(adresler)} adres "
          f"+ panel ({len(PANEL_HEDEFLER)} uc) ===")
    if ilk_kosu:
        print("(ilk kosu: temel cizgi kuruluyor, gerileme karsilastirmasi yok)")
    kritik = sum(1 for x in tum_bulgular if x[1] == "CRITICAL")
    uyari = sum(1 for x in tum_bulgular if x[1] == "WARNING")
    print(f"KRITIK: {kritik}  UYARI: {uyari}  BILGI: {len(tum_bulgular) - kritik - uyari}")
    for _url, onem, _kod, sebep, _kanit in tum_bulgular:
        print(f"  [{onem:<8}] {sebep}")
    if not tum_bulgular:
        print("  sorun bulunmadi.")

    # --- bulgulari kaydet ----------------------------------------------
    if not a.rapor:
        simdi = dt.datetime.now(dt.timezone.utc).isoformat()
        kapanan = _kapanan_http_bulgulari(olcumler, tum_bulgular)
        _bulgu_yaz(kapanan + [{
            "observed_at": simdi,
            "signature": f"{kod}:{url}",
            "reason": sebep,
            "evidence": kanit,
            "signal_code": kod,
            "severity": onem,
            "note": "site-nobeti.py · yalniz okur, hicbir sey onarmaz. "
                    "Onarim ayri zincirden ve insan onayindan gecer.",
        } for url, onem, kod, sebep, kanit in tum_bulgular])

    if not a.rapor or a.taban_sifirla:
        # Olculemeyen sayfa (durum None) eski olcumunu korur; yoksa bir sonraki
        # kosu "None -> 200 degisti" diye yeni bir yanlis alarm uretirdi.
        yeni_taban = {url: (taban[url] if o.get("durum") is None and url in taban else o)
                      for url, o in olcumler.items()}
        TABAN_DOSYA.write_text(json.dumps(yeni_taban, ensure_ascii=False, indent=1),
                               encoding="utf-8")

    return 1 if kritik else 0


if __name__ == "__main__":
    sys.exit(main())
