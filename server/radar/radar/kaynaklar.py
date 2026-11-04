"""Modelsiz, doğrulanabilir rakip kaynakları (29.10.2026).

Ölçüm (29.10.2026, bu bilgisayardan):
  * Trendyol, Hepsiburada, n11, Akakçe, Cimri, Watsons otomatik erişime 403 veriyor
    (gerçek tarayıcıyla da). Engel aşılmaz; bu siteler 'taranamayan kaynak' olarak raporlanır.
  * dermoeczanem.com (online eczane, T-Soft): robots.txt herkese açık ürün/marka sayfalarına izin
    veriyor, dürüst User-Agent istiyor. Site haritasında 976 marka var; her marka sayfası ürünleri
    schema.org JSON-LD olarak (ürün, marka, fiyat) taşıyor -> fiyatı sayfanın kendi verisinden okuruz.

Akış: marka site haritası -> (a) dünden bu yana listeye giren marka = eczaneye yeni giriş,
(b) her gün sıradaki N marka taranır (tüm liste ~40 günde döner), (c) izlenen markalar her gün.
Çıktı Radar'ın ingest JSON'udur; alıntı (excerpt) JSON-LD satırının kendisidir.
"""
import json
import os
import re
import time
import urllib.parse
from collections import Counter

from .ajan import http_getir, yapisal_veri
from .util import iso, katla, now

