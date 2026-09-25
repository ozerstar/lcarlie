"""A real search+crawl source for the existing Research Controller.

This is one CapabilityAdapter, not a research framework: the controller
already owns adaptive expansion, confidence, contradiction, cache, diff and
bounded parallelism. All this adds is the thing that was missing -- an
adapter that actually reaches the internet.

    query -> search -> result URLs -> safe fetch -> extracted text
          -> near-duplicate removal -> normalized source rows

Search backend is pluggable through the environment, with no code change:
RESEARCH_SEARXNG_URL points at a self-hosted SearXNG JSON endpoint; without
it the adapter falls back to DuckDuckGo's keyless HTML endpoint.

SECURITY
Every URL passes the controller's own canonicalize_url before it is fetched,
so the SSRF rules (no localhost, private, reserved or link-local targets, no
credentials in URL, HTTP(S) only) are enforced by the same code that the
controller uses -- not by a second implementation. Redirects are followed
manually so each hop is re-validated. Page content is data: nothing read from
a page is ever executed, and the controller flags injection markers.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import unicodedata
import socket
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from time import perf_counter
from typing import Any

from concurrent.futures import ThreadPoolExecutor

from . import gunluk
from .adapter_factory import AdapterEvidence, AdapterState, CapabilityAdapter
from .research_controller import RESEARCH_CAPABILITY, UnsafeUrl, canonicalize_url

USER_AGENT = "LCarlieResearchBot/1.0 (+https://lcarlie.shop; contact=owner)"
MAX_REDIRECTS = 3
MAX_BYTES = 400_000
DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_SEARCH_MODEL = os.environ.get("RESEARCH_GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_TIMEOUT = float(os.environ.get("RESEARCH_GEMINI_TIMEOUT", "45"))

_TAG_STRIP = re.compile(r"(?is)<(script|style|noscript|template|svg)[^>]*>.*?</\1>")
_TAGS = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK = re.compile(r"\n{3,}")
_WORD = re.compile(r"\w{3,}", re.UNICODE)
_NUMERIC_CLAIM = re.compile(
    r"([\wÀ-ɏ]{3,}(?:\s+[\wÀ-ɏ]{3,}){0,2})\s*[:\-–]?\s*"
    r"(%\s?\d+[.,]?\d*|\d+[.,]?\d*\s?%|\d[\d.,]{2,}\s?(?:TL|USD|EUR|₺|\$|€))",
    re.UNICODE)


class SearchError(RuntimeError):
    pass


class _MetaParser(HTMLParser):
    """Title, canonical link and publication date -- nothing executed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.canonical = ""
        self.published = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = values.get("href", "")
        elif tag == "meta":
            name = (values.get("property") or values.get("name") or "").lower()
            if name in {"article:published_time", "datepublished", "pubdate",
                        "og:published_time", "date"} and not self.published:
                self.published = values.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self.title) < 300:
            self.title += data


def extract_text(html: str) -> str:
    stripped = _TAG_STRIP.sub(" ", html)
    text = unescape(_TAGS.sub("\n", stripped))
    text = _WS.sub(" ", text)
    return _BLANK.sub("\n\n", "\n".join(line.strip() for line in text.splitlines())).strip()


# --- istege bagli: daha iyi ana metin ve YAYIN TARIHI -------------------
# Yoklugu bir hata degil, bir durumdur: kurulu degilse asagidaki iki yardimci
# eski davranisi aynen surdurur.
try:  # pragma: no cover - yorumlayiciya gore degisir
    import trafilatura as _TRAFILATURA
except Exception:  # noqa: BLE001
    _TRAFILATURA = None

# trafilatura'nin donusu bu esigin altindaysa guvenilmez sayilir ve mevcut
# cikariciya dusulur. OLCULDU: teis.org.tr'de 0 karakter dondu; o sayfa
# olcumde gelen en degerli kaynaklardan biriydi.
_MIN_MAIN_TEXT = 200


def best_text(html: str) -> str:
    """Ana metin. trafilatura kullanilabiliyorsa o, degilse mevcut cikarici.

    trafilatura menu/altbilgi/urun listesi gurultusunu temizler -- olcumde
    bir magaza sayfasinin sisirilmis alaka puani 0,430'dan 0,052'ye indi,
    yani dogru yere. Ama bazi sayfalarda hic metin dondurmuyor; o yuzden
    donusu dogrulanmadan kullanilmaz.
    """
    if _TRAFILATURA is not None:
        try:
            main = _TRAFILATURA.extract(html, include_comments=False,
                                        include_tables=True) or ""
        except Exception:  # noqa: BLE001 - cikarim asla arastirmayi durdurmaz
            main = ""
        if len(main) >= _MIN_MAIN_TEXT:
            return main
    return extract_text(html)


def published_date(html: str) -> str:
    """Sayfanin yayin tarihi (YYYY-MM-DD) veya bos.

    OLCULDU: mevcut _MetaParser 6 sayfanin 0'inda tarih buluyordu,
    trafilatura 5'inde buldu. Tarihsiz kaynak "guncel mi" sorusuna cevap
    veremez ve 2023 tarihli bir pazar raporu bugunku gibi sunulur.
    """
    if _TRAFILATURA is None:
        return ""
    try:
        meta = _TRAFILATURA.extract_metadata(html)
    except Exception:  # noqa: BLE001
        return ""
    return (getattr(meta, "date", None) or "") if meta else ""


