"""Company data fabric: allowlist integrity, read-only shape, the data
contract, PII minimisation and planner domain resolution.

The offline tests assert properties of the fixed query text and of the
planner's domain table -- no database. The live block (JARVIS_LIVE_TEST=1)
additionally runs every domain query against the real ai_reader path.
"""
import os
import re
import unittest

from jarvis.execution_planner import DATA_UNAVAILABLE, DOMAINS
from jarvis.memory import CompanyMemory, Evidence
from jarvis.transport import memory_host

FABRIC_QUERIES = (
    "sales_orders", "sales_items",
    "ecommerce_profitability", "ecommerce_price", "ecommerce_funnel",
    "advertising_performance", "advertising_spend",
    "crm_customers", "crm_unanswered",
    "operations_shipments",
    "provenance", "data_quality",
)

WRITE_KEYWORDS = ("insert", "update ", "delete", "drop", "truncate", "grant",
                  "revoke", "alter", "create", "copy ")

# Sources that carry customer names or raw message bodies. The fabric reaches
# customers through identifiers, counts and a pseudonym instead.
PII_SOURCES = ("lcarlie.konusma", "lcarlie.mesaj", "musteri_ad", "telefon",
               "email", "e_posta", "adres", "metin")


class AllowlistTests(unittest.TestCase):
    def test_every_fabric_query_is_allowlisted(self):
        for name in FABRIC_QUERIES:
            self.assertIn(name, CompanyMemory.QUERIES, name)

    def test_every_domain_query_is_allowlisted(self):
        for domain, names in CompanyMemory.DOMAIN_QUERIES.items():
            for name in names:
                self.assertIn(name, CompanyMemory.QUERIES, f"{domain}:{name}")

    def test_unknown_query_is_refused(self):
        memory = CompanyMemory(host=None)
        with self.assertRaises(ValueError):
            memory._fetch("mart.siparis")

    def test_unknown_domain_raises_rather_than_returning_empty(self):
        memory = CompanyMemory(host=None)
        with self.assertRaises(ValueError):
            memory.get_domain("finance")


class ReadOnlyTests(unittest.TestCase):
    def test_no_query_contains_a_write_statement(self):
        # KELIME SINIRI ile aranir, alt dizgi ile degil. 'created_at' bir
        # sutun adidir ve icinde 'create' gecer; alt dizgi aramasi bu
        # yuzden yanlis alarm veriyordu (olculdu: gunluk_brief sorgusu).
        # Sinirli arama yakaladigini KAYBETMEZ -- bunu bir alttaki test
        # kanitliyor, bu yuzden burada gevseme olmadigi iddia degil olcum.
        for name, sql in CompanyMemory.QUERIES.items():
            lowered = sql.lower()
            for keyword in WRITE_KEYWORDS:
                self.assertIsNone(
                    re.search(rf"\b{keyword.strip()}\b", lowered),
                    f"{name} contains {keyword!r}")

    def test_the_write_guard_still_catches_real_write_statements(self):
        """Kelime sinirina gecerken korumayi gevsetmedik mi?

        Bir koruma kurali degistirildiginde asil risk, sessizce ise
        yaramaz hale gelmesidir. Asagidaki ifadelerin HEPSI yakalanmali;
        biri kacarsa bu test patlar ve gevseme gorunur olur.
        """
        yazma_ifadeleri = (
            "select 1; create table x(a int)",
            "select 1; create or replace view v as select 1",
            "insert into core.urun values (1)",
            "update core.urun set ad='x'",
            "delete from core.urun",
            "drop view mart.gunluk_brief",
            "truncate core.urun",
            "grant select on core.urun to ai_reader",
            "revoke select on core.urun from ai_reader",
            "alter table core.urun add column x int",
            "copy core.urun to '/tmp/x'",
        )
        for sql in yazma_ifadeleri:
            yakalandi = any(re.search(rf"\b{k.strip()}\b", sql.lower())
                            for k in WRITE_KEYWORDS)
            self.assertTrue(yakalandi, f"yakalanmadi: {sql!r}")

    def test_a_column_named_created_at_is_not_a_write(self):
        """Yanlis alarmin kendisi de sinaniyor ki geri gelmesin."""
        masum = "select b.brief_key, b.created_at from mart.gunluk_brief b"
        for k in WRITE_KEYWORDS:
            self.assertIsNone(re.search(rf"\b{k.strip()}\b", masum),
                              f"masum sorgu {k!r} ile yanlis eslesti")

    def test_every_query_starts_with_select(self):
        for name, sql in CompanyMemory.QUERIES.items():
            self.assertTrue(sql.lstrip().lower().startswith("select"), name)

    def test_fetch_wraps_every_query_as_ai_reader_and_rolls_back(self):
        memory = CompanyMemory(host=None)
        captured = {}

        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(command, **kwargs):
            captured["sql"] = command[-1]
            return FakeResult()

        import subprocess
        original = subprocess.run
        subprocess.run = fake_run
        try:
            memory._fetch("sales_orders")
        finally:
            subprocess.run = original

        self.assertIn("SET SESSION AUTHORIZATION ai_reader", captured["sql"])
        self.assertTrue(captured["sql"].strip().endswith("ROLLBACK;"))


