import os
import unittest
from uuid import uuid4


try:
    from jarvis.geo_f2 import fetch_searxng, find_brand_mentions, ingest_response, record_unavailable
except ModuleNotFoundError:
    from geo_f2 import fetch_searxng, find_brand_mentions, ingest_response, record_unavailable


class AliasTests(unittest.TestCase):
    def test_searx_endpoint_must_be_loopback(self):
        for endpoint in ("http://localhost:8888@evil.example", "https://localhost:8888",
                         "http://127.0.0.1:8888/search", "http://example.com:8888"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                fetch_searxng(endpoint, "test", "tr")

    def test_whole_alias_only(self):
        aliases = [(1, "L'CARLIÉ"), (1, "LCARLIE"), (2, "SUNACNEA")]
        self.assertEqual(find_brand_mentions("L'Carlie and SUNACNEA are shown", aliases), [1, 2])
        self.assertEqual(find_brand_mentions("SUNACNEAX is different", aliases), [])


@unittest.skipUnless(os.environ.get("GEO_TEST_DATABASE_URL"), "test DB not configured")
class DatabaseTests(unittest.TestCase):
    def test_evidence_separation_and_variant_identity(self):
        import psycopg  # Required only when the integration DB is configured.

        conn = psycopg.connect(os.environ["GEO_TEST_DATABASE_URL"])
        try:
            alias = "GEO_TEST_" + uuid4().hex
            brand_id = conn.execute(
                "INSERT INTO core.geo_brand(canonical_name,bizim_mi) VALUES (%s,true) RETURNING brand_id",
                (alias,),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO core.geo_alias
                   (canonical_brand_id,alias,normalized_alias,alias_type,language)
                   VALUES (%s,%s,%s,'OFFICIAL','tr')""",
                (brand_id, alias, alias.lower()),
            )
            query_id = conn.execute(
                """INSERT INTO core.geo_query
                   (sorgu_metni,language,country,niyet,kaynak,set_surum)
                   VALUES ('test ürün','tr','TR','DISCOVERY','TEST','test-v1')
                   RETURNING query_id"""
            ).fetchone()[0]
            payload = {"results": [
                {"url": "https://www.example.com/p?variant=50ml&utm_source=x",
                 "title": alias + " 50 ml", "content": "Ürün listesi"},
                {"url": "https://www.example.com/p?variant=100ml",
                 "title": "Başka boy", "content": ""},
            ]}
            result = ingest_response(conn, query_id, payload)
            self.assertEqual(result["citations"], 2)
            self.assertEqual(result["mentions"], 1)
            observation_id = result["observation_id"]
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM core.geo_citation_mention WHERE citation_id IN "
                "(SELECT citation_id FROM core.geo_citation WHERE observation_id=%s)",
                (observation_id,),
            ).fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM core.geo_citation WHERE observation_id=%s",
                (observation_id,),
            ).fetchone()[0], 2)
            unavailable_id = record_unavailable(conn, query_id)
            self.assertEqual(conn.execute(
                "SELECT durum,ham_id FROM core.geo_observation WHERE observation_id=%s",
                (unavailable_id,),
            ).fetchone(), ("UNAVAILABLE", None))
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