def _token_set(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


# Turkce sondan eklemelidir: sorgudaki "etiketlerinde" ile sayfadaki "etiket"
# ayni seydir, ama tam kelime esitligi bunu goremez. OLCULDU: bu yuzden
# "titck kozmetik iddia yasaklari" aramasinda TITCK kilavuzunun kendisi dahil
# cekilen 12 sayfanin 12'si "konu disi" diye atildi; geriye yalniz eksiz
# kelime tasiyan magaza sayfalari kaldi.
#
# Sabit uzunlukta govde (ilk 5 harf) Turkce bilgi erisiminde yerlesik bir
# yontemdir; tam bicimbirim cozumlemesine yakin sonuc verir ve hicbir
# bagimlilik gerektirmez. Kisa kelimeler oldugu gibi kalir.
STEM_LEN = 5

_TR_FOLD = str.maketrans(
    "\u0131\u0130\u015f\u015e\u011f\u011e\u00fc\u00dc\u00f6\u00d6\u00e7\u00c7",
    "iissgguuoocc")


def _fold_tr(word: str) -> str:
    """Aksansiz karsilastirma govdesi.

    Cevirme casefold'dan ONCE yapilir: "\u0130".casefold() birlesik nokta
    tasiyan iki karakter uretir ve duz "i" ile ESLESMEZ -- bu tuzak bu
    kod tabaninda daha once uyumluluk taramasini da yanlis calistirmisti.
    Kalan birlesik isaretler NFD ile ayiklanir.
    """
    folded = unicodedata.normalize("NFD", word.translate(_TR_FOLD).casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _stem(word: str) -> str:
    return _fold_tr(word)[:STEM_LEN]


def _stem_set(text: str, min_len: int = 4) -> set[str]:
    return {_stem(word) for word in _WORD.findall(text.casefold())
            if len(word) >= min_len}


def _query_groups(text: str, min_len: int = 4) -> tuple[frozenset[str], ...]:
    """Her sorgu kelimesi icin bir govde KUMESI -- duzlestirilmis tek kume degil.

    "urunlerin" hem "urunl" hem (bicimbilgisi varsa) "urun" verir; ikisi ayni
    kelimenin bicimleridir, iki ayri terim degil. Kelime, kumesinden herhangi
    biri sayfada geciyorsa eslesmis sayilir ve payda kelime sayisi olarak
    kalir.

    Duzlestirme OLCULDU ve zarar verdi: varyantlar terim sayisini sisirince
    ayni sayfalarin puani dustu, tutulan kaynak 3'ten 1'e indi.

    Bicimbilgisi yoksa (test yorumlayicisinda zeyrek kurulu degil) her grup
    tek govdeye iner ve davranis eski haliyle ayni kalir.
    """
    try:
        from .turkish import lemmas
    except Exception:  # noqa: BLE001 - bicimbilgisi istege baglidir
        lemmas = None  # type: ignore[assignment]

    groups: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    for word in _WORD.findall(text.casefold()):
        if len(word) < min_len:
            continue
        stems = {_stem(word)}
        if lemmas is not None:
            stems.update(_stem(lemma) for lemma in lemmas(word) if len(lemma) >= 3)
        group = frozenset(stems)
        if group not in seen:
            seen.add(group)
            groups.append(group)
    return tuple(groups)


def _hit_ratio(groups: tuple[frozenset[str], ...], stems: set[str]) -> float:
    """Kac sorgu kelimesi bu metinde gecti? Varyant sayisi degil, KELIME sayisi."""
    if not groups:
        return 0.0
    return sum(1 for group in groups if group & stems) / len(groups)


def _stem_list(text: str, min_len: int = 4) -> list[str]:
    return [_stem(word) for word in _WORD.findall(text.casefold())
            if len(word) >= min_len]


def near_duplicate(a: str, b: str, threshold: float = 0.9) -> bool:
    """Jaccard overlap on word tokens. Catches the same wire story republished
    with a different headline, which must not count as independent evidence."""
    left, right = _token_set(a), _token_set(b)
    if not left or not right:
        return False
    intersection = len(left & right)
    union = len(left | right)
    return union > 0 and intersection / union >= threshold


def anchor_terms(query: str, count: int = 3) -> tuple[str, ...]:
    """The query's most distinctive words, approximated by length.

    In "Türkiye premium dermokozmetik ... pazarı ... fırsat sinyalleri" the
    word that decides topicality is `dermokozmetik`, not `pazarı`. Length is a
    crude proxy for specificity, but it is deterministic and needs no corpus.
    """
    terms = sorted({term for term in _token_set(query) if len(term) > 3},
                   key=lambda term: (-len(term), term))
    return tuple(terms[:count])


# Facets a market research request can ask about. A facet is only used when
# the request actually contains one of its cues -- there is no fixed query
# list, so "rakip fiyatlarını bul" does not also search regulation.
FACETS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("market", ("pazar", "market", "gelişme", "gelisme", "büyüme", "buyume",
                "trend", "sektör", "sektor", "rapor"), "pazar raporu son gelişmeler"),
    ("competitor", ("rakip", "competitor", "marka", "lansman", "launch",
                    "hareket", "yeni ürün", "yeni urun"), "rakip markalar yeni ürün lansmanı"),
    ("pricing", ("fiyat", "price", "indirim", "kampanya", "promosyon",
                 "zam", "ücret", "ucret"), "fiyat kampanya indirim"),
    ("consumer", ("tüketici", "tuketici", "consumer", "talep", "tercih",
                  "davranış", "davranis", "trend"), "tüketici talebi kategori trendi"),
    ("retail", ("eczane", "perakende", "retail", "e-ticaret", "eticaret",
                "mağaza", "magaza", "satış kanalı", "pharmacy"), "eczane perakende e-ticaret satış"),
    ("regulatory", ("mevzuat", "regülasyon", "regulasyon", "yönetmelik",
                    "yonetmelik", "titck", "denetim", "yasak"), "kozmetik mevzuat yönetmelik"),
)

DEFAULT_FACETS = ("market", "competitor")


# Words that describe HOW to research, not WHAT to research. Without this the
# length proxy picks "kaynaklarıyla" out of "kanıtları kaynaklarıyla döndür"
# and every generated query -- and every relevance score -- is about the wrong
# noun. Measured: it produced 0 usable sources from 15 crawled pages.
_NON_SUBJECT_STEMS = frozenset(
    {cue[:6] for _, cues, _ in FACETS for cue in cues}
    | {"araştı", "arasti", "göster", "goster", "öneml", "onemli",
       "güncel", "guncel", "sinyal", "acisin", "açısın",
       "kaynak", "kanıtl", "kanitl", "kopya", "çeliş", "celis",
       "doğrul", "dogrul", "kullan", "döndür", "dondur", "ayrı",
       "ayri", "sayma", "bilgi", "durum", "bağıms", "bagims",
       "orijin", "haberi", "yapmak", "olarak",
       # Olculdu: bu ikisi uzunluk olcutunu gecip konu sanildi --
       # "dermokozmetik birbirinden pazar raporu", "dermokozmetik bulgulari".
       "birbir", "bulgul"}
)


def research_subject(request: str, count: int = 3) -> tuple[str, ...]:
    """The distinctive nouns a request is actually about.

    Used both to build search queries and to score pages. Scoring against the
    whole request is what broke V2's first run: a 40-word instruction sentence
    makes every page look irrelevant, because no page contains "kopyalarını"
    or "döndür".
    """
    # Pool size is measured, not guessed. At 25 the instruction vocabulary of a
    # long Turkish request survives filtering and pollutes both the queries and
    # the relevance terms; at 10 the surviving subject is tight. A wider topic
    # also HURTS scoring, because one unmatchable token (a brand name) caps
    # every page's title and lead score.
    terms = [term for term in anchor_terms(request, count=10)
             if not any(term.startswith(stem) for stem in _NON_SUBJECT_STEMS)]
    return tuple(terms[:count]) or anchor_terms(request, count=count)


# Son sorgu planinin teshis kaydi (kaynak: model/deterministik, elenenler).
# Arastirma ciktisinda raporlanir; sorgu kalitesi boyle izlenir.
LAST_PLAN: dict[str, object] = {}


def _decompose_best(request: str, max_queries: int = 5) -> tuple[str, ...]:
    """Model decomposition when the model layer has it, deterministic otherwise.

    This is the connection the docstring below anticipated -- the adapter still
    only consumes the returned tuple. A model that is down, slow or produces
    nothing usable falls straight back to the deterministic path, so research
    never depends on a model being available.
    """
    try:
        from .model_layer import ModelRouter

        # OLCULDU: sorgulari kisa anahtar kelimelere cevirmek ZARAR VERDI.
        # Iki bagimsiz kosuda bilgi kaynagi ortalamasi 2,17'den 1,17'ye dustu.
        # (Ucuncu bir kosu gurultu tabanini +-0,2 olarak olctu; bu fark onun
        # bes kati ve iki kosuda da ayni yonde.) Arama motoru uzun tarif
        # cumlesini MAKALE metniyle eslestiriyor, kisa urun ismini ise
        # alisveris niyeti gibi okuyup MAGAZA getiriyor.
        #
        # Verimdeki asil kazanc Turkce govde eslesmesindendi (score_source,
        # _stem) ve o, buradaki cumleleri de ayni sekilde iyilestirdi.
        # Rakamlar ve gerekce: jarvis/query_planner.py.
        if os.environ.get("RESEARCH_QUERY_PLANNER") == "1":
            from .query_planner import plan
            result = plan(request, ModelRouter(), max_queries=max_queries)
            LAST_PLAN.clear()
            LAST_PLAN.update(result)
            if result["queries"]:
                return tuple(result["queries"])[:max_queries]
        else:
            queries = ModelRouter().decompose_query(request, count=max_queries)
            usable = tuple(q.strip() for q in queries
                           if isinstance(q, str) and q.strip())
            if usable:
                return usable[:max_queries]
    except Exception:  # noqa: BLE001 - decomposition must never break research
        pass
    return decompose(request, max_queries)


def decompose(request: str, max_queries: int = 5) -> tuple[str, ...]:
    """Turn one long natural-language request into focused search queries.

    Deterministic: no model. A long Turkish sentence is a poor search query --
    the first benchmark proved it, returning a real-estate article and the
    Wikipedia page for Turkey. The subject is the request's distinctive terms;
    each selected facet becomes one query against that subject.

    If the AI model layer later exposes a QUERY_DECOMPOSITION capability, it
    can replace this function without touching anything else: the rest of the
    adapter only consumes the returned tuple.
    """
    normalized = " ".join(request.split())
    lowered = normalized.casefold()
    # A word that signals a facet is not the subject. Without this the
    # length proxy picks the inflected "kampanyalarını" (14 chars) over
    # "dermokozmetik" (13) and every generated query searches the wrong noun.
    cue_stems = _NON_SUBJECT_STEMS

    subject = " ".join(research_subject(normalized, count=2))

    chosen = [name for name, cues, _ in FACETS
              if any(cue in lowered for cue in cues)] or list(DEFAULT_FACETS)
    modifiers = {name: modifier for name, _, modifier in FACETS}

    queries = [f"{subject} {modifiers[name]}".strip() for name in chosen[:max_queries]]
    # The bare subject is deliberately NOT searched when a facet exists.
    # Measured: "dermokozmetik" on its own returned five online pharmacies and
    # nothing else -- a plain product noun is a shopping query, and shops do
    # not report what changed in a market. Without a facet it is all we have.
    if not queries and subject:
        queries = [subject]
    return tuple(dict.fromkeys(queries))[:max_queries]


# ------------------------------------------------------------- source typing
MARKETPLACE_HOSTS = ("trendyol.", "hepsiburada.", "amazon.", "n11.", "ciceksepeti.",
                     "pazarama.", "gittigidiyor.", "etsy.")
REGULATOR_HOSTS = ("titck.gov.tr", "saglik.gov.tr", "ticaret.gov.tr", "resmigazete.gov.tr",
                   "tuik.gov.tr", "rekabet.gov.tr")
COMMUNITY_HOSTS = ("reddit.", "eksisozluk.", "forum.", "quora.", "facebook.",
                   "instagram.", "x.com", "twitter.", "youtube.")
NEWS_MARKERS = ("muhabir", "haber merkezi", "son dakika", "yayınlanma tarihi",
                "güncelleme tarihi", "editör", "ajans")
TRADE_MARKERS = ("sektör raporu", "sektor raporu", "pazar araştırması", "pazar arastirmasi",
                 "ciro", "pazar payı", "pazar payi", "büyüme oranı", "ihracat")
# "1.249,00 TL" / "349 ₺" / "₺1.899" -- a listed price, not a statistic.
PRICE_TAG = re.compile(r"(?:\d[\d.]{1,7},\d{2}\s?(?:TL|₺)|\d[\d.]{1,7}\s?(?:TL|₺)|₺\s?\d[\d.]{1,7})", re.IGNORECASE)

SHOP_MARKERS = ("sepete ekle", "sepete at", "satın al", "satin al", "stokta",
                "ücretsiz kargo", "ucretsiz kargo", "taksit")
COMPANY_MARKERS = ("hakkımızda", "hakkimizda", "markamız", "markamiz",
                   "ürünlerimiz", "urunlerimiz", "bize ulaşın", "bize ulasin")

SOURCE_TYPES = ("OFFICIAL", "REGULATOR", "COMPANY", "NEWS", "TRADE_PUBLICATION",
                "RETAILER", "MARKETPLACE", "COMMUNITY", "UNKNOWN")


# Meslek birligi / oda / dernek. Turkiye'de bu sonek tahsislidir: teis.org.tr
# (eczacilar), uste.org.tr. Bu kaynaklar sektor verisi yayimlar ve olcumde
# gelen en degerli sayfalar bunlardi -- ama hepsi UNKNOWN donuyordu.
ASSOCIATION_SUFFIXES = (".org.tr", ".edu.tr", ".bel.tr", ".tsk.tr")

# schema.org tipleri -> bizim sinifimiz. Sayfanin KENDI beyanidir; bir
# magazanin "Product" basmasi kelime listesinden cok daha guvenilirdir.
_LD_TYPE_MAP = {
    "product": "RETAILER", "offer": "RETAILER", "aggregateoffer": "RETAILER",
    "itemlist": "RETAILER", "onlinestore": "RETAILER",
    "newsarticle": "NEWS", "reportagenewsarticle": "NEWS",
    "article": "NEWS", "blogposting": "NEWS", "techarticle": "NEWS",
    "governmentorganization": "REGULATOR", "govermentservice": "REGULATOR",
    "legislation": "OFFICIAL", "medicalwebpage": "NEWS",
    "discussionforumposting": "COMMUNITY", "qapage": "COMMUNITY",
}

_LD_BLOCK = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL)
_OG_TYPE = re.compile(
    r"<meta[^>]+property=[\"']og:type[\"'][^>]+content=[\"']([^\"']+)",
    re.IGNORECASE)