class DataContractTests(unittest.TestCase):
    """Section F: a row must be traceable back to its source record."""

    CONTRACT_EXEMPT = {"data_quality"}

    def test_fabric_rows_carry_entity_id_source_and_record_id(self):
        for name in FABRIC_QUERIES:
            sql = CompanyMemory.QUERIES[name]
            self.assertIn("AS entity_id", sql, name)
            self.assertIn("AS source", sql, name)
            self.assertIn("AS source_record_id", sql, name)

    def test_source_literal_names_a_real_relation(self):
        for name in FABRIC_QUERIES:
            sql = CompanyMemory.QUERIES[name]
            match = re.search(r"'([a-z_]+\.[a-z_]+)' AS source", sql)
            self.assertIsNotNone(match, name)
            self.assertIn(match.group(1).split(".")[0], ("mart", "core"), name)

    def test_provenance_query_exposes_freshness_and_connection(self):
        sql = CompanyMemory.QUERIES["provenance"]
        for column in ("freshness", "current_connection", "authority", "observed_at"):
            self.assertIn(column, sql)

    def test_provenance_and_quality_getters_exist(self):
        for name in ("get_provenance", "get_data_quality", "get_domain"):
            self.assertTrue(callable(getattr(CompanyMemory, name, None)), name)


class PiiMinimisationTests(unittest.TestCase):
    def test_no_query_reads_a_pii_source(self):
        for name, sql in CompanyMemory.QUERIES.items():
            lowered = sql.lower()
            for marker in PII_SOURCES:
                self.assertNotIn(marker, lowered, f"{name} references {marker!r}")

    def test_customer_query_exposes_identifiers_not_identities(self):
        sql = CompanyMemory.QUERIES["crm_customers"]
        self.assertIn("customer_id", sql)
        self.assertIn("mart.musteri", sql)

    def test_unanswered_conversations_use_a_pseudonym(self):
        sql = CompanyMemory.QUERIES["crm_unanswered"]
        self.assertIn("musteri_takma", sql)


