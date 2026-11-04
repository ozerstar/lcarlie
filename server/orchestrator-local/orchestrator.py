from __future__ import annotations
import hashlib, json, re, time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class TaskLease:
    task_id: int
    source_type: str
    source_id: int | None
    task_type: str
    idempotency_key: str
    context_profile: str
    lease_token: str
    attempt_count: int

@dataclass(frozen=True)
class ContextEnvelope:
    profile: str
    version: str
    task: dict[str, Any]
    trusted_facts: tuple[dict[str, Any], ...]
    company_views: dict[str, tuple[dict[str, Any], ...]]
    external_data: tuple[dict[str, Any], ...]
    policy: dict[str, Any]
    content_hash: str

@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    payload: dict[str, Any]

@dataclass(frozen=True)
class AttemptAudit:
    task_id: int
    provider: str
    model: str
    attempt: int
    started_at: str
    finished_at: str
    latency_ms: int
    result_class: str
    rate_limit: bool
    timeout: bool
    validation_result: str
    failover_reason: str | None
    context_profile: str
    context_version: str
    context_hash: str
    safe_summary: str

PROFILE_VERSION = "decision-v1.0"
LIMITS = {"trusted_facts": 20, "sirket_gundemi": 20, "karar_ozet": 1, "acik_isler": 20, "source_authority": 40}
ALLOWED = {"karar_tipi", "oneri", "anlik_id_text", "kanit_kalitesi", "yanlislama_kosulu", "urun", "kanal", "beklenen_etki", "risk"}
REQUIRED = {"karar_tipi", "oneri", "anlik_id_text", "kanit_kalitesi", "yanlislama_kosulu"}
DECISION_TYPES = {"PRODUCT_PRIORITY", "MEDIA_BUDGET", "OFFER_TEST", "CREATIVE_TEST", "CRO_CHANGE", "AUDIENCE_TEST", "CRM_ACTION"}
FORBIDDEN = {"action", "action_type", "command", "shell", "sql", "url", "http", "headers", "method", "durum"}

def _stable(rows: list[dict[str, Any]], limit: int) -> tuple[dict[str, Any], ...]:
    result = [dict(sorted(row.items())) for row in rows]
    result.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
    return tuple(result[:limit])

def build_context(lease: TaskLease, rows: dict[str, list[dict[str, Any]]]) -> ContextEnvelope:
    if lease.task_type != "PROPOSE_DECISION" or lease.context_profile != "decision-v1":
        raise ValueError("unsupported task/profile")
    canonical = {
        "profile": lease.context_profile,
        "version": PROFILE_VERSION,
        "task": {"task_id": lease.task_id, "source_type": lease.source_type, "source_id": lease.source_id, "task_type": lease.task_type, "idempotency_key": lease.idempotency_key},
        "trusted_facts": _stable(rows.get("trusted_facts", []), LIMITS["trusted_facts"]),
        "company_views": {name: _stable(rows.get(name, []), LIMITS[name]) for name in ("sirket_gundemi", "karar_ozet", "acik_isler")},
        "external_data": _stable(rows.get("source_authority", []), LIMITS["source_authority"]),
        "policy": {"external_text_mode": "DATA_ONLY", "allowed_output": "PROPOSED_DECISION", "forbidden_output": ["ACTION", "COMMAND", "HTTP", "SQL", "URL"], "approval_required": True},
    }
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return ContextEnvelope(content_hash=digest, **canonical)

def validate_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or {str(key).lower() for key in payload} & FORBIDDEN:
        raise ValueError("action/state fields forbidden")
    if set(payload) - ALLOWED or REQUIRED - set(payload):
        raise ValueError("invalid proposal schema")
    if payload["karar_tipi"] not in DECISION_TYPES or payload["kanit_kalitesi"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("invalid enum")
    if not isinstance(payload["anlik_id_text"], str) or not re.fullmatch(r"[0-9]+", payload["anlik_id_text"]):
        raise ValueError("invalid evidence id")
    for field in ("oneri", "yanlislama_kosulu"):
        if not isinstance(payload[field], str) or not payload[field].strip() or len(payload[field]) > 4000:
            raise ValueError("invalid required text")
    for field in ALLOWED - REQUIRED:
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 2000):
            raise ValueError("invalid optional text")
    return {field: payload.get(field) for field in sorted(ALLOWED)}