def _ld_types(html: str) -> set[str]:
    found: set[str] = set()
    for blob in _LD_BLOCK.findall(html or "")[:12]:
        try:
            data = json.loads(blob.strip())
        except Exception:  # noqa: BLE001 - bozuk JSON-LD yaygin, sinyal yok demektir
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            for item in [node] + (graph if isinstance(graph, list) else []):
                if not isinstance(item, dict):
                    continue
                declared = item.get("@type")
                if not declared:
                    continue
                for name in (declared if isinstance(declared, list) else [declared]):
                    if isinstance(name, str):
                        found.add(name.casefold())
    return found


def structural_signals(html: str) -> dict[str, object]:
    """Sayfanin kendi beyan ettigi tip sinyalleri. Dilden bagimsiz."""
    types = _ld_types(html)
    og = _OG_TYPE.search(html or "")
    return {"ld_types": sorted(types),
            "og_type": (og.group(1).casefold() if og else "")}


def prices_declared(body: str) -> bool:
    """Sayfa fiyat listeliyor mu? Magaza ile sirket tanitimini ayirir."""
    return len(PRICE_TAG.findall(body)) >= 4


def classify_source(host: str, title: str, text: str, html: str = "") -> str:
    """Deterministic source class from host and page markers.

    Used as reliability metadata, and to keep a company's own statement from
    being treated as independent confirmation of itself.
    """
    host = (host or "").casefold()
    body = (title + " " + text[:6000]).casefold()

    if any(marker in host for marker in REGULATOR_HOSTS):
        return "REGULATOR"
    if host.endswith(".gov.tr") or host.endswith(".gov") or host.endswith(".gov.uk"):
        return "OFFICIAL"
    if any(marker in host for marker in MARKETPLACE_HOSTS):
        return "MARKETPLACE"
    if any(marker in host for marker in COMMUNITY_HOSTS):
        return "COMMUNITY"
    if host.endswith(ASSOCIATION_SUFFIXES):
        # Meslek birligi: sektor verisi yayimlar, sirketin kendi beyani degil.
        return "TRADE_PUBLICATION"

    # --- sayfanin KENDI beyani: kelime listesinden once, cunku dilden
    # bagimsiz ve Turkce ek tuzagina girmez. Olculdu: 7 sayfanin 6'sinda var.
    signals = structural_signals(html) if html else {"ld_types": [], "og_type": ""}
    ld_types = set(signals["ld_types"])  # type: ignore[arg-type]
    # Magaza once: bir sayfa hem Product hem Article basiyorsa magazadir.
    for name in ("product", "offer", "aggregateoffer", "onlinestore"):
        if name in ld_types:
            return "RETAILER"
    for name in sorted(ld_types):
        mapped = _LD_TYPE_MAP.get(name)
        if mapped:
            return mapped
    # Kurumsal site sekli: Organization + WebSite (+BreadcrumbList) var ama
    # makale de urun de yok. OLCULDU -- dermoeczanem.com ve dermo.com.tr tam
    # bu sekli veriyor. Onemli olan haber mi magaza mi degil, BAGIMSIZ kaynak
    # olup olmadigi: ikisi de degil, ikisi de NON_INDEPENDENT_TYPES icinde.
    SELF_DECLARED_SITE = {"organization", "website"}
    if SELF_DECLARED_SITE <= ld_types and signals["og_type"] != "article":
        return "RETAILER" if prices_declared(body) else "COMPANY"

    if signals["og_type"] == "article":
        # OLCULDU: magaza ve acilis sayfalari og:type basmiyor, gercek
        # icerik basiyor -- bu ikisini ayiran en net tek sinyaldi.
        return "NEWS"

    prices = len(PRICE_TAG.findall(body))
    shop = sum(marker in body for marker in SHOP_MARKERS) + (2 if prices >= 8 else 0)
    company = sum(marker in body for marker in COMPANY_MARKERS)
    news = sum(marker in body for marker in NEWS_MARKERS)
    trade = sum(marker in body for marker in TRADE_MARKERS)

    # A catalogue page full of prices is a shop even when it never says
    # "sepete ekle" -- category landing pages often do not.
    if prices >= 8 or (shop >= 2 and company >= 1):
        return "RETAILER"
    if company >= 2:
        return "COMPANY"
    if trade >= 2 and trade > news:
        return "TRADE_PUBLICATION"
    if news >= 1:
        return "NEWS"
    if shop >= 2:
        return "RETAILER"
    return "UNKNOWN"