class DomainResolutionReadinessTests(unittest.TestCase):
    """Section H, the half this workstream owns.

    CompanyMemory now carries a real, allowlisted query set for all five
    domains. Wiring them into the planner's DOMAINS table is a separate,
    prepared change on branch `planner-domain-wiring`: flipping sales,
    ecommerce and advertising away from DATA_UNAVAILABLE changes the
    Execution Runtime's contract, and thirteen of that workstream's tests
    assert the current state. These tests therefore verify that the data side
    is ready and correct, without asserting the planner's own table.
    """

    def test_every_planner_domain_has_a_query_set_available(self):
        for domain in DOMAINS:
            self.assertIn(domain.domain_id, CompanyMemory.DOMAIN_QUERIES,
                          f"{domain.domain_id} has no fabric entry")
            self.assertTrue(CompanyMemory.DOMAIN_QUERIES[domain.domain_id],
                            f"{domain.domain_id} fabric entry is empty")

    def test_the_five_business_domains_are_present(self):
        ids = {domain.domain_id for domain in DOMAINS}
        self.assertEqual(ids, {"sales", "ecommerce", "advertising", "crm", "operations"})
        self.assertEqual(set(CompanyMemory.DOMAIN_QUERIES), ids)

    def test_already_wired_domains_name_only_allowlisted_queries(self):
        for domain in DOMAINS:
            for name in domain.memory_queries:
                self.assertIn(name, CompanyMemory.QUERIES,
                              f"{domain.domain_id}:{name}")

    def test_data_unavailable_marker_still_exists(self):
        """A domain with no source must stay expressible."""
        self.assertEqual(DATA_UNAVAILABLE, "DATA_UNAVAILABLE")


class MalformedDataTests(unittest.TestCase):
    """_fetch must not invent records from unusable output."""

    def _fetch_with_stdout(self, stdout):
        memory = CompanyMemory(host=None)

        class FakeResult:
            returncode = 0
            stderr = ""

        FakeResult.stdout = stdout
        import subprocess
        original = subprocess.run
        subprocess.run = lambda command, **kwargs: FakeResult()
        try:
            return memory._fetch("sales_orders")
        finally:
            subprocess.run = original

    def test_empty_output_gives_zero_records_not_a_placeholder(self):
        evidence = self._fetch_with_stdout("")
        self.assertEqual(evidence.records, [])
        self.assertEqual(evidence.authority, "CANONICAL_COMPANY_MEMORY")

    def test_blank_lines_are_skipped(self):
        evidence = self._fetch_with_stdout('\n\n{"entity_id": 1}\n\n')
        self.assertEqual(len(evidence.records), 1)

    def test_malformed_json_raises_rather_than_guessing(self):
        with self.assertRaises(Exception):
            self._fetch_with_stdout("{not json")

    def test_duplicate_rows_are_preserved_not_silently_merged(self):
        evidence = self._fetch_with_stdout('{"entity_id": 1}\n{"entity_id": 1}\n')
        self.assertEqual(len(evidence.records), 2)


@unittest.skipUnless(os.environ.get("JARVIS_LIVE_TEST") == "1", "live test disabled")
class LiveFabricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = CompanyMemory(host=memory_host())

    def test_every_domain_query_runs_as_ai_reader(self):
        for domain, names in CompanyMemory.DOMAIN_QUERIES.items():
            for name in names:
                evidence = self.memory._fetch(name)
                self.assertIsInstance(evidence, Evidence, f"{domain}:{name}")

    def test_sales_returns_real_orders(self):
        evidence = self.memory._fetch("sales_orders")
        self.assertGreater(len(evidence.records), 0)
        self.assertIn("entity_id", evidence.records[0])
        self.assertIn("source", evidence.records[0])

    def test_advertising_returns_real_spend(self):
        evidence = self.memory._fetch("advertising_spend")
        self.assertGreater(len(evidence.records), 0)
        self.assertIn("harcama", evidence.records[0])

    def test_provenance_reports_connection_state(self):
        evidence = self.memory.get_provenance()
        states = {row.get("current_connection") for row in evidence.records}
        self.assertIn("CONNECTED", states)

    def test_single_query_latency_is_reasonable(self):
        evidence = self.memory._fetch("sales_orders")
        self.assertLess(evidence.latency_ms, 2000)

    def test_write_is_denied_for_ai_reader(self):
        from jarvis.memory import MemoryError
        memory = CompanyMemory(host=memory_host())
        original = CompanyMemory.QUERIES.get("__probe__")
        CompanyMemory.QUERIES["__probe__"] = "INSERT INTO mart.musteri DEFAULT VALUES;"
        try:
            with self.assertRaises(MemoryError):
                memory._fetch("__probe__")
        finally:
            if original is None:
                del CompanyMemory.QUERIES["__probe__"]


if __name__ == "__main__":
    unittest.main()
