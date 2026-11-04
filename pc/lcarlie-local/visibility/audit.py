"""Audit public L'CARLIÉ discovery pages without private credentials.

Run: python visibility/audit.py
Outputs: visibility/report.json and visibility/products.csv
"""

from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree


BASE = "https://www.lcarlie.shop"
GUIDE = BASE + "/post/l-carlié-ürün-rehberi-bakım-alanına-göre-ürünler"
OUTPUT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "LcarlieVisibilityAudit/1.0 (+https://www.lcarlie.shop/)"}
SCHEMA_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.canonical = ""
        self.description = ""
        self.robots = ""
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self._tag = ""
        self._json = False
        self._json_buffer = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        self._tag = tag
        if tag == "link" and data.get("rel") == "canonical":
            self.canonical = data.get("href") or ""
        if tag == "meta" and data.get("name", "").lower() == "description":
            self.description = data.get("content") or ""
        if tag == "meta" and data.get("name", "").lower() == "robots":
            self.robots = data.get("content") or ""
        if tag == "a" and data.get("href"):
            self.links.append(data["href"] or "")
        if tag == "script" and data.get("type", "").lower() == "application/ld+json":
            self._json = True
            self._json_buffer = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._json:
                self.jsonld.append(self._json_buffer)
            self._json = False
        if tag == self._tag:
            self._tag = ""

    def handle_data(self, data: str) -> None:
        if self._tag == "title":
            self.title += data
        if self._json:
            self._json_buffer += data


def fetch(url: str) -> tuple[int, str]:
    parts = urlsplit(url)
    safe_url = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%"), parts.query, parts.fragment))
    try:
        with urlopen(Request(safe_url, headers=HEADERS), timeout=25) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except HTTPError as exc:
        return exc.code, ""
    except (URLError, TimeoutError) as exc:
        return 0, type(exc).__name__


def parse_html(content: str) -> PageParser:
    parser = PageParser()
    parser.feed(content)
    return parser


def product_nodes(parser: PageParser) -> list[dict]:
    nodes: list[dict] = []
    for raw in parser.jsonld:
        try:
            document = json.loads(unescape(raw))
        except json.JSONDecodeError:
            continue
        candidates = document if isinstance(document, list) else [document]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidates2 = candidate.get("@graph", [candidate])
            for node in candidates2:
                if isinstance(node, dict) and "Product" in str(node.get("@type", "")):
                    nodes.append(node)
    return nodes


def audit_product(url: str, in_sitemap: bool) -> dict:
    status, content = fetch(url)
    parser = parse_html(content)
    products = product_nodes(parser)
    product = products[0] if len(products) == 1 else {}
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    issues = []
    if status != 200:
        issues.append("http_not_200")
    if not in_sitemap:
        issues.append("missing_from_product_sitemap")
    if "noindex" in parser.robots.lower():
        issues.append("noindex")
    if unquote(parser.canonical).rstrip("/") != unquote(url).rstrip("/"):
        issues.append("canonical_mismatch")
    if len(products) != 1:
        issues.append("product_schema_count_" + str(len(products)))
    if not product.get("name"):
        issues.append("schema_name_missing")
    if not product.get("image"):
        issues.append("schema_image_missing")
    if not isinstance(offers, dict) or not offers.get("price") or not offers.get("availability"):
        issues.append("schema_offer_incomplete")
    if isinstance(offers, dict) and unquote(offers.get("url", "")).rstrip("/") != unquote(url).rstrip("/"):
        issues.append("schema_offer_url_mismatch")
    sku = str(product.get("sku") or "")
    if re.fullmatch(r"\d{13}", sku) and not product.get("gtin13"):
        issues.append("gtin13_candidate_unverified")
    return {
        "url": url,
        "http_status": status,
        "title": parser.title,
        "canonical": parser.canonical,
        "product_name": product.get("name", ""),
        "sku": sku,
        "price": offers.get("price", "") if isinstance(offers, dict) else "",
        "availability": offers.get("availability", "") if isinstance(offers, dict) else "",
        "issues": issues,
    }


def main() -> None:
    robots_status, robots = fetch(BASE + "/robots.txt")
    sitemap_status, sitemap = fetch(BASE + "/store-products-sitemap.xml")
    guide_status, guide_html = fetch(GUIDE)
    guide = parse_html(guide_html)
    sitemap_urls: set[str] = set()
    if sitemap_status == 200:
        tree = ElementTree.fromstring(sitemap)
        sitemap_urls = {unquote(node.text or "") for node in tree.findall("s:url/s:loc", SCHEMA_NS)}
    guide_urls = sorted({urljoin(BASE, link) for link in guide.links
                         if urlparse(urljoin(BASE, link)).netloc == "www.lcarlie.shop"
                         and urlparse(urljoin(BASE, link)).path.startswith("/product-page/")})
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {pool.submit(audit_product, url, unquote(url) in sitemap_urls): url for url in guide_urls}
        for task in as_completed(tasks):
            rows.append(task.result())
    rows.sort(key=lambda row: row["url"])
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "robots_status": robots_status,
        "robots_allows_crawling": "User-agent: *\nAllow: /" in robots,
        "sitemap_status": sitemap_status,
        "sitemap_product_count": len(sitemap_urls),
        "guide_url": GUIDE,
        "guide_status": guide_status,
        "guide_title": guide.title,
        "guide_canonical": guide.canonical,
        "guide_product_link_count": len(guide_urls),
        "checked_product_count": len(rows),
        "products_with_critical_issues": sum(any(issue != "gtin13_candidate_unverified" for issue in row["issues"]) for row in rows),
        "products_with_unverified_gtin13_candidate": sum("gtin13_candidate_unverified" in row["issues"] for row in rows),
        "products": rows,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUTPUT / "products.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url", "http_status", "title", "canonical", "product_name", "sku", "price", "availability", "issues"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "issues": ";".join(row["issues"])})
    print(json.dumps({key: value for key, value in summary.items() if key != "products"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