# A company talking about itself is evidence of what the company says, not an
# independent check on whether it is true.
NON_INDEPENDENT_TYPES = frozenset({"COMPANY", "RETAILER", "MARKETPLACE"})


def score_source(title: str, text: str, query: str) -> dict[str, float]:
    """Relevance from three separate signals instead of one bag of words.

    The failure this replaces is recorded because it was not obvious: scoring
    a page by how many query words it contains anywhere gave a Kocaeli
    real-estate article 0.75 on a dermocosmetics query, because a 58 KB page
    contains `Türkiye`, `pazar` and `fırsat` somewhere regardless of subject.
    Title and lead are where a page declares its subject; the body only
    confirms it. So they are weighted separately and the anchor term has to
    show up where a page states what it is about.
    """
    # Her sorgu kelimesi icin bir govde kumesi. Sorgu tarafi bicimbilgisiyle
    # genisletilir -- maliyeti arama basina birkac kelime, sayfa basina degil.
    groups = _query_groups(query)
    if not groups:
        return {"relevance": 1.0, "title": 1.0, "lead": 1.0, "density": 1.0, "anchor_hits": 0.0}
    terms = frozenset().union(*groups)

    anchors = anchor_terms(query, count=1)
    # Capa tek govde degil KUME: "etiketlerinde" hem kendi kesmesini hem
    # lemmasinin kesmesini verir, ikisi de sayfada gecerli bir capadir.
    anchor_groups = _query_groups(anchors[0]) if anchors else ()
    anchor_set = set(frozenset().union(*anchor_groups)) if anchor_groups else set()
    anchor = sorted(anchor_set)[0] if anchor_set else ""
    title_l, lead_l = title.casefold(), text[:1500].casefold()
    body_l = (title + " " + text).casefold()

    # Oran KELIME uzerinden: bir kelimenin iki bicimi iki eslesme saymaz.
    title_score = _hit_ratio(groups, _stem_set(title_l))
    lead_score = _hit_ratio(groups, _stem_set(lead_l))
    body_stems = _stem_list(body_l)
    density = (sum(1 for stem in body_stems if stem in terms) / len(body_stems)
               ) if body_stems else 0.0
    density_score = min(1.0, density / 0.02)
    # Govde sayimi: "etiket", "etiketleme", "etiketlerinde" ayni cengele sayilir.
    anchor_hits = float(sum(1 for stem in body_stems if stem in anchor_set)
                        ) if anchor_set else 0.0

    declared = bool(anchor_set) and bool(
        anchor_set & (_stem_set(title_l) | _stem_set(lead_l)))
    if anchor and anchor_hits < 2:
        relevance = 0.0
    elif anchor and not declared and anchor_hits < 4:
        # Mentioned in passing deep inside a long page: not what it is about.
        relevance = 0.0
    else:
        relevance = 0.45 * title_score + 0.35 * lead_score + 0.20 * density_score
    return {"relevance": round(relevance, 3), "title": round(title_score, 3),
            "lead": round(lead_score, 3), "density": round(density_score, 3),
            "anchor_hits": anchor_hits}