UA_JETON = "lcarlieradar"
ECZANE_SITEMAP = "https://www.dermoeczanem.com/xml/sitemap/brand.xml"
_LOC = re.compile(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", re.S)
_LD_SATIR = re.compile(r"^Ürün: (?P<urun>.+?) \| Marka: (?P<marka>.+?)(?: \| Fiyat: (?P<fiyat>[\d.]+) (?P<pb>\w+))?$")


# ---------------- robots.txt ----------------

def _kurallar(metin, jeton=UA_JETON):
    """robots.txt -> bizim için geçerli (izin, yol) kuralları. Önce kendi adımız, yoksa '*'."""
    gruplar, ajanlar, kurallar, onceki_ua = {}, [], [], False
    for ham in metin.splitlines():
        satir = ham.split("#", 1)[0].strip()
        if ":" not in satir:
            continue
        k, v = (x.strip() for x in satir.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not onceki_ua:
                ajanlar, kurallar = [], []
            ajanlar.append(v.lower())
            for a in ajanlar:
                gruplar.setdefault(a, kurallar)
            onceki_ua = True
        elif k in ("allow", "disallow"):
            onceki_ua = False
            if ajanlar and (v or k == "allow"):
                kurallar.append((k == "allow", v))
    for a, kr in gruplar.items():
        if a != "*" and a in jeton:
            return kr
    return gruplar.get("*", [])


def _eslesir(desen, yol):
    rx = "^" + re.escape(desen).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.match(rx, yol) is not None


def izinli(kurallar, url):
    """Google kuralı: en uzun eşleşen desen kazanır; eşitlikte izin."""
    p = urllib.parse.urlparse(url)
    yol = (p.path or "/") + (("?" + p.query) if p.query else "")
    en_iyi = (-1, True)
    for izin, desen in kurallar:
        if desen and _eslesir(desen, yol):
            uz = len(desen)
            if uz > en_iyi[0] or (uz == en_iyi[0] and izin):
                en_iyi = (uz, izin)
    return en_iyi[1]


class NazikGetir:
    """robots.txt'ye uyan, istekler arasında bekleyen getirici."""

    def __init__(self, getir=http_getir, bekle=2.0, uyu=time.sleep):
        self.getir, self.bekle, self.uyu = getir, bekle, uyu
        self.robots, self.son = {}, {}

    def __call__(self, url):
        p = urllib.parse.urlparse(url)
        kok = f"{p.scheme}://{p.netloc}"
        if kok not in self.robots:
            try:
                self.robots[kok] = _kurallar(self.getir(kok + "/robots.txt")[1])
            except Exception:  # noqa: BLE001 -- robots.txt yoksa genel izin
                self.robots[kok] = []
        if not izinli(self.robots[kok], url):
            raise PermissionError(f"robots.txt izin vermiyor: {p.path}")
        gecen = time.monotonic() - self.son.get(kok, 0)
        if gecen < self.bekle:
            self.uyu(self.bekle - gecen)
        self.son[kok] = time.monotonic()
        return self.getir(url)


# ---------------- online eczane ----------------

def site_haritasi(getir, url):
    _, xml = getir(url)
    return {u.strip(): (m or "").strip() for u, m in _LOC.findall(xml)}


def eczane_markalari(getir):
    return site_haritasi(getir, ECZANE_SITEMAP)


def json_ld_sayfasi(url, getir, kanal, zaman=None):
    """Marka veya ürün sayfası -> Radar marka kayıtları (yalnız sayfanın kendi JSON-LD verisi)."""
    son_url, ham = getir(url)
    satirlar = [m.groupdict() | {"satir": s} for s in yapisal_veri(ham).splitlines()
                if (m := _LD_SATIR.match(s))]
    if not satirlar:
        return []
    ts = iso(zaman or now())
    out = {}
    for s in satirlar:
        b = out.setdefault(s["marka"], {"name": s["marka"], "texts": [], "observations": [
            {"kind": "channel", "value": kanal, "source_url": son_url, "fetched_at": ts}]})
        if s["urun"] in b["texts"]:
            continue
        b["texts"].append(s["urun"])
        b["observations"].append({"kind": "product", "product": s["urun"], "source_url": son_url, "fetched_at": ts})
        if s["fiyat"] and (s["pb"] or "").upper() in ("TRY", "TL"):
            b["observations"].append({"kind": "price", "product": s["urun"], "value": float(s["fiyat"]),
                                      "source_url": son_url, "fetched_at": ts, "excerpt": s["satir"]})
    # Marka sayfasında başka markanın ürünü de geçebilir: en çok ürünü olan marka asıl markadır.
    return sorted(out.values(), key=lambda b: -len(b["texts"]))


def marka_sayfasi(url, getir, zaman=None):
    bs = json_ld_sayfasi(url, getir, "eczane", zaman)
    if not bs:
        return None
    b = bs[0]
    b["texts"] = sorted(b["texts"])[:30]
    return b


# Gratis: ürünlerin çoğu makyaj; yalnız bakım kategorilerinin ürün sayfaları taranır.
GRATIS = {"marka": "https://www.gratis.com/sitemap/Brand-tr-TRY.xml",
          "urun": "https://www.gratis.com/sitemap/Product-tr-TRY.xml"}
BAKIM_KATEGORI = re.compile(r"nemlendirici|serum|krem|gunes|temizle|tonik|maske|bebek|pisik|vucut|el-|yuz|"
                            r"dudak-krem|bakim|losyon|peeling|goz-cevresi|leke|akne|sivilce")
MAKYAJ_KATEGORI = re.compile(r"ruj|fondoten|allik|^far$|maskara|oje|kapatici|pudra|eyeliner|kalem|highlighter|makyaj|"
                             r"parfum|boya|kirpik|tirnak|toka|corap|firca")


def _durum_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _durum_yaz(yol, veri):
    os.makedirs(os.path.dirname(os.path.abspath(yol)), exist_ok=True)
    with open(yol + ".tmp", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(yol + ".tmp", yol)


def _sira(liste, gunluk, gun):
    tum = sorted(liste)
    if not tum:
        return []
    bas = (gun.toordinal() * gunluk) % len(tum)
    return [tum[(bas + i) % len(tum)] for i in range(min(gunluk, len(tum)))]


def _izlenen_mi(url, izlenen):
    son = katla(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))
    return any(katla(i) in son for i in izlenen)


def eczane_tara(durum_yolu, getir, izlenen=(), gunluk=25, gun=None):
    """Eczane: marka site haritası; yeni marka = eczaneye yeni giriş. Döner: Radar ingest JSON'u."""
    gun = gun or now().date()
    durumlar, markalar = [], []
    try:
        liste = eczane_markalari(getir)
    except Exception as e:  # noqa: BLE001
        return {"source": "eczane", "source_status": [{"source": "dermoeczanem.com", "ok": False,
                                                        "error": str(e)[:200]}], "brands": [], "yeni_giren": []}
    bilinen = _durum_oku(durum_yolu)
    ilk_tur = bilinen is None
    bilinen = bilinen or {}
    yeni = [] if ilk_tur else sorted(u for u in liste if u not in bilinen)
    izl = [u for u in sorted(liste) if _izlenen_mi(u, izlenen)]
    for u in dict.fromkeys(yeni + izl + _sira(liste, gunluk, gun)):
        try:
            b = marka_sayfasi(u, getir)
        except Exception as e:  # noqa: BLE001
            durumlar.append({"source": "dermoeczanem.com", "ok": False, "error": f"{u}: {str(e)[:150]}"})
            continue
        if not b:
            continue
        if u in yeni:
            b["first_seen_hint"] = gun.isoformat()   # eczane kanalında ilk görüldüğü gün
        markalar.append(b)
    for u, m in liste.items():
        bilinen.setdefault(u, {"ilk": gun.isoformat(), "lastmod": m})
    _durum_yaz(durum_yolu, bilinen)
    durumlar.append({"source": "dermoeczanem.com", "ok": True})
    return {"source": "eczane", "source_status": durumlar, "brands": markalar,
            "yeni_giren": [b["name"] for b in markalar if b.get("first_seen_hint")], "ilk_tur": ilk_tur}


def _gratis_marka_slug(url):
    return re.sub(r"-b-\d+$", "", url.rstrip("/").rsplit("/", 1)[-1])


def gratis_tara(durum_yolu, getir, izlenen=(), gunluk=25, gun=None, marka_basina=3):
    """Gratis: marka site haritasından yeni marka; bakım kategorisi ürün sayfalarından JSON-LD fiyat."""
    from .ajan import _birlestir
    gun = gun or now().date()
    durumlar, markalar = [], []
    try:
        marka_liste = site_haritasi(getir, GRATIS["marka"])
        urunler = [u for u in site_haritasi(getir, GRATIS["urun"])
                   if len(u.split("/")) > 4 and BAKIM_KATEGORI.search(u.split("/")[3])
                   and not MAKYAJ_KATEGORI.search(u.split("/")[3])]
    except Exception as e:  # noqa: BLE001
        return {"source": "gratis", "source_status": [{"source": "gratis.com", "ok": False, "error": str(e)[:200]}],
                "brands": [], "yeni_giren": []}
    bilinen = _durum_oku(durum_yolu)
    ilk_tur = bilinen is None
    bilinen = bilinen or {}
    yeni_slug = [] if ilk_tur else sorted(_gratis_marka_slug(u) for u in marka_liste if u not in bilinen)
    hedef = []
    for sl in yeni_slug:
        hedef += [u for u in urunler if u.rsplit("/", 1)[-1].startswith(sl + "-")][:marka_basina]
    hedef += [u for u in urunler if _izlenen_mi(u, izlenen)][:marka_basina * max(1, len(izlenen))]
    hedef += _sira(urunler, gunluk, gun)
    for u in dict.fromkeys(hedef):
        try:
            bs = json_ld_sayfasi(u, getir, "gratis")
        except Exception as e:  # noqa: BLE001
            durumlar.append({"source": "gratis.com", "ok": False, "error": f"{u}: {str(e)[:150]}"})
            continue
        for b in bs:
            if any(u.rsplit("/", 1)[-1].startswith(sl + "-") for sl in yeni_slug):
                b["first_seen_hint"] = gun.isoformat()
            markalar.append(b)
    for u, m in marka_liste.items():
        bilinen.setdefault(u, {"ilk": gun.isoformat(), "lastmod": m})
    _durum_yaz(durum_yolu, bilinen)
    durumlar.append({"source": "gratis.com", "ok": True})
    markalar = _birlestir(markalar)
    return {"source": "gratis", "source_status": durumlar, "brands": markalar,
            "yeni_giren": [b["name"] for b in markalar if b.get("first_seen_hint")], "ilk_tur": ilk_tur,
            "bakim_urun_sayisi": len(urunler)}
