"""GEO F2: capture SearXNG results with separate mentions and citations.

This job records evidence. It does not claim that a cited page supports a
mentioned brand, create action proposals, or change published content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

import psycopg
from psycopg.types.json import Jsonb

try:
    from jarvis.geo_url import normalize_url
except ModuleNotFoundError:
    from geo_url import normalize_url

PARSER_VERSION = "searxng-json-v1"
NORMALIZER_VERSION = "geo-url-v1"
MAX_RESPONSE_BYTES = 2_000_000
MAX_RESULTS = 10


def fetch_searxng(base_url: str, query: str, language: str) -> dict:
    parsed = urlsplit(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("SearXNG must use a loopback endpoint")
    try:
        if parsed.port is None:
            raise ValueError("SearXNG port is required")
    except ValueError as exc:
        raise ValueError("Invalid SearXNG port") from exc
    params = urlencode({"q": query, "format": "json", "language": language})
    url = base_url.rstrip("/") + "/search?" + params
    with urlopen(url, timeout=15) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("SearXNG response is too large")
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Unexpected SearXNG response")
    return payload


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def find_brand_mentions(text: str, aliases: list[tuple[int, str]]) -> list[int]:
    folded = _fold(text)
    found = set()
    for brand_id, alias in aliases:
        token = _fold(alias.strip())
        if token and re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", folded):
            found.add(brand_id)
    return sorted(found)


def load_aliases(conn: psycopg.Connection) -> list[tuple[int, str]]:
    return conn.execute(
        "SELECT canonical_brand_id, alias FROM core.geo_alias WHERE active"
    ).fetchall()


def ingest_response(
    conn: psycopg.Connection, query_id: int, payload: dict,
    observed_at: datetime | None = None,
) -> dict:
    observed_at = observed_at or datetime.now(timezone.utc)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Unexpected SearXNG response")
    with conn.transaction():
        query = conn.execute(
            "SELECT sorgu_metni,language,country FROM core.geo_query WHERE query_id=%s",
            (query_id,),
        ).fetchone()
        if query is None:
            raise ValueError("Unknown GEO query")
        query_text, language, country = query
        raw_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        response_hash = sha256(raw_json.encode("utf-8")).hexdigest()
        raw_id = conn.execute(
            """INSERT INTO raw.geo_response
               (saglayici,yuzey,sorgu_metni,language,country,cevap_hash,ham,cekim_at,parser_surum)
               VALUES ('searxng','WEB_SEARCH',%s,%s,%s,%s,%s,%s,%s) RETURNING ham_id""",
            (query_text, language, country, response_hash, Jsonb(payload), observed_at, PARSER_VERSION),
        ).fetchone()[0]
        observation_id = conn.execute(
            """INSERT INTO core.geo_observation
               (query_id,yuzey,model,language,country,gozlem_at,durum,ham_id,cevap_hash,guven,parser_surum,normalizer_surum)
               VALUES (%s,'WEB_SEARCH','searxng',%s,%s,%s,'OBSERVED',%s,%s,1.000,%s,%s)
               RETURNING observation_id""",
            (query_id, language, country, observed_at, raw_id, response_hash,
             PARSER_VERSION, NORMALIZER_VERSION),
        ).fetchone()[0]
        aliases = load_aliases(conn)
        citation_count = 0
        mentions = set()
        for position, result in enumerate(payload["results"][:MAX_RESULTS], 1):
            if not isinstance(result, dict):
                continue
            title = str(result.get("title") or "")[:500]
            snippet = str(result.get("content") or "")[:4000]
            for brand_id in find_brand_mentions(title + " " + snippet, aliases):
                mentions.add(brand_id)
            try:
                target = normalize_url(str(result.get("url") or ""))
            except ValueError:
                continue
            source_id = conn.execute(
                """INSERT INTO core.geo_source (domain,tur) VALUES (%s,'SEARCH_RESULT')
                   ON CONFLICT (domain) DO UPDATE SET son_gorulme=now()
                   RETURNING source_id""",
                (target.domain,),
            ).fetchone()[0]
            inserted = conn.execute(
                """INSERT INTO core.geo_citation
                   (observation_id,source_id,kanonik_url,url_hash,baslik,sira)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                   RETURNING citation_id""",
                (observation_id, source_id, target.url, target.url_hash, title, position),
            ).fetchone()
            citation_count += int(inserted is not None)
        for brand_id in sorted(mentions):
            conn.execute(
                """INSERT INTO core.geo_mention (observation_id,brand_id,tip)
                   VALUES (%s,%s,'BRAND') ON CONFLICT DO NOTHING""",
                (observation_id, brand_id),
            )
    return {"query_id": query_id, "observation_id": observation_id,
            "citations": citation_count, "mentions": len(mentions)}


def record_unavailable(conn: psycopg.Connection, query_id: int) -> int:
    with conn.transaction():
        query = conn.execute(
            "SELECT language,country FROM core.geo_query WHERE query_id=%s", (query_id,)
        ).fetchone()
        if query is None:
            raise ValueError("Unknown GEO query")
        return conn.execute(
            """INSERT INTO core.geo_observation
               (query_id,yuzey,model,language,country,gozlem_at,durum,parser_surum,normalizer_surum)
               VALUES (%s,'WEB_SEARCH','searxng',%s,%s,now(),'UNAVAILABLE',%s,%s)
               RETURNING observation_id""",
            (query_id, query[0], query[1], PARSER_VERSION, NORMALIZER_VERSION),
        ).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query_id", type=int)
    parser.add_argument("--searx-url", default="http://127.0.0.1:8888")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    # An explicit URL is optional; libpq also accepts the existing PG* service
    # variables so credentials never need to be copied into this module.
    with psycopg.connect(os.environ.get("GEO_DATABASE_URL", ""), autocommit=True) as conn:
        row = conn.execute(
            "SELECT sorgu_metni,language FROM core.geo_query WHERE query_id=%s",
            (args.query_id,),
        ).fetchone()
        if row is None:
            raise SystemExit("Unknown GEO query")
        try:
            response = fetch_searxng(args.searx_url, row[0], row[1])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if args.dry_run:
                print(json.dumps({"status": "UNAVAILABLE", "error": type(exc).__name__}))
                return
            observation_id = record_unavailable(conn, args.query_id)
            print(json.dumps({"status": "UNAVAILABLE", "observation_id": observation_id}))
            return
        if args.dry_run:
            print(json.dumps({"status": "READY", "results": len(response["results"])}))
            return
        print(json.dumps({"status": "OBSERVED", **ingest_response(conn, args.query_id, response)}))


if __name__ == "__main__":
    main()