_SENTENCE = re.compile(r"[^.!?\n]{40,400}[.!?]")


def evidence_snippets(text: str, query: str, limit: int = 3) -> list[str]:
    """Sentences from the page that actually mention the subject.

    Grounded by construction: every snippet is a verbatim span of the fetched
    page, so a reader can check it against the source. Numeric claims stay in
    extract_claims; this is the readable half of the same evidence.
    """
    anchors = set(anchor_terms(query, count=2))
    terms = {term for term in _token_set(query) if len(term) > 4}
    found: list[str] = []
    for match in _SENTENCE.finditer(text):
        sentence = " ".join(match.group(0).split())
        lowered = sentence.casefold()
        if anchors and not any(anchor in lowered for anchor in anchors):
            continue
        if len(_token_set(lowered) & terms) < min(2, len(terms)):
            continue
        if sentence not in found:
            found.append(sentence)
        if len(found) >= limit:
            break
    return found


def extract_claims(text: str, query: str, limit: int = 6) -> dict[str, str]:
    """Deterministic claims: a subject phrase paired with a number it is
    stated with. No model, no inference -- if the page does not state a
    number, no claim is produced."""
    terms = {term for term in _token_set(query) if len(term) > 3}
    claims: dict[str, str] = {}
    for match in _NUMERIC_CLAIM.finditer(text):
        subject = " ".join(match.group(1).split()).casefold()
        if terms and not (_token_set(subject) & terms):
            continue
        claims.setdefault(subject, " ".join(match.group(2).split()))
        if len(claims) >= limit:
            break
    return claims


