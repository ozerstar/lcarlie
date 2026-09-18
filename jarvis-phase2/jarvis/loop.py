"""Minimum Operational Jarvis: READ -> ANALYZE -> DETECT -> PROPOSE -> STOP.

Discovered during this task: a SEPARATE, older, pre-existing orchestrator
("System A": ai_generate_company_intelligence_task -> PROPOSE_DECISION tasks
-> core.karar rows -> mart.ai_approval_inbox -> human-approval-cli.sh ->
core.human_decide_karar) already runs on this host, with its own worker
(worker.js, currently failing on an unrelated DNS issue -- EAI_AGAIN
lcarlie-postgres inside the lcarlie_ai_egress docker network) and its own
human approval CLI. That system is NOT touched, NOT fixed, and NOT reused
here: this task's mandate is specifically the Action Firewall / PROPOSE_ACTION
/ core.ai_action_proposal pipeline built in Phase 2C/2D ("System B"). Naming a
different action type/table would be scope creep.

core.ai_claim_task() has no task_type filter -- it claims whatever OPEN task
is oldest, regardless of who it belongs to. To avoid ever silently absorbing a
System-A PROPOSE_DECISION task, this loop:
  1. claims at most one task per cycle,
  2. immediately checks task_type,
  3. if it is not PROPOSE_ACTION, calls core.ai_fail_task(..., FAILED_RETRYABLE)
     to hand it straight back to the pool (it stays eligible for whoever
     actually owns it), and stops -- it never touches the task's payload.

ai_writer has no SELECT on core.ai_task (table ACL is owner-only), so the only
task content this loop can see after claiming is what ai_claim_task() itself
returns: task_id, source_type, source_id, task_type, idempotency_key,
context_profile, lease_token, attempt_count. There is no free-text field
available to ai_writer. The internal intent is therefore carried in the
idempotency_key by convention, set by a human via `jarvis-operator create-task`:

    jarvis:<INTERNAL_INTENT>:<slug>

e.g. jarvis:HUMAN_REVIEW_REQUEST:demo-2026-09-18. This requires no new grant
and needs no schema change. A richer per-task context field is a real
improvement -- recorded in the report backlog, not implemented here.

Zero model calls anywhere in this module. Analysis is pure deterministic
Python.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

from .action_contract import ContractCache
from .firewall import ContractDriftError, FirewallError, validate_proposal
from .memory import CompanyMemory, MemoryError

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
STATE_FILE = STATE_DIR / "loop-state.json"
FINDINGS_LOG = STATE_DIR / "findings.jsonl"
AUDIT_LOG = STATE_DIR / "audit.jsonl"

WORKER_ID = "jarvis-operational-loop"
LEASE_SECONDS = 60


# --------------------------------------------------------------------------
# local operational bookkeeping (NOT company truth -- that stays in Postgres)
# --------------------------------------------------------------------------
def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"cycle_count": 0, "noop_count": 0, "issue_found_count": 0,
                "task_claimed_count": 0, "proposal_created_count": 0,
                "skipped_not_mine_count": 0, "last_issue_signature": None,
                "last_run_at": None}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# --------------------------------------------------------------------------
# database access -- one-shot subprocess calls, exactly the pattern already
# used by jarvis/memory.py and jarvis/operator.py in this repository
# --------------------------------------------------------------------------
def _psql(sql: str, host: str | None, role: str | None = None, timeout_s: int = 15) -> list[Any]:
    body = f"SET SESSION AUTHORIZATION {role}; {sql}" if role else sql
    wrapped = f"BEGIN; {body} COMMIT;"
    psql = ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-U", "n8n", "-d", "n8n", "-Atc", wrapped]
    command = (["ssh", host, " ".join(
        ["docker exec lcarlie-postgres psql -X -q -v ON_ERROR_STOP=1 -U n8n -d n8n -Atc",
         f'"{wrapped}"']
    )] if host else psql)
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    if result.returncode:
        raise MemoryError(result.stderr.strip() or "loop query failed")
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _claim_task(host: str | None) -> dict[str, Any] | None:
    sql = (f"SELECT row_to_json(x) FROM (SELECT task_id,source_type,source_id,task_type,"
           f"idempotency_key,context_profile,lease_token,attempt_count "
           f"FROM core.ai_claim_task('{WORKER_ID}', {LEASE_SECONDS})) x;")
    rows = _psql(sql, host, role="ai_writer")
    return rows[0] if rows else None


def _fail_task(task_id: int, lease_token: str, reason: str, host: str | None) -> None:
    safe_reason = reason.replace("'", "''")[:500]
    sql = (f"SELECT core.ai_fail_task({int(task_id)}, '{lease_token}'::uuid, "
           f"'FAILED_RETRYABLE', '{safe_reason}');")
    _psql(sql, host, role="ai_writer")


def _propose_action(task_id: int, lease_token: str, idempotency_key: str,
                    action_type: str, payload: dict[str, Any], host: str | None) -> int:
    escaped_key = idempotency_key.replace("'", "''")
    payload_json = json.dumps(payload, ensure_ascii=False).replace("'", "''")
    sql = (f"SELECT core.ai_propose_action({int(task_id)}, '{lease_token}'::uuid, "
           f"'{escaped_key}', '{action_type}', '{payload_json}'::jsonb) AS proposal_id;")
    rows = _psql(sql, host, role="ai_writer")
    return int(rows[0]) if rows else None


# --------------------------------------------------------------------------
# observation + deterministic analysis (zero model calls)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Observation:
    health: dict[str, Any]
    agenda_count: int
    observed_at: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe(memory: CompanyMemory) -> Observation:
    health_evidence = memory.get_system_status()
    health = health_evidence.records[0] if health_evidence.records else {}
    agenda_evidence = memory.get_company_agenda()
    agenda_count = len(agenda_evidence.records)
    payload = {"health": health, "agenda_count": agenda_count}
    content_hash = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return Observation(health=health, agenda_count=agenda_count,
                       observed_at=datetime.now(timezone.utc).isoformat(),
                       content_hash=content_hash)


@dataclass(frozen=True)
class Analysis:
    status: str  # NOOP | ISSUE
    reason: str
    signature: str | None
    evidence: dict[str, Any]


def analyze(observation: Observation) -> Analysis:
    """Deterministic rule set. No model call. No fabricated issue."""
    failed = int(observation.health.get("failed_executions") or 0)
    if failed > 0:
        return Analysis(
            status="ISSUE", reason=f"{failed} failed execution(s) detected",
            signature=f"failed_executions:{failed}",
            evidence={"failed_executions": failed, "checked_at": observation.health.get("checked_at")},
        )
    open_tasks = int(observation.health.get("open_tasks") or 0)
    leased = int(observation.health.get("leased_tasks") or 0)
    if open_tasks > 50:
        return Analysis(
            status="ISSUE", reason=f"{open_tasks} open tasks, queue may be stuck",
            signature=f"open_tasks_high:{open_tasks}",
            evidence={"open_tasks": open_tasks, "leased_tasks": leased},
        )
    return Analysis(status="NOOP", reason="no rule matched current evidence",
                    signature=None, evidence=observation.to_dict())


# --------------------------------------------------------------------------
# one operational cycle
# --------------------------------------------------------------------------
def run_cycle(host: str | None = "lcarlie") -> dict[str, Any]:
    started = perf_counter()
    state = _load_state()
    timings: dict[str, float] = {}

    memory = CompanyMemory(host=host)
    t0 = perf_counter()
    observation = observe(memory)
    timings["observe_ms"] = round((perf_counter() - t0) * 1000, 3)

    t0 = perf_counter()
    analysis = analyze(observation)
    timings["analyze_ms"] = round((perf_counter() - t0) * 1000, 3)

    finding_logged = False
    if analysis.status == "ISSUE":
        if analysis.signature != state.get("last_issue_signature"):
            _append_jsonl(FINDINGS_LOG, {
                "observed_at": observation.observed_at, "signature": analysis.signature,
                "reason": analysis.reason, "evidence": analysis.evidence,
                "note": ("Jarvis cannot enqueue its own task (ai_enqueue_task is granted to "
                         "human_approver only, by design). This finding is recorded for a "
                         "human or another authorized source to act on."),
            })
            finding_logged = True
            state["issue_found_count"] = state.get("issue_found_count", 0) + 1
        state["last_issue_signature"] = analysis.signature
    else:
        state["last_issue_signature"] = None

    # -- claim at most one PROPOSE_ACTION task, fail-safe on anything else --
    t0 = perf_counter()
    claimed = None
    try:
        claimed = _claim_task(host)
    except MemoryError as exc:
        claimed_error = str(exc)
    else:
        claimed_error = None
    timings["claim_ms"] = round((perf_counter() - t0) * 1000, 3)

    result = "NOOP"
    proposal_id = None
    task_detail = None

    if claimed_error:
        result = "CLAIM_FAILED"
        task_detail = {"error": claimed_error}
    elif claimed is None:
        result = "NOOP"
    elif claimed.get("task_type") != "PROPOSE_ACTION":
        _fail_task(claimed["task_id"], claimed["lease_token"],
                  "not owned by jarvis operational loop; wrong task_type", host)
        result = "SKIPPED_NOT_MINE"
        state["skipped_not_mine_count"] = state.get("skipped_not_mine_count", 0) + 1
        task_detail = {"task_id": claimed["task_id"], "task_type": claimed.get("task_type")}
    else:
        state["task_claimed_count"] = state.get("task_claimed_count", 0) + 1
        key = claimed.get("idempotency_key") or ""
        parts = key.split(":", 2)
        internal_intent = parts[1] if len(parts) >= 2 and parts[0] == "jarvis" else None
        t0 = perf_counter()
        try:
            contract = ContractCache(memory).get()
            if internal_intent is None:
                raise FirewallError(f"idempotency_key does not follow jarvis:<intent>:<slug>: {key!r}")
            payload = {"subject_ref": key,
                      "reason": f"Automated proposal from operator-originated task {key}"}
            validated = validate_proposal(internal_intent, payload, contract,
                                          idempotency_key=f"action:{key}")
            proposal_id = _propose_action(claimed["task_id"], claimed["lease_token"],
                                          validated["idempotency_key"],
                                          validated["action_type"], validated["payload"], host)
            result = "PROPOSED"
            state["proposal_created_count"] = state.get("proposal_created_count", 0) + 1
            task_detail = {"task_id": claimed["task_id"], "internal_intent": internal_intent,
                          "action_type": validated["action_type"], "proposal_id": proposal_id}
        except (FirewallError, ContractDriftError, MemoryError) as exc:
            _fail_task(claimed["task_id"], claimed["lease_token"], str(exc)[:500], host)
            result = "FIREWALL_REJECTED"
            task_detail = {"task_id": claimed["task_id"], "error": str(exc)}
        timings["propose_ms"] = round((perf_counter() - t0) * 1000, 3)

    if result == "NOOP" and not finding_logged:
        state["noop_count"] = state.get("noop_count", 0) + 1

    state["cycle_count"] = state.get("cycle_count", 0) + 1
    state["last_run_at"] = observation.observed_at
    _save_state(state)

    report = {
        "cycle": state["cycle_count"], "result": result,
        "analysis_status": analysis.status, "analysis_reason": analysis.reason,
        "finding_logged": finding_logged, "task_detail": task_detail,
        "observation_hash": observation.content_hash,
        "timings_ms": timings, "total_ms": round((perf_counter() - started) * 1000, 3),
        "model_calls": 0, "external_provider_calls": 0, "external_actions": 0,
        "state_summary": {k: v for k, v in state.items() if k.endswith("_count")},
    }
    _append_jsonl(AUDIT_LOG, report)
    return report
