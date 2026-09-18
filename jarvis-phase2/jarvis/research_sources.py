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
import socket
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from time import perf_counter
from typing import Any

from .adapter_factory import AdapterEvidence, AdapterState, CapabilityAdapter
from .research_controller import RESEARCH_CAPABILITY, UnsafeUrl, canonicalize_url

USER_AGENT = "LCarlieResearchBot/1.0 (+https://lcarlie.shop; contact=owner)"
MAX_REDIRECTS = 3
MAX_BYTES = 400_000
DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"

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


def _token_set(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


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


def relevance(text: str, title: str, query: str) -> float:
    """How much of the question this page is actually about.

    Measured the hard way, because the easy way fails: a plain
    presence-ratio over the query's words scored a Kocaeli real-estate
    article 0.75 on a dermocosmetics market query -- a 58 KB page contains
    `Türkiye`, `pazar`, `fırsat` and `2026` somewhere no matter its subject.
    So the page must repeat at least one distinctive term, and the score is
    term DENSITY rather than presence. No model, no embedding.
    """
    terms = {term for term in _token_set(query) if len(term) > 3}
    if not terms:
        return 1.0
    body = (title + " " + text).casefold()
    words = _WORD.findall(body)
    if not words:
        return 0.0
    # Only the single most distinctive term counts as the topic anchor.
    # Allowing any of the top three let the Wikipedia article on Turkey pass a
    # dermocosmetics query on the word . The trade-off is
    # explicit: a relevant page that uses only a synonym of the anchor is
    # dropped, and a dropped page is visible in off_topic_dropped rather than
    # silently weighted down.
    anchors = anchor_terms(query, count=1)
    if anchors and body.count(anchors[0]) < 2:
        return 0.0
    hits = sum(1 for word in words if word in terms)
    density = hits / len(words)
    # 2% of a page being query terms is already a strongly on-topic page.
    return min(1.0, density / 0.02)


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
                 timeout: float = 10.0, min_relevance: float = 0.34) -> None:
        self.searxng_url = searxng_url if searxng_url is not None else os.environ.get("RESEARCH_SEARXNG_URL", "")
        self.max_results = max_results
        self.max_pages = max_pages
        self.resolver = resolver
        self.timeout = timeout
        self.min_relevance = min_relevance
        self._last: dict[str, Any] = {}

    # -- contract ---------------------------------------------------------
    def capabilities(self) -> tuple[str, ...]:
        return (RESEARCH_CAPABILITY,)

    def health(self) -> dict[str, Any]:
        backend = "searxng" if self.searxng_url else "duckduckgo_html"
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
            reference=f"backend={'searxng' if self.searxng_url else 'duckduckgo_html'}"),)

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
        urls, search_ms = self._search(query)
        sources, fetch_stats = self._crawl(urls, query, budget)
        self._last = {
            "search_ms": search_ms, "results_found": len(urls),
            "pages_fetched": fetch_stats["fetched"],
            "pages_failed": fetch_stats["failed"],
            "duplicates_dropped": fetch_stats["duplicates"],
            "off_topic_dropped": fetch_stats["off_topic"],
            "total_ms": round((perf_counter() - started) * 1000, 3),
        }
        return {"sources": sources, "model_calls": 0, "cost": 0.0,
                "external_actions": 0, "metrics": dict(self._last)}

    # -- internals --------------------------------------------------------
    def _search(self, query: str) -> tuple[list[str], float]:
        started = perf_counter()
        if self.searxng_url:
            try:
                urls = _searxng_search(self.searxng_url, query, self.max_results, self.resolver)
            except Exception:
                urls = _duckduckgo_search(query, self.max_results, self.resolver)
        else:
            urls = _duckduckgo_search(query, self.max_results, self.resolver)
        return urls, round((perf_counter() - started) * 1000, 3)

    def _crawl(self, urls: list[str], query: str, budget: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
        rows: list[dict[str, Any]] = []
        texts: list[str] = []
        stats = {"fetched": 0, "failed": 0, "duplicates": 0, "off_topic": 0}
        for url in urls:
            if len(rows) >= self.max_pages:
                break
            try:
                final_url, html = _open(url, self.resolver, self.timeout)
            except Exception:
                stats["failed"] += 1
                continue
            stats["fetched"] += 1
            text = extract_text(html)
            if len(text) < 200:
                continue
            if any(near_duplicate(text, seen) for seen in texts):
                stats["duplicates"] += 1
                continue
            meta = _MetaParser()
            try:
                meta.feed(html)
            except Exception:
                pass
            score = relevance(text, meta.title, query)
            if score < self.min_relevance:
                stats["off_topic"] += 1
                continue
            texts.append(text)
            host = (urllib.parse.urlsplit(final_url).hostname or "").casefold()
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
                "observed_at": meta.published or "",
                # Authority is not a reputation score -- we have no ground
                # truth for that. It is how much of the question the page
                # actually addresses, discounted for plain HTTP.
                "authority": round(min(1.0, score) * (1.0 if final_url.startswith("https://") else 0.7), 3),
                "relevance": round(score, 3),
                "freshness": 0.8 if meta.published else 0.4,
                "claims": extract_claims(text, query),
                "evidence_ref": final_url,
            })
        return rows, stats