def _open(url: str, resolver: Any = socket.getaddrinfo, timeout: float = 10.0) -> tuple[str, str]:
    """Fetch with every redirect hop re-validated. Returns (final_url, body)."""
    current = canonicalize_url(url, resolver)
    for _ in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip",
            "Accept-Language": "tr,en;q=0.8",
        })
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                location = exc.headers.get("Location") or ""
                current = canonicalize_url(urllib.parse.urljoin(current, location), resolver)
                continue
            raise
        raw = response.read(MAX_BYTES)
        if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError):
                pass
        charset = response.headers.get_content_charset() or "utf-8"
        return current, raw.decode(charset, errors="ignore")
    raise SearchError("too many redirects")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _searxng_search(endpoint: str, query: str, limit: int, resolver: Any) -> list[str]:
    url = endpoint.rstrip("/") + "/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "language": "tr", "safesearch": "0"})
    parsed = urllib.parse.urlsplit(url)
    # A self-hosted SearXNG usually lives on a private address, which
    # canonicalize_url would correctly refuse. It is our own service and an
    # explicit operator setting, so it is fetched directly -- but only ever
    # for the search index, never for page content.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    if parsed.scheme not in {"http", "https"}:
        raise SearchError("SearXNG endpoint must be HTTP(S)")
    with urllib.request.urlopen(request, timeout=10.0) as response:
        payload = json.loads(response.read(MAX_BYTES).decode("utf-8", errors="ignore"))
    return [str(row.get("url")) for row in payload.get("results", [])[:limit] if row.get("url")]


