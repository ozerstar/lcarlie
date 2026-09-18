from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from time import perf_counter
from typing import Any


class MemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Evidence:
    source: str
    authority: str
    retrieved_at: str
    records: list[dict[str, Any]]
    latency_ms: float


class CompanyMemory:
    """Fixed-query adapter. User/model text is never interpolated into SQL."""

    QUERIES = {
        "system": "SELECT core.ai_orchestrator_health();",
        "agenda": (
            "SELECT row_to_json(x) FROM (SELECT soru_id,hedef,oncelik,soru,"
            "neden_onemli,kaynak_plani,durum,olusturma FROM mart.sirket_gundemi "
            "ORDER BY olusturma DESC LIMIT 25) x;"
        ),
        "open_work": (
            "SELECT row_to_json(x) FROM (SELECT tur,anahtar,detay,zaman,yapilacak "
            "FROM mart.acik_isler ORDER BY zaman DESC LIMIT 25) x;"
        ),
        "decision_summary": "SELECT row_to_json(x) FROM (SELECT * FROM mart.karar_ozet) x;",
        "capabilities": "SELECT core.ai_get_model_policy();",
        "company_dashboard": (
            "SELECT row_to_json(x) FROM (SELECT * FROM "
            "mart.ai_company_intelligence_dashboard) x;"
        ),
        # Phase 2D / F-1: the canonical action contract. Only the six columns
        # ai_reader is granted are named; `description` and `created_at` are
        # deliberately absent and would be denied.
        "action_contract": (
            "SELECT row_to_json(x) FROM (SELECT action_type,risk_class,"
            "approval_mode,proposal_enabled,execution_enabled,schema_version "
            "FROM core.ai_action_type ORDER BY action_type) x;"
        ),
        # Phase 2D / F-2: infrastructure facts for the capability registry.
        # pg_catalog only -- readable by PUBLIC, and unlike
        # information_schema it is not filtered by the caller's privileges,
        # so a missing EXECUTE grant cannot masquerade as a missing function.
        "capability_state": (
            "SELECT row_to_json(x) FROM (SELECT "
            "(SELECT extversion FROM pg_extension WHERE extname='vector') "
            "AS pgvector_version,"
            "(SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname='ai_semantic' "
            "AND c.relname='memory_embedding') AS semantic_table,"
            "(SELECT count(*) FROM pg_indexes WHERE schemaname='ai_semantic') "
            "AS semantic_indexes,"
            "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid=p.pronamespace WHERE n.nspname='core' AND p.proname IN "
            "('ai_save_jarvis_task_state','ai_load_jarvis_task_state')) "
            "AS state_functions,"
            "(SELECT core.ai_orchestrator_health()) AS health) x;"
        ),
    }

    def __init__(self, host: str | None = "lcarlie", timeout_s: int = 12):
        self.host = host
        self.timeout_s = timeout_s

    def _fetch(self, query_name: str) -> Evidence:
        if query_name not in self.QUERIES:
            raise ValueError("query is not allowlisted")
        sql = f"BEGIN; SET SESSION AUTHORIZATION ai_reader; {self.QUERIES[query_name]} ROLLBACK;"
        psql = ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q",
                "-U", "n8n", "-d", "n8n", "-Atc", sql]
        command = (["ssh", self.host, " ".join(
            ["docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -Atc", f'"{sql}"']
        )] if self.host else psql)
        started = perf_counter()
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=self.timeout_s, check=False,
        )
        latency = (perf_counter() - started) * 1000
        if result.returncode:
            raise MemoryError(result.stderr.strip() or "company memory query failed")
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            rows.append(value if isinstance(value, dict) else {"value": value})
        return Evidence(
            source=f"postgres:{query_name}", authority="CANONICAL_COMPANY_MEMORY",
            retrieved_at="live", records=rows, latency_ms=round(latency, 3),
        )

    def get_system_status(self) -> Evidence:
        return self._fetch("system")

    def get_company_context(self) -> Evidence:
        return self._fetch("decision_summary")

    def get_open_tasks(self) -> Evidence:
        status = self.get_system_status()
        return Evidence(status.source, status.authority, status.retrieved_at,
                        [{"open_tasks": status.records[0].get("open_tasks", 0)}], status.latency_ms)

    def get_open_proposals(self) -> Evidence:
        status = self.get_system_status()
        return Evidence(status.source, status.authority, status.retrieved_at,
                        [{"pending_actions": status.records[0].get("pending_actions", 0)}], status.latency_ms)

    def get_executive_brief(self) -> Evidence:
        return self._fetch("company_dashboard")

    def get_company_agenda(self) -> Evidence:
        return self._fetch("agenda")

    def get_open_work(self) -> Evidence:
        return self._fetch("open_work")


    def get_model_policy(self) -> Evidence:
        return self._fetch("capabilities")

    def get_action_contract(self) -> Evidence:
        return self._fetch("action_contract")

    def get_capability_state(self) -> Evidence:
        return self._fetch("capability_state")

    def get_product_context(self, entity: str) -> Evidence:
        agenda = self.get_company_agenda()
        needle = entity.casefold()
        records = [row for row in agenda.records if needle in json.dumps(row, ensure_ascii=False).casefold()]
        return Evidence(agenda.source, agenda.authority, agenda.retrieved_at, records, agenda.latency_ms)
