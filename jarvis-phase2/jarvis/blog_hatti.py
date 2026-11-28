# -*- coding: utf-8 -*-
"""BLOG HATTI — günlük otonom SEO blog yayını (25.11.2026).

Sahip: "Her gün 3 SEO yazısı yazılsın, görselleri GPT ile üretilsin, blogda
tüm dil seçenekleriyle paylaşılsın; Claude sayfasına bağlı OLMASIN."

Bu modül hattın saf (yan etkisiz) parçalarını ve dış istemcileri tutar:

  kaynak dosya ayrıştırma   hazir_dosya_oku()
  kapılar (gate)            kelime_kapisi, yapi_kapisi, iddia_kapisi,
                            kaynak_kapisi (PMID/DOI çözümleme)
  HTML -> Ricos             html_to_ricos()
  model istemcisi           gemini() -> varsayılan ChatGPT web (chatgpt_web); BLOG_METIN_YOLU=gemini eski yol
  Wix istemcisi             WixBlog
  görsel dizgi              kapak_diz(), ic_gorsel_diz()
  kuyruk (Postgres)         Kuyruk

Durum makinesi scripts/blog-hatti.py içindedir.

🔴 KAPI KURALI: herhangi bir kapı düşerse yazı YAYINLANMAZ, INSANA olur ve
   sahibe bildirilir. "Kapı çalışmadı" (ağ hatası) ile "kapı reddetti" ayrı
   tutulur: ağ hatası HATA'dır (yeniden denenir), ret INSANA'dır.
🔴 AMBALAJ KİLİDİ: ChatGPT'ye ürünsüz sahne çizdirilir; ürün katmanı sunucuda
   gerçek kesik PNG'nin pikselleriyle yapıştırılır. Yazı da görsel modeline
   yazdırılmaz, marka fontlarıyla dizilir.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import json
import os
import re
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- sabitler
SITE = "https://www.lcarlie.shop"
DILLER = ("en", "de", "ru", "ar")
TUM_DILLER = ("tr",) + DILLER
MEMBER_ID = "92cdbf70-32b1-4049-8350-1e1324bc81f2"
KATEGORI = {
    "icerik-sozlugu": "520f0396-b183-411d-91ad-091497377d62",
    "rituel": "455366dd-661b-46e7-ba00-5ce427090948",
    "urun-rehber": "e6182d7a-65ff-449e-b754-d3e3856e174a",
    "formul": "11d0b004-e592-4978-9f20-ed04f68cec52",
    "botanik": "6cc561b5-2944-457a-b831-d8f33957436f",
    "urun-kategori": "12efe873-34ed-47e2-8f06-c67bd73fd241",
    "bilincli-bakim": "47ca514d-af99-4c62-8f04-fb0dac1723db",
}
KATEGORI_RENK = {  # kapak vurgu çubuğu
    KATEGORI["icerik-sozlugu"]: (122, 140, 110),
    KATEGORI["rituel"]: (176, 132, 96),
    KATEGORI["urun-rehber"]: (95, 120, 140),
    KATEGORI["formul"]: (110, 110, 140),
    KATEGORI["botanik"]: (98, 132, 92),
    KATEGORI["urun-kategori"]: (150, 110, 120),
    KATEGORI["bilincli-bakim"]: (196, 150, 84),
}
KOK = Path(os.environ.get("BLOG_KOK", "/opt/lcarlie/blog-hatti"))
KESIT_DIR = KOK / "kesit"
YAYIN_DIR = Path(os.environ.get("BLOG_YAYIN_DIR", "/opt/lcarlie/urun-gorsel/blog"))
YAYIN_URL = os.environ.get("BLOG_YAYIN_URL", "https://n8n.lcarlie.shop/urun-gorsel/blog")
FONT_DIR = Path("/opt/lcarlie/jarvis-phase2/varliklar")
UA = "lcarlie-blog-hatti/1.0 (mailto:info@lcarlie.com.tr)"

EN_AZ_KELIME = 1200
EN_AZ_KAYNAK = 4


class KapiRed(Exception):
    """Kapı içeriği reddetti -> INSANA."""


class DisHata(Exception):
    """Dış servis cevap vermedi -> HATA (yeniden denenir)."""


# ---------------------------------------------------------------- yardımcı
def slugla(metin: str) -> str:
    tablo = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                           "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
                           "ß": "ss", "ä": "a", "Ä": "a"})
    m = unicodedata.normalize("NFKD", metin.translate(tablo))
    m = "".join(c for c in m if not unicodedata.combining(c)).lower()
    m = re.sub(r"[^a-z0-9]+", "-", m).strip("-")
    return re.sub(r"-{2,}", "-", m)[:80].strip("-")


def duz_metin(html: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?i)</(p|li|h[1-6]|tr|td|th)>", ". ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()


def govde_kaynaksiz(html: str) -> tuple[str, str]:
    """Gövdeyi 'Kaynaklar' bölümünden ayırır (çok dilli başlık eşlemesi)."""
    m = re.search(r"(?is)<h2[^>]*>\s*(Kaynaklar|Sources|References|Quellen|Literatur|Источники|"
                  r"Литература|المصادر|المراجع)\s*</h2>", html)
    if not m:
        return html, ""
    return html[:m.start()], html[m.start():]


def kelime_say(html: str) -> int:
    govde, _ = govde_kaynaksiz(html)
    return len(re.findall(r"[\w’'-]+", duz_metin(govde), re.U))


# ------------------------------------------------------- hazır dosya ayrıştır
_ANAHTAR = re.compile(r"^([A-Z][A-Z0-9_]+):\s?(.*)$")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def hazir_dosya_oku(yol: Path) -> dict[str, Any]:
    ham = yol.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.match(r"\s*<!--(.*?)-->(.*)$", ham, re.S)
    if not m:
        raise ValueError("başlık yorum bloğu yok: %s" % yol.name)
    bas, govde = m.group(1), m.group(2).strip()
    alan: dict[str, str] = {}
    son = None
    for satir in bas.split("\n"):
        a = _ANAHTAR.match(satir)
        if a and not satir.startswith(" "):
            son = a.group(1)
            alan[son] = a.group(2).strip()
        elif son:
            alan[son] = (alan[son] + "\n" + satir).strip("\n")
    faq = None
    fm = re.search(r"<script[^>]*>(.*?)</script>", alan.get("FAQ_JSONLD", ""), re.S)
    if fm:
        faq = json.loads(fm.group(1))
    h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", govde)
    baslik = duz_metin(h1.group(1)) if h1 else alan.get("SEO_BASLIK", "")
    govde_h1siz = re.sub(r"(?is)<h1[^>]*>.*?</h1>", "", govde, count=1).strip()
    durum = alan.get("DURUM", "")
    tur = "REFRESH" if durum.upper().startswith("REFRESH") else "NEW"
    mevcut = None
    if tur == "REFRESH":
        um = re.search(r"https://www\.lcarlie\.shop/post/([A-Za-z0-9%._-]+)", durum)
        mevcut = um.group(1) if um else None
    kat = _UUID.search(alan.get("KATEGORI", ""))
    plan = yol.name.split("-", 1)[0]
    brif = alan.get("GORSEL_BRIFI", "")
    kesitler = []
    kapak = next((s for s in brif.split("\n") if "KAPAK" in s), brif)
    for ad in re.findall(r"([a-z0-9-]+)\.png", kapak):
        if ad not in kesitler:
            kesitler.append(ad)
    sahne = re.search(r"sahne:\s*([^|]+)", kapak)
    return {
        "plan_no": plan, "slug": alan.get("SLUG", "").strip(), "tur": tur,
        "mevcut_slug": mevcut, "baslik": baslik,
        "seo_baslik": alan.get("SEO_BASLIK", baslik)[:70],
        "meta": alan.get("META_ACIKLAMA", ""),
        "anahtar": alan.get("BIRINCIL_ANAHTAR", ""),
        "ikincil": [x.strip() for x in alan.get("IKINCIL_ANAHTARLAR", "").split(",") if x.strip()],
        "kategori_id": kat.group(0) if kat else None,
        "faq_jsonld": faq, "html": govde_h1siz,
        "gorsel_brif": brif, "sahne_tr": (sahne.group(1).strip() if sahne else baslik),
        "kesitler": kesitler,
        "alt_1": alan.get("GORSEL_ALT_1", ""), "alt_2": alan.get("GORSEL_ALT_2", ""),
        "notlar": {k: alan[k] for k in ("NOT", "MEVZUAT_NOTU", "SAHIBE_SORULAR") if k in alan},
        "kaynak_dosya": yol.name,
        "kaynak_sha": hashlib.sha256(ham.encode("utf-8")).hexdigest()[:16],
    }


# ------------------------------------------------------------------- kapılar
def yapi_kapisi(html: str, dil: str = "tr") -> list[str]:
    """Yapı: tablo ya da adım listesi, SSS (4-6 soru), kaynak bölümü."""
    sorun = []
    if not re.search(r"(?i)<table|<ol", html):
        sorun.append("tablo/adım listesi yok")
    govde, kaynak = govde_kaynaksiz(html)
    if not kaynak:
        sorun.append("Kaynaklar bölümü yok")
    return sorun


def kelime_kapisi(html: str, en_az: int = EN_AZ_KELIME) -> list[str]:
    n = kelime_say(html)
    return [] if n >= en_az else ["gövde %d kelime (< %d)" % (n, en_az)]


# Hangi dilde olursa olsun HER YERDE yasak (bağlamdan bağımsız).
SERT_YASAK = {
    "tr": [r"mucize", r"(dermatolog|doktor|hekim|uzman)(lar|ler)?(ın|in)?\s+(öneri(r|yor)|tavsiye\s+ed(er|iyor))",
           r"tedavi\s+eder", r"iyileştirir", r"yok\s+eder", r"kolajen\s+üretimini\s+artır",
           r"leke(leri)?\s+giderir", r"%\s?100\s+(etkili|doğal|garanti)"],
    "en": [r"miracle", r"dermatologist[s]?[- ]recommended", r"doctor[s]?[- ]recommended", r"\bcures?\b",
           r"\bheals?\b", r"boosts? collagen production", r"removes? (dark )?spots", r"100% (effective|natural|guaranteed)"],
    "de": [r"wunder", r"von dermatologen empfohlen", r"ärztlich empfohlen", r"\bheilt\b", r"\bheilen\b",
           r"kollagenproduktion (steigert|anregt)", r"entfernt flecken", r"100 ?% (wirksam|natürlich|garantiert)"],
    "ru": [r"чудо", r"рекомендова\w* дерматолог", r"рекомендова\w* врач", r"\bлечит\b", r"\bизлечива",
           r"стимулирует выработку коллагена", r"удаляет пятна", r"100 ?% (эффектив|натурал|гарант)"],
    "ar": [r"معجز", r"يوصي به أطباء الجلد", r"يوصي به الأطباء", r"يعالج", r"يشفي",
           r"يحفز إنتاج الكولاجين", r"يزيل البقع", r"100 ?% (فعال|طبيعي|مضمون)"],
}
# Yalnız ÜRÜN cümlesinde (cümlede ürün/marka adı geçiyorsa) yasak: hastalık,
# fizyolojik işlev ve tedavi dili ürünün nesnesi olamaz.
URUN_CUMLE_YASAK = {
    "tr": [r"tedavi", r"iyileş", r"geçirir", r"giderir", r"onarır", r"yeniler\b", r"sivilce", r"egzama",
           r"hastalık", r"akne(yi|ye karşı)", r"dolaşım", r"kan akışı", r"hormon", r"(?<!\w)kas(lar|ları|ı)?(?!\w)",
           r"ağrı", r"kızarıklığı", r"\bönler\b", r"güvenli(dir)?\b"],
    "en": [r"\btreat", r"\bheal", r"\bcure", r"\brepair", r"eczema", r"\bacne\b(?! ?-?prone)", r"disease",
           r"circulation", r"blood flow", r"hormon", r"muscle", r"\bpain\b", r"prevents?", r"\bsafe\b"],
    "de": [r"behandel", r"\bheil", r"repariert", r"ekzem", r"\bakne\b(?!-?neigung|-anfällig)", r"krankheit",
           r"durchblutung", r"hormon", r"muskel", r"schmerz", r"verhindert", r"\bsicher\b"],
    "ru": [r"лечени", r"лечит", r"заживл", r"восстанавлива", r"экзем", r"болезн", r"кровообращ",
           r"гормон", r"мышц", r"\bболь", r"предотвращ", r"безопас"],
    "ar": [r"علاج", r"يعالج", r"شفاء", r"إكزيما", r"مرض", r"الدورة الدموية", r"هرمون", r"عضل",
           r"ألم", r"يمنع", r"آمن"],
}


def _cumleler(metin: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.!?؟。])\s+", metin) if c.strip()]


def urun_adlari() -> list[str]:
    adlar = {"l'carlié", "l'carlie", "lcarlie"}
    for p in (KESIT_DIR.glob("*.png") if KESIT_DIR.is_dir() else []):
        adlar.add(p.stem.lower())
    adlar |= {"baby rescue", "bright smile", "hair nourisher", "kinesis+", "femisia", "vireon",
              "sunacnea", "caljaw", "calmjaw", "earclia", "aurolis", "nomore"}
    return sorted(adlar)


def _urunlu(cumle: str, adlar: list[str]) -> bool:
    """Cümlede ürün/marka adı geçiyor mu? Ürün adları Latin harfli olduğu için
    Türkçe I->ı katlaması UYGULANMAZ (HYDRAVIE -> hydravıe olurdu)."""
    k = cumle.lower()
    return any(re.search(r"(?<![\w])" + re.escape(a) + r"(?![\w])", k) for a in adlar)


def iddia_kapisi(html: str, dil: str = "tr", adlar: list[str] | None = None) -> dict[str, list]:
    """İddia kapısı.

    SERT_YASAK her cümlede, URUN_CUMLE_YASAK yalnız ürün/marka adı geçen
    cümlede aranır (brif: "bilimsel bulgu genel bilgi olarak verilir, ürüne
    etki iddiası olarak bağlanmaz"). TR'de ek olarak Jarvis'in mevzuat kapısı
    (jarvis.compliance) ÜRÜN cümlelerine uygulanır; genel cümlelerdeki
    bulguları 'kayit' olarak döndürür (engellemez, görünür kalır).
    """
    adlar = adlar or urun_adlari()
    govde, _ = govde_kaynaksiz(html)
    metin = duz_metin(govde)
    red, kayit = [], []
    katlama = (lambda s: s.replace("I", "ı").replace("İ", "i").lower()) if dil == "tr" else str.lower
    for c in _cumleler(metin):
        k = katlama(c)
        for d in SERT_YASAK.get(dil, []):
            if re.search(d, k):
                red.append({"kural": "sert yasak", "eslesen": d, "cumle": c[:220]})
        urunlu = _urunlu(c, adlar)
        if urunlu:
            for d in URUN_CUMLE_YASAK.get(dil, []):
                if re.search(d, k) and not re.search(r"eğilimli|prone|neigung|склонн|المعرضة", k):
                    red.append({"kural": "ürün cümlesinde yasak nesne", "eslesen": d, "cumle": c[:220]})
    if dil == "tr":
        try:
            from jarvis import compliance  # sunucuda
        except Exception:  # noqa: BLE001
            compliance = None
        if compliance is not None:
            for c in _cumleler(metin):
                r = compliance.review(c)
                urunlu = _urunlu(c, adlar)
                for b in r.blocked:
                    if b.rule.startswith("güneş koruyucu zorunlu"):
                        continue  # bütün metne bakılır, aşağıda
                    hedef = red if urunlu and "eğilimli" not in katlama(c) else kayit
                    hedef.append({"kural": "mevzuat:" + b.rule, "eslesen": b.matched, "cumle": c[:220]})
    return {"red": red, "kayit": kayit}


GUNES_UYARI_TR = (
    "<h3>Güneş koruyucu kullanım uyarıları</h3>"
    "<ul><li>Hiçbir ürün %100 koruma sağlamaz.</li>"
    "<li>Güneş ürününün yeterli miktarda uygulanmaması korumayı önemli ölçüde düşürür.</li>"
    "<li>Aşırı güneş maruziyeti sağlık tehdididir; öğle saatlerinde gölge, şapka ve giysiyle birlikte düşünün.</li>"
    "<li>Terleme, yüzme ve havluyla kurulanmadan sonra ve güneş altında en az 2 saatte bir yeniden uygulayın.</li>"
    "<li>Bebek ve küçük çocuklar doğrudan güneşe maruz bırakılmamalıdır.</li></ul>")


def gunes_uyarisi_ekle(html: str) -> tuple[str, bool]:
    """Güneş koruyucudan söz eden yazıya zorunlu ibare setini (TİTCK
    kılavuzu) Kaynaklar'dan hemen önce ekler. Kapı (compliance) setin
    tamamını ister; brif de 'doğru kullanım uyarıları bulunur' diyor."""
    try:
        from jarvis import compliance
    except Exception:  # noqa: BLE001
        return html, False
    govde, kaynak = govde_kaynaksiz(html)
    if not compliance._sunscreen_findings(duz_metin(govde)):
        return html, False
    yeni = govde + GUNES_UYARI_TR + kaynak
    if compliance._sunscreen_findings(duz_metin(govde_kaynaksiz(yeni)[0])):
        raise KapiRed("güneş koruyucu zorunlu ibare seti eklendi ama kapı hâlâ eksik diyor")
    return yeni, True


# ----------------------------------------------------------- kaynak kapısı
def _http_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _kelimeler(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 3}


def baslik_uyar(bulunan: str, satir: str, esik: float = 0.6) -> bool:
    b = _kelimeler(bulunan)
    if not b:
        return False
    return len(b & _kelimeler(satir)) / len(b) >= esik


def pmid_baslik(pmid: str) -> str | None:
    d = _http_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id="
                   + urllib.parse.quote(pmid))
    k = (d.get("result") or {}).get(pmid) or {}
    if k.get("error") or not k.get("title"):
        return None
    return k["title"]


def doi_baslik(doi: str) -> str | None:
    try:
        d = _http_json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/"))
        t = (d.get("message") or {}).get("title") or []
        if t:
            return t[0]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    try:  # DataCite (ör. AB yayın ofisi DOI'leri)
        d = _http_json("https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="/"))
        t = ((d.get("data") or {}).get("attributes") or {}).get("titles") or []
        if t:
            return t[0].get("title")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    return None


RESMI_ALAN = re.compile(r"(?i)(europa\.eu|titck\.gov\.tr|fda\.gov|who\.int|cir-safety\.org|ncbi\.nlm\.nih\.gov|"
                        r"nih\.gov|iso\.org|legislation\.gov\.uk|tse\.org\.tr|resmigazete\.gov\.tr|mevzuat\.gov\.tr|aad\.org|"
                        r"cosmeticseurope\.eu|efsa\.europa\.eu|ema\.europa\.eu|cdc\.gov|nhs\.uk|aap\.org|"
                        r"healthychildren\.org|bfr\.bund\.de|cancer\.org|skincancer\.org)")


def url_canli(url: str) -> bool:
    for yontem in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=yontem, headers={"User-Agent": "Mozilla/5.0 " + UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                if r.status < 400:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 405, 429) and yontem == "HEAD":
                continue
            if e.code in (401, 403, 429):
                return True  # bot engeli: sayfa var
        except Exception:  # noqa: BLE001
            pass
    return False


def kaynak_kapisi(html: str, uyku: float = 0.4) -> dict[str, Any]:
    """Kaynaklar listesindeki her maddeyi doğrular.

    PMID -> NCBI esummary başlığı satırla örtüşmeli; DOI -> Crossref/DataCite
    başlığı örtüşmeli; kimliksiz resmî kurum bağlantısı -> adres canlı olmalı.
    Çözülmeyen / başlığı tutmayan madde listeden ÇIKARILIR. Doğrulanmış madde
    sayısı EN_AZ_KAYNAK'tan azsa çağıran INSANA yapar.
    """
    govde, kaynak = govde_kaynaksiz(html)
    maddeler = re.findall(r"(?is)<li[^>]*>(.*?)</li>", kaynak)
    sonuc = {"madde": len(maddeler), "dogrulanan": 0, "cikarilan": [], "ayrinti": []}
    kalan = []
    for ham in maddeler:
        satir = duz_metin(ham)
        pmid = re.search(r"PMID:?\s*(\d{5,9})", satir)
        doi = re.search(r"(10\.\d{4,9}/[^\s\"<>]+)", htmlmod.unescape(ham))
        durum, not_ = "DOGRULANAMADI", ""
        try:
            if pmid:
                t = pmid_baslik(pmid.group(1))
                time.sleep(uyku)
                if t and baslik_uyar(t, satir):
                    durum, not_ = "PMID_OK", t[:120]
                else:
                    durum, not_ = "PMID_TUTMADI", (t or "bulunamadı")[:120]
            if durum != "PMID_OK" and doi:
                d = doi.group(1).rstrip(".,;)")
                t = doi_baslik(d)
                time.sleep(uyku)
                if t and baslik_uyar(t, satir):
                    durum, not_ = "DOI_OK", t[:120]
                elif durum == "DOGRULANAMADI":
                    durum, not_ = "DOI_TUTMADI", (t or "bulunamadı")[:120]
            if not pmid and not doi:
                link = re.search(r'href="([^"]+)"', ham)
                if link and RESMI_ALAN.search(link.group(1)) and url_canli(htmlmod.unescape(link.group(1))):
                    durum, not_ = "RESMI_URL_OK", link.group(1)[:120]
                elif link:
                    durum, not_ = "URL_RESMI_DEGIL_YA_DA_OLU", link.group(1)[:120]
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            raise DisHata("kaynak doğrulama servisi cevap vermedi: %s" % e) from e
        sonuc["ayrinti"].append({"satir": satir[:160], "durum": durum, "not": not_})
        if durum.endswith("_OK"):
            sonuc["dogrulanan"] += 1
            kalan.append(ham)
        else:
            sonuc["cikarilan"].append(satir[:160])
    if sonuc["cikarilan"]:
        baslik = re.match(r"(?is)\s*(<h2[^>]*>.*?</h2>)", kaynak)
        yeni = (baslik.group(1) if baslik else "<h2>Kaynaklar</h2>") + "<ul>" + "".join(
            "<li>%s</li>" % m for m in kalan) + "</ul>"
        sonuc["html"] = govde + yeni
    else:
        sonuc["html"] = html
    return sonuc


# --------------------------------------------------------------- HTML -> Ricos
class _Ricos(HTMLParser):
    BLOK = {"p", "h2", "h3", "h4", "li", "td", "th", "blockquote"}

    def __init__(self, link_cevir=None):
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict] = []
        self.yigin: list[dict] = []      # liste/tablo kapları
        self.metin: list[dict] | None = None
        self.blok: dict | None = None
        self.bicim: list[str] = []
        self.link: str | None = None
        self.link_cevir = link_cevir or (lambda u: u)
        self.satir: dict | None = None
        self.tablo: dict | None = None

    def _text(self, s: str):
        if self.blok is None:
            if not s.strip():
                return
            self._ac_blok("p")
        dek = []
        if "b" in self.bicim:
            dek.append({"type": "BOLD", "fontWeightValue": 700})
        if "i" in self.bicim:
            dek.append({"type": "ITALIC", "italicData": True})
        if self.link:
            dek.append({"type": "LINK", "linkData": {"link": {"url": self.link, "target": "SELF"
                        if "lcarlie.shop" in self.link else "BLANK"}}})
        s = re.sub(r"\s+", " ", s)
        if not s:
            return
        if self.metin and self.metin[-1]["textData"]["decorations"] == dek:
            self.metin[-1]["textData"]["text"] += s
        else:
            self.metin.append({"type": "TEXT", "nodes": [], "textData": {"text": s, "decorations": dek}})

    def _ac_blok(self, tag):
        self.metin = []
        if tag in ("h2", "h3", "h4"):
            self.blok = {"type": "HEADING", "nodes": self.metin,
                         "headingData": {"level": int(tag[1]), "textStyle": {"textAlignment": "AUTO"}}}
        else:
            self.blok = {"type": "PARAGRAPH", "nodes": self.metin,
                         "paragraphData": {"textStyle": {"textAlignment": "AUTO"}}}
        self.blok_tag = tag

    def _kapat_blok(self):
        if self.blok is None:
            return
        if self.metin:
            self.metin[0]["textData"]["text"] = self.metin[0]["textData"]["text"].lstrip()
            self.metin[-1]["textData"]["text"] = self.metin[-1]["textData"]["text"].rstrip()
            self.metin[:] = [t for t in self.metin if t["textData"]["text"]]
        b = self.blok
        self.blok, self.metin = None, None
        if not b["nodes"] and b["type"] == "HEADING":
            return
        hedef = self.yigin[-1] if self.yigin else None
        if hedef is None:
            if self.nodes and b["type"] in ("PARAGRAPH", "HEADING"):
                self.nodes.append({"type": "PARAGRAPH", "nodes": [], "paragraphData": {}})
            self.nodes.append(b)
        else:
            hedef["_icerik"].append(b)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("strong", "b"):
            self.bicim.append("b")
        elif tag in ("em", "i"):
            self.bicim.append("i")
        elif tag == "a":
            self.link = self.link_cevir(htmlmod.unescape(a.get("href") or "")) or None
        elif tag == "br":
            self._text(" ")
        elif tag in ("ul", "ol"):
            self._kapat_blok()
            liste = {"type": "BULLETED_LIST" if tag == "ul" else "ORDERED_LIST", "nodes": [],
                     ("bulletedListData" if tag == "ul" else "orderedListData"): {"indentation": 0}}
            self._yerlestir(liste)
            self.yigin.append({"tip": "liste", "node": liste, "_icerik": []})
        elif tag == "li":
            self._kapat_blok()
            ust = self.yigin[-1] if self.yigin else None
            if ust and ust["tip"] == "liste":
                li = {"type": "LIST_ITEM", "nodes": []}
                ust["node"]["nodes"].append(li)
                self.yigin.append({"tip": "li", "node": li, "_icerik": li["nodes"]})
            self._ac_blok("li")
        elif tag == "table":
            self._kapat_blok()
            tablo = {"type": "TABLE", "nodes": [], "tableData": {"dimensions": {}}}
            self._yerlestir(tablo)
            self.tablo = tablo
            self.yigin.append({"tip": "tablo", "node": tablo, "_icerik": []})
        elif tag == "tr" and self.tablo is not None:
            satir = {"type": "TABLE_ROW", "nodes": []}
            self.tablo["nodes"].append(satir)
            self.satir = satir
        elif tag in ("td", "th") and self.satir is not None:
            self._kapat_blok()
            stil = {"verticalAlignment": "TOP"}
            if tag == "th":
                stil["backgroundColor"] = "#EFE7DC"
            hucre = {"type": "TABLE_CELL", "nodes": [], "tableCellData": {"cellStyle": stil, "borderColors": {}}}
            self.satir["nodes"].append(hucre)
            self.yigin.append({"tip": "hucre", "node": hucre, "_icerik": hucre["nodes"], "th": tag == "th"})
            self._ac_blok("td")
            if tag == "th":
                self.bicim.append("b")
        elif tag in ("p", "h2", "h3", "h4", "blockquote"):
            self._kapat_blok()
            self._ac_blok(tag if tag != "blockquote" else "p")

    def _yerlestir(self, node):
        ust = self.yigin[-1] if self.yigin else None
        if ust is None:
            if self.nodes:
                self.nodes.append({"type": "PARAGRAPH", "nodes": [], "paragraphData": {}})
            self.nodes.append(node)
        else:  # iç içe liste: LIST_ITEM içine doğrudan konamaz -> düz paragraf olarak kalır
            ust["_icerik"].append(node)

    def handle_endtag(self, tag):
        if tag in ("strong", "b") and "b" in self.bicim:
            self.bicim.remove("b")
        elif tag in ("em", "i") and "i" in self.bicim:
            self.bicim.remove("i")
        elif tag == "a":
            self.link = None
        elif tag in ("p", "h2", "h3", "h4", "blockquote"):
            self._kapat_blok()
        elif tag == "li":
            self._kapat_blok()
            if self.yigin and self.yigin[-1]["tip"] == "li":
                li = self.yigin.pop()["node"]
                if not li["nodes"]:
                    li["nodes"].append({"type": "PARAGRAPH", "nodes": [], "paragraphData": {}})
        elif tag in ("ul", "ol"):
            self._kapat_blok()
            if self.yigin and self.yigin[-1]["tip"] == "liste":
                self.yigin.pop()
        elif tag in ("td", "th"):
            self._kapat_blok()
            if self.yigin and self.yigin[-1]["tip"] == "hucre":
                h = self.yigin.pop()
                if h.get("th") and "b" in self.bicim:
                    self.bicim.remove("b")
                if not h["node"]["nodes"]:
                    h["node"]["nodes"].append({"type": "PARAGRAPH", "nodes": [], "paragraphData": {}})
        elif tag == "tr":
            self.satir = None
        elif tag == "table":
            self._kapat_blok()
            if self.yigin and self.yigin[-1]["tip"] == "tablo":
                self.yigin.pop()
            t = self.tablo
            self.tablo = None
            if t is not None:
                sutun = max((len(r["nodes"]) for r in t["nodes"]), default=1) or 1
                for r in t["nodes"]:  # eksik hücreleri doldur
                    while len(r["nodes"]) < sutun:
                        r["nodes"].append({"type": "TABLE_CELL", "nodes": [{"type": "PARAGRAPH", "nodes": [],
                                           "paragraphData": {}}], "tableCellData": {"cellStyle": {}, "borderColors": {}}})
                # Wix güncellemede (PATCH) ondalıklı oranı "Not a numeric value" diye reddeder; tam sayı ver
                oran = [100 // sutun + (1 if i < 100 % sutun else 0) for i in range(sutun)]
                t["tableData"]["dimensions"] = {"colsWidthRatio": oran,
                                                "colsMinWidth": [120] * sutun,
                                                "rowsHeight": [47] * len(t["nodes"])}

    def handle_data(self, data):
        if self.blok is None and self.yigin and self.yigin[-1]["tip"] in ("liste", "tablo"):
            return  # kap arası boşluk
        self._text(data)


def html_to_ricos(html: str, gorseller: list[dict] | None = None, link_cevir=None) -> dict:
    """Gövde HTML'ini Ricos belgesine çevirir.

    gorseller: [{"id": wix_media_id, "width", "height", "alt", "sonra_h2": n}]
    -> n'inci H2'den hemen önce IMAGE düğümü olarak eklenir (0 = en başa).
    """
    p = _Ricos(link_cevir)
    p.feed(html)
    p.close()
    p._kapat_blok()
    nodes = p.nodes
    for g in sorted(gorseller or [], key=lambda g: -g.get("sonra_h2", 0)):
        img = {"type": "IMAGE", "nodes": [], "imageData": {
            "containerData": {"width": {"size": "CONTENT"}, "alignment": "CENTER"},
            "image": {"src": {"id": g["id"]}, "width": g["width"], "height": g["height"]},
            "altText": g.get("alt", "")[:200]}}
        hedef = g.get("sonra_h2", 0)
        if hedef <= 0:
            nodes[0:0] = [img, {"type": "PARAGRAPH", "nodes": [], "paragraphData": {}}]
            continue
        say, konum = 0, len(nodes)
        for i, n in enumerate(nodes):
            if n["type"] == "HEADING" and n["headingData"]["level"] == 2:
                say += 1
                if say == hedef:
                    konum = i
                    break
        nodes[konum:konum] = [img, {"type": "PARAGRAPH", "nodes": [], "paragraphData": {}}]
    return {"nodes": nodes}


def ricos_denetle(doc: dict) -> list[str]:
    """Belge kendi kendini denetler (Wix 'Author Ricos' öz-denetimi)."""
    sorun = []

    def gez(n, ust):
        t = n.get("type")
        if not isinstance(t, str):
            sorun.append("type dize değil")
        if t == "TEXT" and ust not in ("PARAGRAPH", "HEADING"):
            sorun.append("TEXT yanlış yerde: %s" % ust)
        if t == "TEXT" and "\n" in n["textData"]["text"]:
            sorun.append("TEXT içinde satır sonu")
        if t == "LIST_ITEM" and ust not in ("BULLETED_LIST", "ORDERED_LIST"):
            sorun.append("LIST_ITEM yanlış yerde")
        if t == "TABLE_CELL" and ust != "TABLE_ROW":
            sorun.append("TABLE_CELL yanlış yerde")
        for c in n.get("nodes") or []:
            gez(c, t)
    for n in doc["nodes"]:
        gez(n, "ROOT")
    return sorted(set(sorun))


# ------------------------------------------------------------------- Gemini
def _env(yol: str) -> dict[str, str]:
    d: dict[str, str] = {}
    try:
        with open(yol, encoding="utf-8") as f:
            satirlar = f.readlines()
        for satir in satirlar:
            satir = satir.strip()
            if "=" in satir and not satir.startswith("#"):
                k, v = satir.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return d


def gemini_anahtar() -> str:
    k = os.environ.get("GEMINI_API_KEY") or _env("/etc/lcarlie/jarvis-web.env").get("GEMINI_API_KEY")
    if not k:
        raise DisHata("GEMINI_API_KEY yok")
    return k


YAZI_MODELLERI = [m for m in os.environ.get(
    "BLOG_YAZI_MODELLERI", "gemini-pro-latest,gemini-3.1-pro-preview,gemini-2.5-pro").split(",") if m]
CEVIRI_MODELLERI = [m for m in os.environ.get(
    "BLOG_CEVIRI_MODELLERI", "gemini-pro-latest,gemini-3.1-pro-preview,gemini-3.5-flash").split(",") if m]


def gemini(istem: str, *, modeller: list[str], arama: bool = False, json_cikti: bool = True,
           sistem: str | None = None, en_cok: int = 32000, zaman: int = 600) -> tuple[str, str]:
    """Gemini çağrısı; sırayla modelleri dener. (metin, model) döner."""
    govde: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": istem}]}],
                             "generationConfig": {"maxOutputTokens": en_cok, "temperature": 0.4}}
    if sistem:
        govde["systemInstruction"] = {"parts": [{"text": sistem}]}
    if arama:
        govde["tools"] = [{"google_search": {}}]
    elif json_cikti:
        govde["generationConfig"]["responseMimeType"] = "application/json"
    if METIN_YOLU == "chatgpt":
        return chatgpt_web(istem, sistem=sistem, arama=arama, zaman=max(zaman, 1800))
    anahtar = gemini_anahtar()
    hatalar = []
    for model in modeller:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
               % (model, anahtar))
        req = urllib.request.Request(url, data=json.dumps(govde).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=zaman) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            hatalar.append("%s: HTTP %s %s" % (model, e.code, e.read()[:160]))
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            hatalar.append("%s: %s" % (model, str(e)[:120]))
            continue
        aday = (d.get("candidates") or [{}])[0]
        metin = "".join(p.get("text", "") for p in ((aday.get("content") or {}).get("parts") or [])
                        if not p.get("thought"))
        if metin.strip():
            _kullanim_yaz(model, d.get("usageMetadata") or {})
            return metin, model
        hatalar.append("%s: boş (%s)" % (model, aday.get("finishReason")))
    kredi = any("HTTP 402" in h or "HTTP 429" in h for h in hatalar)
    # Yedek: OpenRouter (sahip izinli; anahtar ücretsiz kademede). Google arama
    # desteği gerektiren YAZIM işinde yedeğe inilmez: kaynaksız yazı üretmek yerine beklenir.
    # 25.11 ölçüldü: ücretsiz yedek (nemotron) RU/AR'da terim hatası yaptı (borage -> "الحوذان"
    # = düğün çiçeği). Kalite kapısı anlamı yakalayamadığı için yedek VARSAYILAN KAPALI;
    # kredi bitince hat bekler ve sahibe haber verir. Açmak: BLOG_OPENROUTER_YEDEK=1.
    if not arama and os.environ.get("BLOG_OPENROUTER_YEDEK", "0") == "1":
        try:
            return openrouter(istem, sistem=sistem, json_cikti=json_cikti, en_cok=en_cok, zaman=zaman)
        except DisHata as e:
            hatalar.append(str(e)[:200])
    if kredi:
        raise KrediBitti("Gemini ön ödeme kredisi bitti/kota doldu ve yedek model de cevap vermedi: "
                         + " | ".join(hatalar)[:500])
    raise DisHata("Gemini cevap vermedi: " + " | ".join(hatalar)[:600])


class KrediBitti(DisHata):
    """Ücretli model kredisi bitti: deneme yakılmaz, sahibe günde bir haber verilir."""


# 25.11.2026 sahip: "O hattı Gemini'den al, ChatGPT'nin Chrome'una bağla". Metin
# işleri PC-1'deki tarayıcı worker'ına (core.tarayici_isi, hedef chatgpt_chat)
# gider; worker ayrı sekmede YENİ sohbet açar, yanıtın kod bloğunu ham döndürür.
METIN_YOLU = os.environ.get("BLOG_METIN_YOLU", "chatgpt")
MD_LINK_RE = re.compile(r"\[(https?://[^\]\s\\]+)\\*\]\((?:https?://[^)\s]+?)\\*\)")  # [url](url), JSON kaçışı \ kuyruğu dahil
CIKTI_TALIMATI = ("\n\nÇIKTI BİÇİMİ: Cevabının TAMAMINI tek bir ```json kod bloğu içinde ver; blok dışında "
                  "hiçbir şey yazma, açıklama ekleme, metni kısaltma.")


def chatgpt_web(istem: str, *, sistem: str | None = None, arama: bool = False,
                zaman: int = 1800) -> tuple[str, str]:
    """ChatGPT web (PC-1 Chrome) üzerinden üretim; (metin, "chatgpt-web") döner.

    Giriş/doğrulama istenirse ya da worker/Chrome işi hiç almazsa KrediBitti
    yükselir: deneme yakılmaz, kuyruk bekler, sahibe günde bir haber gider.
    """
    from jarvis import tarayici
    govde = "[YENI_SOHBET] " + (("SİSTEM TALİMATI: %s\n\n" % sistem) if sistem else "") + istem
    if arama:
        govde += ("\n\nKAYNAKLAR İÇİN WEB'DE ARA: PubMed/PMC, DOI ve resmî kurum sayfalarını açıp doğrula; "
                  "açamadığın kaynağı yazma.")
    govde += CIKTI_TALIMATI
    ozet = hashlib.sha256(govde.encode("utf-8")).hexdigest()[:20]
    try:
        is_ = tarayici.enqueue_browser_task(govde, "chatgpt_chat", requested_by="blog-hatti",
                                            idempotency_key="blog-metin:%s:%d" % (ozet, int(time.time())),
                                            uyum_kapisi=False)
    except tarayici.TarayiciHatasi as e:
        raise DisHata("ChatGPT işi kuyruğa yazılamadı: %s" % e) from None
    is_id = int(is_["is_id"])
    bitis = time.time() + zaman
    d: dict[str, Any] = {}
    while time.time() < bitis:
        time.sleep(15)
        d = tarayici.isi_sonucu(is_id) or {}
        durum = d.get("durum")
        if durum in ("BITTI", "SUNULDU"):
            metin = d.get("sonuc_metin") or ""
            if not metin.strip():
                raise DisHata("ChatGPT boş yanıt döndü (iş %d)" % is_id)
            # ChatGPT web, kod bloğundaki adresleri de "[url](url)" diye
            # markdown bağlantısına çeviriyor (25.11 ölçüldü: href kapısı düştü).
            metin = MD_LINK_RE.sub(r"\1", metin)
            return metin, "chatgpt-web"
        if durum == "INSAN_GEREKLI":
            raise KrediBitti("ChatGPT (PC-1 Chrome) giriş/doğrulama istiyor: %s" % (d.get("hata") or "")[:200])
        if durum == "HATA":
            raise DisHata("ChatGPT işi %d hata verdi: %s" % (is_id, (d.get("hata") or "")[:300]))
    if d.get("durum") == "BEKLIYOR":
        raise KrediBitti("ChatGPT işi %d %d sn kuyrukta bekledi; PC-1 worker/Chrome kapalı olabilir" % (is_id, zaman))
    raise DisHata("ChatGPT işi %d %d sn içinde bitmedi (durum %s)" % (is_id, zaman, d.get("durum")))


OPENROUTER_MODELLERI = [m for m in os.environ.get(
    "BLOG_OPENROUTER_MODELLERI", "nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free").split(",") if m]


def openrouter(istem: str, *, sistem: str | None = None, json_cikti: bool = True, en_cok: int = 32000,
               zaman: int = 600) -> tuple[str, str]:
    anahtar = os.environ.get("OPENROUTER_API_KEY") or _env("/etc/lcarlie/jarvis-web.env").get("OPENROUTER_API_KEY")
    if not anahtar:
        raise DisHata("OPENROUTER_API_KEY yok")
    mesaj = ([{"role": "system", "content": sistem}] if sistem else []) + [{"role": "user", "content": istem}]
    hatalar = []
    for model in OPENROUTER_MODELLERI:
        govde = {"model": model, "messages": mesaj, "max_tokens": min(en_cok, 60000), "temperature": 0.3}
        if json_cikti:
            govde["response_format"] = {"type": "json_object"}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(govde).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + anahtar, "Content-Type": "application/json",
                                              "HTTP-Referer": "https://jarvis.lcarlie.shop", "X-Title": "lcarlie-blog-hatti"})
        try:
            with urllib.request.urlopen(req, timeout=zaman) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            hatalar.append("%s: HTTP %s %s" % (model, e.code, e.read()[:120]))
            continue
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            hatalar.append("%s: %s" % (model, str(e)[:120]))
            continue
        ch = (d.get("choices") or [{}])[0]
        metin = ((ch.get("message") or {}).get("content") or "")
        if metin.strip() and ch.get("finish_reason") not in ("length",):
            return metin, "openrouter:" + model
        hatalar.append("%s: boş/kesik (%s)" % (model, ch.get("finish_reason")))
    raise DisHata("OpenRouter cevap vermedi: " + " | ".join(hatalar)[:400])


def _kullanim_yaz(model: str, u: dict) -> None:
    """Jarvis'in model kullanım defterine (varsa) yazar; yazamazsa sessiz geçer."""
    try:
        from jarvis import usage  # noqa: F401
        from jarvis.providers import PROVIDERS, _record_usage
        p = next(x for x in PROVIDERS if x.name == "gemini")
        _record_usage(p, model, time.perf_counter(), is_anahtari="blog-hatti", kademe="blog",
                      prompt_tokens=u.get("promptTokenCount"), completion_tokens=u.get("candidatesTokenCount"))
    except Exception:  # noqa: BLE001
        pass


def json_ayikla(metin: str) -> Any:
    m = re.search(r"```(?:json)?\s*(.*?)```", metin, re.S)
    ham = m.group(1) if m else metin
    bas = min([i for i in (ham.find("{"), ham.find("[")) if i >= 0], default=0)
    # ChatGPT web kod bloğunun önünde/arkasında "json", "Kopyala" gibi arayüz
    # metni kalabilir: ilk geçerli JSON değeri alınır, kuyruğu atılır.
    return json.JSONDecoder().raw_decode(ham[bas:].strip())[0]


# ---------------------------------------------------------------------- Wix
class WixHata(Exception):
    def __init__(self, kod, govde, yol):
        self.kod, self.govde, self.yol = kod, govde, yol
        super().__init__("Wix %s %s: %s" % (kod, yol, str(govde)[:300]))


class WixBlog:
    BASE = "https://www.wixapis.com"

    def __init__(self, kuru: bool = False):
        e = _env("/opt/lcarlie/n8n/.env")
        self.key = os.environ.get("WIX_API_KEY") or e.get("WIX_API_KEY")
        self.site = os.environ.get("WIX_SITE_ID") or e.get("WIX_SITE_ID")
        if not self.key or not self.site:
            raise DisHata("WIX_API_KEY/WIX_SITE_ID yok")
        self.kuru = kuru

    def call(self, yontem: str, yol: str, govde: Any = None, yazma: bool = False) -> dict:
        if self.kuru and yazma:
            return {"KURU": True, "yol": yol}
        req = urllib.request.Request(self.BASE + yol, method=yontem,
                                     data=None if govde is None else json.dumps(govde).encode("utf-8"),
                                     headers={"Authorization": self.key, "wix-site-id": self.site,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                ham = r.read()
            return json.loads(ham) if ham else {}
        except urllib.error.HTTPError as e:
            ham = e.read().decode("utf-8", "replace")
            try:
                g = json.loads(ham)
            except json.JSONDecodeError:
                g = ham[:300]
            raise WixHata(e.code, g, yol) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise DisHata("Wix ağ hatası %s: %s" % (yol, e)) from e

    # --- yetki ölçümü (okuma; yazma yapmaz)
    def yetki(self) -> dict[str, Any]:
        out = {}
        for ad, (m, y) in {"blog_okuma": ("GET", "/blog/v3/categories?paging.limit=1"),
                           "medya": ("GET", "/site-media/v1/folders?paging.limit=1"),
                           "yonlendirme": ("GET", "/seo-redirects-service/v1/redirects?paging.limit=1")}.items():
            try:
                self.call(m, y)
                out[ad] = "VAR"
            except WixHata as e:
                out[ad] = "YOK (HTTP %s)" % e.kod
        return out

    # --- medya
    def medya_ice_al(self, url: str, ad: str) -> str:
        d = self.call("POST", "/site-media/v1/files/import",
                      {"url": url, "mediaType": "IMAGE", "mimeType": "image/jpeg", "displayName": ad,
                       "private": False}, yazma=True)
        if d.get("KURU"):
            return "KURU-" + ad
        return d["file"]["id"]

    def medya_hazir_bekle(self, fid: str, sure: int = 120) -> bool:
        if fid.startswith("KURU-"):
            return True
        son = time.time() + sure
        while time.time() < son:
            d = self.call("GET", "/site-media/v1/files/get-file-by-id?" + urllib.parse.urlencode({"fileId": fid}))
            f = d.get("file") or {}
            if f.get("operationStatus") == "READY":
                return True
            if f.get("operationStatus") == "FAILED":
                raise WixHata("MEDYA", f, fid)
            time.sleep(4)
        return False

    # --- yazılar
    def post_slugdan(self, slug: str) -> dict | None:
        try:
            return self.call("GET", "/blog/v3/posts/slugs/%s?fieldsets=URL&fieldsets=SEO" % urllib.parse.quote(slug))["post"]
        except WixHata as e:
            if e.kod == 404:
                return None
            raise

    def taslak(self, pid: str) -> dict:
        return self.call("GET", "/blog/v3/draft-posts/%s?fieldsets=RICH_CONTENT&fieldsets=URL" % pid)["draftPost"]

    def taslak_olustur(self, dp: dict) -> dict:
        d = self.call("POST", "/blog/v3/draft-posts", {"draftPost": dp, "publish": False, "fieldsets": ["URL"]},
                      yazma=True)
        return d.get("draftPost") or {"id": "KURU", "KURU": True}

    def yayinla(self, pid: str) -> str:
        d = self.call("POST", "/blog/v3/draft-posts/%s/publish" % pid, {}, yazma=True)
        return d.get("postId") or pid

    def guncelle_yayinla(self, pid: str, dp: dict) -> dict:
        dp = dict(dp, id=pid)
        d = self.call("PATCH", "/blog/v3/draft-posts/%s" % pid,
                      {"draftPost": dp, "action": "UPDATE_PUBLISH", "fieldsets": ["URL"]}, yazma=True)
        return d.get("draftPost") or {}

    def cevir_kopya(self, pid: str, dil: str) -> dict:
        d = self.call("POST", "/blog/v3/multilingual/draft/%s" % pid, {"language": dil, "fieldsets": ["URL"]},
                      yazma=True)
        return d.get("draftPost") or {"id": "KURU-" + dil}

    def ceviri_bul(self, translation_id: str, dil: str) -> dict | None:
        """Aynı çeviri grubunda verilen dildeki yazı (canlı ya da taslak)."""
        for yol, anahtar in (("/blog/v3/posts/query", "posts"), ("/blog/v3/draft-posts/query", "draftPosts")):
            try:
                d = self.call("POST", yol, {"query": {"filter": {"translationId": translation_id, "language": dil},
                                                      "paging": {"limit": 5}}, "fieldsets": ["URL"]})
            except WixHata:
                continue
            for p in d.get(anahtar) or []:
                if p.get("language") == dil and p.get("translationId") == translation_id:
                    return p
        return None

    def yonlendirme(self, kaynak: str, hedef: str) -> dict:
        return self.call("POST", "/seo-redirects-service/v1/create-redirect",
                         {"redirect": {"from": kaynak, "to": hedef}}, yazma=True)


def seo_verisi(seo_baslik: str, meta: str, faq: dict | None, anahtar: str, ikincil: list[str]) -> dict:
    etiket = [{"type": "title", "children": seo_baslik, "custom": True, "disabled": False},
              {"type": "meta", "props": {"name": "description", "content": meta}, "custom": True, "disabled": False},
              {"type": "meta", "props": {"property": "og:title", "content": seo_baslik}, "custom": True, "disabled": False},
              {"type": "meta", "props": {"property": "og:description", "content": meta}, "custom": True, "disabled": False}]
    if faq:
        etiket.append({"type": "script", "props": {"type": "application/ld+json"},
                       "children": json.dumps(faq, ensure_ascii=False), "custom": True, "disabled": False})
    kelimeler = [{"term": anahtar, "isMain": True}] if anahtar else []
    kelimeler += [{"term": k, "isMain": False} for k in ikincil[:4]]
    return {"tags": etiket, "settings": {"keywords": kelimeler, "preventAutoRedirect": False}}


# --------------------------------------------------------------- canlı denetim
def http_durum(url: str, zaman: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; lcarlie-blog-hatti)"})
    try:
        with urllib.request.urlopen(req, timeout=zaman) as r:
            return r.status, r.read(600000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return 0, ""


def canli_denetle(url: str, baslik: str) -> dict:
    kod, govde = http_durum(url)
    t = re.search(r"(?is)<title[^>]*>(.*?)</title>", govde)
    hreflang = sorted(set(re.findall(r'hreflang="([a-zA-Z-]+)"', govde)))
    bas = htmlmod.unescape(t.group(1)).strip() if t else ""
    return {"url": url, "http": kod, "title": bas[:120],
            "baslik_tutuyor": bool(baslik) and baslik[:25].lower() in bas.lower(),
            "hreflang": hreflang}


# ----------------------------------------------------------- görsel dizgi
FONTLAR = {
    "baslik": FONT_DIR / "fontlar" / "MonumentExtended-Ultrabold.otf",
    "govde": FONT_DIR / "fontlar" / "Metropolis-SemiBold.otf",
    "etiket": FONT_DIR / "fontlar" / "MonumentExtended-Regular.otf",
    "ru": FONT_DIR / "fontlar-ek" / "Montserrat.ttf",
    "ar": FONT_DIR / "fontlar-ek" / "Cairo.ttf",
}


def _font(dil: str, rol: str, boy: int):
    from PIL import ImageFont
    if dil in ("ru", "ar"):
        f = ImageFont.truetype(str(FONTLAR[dil]), boy,
                               layout_engine=ImageFont.Layout.RAQM if dil == "ar" else ImageFont.Layout.BASIC)
        try:  # değişken font: wght ekseni (Cairo'da slnt ekseni de var, ilk eksen wght değilse ad ile seç)
            agirlik = 800 if rol == "baslik" else 600
            deger = []
            for a in f.get_variation_axes():
                ad = a.get("name", b"")
                ad = ad.decode("latin-1") if isinstance(ad, bytes) else str(ad)
                deger.append(agirlik if ad.lower().startswith("weight") else a.get("default", 0))
            f.set_variation_by_axes(deger)
        except Exception:  # noqa: BLE001
            pass
        return f
    return ImageFont.truetype(str(FONTLAR[rol]), boy)


def _sar(cizim, metin: str, font, genislik: int) -> list[str]:
    satirlar, sat = [], ""
    for k in metin.split():
        aday = (sat + " " + k).strip()
        if cizim.textlength(aday, font=font) <= genislik or not sat:
            sat = aday
        else:
            satirlar.append(sat)
            sat = k
    if sat:
        satirlar.append(sat)
    return satirlar


def _kapla(im, w: int, h: int, odak_x: float = 0.6):
    from PIL import Image
    oran = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * oran), round(im.height * oran)), Image.LANCZOS)
    x = int((im.width - w) * odak_x)
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def kesit_yukle(ad: str):
    from PIL import Image
    p = KESIT_DIR / (ad + ".png")
    if not p.is_file():
        return None
    im = Image.open(p).convert("RGBA")
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return im.crop(bbox) if bbox else im


def _urun_yapistir(zemin, kesitler: list[str], sag: bool, alan_h: float = 0.72):
    """Gerçek kesik PNG'yi (piksel birebir) sahneye yapıştırır; yumuşak gölge ekler."""
    from PIL import Image, ImageFilter
    W, H = zemin.size
    urunler = [u for u in (kesit_yukle(a) for a in kesitler[:2]) if u is not None]
    if not urunler:
        return zemin, []
    yer = []
    hedef_h = int(H * alan_h) if len(urunler) == 1 else int(H * alan_h * 0.88)
    olcekli = []
    for u in urunler:
        o = hedef_h / u.height
        if u.width * o > W * 0.30:
            o = W * 0.30 / u.width
        olcekli.append(u.resize((max(1, int(u.width * o)), max(1, int(u.height * o))), Image.LANCZOS))
    toplam_w = sum(u.width for u in olcekli) + 24 * (len(olcekli) - 1)
    x = (W - toplam_w - int(W * 0.06)) if sag else int(W * 0.06)
    taban = H - int(H * 0.07)
    for u in olcekli:
        y = taban - u.height
        golge = Image.new("RGBA", zemin.size, (0, 0, 0, 0))
        maske = u.getchannel("A").point(lambda a: int(a * 0.35))
        golge.paste((40, 30, 20, 255), (x + 14, y + 18), maske)
        golge = golge.filter(ImageFilter.GaussianBlur(16))
        zemin = Image.alpha_composite(zemin, golge)
        zemin.alpha_composite(u, (x, y))
        yer.append((x, y, u.width, u.height))
        x += u.width + 24
    return zemin, yer


def kapak_diz(sahne_yolu: str, baslik: str, dil: str, kesitler: list[str], renk: tuple[int, int, int],
              cikti: str, etiket_metni: str = "L'CARLIÉ BLOG", W: int = 1200, H: int = 630) -> dict:
    """1200x630 kapak: sahne + yarı saydam panel + vurgu çubuğu + başlık +
    gerçek ürün kesiti. Arapçada düzen aynalanır."""
    from PIL import Image, ImageDraw
    rtl = dil == "ar"
    sahne = Image.open(sahne_yolu).convert("RGB")
    zemin = _kapla(sahne, W, H, odak_x=0.35 if rtl else 0.65).convert("RGBA")
    # panel: metin tarafında krem degrade
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pw = int(W * 0.56)
    for i in range(pw + 160):
        a = 236 if i < pw else int(236 * (1 - (i - pw) / 160))
        x = (W - 1 - i) if rtl else i
        pd.line([(x, 0), (x, H)], fill=(246, 241, 234, a))
    zemin = Image.alpha_composite(zemin, panel)
    zemin, yer = _urun_yapistir(zemin, kesitler, sag=not rtl)
    d = ImageDraw.Draw(zemin)
    pad = 64
    metin_w = pw - pad - 40
    cubuk_x = (W - pad - 10) if rtl else pad
    baslik = baslik.replace("·", "–")
    boy = 50 if dil not in ("ru", "ar") else 54
    while True:
        f = _font(dil, "baslik" if dil in ("ru", "ar") else "govde", boy)
        satirlar = _sar(d, baslik, f, metin_w - 30)
        if len(satirlar) <= 4 or boy <= 30:
            break
        boy -= 4
    ef = _font(dil, "etiket" if dil not in ("ru", "ar") else "govde", 17)
    satir_h = int(boy * (1.5 if rtl else 1.18))
    blok_h = 34 + len(satirlar) * satir_h
    y0 = (H - blok_h) // 2
    d.rectangle([cubuk_x, y0, cubuk_x + 10, y0 + blok_h], fill=renk + (255,))
    tx = (W - pad - 30) if rtl else pad + 30
    if rtl:
        d.text((tx, y0), etiket_metni, font=ef, fill=renk + (255,), anchor="ra")
    else:
        d.text((tx, y0), etiket_metni, font=ef, fill=renk + (255,))
    y = y0 + 34
    for s in satirlar:
        if rtl:
            d.text((tx, y), s, font=f, fill=(38, 34, 30, 255), anchor="ra", direction="rtl", language="ar")
        else:
            d.text((tx, y), s, font=f, fill=(38, 34, 30, 255))
        y += satir_h
    zemin.convert("RGB").save(cikti, "JPEG", quality=86, optimize=True, progressive=True)
    return {"yol": cikti, "w": W, "h": H, "urun_yeri": yer, "satir": len(satirlar), "font_boy": boy}


def ic_gorsel_diz(sahne_yolu: str, kesitler: list[str], cikti: str, W: int = 1200, H: int = 800) -> dict:
    from PIL import Image
    zemin = _kapla(Image.open(sahne_yolu).convert("RGB"), W, H, 0.5).convert("RGBA")
    zemin, yer = _urun_yapistir(zemin, kesitler, sag=True, alan_h=0.62)
    zemin.convert("RGB").save(cikti, "JPEG", quality=86, optimize=True, progressive=True)
    return {"yol": cikti, "w": W, "h": H, "urun_yeri": yer}


def kesit_birebir_mi(cikti: str, kesit_ad: str, yer: tuple[int, int, int, int]) -> float:
    """Yapıştırılan ürün bölgesi ile kesitin aynı boyuta ölçeklenmiş hali
    arasındaki ortalama mutlak fark (0 = birebir). JPEG kaybı ~3-6."""
    from PIL import Image, ImageChops, ImageStat
    x, y, w, h = yer
    k = kesit_yukle(kesit_ad).resize((w, h), Image.LANCZOS)
    bolge = Image.open(cikti).convert("RGB").crop((x, y, x + w, y + h))
    maske = k.getchannel("A").point(lambda a: 255 if a > 250 else 0)
    ref = Image.new("RGB", (w, h))
    ref.paste(k.convert("RGB"), (0, 0))
    fark = ImageChops.difference(bolge, ref)
    st = ImageStat.Stat(fark, mask=maske)
    return round(sum(st.mean) / 3, 2)


# ------------------------------------------------------------------ kuyruk
class Kuyruk:
    """core.blog_kuyruk üzerinde ince katman. Değerler SQL metnine
    dolar-tırnaklı (rastgele etiketli) literal olarak girer; etiket metinde
    geçiyorsa yenisi üretilir."""

    JSON_ALAN = {"icerik", "ceviriler", "gorsel", "wix", "kapilar", "gecmis"}
    DUZ_ALAN = {"kaynak", "plan_no", "oncelik", "konu", "tur", "mevcut_slug", "kategori_id", "durum",
                "deneme", "hata", "bekleme_sebebi", "kaynak_dosya", "kaynak_sha", "yayinlandi", "gorsel_deneme"}

    def __init__(self, kuru: bool = False):
        self.kuru = kuru

    @staticmethod
    def _lit(deger: Any) -> str:
        if deger is None:
            return "NULL"
        s = deger if isinstance(deger, str) else json.dumps(deger, ensure_ascii=False)
        while True:
            etk = "$b%s$" % hashlib.sha1(os.urandom(8)).hexdigest()[:8]
            if etk not in s:
                return etk + s + etk

    def sql(self, sorgu: str) -> str:
        s = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
                            "-v", "ON_ERROR_STOP=1", "-tAq"], input=sorgu, capture_output=True, text=True,
                           timeout=120)
        if s.returncode:
            raise DisHata("psql: " + (s.stderr or "")[:300])
        return s.stdout.strip()

    def satirlar(self, kosul: str = "TRUE", sira: str = "oncelik, id") -> list[dict]:
        ham = self.sql("SELECT coalesce(json_agg(t ORDER BY %s), '[]') FROM core.blog_kuyruk t WHERE %s;"
                       % (sira, kosul))
        return json.loads(ham or "[]")

    def bir(self, slug: str) -> dict | None:
        r = self.satirlar("slug = %s" % self._lit(slug))
        return r[0] if r else None

    def guncelle(self, slug: str, **alan) -> None:
        parca = []
        for k, v in alan.items():
            if k in self.JSON_ALAN:
                parca.append("%s = coalesce(%s,'{}'::jsonb) || %s::jsonb" % (k, k, self._lit(v)))
            elif k in self.DUZ_ALAN:
                parca.append("%s = %s" % (k, "now()" if v == "NOW()" else self._lit(v)))
            else:
                raise KeyError(k)
        parca.append("guncellendi = now()")
        if self.kuru:
            return
        self.sql("UPDATE core.blog_kuyruk SET %s WHERE slug = %s;" % (", ".join(parca), self._lit(slug)))

    def olay(self, slug: str, olay: str) -> None:
        if self.kuru:
            return
        self.sql("UPDATE core.blog_kuyruk SET gecmis = coalesce(gecmis,'{}'::jsonb) || jsonb_build_object("
                 "to_char(clock_timestamp(),'YYYY-MM-DD\"T\"HH24:MI:SS.MS'), %s::text) WHERE slug = %s;"
                 % (self._lit(olay[:500]), self._lit(slug)))

    def ekle(self, satir: dict) -> str:
        """slug'a göre idempotent ekler; var olan satırın yalnız HAZIR kaynak
        içeriği değiştiyse (sha farkı) ve henüz yayınlanmadıysa içeriği yeniler."""
        alanlar = ["slug", "kaynak", "plan_no", "oncelik", "konu", "tur", "mevcut_slug", "kategori_id", "durum",
                   "kaynak_dosya", "kaynak_sha", "icerik", "bekleme_sebebi"]
        deger = [self._lit(satir.get(a)) + ("::jsonb" if a == "icerik" else "") for a in alanlar]
        sorgu = ("INSERT INTO core.blog_kuyruk (%s) VALUES (%s) ON CONFLICT (slug) DO UPDATE SET "
                 "icerik = EXCLUDED.icerik, kaynak_sha = EXCLUDED.kaynak_sha, kaynak_dosya = EXCLUDED.kaynak_dosya, "
                 "oncelik = EXCLUDED.oncelik, guncellendi = now() "
                 "WHERE core.blog_kuyruk.kaynak_sha IS DISTINCT FROM EXCLUDED.kaynak_sha "
                 "AND core.blog_kuyruk.durum IN ('BEKLIYOR','YAZILDI','INSANA','HATA') "
                 "RETURNING (xmax = 0)::text;" % (", ".join(alanlar), ", ".join(deger)))
        if self.kuru:
            return "KURU"
        r = self.sql(sorgu)
        return {"true": "EKLENDI", "false": "GUNCELLENDI"}.get(r, "DEGISMEDI")


def yukleme_log(kaynak: str, durum: str, okunan: int, yazilan: int, mesaj: str, baslangic: str) -> None:
    k = Kuyruk()
    k.sql("INSERT INTO raw.yukleme_log (kaynak, durum, okunan, yazilan, guncellenen, mesaj, baslangic) "
          "VALUES (%s, %s, %d, %d, 0, %s, %s::timestamptz);"
          % (k._lit(kaynak), k._lit(durum), okunan, yazilan, k._lit(mesaj[:1000]), k._lit(baslangic)))