def _gemini_search(query: str, limit: int, resolver: Any) -> list[str]:
    """Google Search grounding -- yalnizca ARAMA DIZINI olarak.

    NEDEN VAR (20.09.2026'da olculdu, tahmin degil)
    Bu sunucunun veri merkezi IP'sinden ucretsiz kazima arama fiilen olu:
    SearXNG kurulu ve saglikliydi ama motorlarin hepsi engelli --
    google "Suspended: CAPTCHA", google cse "unusual traffic from your
    network", duckduckgo "access denied", brave/qwant "too many requests",
    wikidata timeout. Cevap veren tek motor bing'di ve sorgunun yalniz ILK
    KELIMESINI esliyordu: "kozmetik pazari Turkiye 2026 rapor" -> Hotmail
    ve Microsoft Support sayfalari. Arastirma bu yuzden 51 saniye calisip
    elinde "Turkiye - Vikipedi" ve "Turkiye | United Nations" ile
    kaliyordu. Yani arama vardi, sonuc yoktu.

    NE YAPAR
    Gemini'ye google_search araciyla sorar ve YALNIZ groundingChunks'taki
    kaynak baglantilarini alir. Modelin CEVAP METNI KULLANILMAZ -- burasi
    bir arama dizini, bir cevap kaynagi degil. Sayfalarin kendisi mevcut
    tarama hattindan gecer: canonicalize_url, SSRF kurallari, alaka esigi,
    yakin-kopya elemesi, kaynak siniflandirmasi -- hicbiri atlanmaz.
    Yani kanit disiplini aynen korunur, degisen tek sey URL'lerin NEREDEN
    geldigi.

    Grounding baglantilari vertexaisearch.cloud.google.com uzerinden
    yonlendirir; gercek adrese cozulur ve cagirana GERCEK adres doner --
    boylece canonicalize_url yonlendirmeyi degil, gercekten indirilecek
    sayfayi denetler.
    """
    from . import providers  # gec import: dongusel bagimlilik olmasin
    key = (providers.load_env().get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SearchError("GEMINI_API_KEY yok")
    endpoint = (GEMINI_ENDPOINT.format(model=GEMINI_SEARCH_MODEL)
                + "?key=" + urllib.parse.quote(key, safe=""))
    body = {
        "contents": [{"parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    request = urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT) as response:
            payload = json.loads(response.read(MAX_BYTES).decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        # Anahtar hata metnine sizmasin.
        raise SearchError(f"gemini search HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise SearchError(f"gemini search: {providers.mask(str(exc))}") from None

    candidates = payload.get("candidates") or []
    if not candidates:
        return []
    chunks = ((candidates[0].get("groundingMetadata") or {}).get("groundingChunks") or [])
    uriler = [u for u in (str(((c.get("web") or {}).get("uri") or "")).strip()
                          for c in chunks) if u][:limit]
    if not uriler:
        return []
    # 🔴 YONLENDIRMELER PARALEL COZULUR.
    # Sirali hali olculdu: 8 URL icin arama adimi 15-21 saniye suruyordu ve
    # arastirmanin 45 sn'lik butcesini yiyip TIMEOUT'a dusuruyordu -- yani
    # arama calisiyor ama cevap yetismiyordu. Her yonlendirme bagimsiz bir
    # HTTP gidis-donusu; beklemeyi seri yapmanin hicbir sebebi yok.
    with ThreadPoolExecutor(max_workers=min(8, len(uriler))) as havuz:
        cozulmus = list(havuz.map(_resolve_redirect, uriler))
    urls: list[str] = []
    seen: set[str] = set()
    for real in cozulmus:
        if real and real not in seen:
            seen.add(real)
            urls.append(real)
    return urls


def _resolve_redirect(uri: str) -> str:
    """Grounding yonlendirmesini gercek adrese cozer.

    Cozulemezse bos doner ve o kaynak DUSER: yonlendirme adresini sayfa
    icerigi diye indirmek, denetlenmemis bir adresi denetlenmis gibi
    gostermek olurdu.
    """
    try:
        request = urllib.request.Request(uri, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT) as response:
            final = response.geturl()
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    parsed = urllib.parse.urlsplit(final)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if "grounding-api-redirect" in final:
        return ""      # cozulmedi, yonlendirme adresinde kaldi
    return final


def _duckduckgo_search(query: str, limit: int, resolver: Any) -> list[str]:
    body = urllib.parse.urlencode({"q": query, "kl": "tr-tr"}).encode()
    request = urllib.request.Request(DUCKDUCKGO_HTML, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html",
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=12.0) as response:
        html = response.read(MAX_BYTES).decode("utf-8", errors="ignore")
    urls: list[str] = []
    for href in re.findall(r'href="(//duckduckgo\.com/l/\?[^"]+|https?://[^"]+)"', html):
        candidate = href
        if candidate.startswith("//duckduckgo.com/l/?"):
            query_string = urllib.parse.urlsplit("https:" + candidate).query
            target = urllib.parse.parse_qs(query_string).get("uddg", [""])[0]
            candidate = urllib.parse.unquote(target)
        if not candidate.startswith("http"):
            continue
        host = (urllib.parse.urlsplit(candidate).hostname or "").casefold()
        if "duckduckgo.com" in host or not host:
            continue
        if candidate not in urls:
            urls.append(candidate)
        if len(urls) >= limit:
            break
    return urls


class WebSearchCrawlAdapter(CapabilityAdapter):
    """Search the open web, fetch the results, return normalized source rows."""

    name = "web_search_crawl"
    version = "1.0.0"
    state = AdapterState.AVAILABLE

    def __init__(self, searxng_url: str | None = None, max_results: int = 6,
                 max_pages: int = 4, resolver: Any = socket.getaddrinfo,
                 timeout: float = 10.0, min_relevance: float | None = None,
                 max_queries: int = 4, search_concurrency: int = 3) -> None:
        self.searxng_url = searxng_url if searxng_url is not None else os.environ.get("RESEARCH_SEARXNG_URL", "")
        # Arama arka ucu sirasi. Varsayilan "auto": Gemini grounding varsa o,
        # yoksa SearXNG, o da yoksa DuckDuckGo. Sira 20.09.2026 olcumune
        # dayaniyor (bkz. _gemini_search); RESEARCH_BACKEND ile sabitlenebilir.
        self.backend_pref = (os.environ.get("RESEARCH_BACKEND", "auto") or "auto").strip().lower()
        self.max_results = max_results
        self.max_pages = max_pages
        self.resolver = resolver
        self.timeout = timeout
        # Alaka esigi ise gore degisir ve bu bilerek ayarlanabilir:
        # SORU CEVAPLAMADA yuksek esik dogru -- alakasiz kaynak cevabi kirletir.
        # BILGI BIRIKTIRMEDE dusuk esik dogru -- aday malzeme toplanir, alaka
        # puani kayitta durur ve sonra filtrelenebilir. Olculdu: 0.34'te ayni
        # konu bir kosuda 0, digerinde 1 kaynak veriyor; esik tam sinirda.
        self.min_relevance = (min_relevance if min_relevance is not None
                              else float(os.environ.get("RESEARCH_MIN_RELEVANCE", "0.34")))
        self.max_queries = max_queries
        self.search_concurrency = search_concurrency
        self._last: dict[str, Any] = {}

    # -- contract ---------------------------------------------------------
    def capabilities(self) -> tuple[str, ...]:
        return (RESEARCH_CAPABILITY,)

    def _backends(self) -> list[str]:
        """Denenecek arka uclar, sirayla. Biri patlarsa sonraki denenir."""
        if self.backend_pref in {"gemini", "searxng", "duckduckgo"}:
            chain = [self.backend_pref]
        else:
            chain = ["gemini"]
            if self.searxng_url:
                chain.append("searxng")
            chain.append("duckduckgo")
        return chain

    def _backend_name(self) -> str:
        return self._backends()[0]

    def health(self) -> dict[str, Any]:
        backend = self._backend_name()
        try:
            canonicalize_url("https://duckduckgo.com/", self.resolver)
            state = AdapterState.AVAILABLE.value
            detail = "outbound HTTPS and DNS reachable"
        except (UnsafeUrl, OSError) as exc:
            state = AdapterState.UNAVAILABLE.value
            detail = f"no outbound access: {exc}"
        return {"state": state, "backend": backend, "detail": detail,
                "external_actions": 0, "writes": 0}

    def metrics(self) -> dict[str, Any]:
        return dict(self._last)

    def evidence(self) -> tuple[AdapterEvidence, ...]:
        return (AdapterEvidence(
            kind="adapter_contract",
            summary="search+crawl over the open web; read-only, no business action",
            reference=f"backend={self._backend_name()}"),)

    def cancel(self, handle: str) -> bool:
        return False

    def resume(self, handle: str) -> bool:
        return False

    def execute(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("capability") != RESEARCH_CAPABILITY:
            raise ValueError(f"unsupported capability: {envelope.get('capability')!r}")
        if envelope.get("external_actions"):
            raise PermissionError("research adapter never performs external actions")
        query = " ".join(str(envelope.get("query") or "").split())
        if not query:
            raise ValueError("query must not be empty")
        budget = int(envelope.get("max_bytes") or 64_000)

        started = perf_counter()
        queries = _decompose_best(query, self.max_queries)
        urls, search_ms, raw_count = self._search_many(queries)
        crawl_started = perf_counter()
        sources, fetch_stats = self._crawl(urls, query, budget)
        crawl_ms = round((perf_counter() - crawl_started) * 1000, 3)

        by_type: dict[str, int] = {}
        for source in sources:
            by_type[source["source_type"]] = by_type.get(source["source_type"], 0) + 1
        independent = {source["origin_id"] for source in sources
                       if source["source_type"] not in NON_INDEPENDENT_TYPES}

        self._last = {
            "generated_queries": list(queries),
            "search_ms": search_ms, "crawl_ms": crawl_ms,
            "raw_results": raw_count, "unique_urls": len(urls),
            "url_duplicates_dropped": max(0, raw_count - len(urls)),
            "pages_fetched": fetch_stats["fetched"],
            "pages_failed": fetch_stats["failed"],
            "content_duplicates_dropped": fetch_stats["duplicates"],
            "off_topic_dropped": fetch_stats["off_topic"],
            "relevant_kept": len(sources),
            "source_types": by_type,
            "independent_non_company": len(independent),
            "total_ms": round((perf_counter() - started) * 1000, 3),
        }
        return {"sources": sources, "model_calls": 0, "cost": 0.0,
                "external_actions": 0, "metrics": dict(self._last)}

    # -- internals --------------------------------------------------------
    def _search_many(self, queries: tuple[str, ...]) -> tuple[list[str], float, int]:
        """Run the focused queries in bounded parallel, then merge.

        Ordering is round-robin across queries rather than concatenation, so a
        single broad query cannot fill the whole fetch budget and starve the
        competitor or pricing angle.
        """
        started = perf_counter()
        workers = max(1, min(self.search_concurrency, len(queries)))
        per_query: list[list[str]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(self._search_one, queries):
                per_query.append(result)

        raw_count = sum(len(rows) for rows in per_query)
        merged: list[str] = []
        seen: set[str] = set()
        for index in range(max((len(rows) for rows in per_query), default=0)):
            for rows in per_query:
                if index >= len(rows):
                    continue
                url = rows[index]
                key = url.split("#", 1)[0].rstrip("/").casefold()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(url)
        return merged, round((perf_counter() - started) * 1000, 3), raw_count

    def _search_one(self, query: str) -> list[str]:
        """Sirayla dener; BOS sonuc da basarisizlik sayilir.

        Onceki hali yalnizca istisnada bir sonrakine geciyordu. Olculdu:
        engelli bir motor istisna ATMIYOR, HTTP 200 ile bos/alakasiz liste
        donduruyor -- yani yedek yol hic devreye girmiyordu. Bos liste artik
        bir sonraki arka ucu tetikler.
        """
        for backend in self._backends():
            try:
                if backend == "gemini":
                    urls = _gemini_search(query, self.max_results, self.resolver)
                elif backend == "searxng":
                    if not self.searxng_url:
                        continue
                    urls = _searxng_search(self.searxng_url, query, self.max_results, self.resolver)
                else:
                    urls = _duckduckgo_search(query, self.max_results, self.resolver)
            except Exception as exc:  # noqa: BLE001 - bir motor dusunce digeri denenir
                # 🔴 Iki motor da dusarse bu islev [] donuyor ve bu, "arama
                # sonuc vermedi" ile AYIRT EDILEMEZ. Fark yalniz burada.
                gunluk.yut("research_sources", "search", exc,
                           neden="bir arama motorunun dusmesi digerini denemeyi engellemez",
                           agirlik=gunluk.AGIRLIK_ARIZA, sorgu=query[:120])
                continue
            if urls:
                return urls
        return []

    def _crawl(self, urls: list[str], query: str, budget: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
        topic = " ".join(research_subject(query, count=4)) or query
        rows: list[dict[str, Any]] = []
        texts: list[str] = []
        stats = {"fetched": 0, "failed": 0, "duplicates": 0, "off_topic": 0}
        for url in urls:
            if len(rows) >= self.max_pages:
                break
            try:
                final_url, html = _open(url, self.resolver, self.timeout)
            except Exception as exc:  # noqa: BLE001 - tek sayfa toplamayi durduramaz
                gunluk.yut("research_sources", "_fetch_pages", exc,
                           neden="tek sayfanin acilamamasi toplamayi durduramaz",
                           url=str(url)[:200])
                stats["failed"] += 1
                continue
            stats["fetched"] += 1
            text = best_text(html)
            if len(text) < 200:
                continue
            if any(near_duplicate(text, seen) for seen in texts):
                stats["duplicates"] += 1
                continue
            meta = _MetaParser()
            try:
                meta.feed(html)
            except Exception as exc:  # noqa: BLE001 - baslik yoklugu sayfayi elemez
                gunluk.yut("research_sources", "_meta_parse", exc,
                           neden="basligin ayristirilamamasi sayfayi elemez",
                           url=str(final_url)[:200])
            scores = score_source(meta.title, text, topic)
            if scores["relevance"] < self.min_relevance:
                stats["off_topic"] += 1
                continue
            texts.append(text)
            host = (urllib.parse.urlsplit(final_url).hostname or "").casefold()
            source_type = classify_source(host, meta.title, text, html)
            canonical_host = host
            if meta.canonical:
                canonical_host = (urllib.parse.urlsplit(
                    urllib.parse.urljoin(final_url, meta.canonical)).hostname or host).casefold()
            rows.append({
                "url": final_url,
                "publisher": canonical_host,
                "origin_id": canonical_host,
                "title": " ".join(meta.title.split())[:300],
                "content": text[:budget],
                # Sayfanin kendi bildirdigi tarih once; yoksa trafilatura'nin
                # cikarimi. Ikisi de yoksa bos kalir -- uydurulmaz.
                "observed_at": meta.published or published_date(html),
                # Authority is not a reputation score -- we have no ground
                # truth for that. It is how much of the question the page
                # actually addresses, discounted for plain HTTP and for a
                # source class that cannot corroborate itself.
                "authority": round(min(1.0, scores["relevance"])
                                   * (1.0 if final_url.startswith("https://") else 0.7)
                                   * (0.6 if source_type in NON_INDEPENDENT_TYPES else 1.0), 3),
                "relevance": scores["relevance"],
                "relevance_signals": scores,
                "source_type": source_type,
                "evidence_snippets": evidence_snippets(text, topic),
                "freshness": 0.8 if meta.published else 0.4,
                "claims": extract_claims(text, topic),
                "evidence_ref": final_url,
            })
        return rows, stats
