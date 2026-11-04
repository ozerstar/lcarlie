"""Run one versioned GEO query set; designed for a systemd timer."""

import argparse
import json
import os
import sys

import psycopg

try:
    from jarvis.geo_f2 import fetch_searxng, ingest_response, record_unavailable
except ModuleNotFoundError:
    from geo_f2 import fetch_searxng, ingest_response, record_unavailable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-version", default="sunacnea-tr-v1")
    parser.add_argument("--searx-url", default="http://127.0.0.1:8888")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(os.environ.get("GEO_DATABASE_URL", ""), autocommit=True) as conn:
        queries = conn.execute(
            """SELECT query_id,sorgu_metni,language FROM core.geo_query
               WHERE set_surum=%s ORDER BY oncelik,query_id""",
            (args.set_version,),
        ).fetchall()
        if not queries:
            raise SystemExit("No GEO queries in set")
        results = []
        for query_id, query_text, language in queries:
            try:
                payload = fetch_searxng(args.searx_url, query_text, language)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                if args.dry_run:
                    results.append({"query_id": query_id, "status": "UNAVAILABLE",
                                    "error": type(exc).__name__})
                else:
                    observation_id = record_unavailable(conn, query_id)
                    results.append({"query_id": query_id, "status": "UNAVAILABLE",
                                    "observation_id": observation_id})
                continue
            if args.dry_run:
                results.append({"query_id": query_id, "status": "READY",
                                "results": len(payload["results"])})
            else:
                results.append({"status": "OBSERVED",
                                **ingest_response(conn, query_id, payload)})
    print(json.dumps({"set_version": args.set_version, "results": results}))
    if any(item["status"] == "UNAVAILABLE" for item in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