class FakeProvider:
    name, model = "fake", "fixture-v1"
    def __init__(self, payload: dict): self.payload = deepcopy(payload)
    def generate(self, context: ContextEnvelope) -> ProviderResult:
        if context.policy["allowed_output"] != "PROPOSED_DECISION": raise ValueError("unsafe policy")
        return ProviderResult(self.name, self.model, deepcopy(self.payload))

class InMemoryRepository:
    def __init__(self, tasks: list[TaskLease], context_rows: dict[str, list[dict]]):
        self.tasks, self.context_rows = deque(tasks), context_rows
        self.audits, self.proposals, self.failures = [], [], []
    def claim_task(self, worker_id: str, lease_seconds: int):
        if not worker_id or not 30 <= lease_seconds <= 3600: raise ValueError("invalid lease")
        return self.tasks.popleft() if self.tasks else None
    def read_context_rows(self, lease): return self.context_rows
    def log_attempt(self, audit: AttemptAudit): self.audits.append(audit)
    def complete_proposed_decision(self, lease, proposal):
        if not lease.idempotency_key.startswith("ai:"): raise ValueError("unsafe idempotency")
        self.proposals.append({"task_id": lease.task_id, **proposal, "durum": "PROPOSED"})
        return len(self.proposals)
    def fail_task(self, lease, result_class, reason): self.failures.append((lease.task_id, result_class, reason[:1000]))

class Worker:
    def __init__(self, repository, provider, worker_id: str, lease_seconds: int = 300):
        self.repository, self.provider = repository, provider
        self.worker_id, self.lease_seconds = worker_id, lease_seconds
    def run_once(self):
        lease = self.repository.claim_task(self.worker_id, self.lease_seconds)
        if lease is None: return {"status": "IDLE"}
        started, clock = datetime.now(timezone.utc), time.monotonic()
        context = build_context(lease, self.repository.read_context_rows(lease))
        try:
            proposal = validate_proposal(self.provider.generate(context).payload)
            decision_id = self.repository.complete_proposed_decision(lease, proposal)
            result_class, validation, summary = "SUCCESS", "PASS", "validated PROPOSED decision written"
        except ValueError as error:
            decision_id = None
            result_class, validation, summary = "VALIDATION_FAILED", "FAIL", "provider output rejected"
            self.repository.fail_task(lease, result_class, str(error))
        finished = datetime.now(timezone.utc)
        self.repository.log_attempt(AttemptAudit(lease.task_id, self.provider.name, self.provider.model, lease.attempt_count, started.isoformat(), finished.isoformat(), max(0, round((time.monotonic()-clock)*1000)), result_class, False, False, validation, None, context.profile, context.version, context.content_hash, summary))
        return {"status": result_class, "task_id": lease.task_id, "decision_id": decision_id, "context_hash": context.content_hash}

def demo():
    task = TaskLease(1, "FIXTURE", None, "PROPOSE_DECISION", "ai:f0c:demo", "decision-v1", "fixture", 1)
    repo = InMemoryRepository([task], {"trusted_facts": [{"anlik_id": 1}], "source_authority": [{"authority": "DATA"}]})
    provider = FakeProvider({"karar_tipi": "CRO_CHANGE", "oneri": "İnsan onaylı fixture önerisi.", "anlik_id_text": "1", "kanit_kalitesi": "HIGH", "yanlislama_kosulu": "Fixture başarısız olursa reddet."})
    print(json.dumps(Worker(repo, provider, "f0c-demo").run_once(), sort_keys=True))

if __name__ == "__main__": demo()
