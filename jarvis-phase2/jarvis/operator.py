"""Minimum human proposal surface: list / inspect / approve / reject.

Separation of authority, enforced structurally, not by convention:

  * This module is NEVER imported by jarvis.shadow, jarvis.phase2 or any
    autonomous Jarvis code path. It is only invoked directly, by a human,
    from bin/jarvis-operator.
  * It connects to PostgreSQL as the OPERATOR identity (the same superuser
    docker-exec path every test harness in this repo already uses), then
    does `SET SESSION AUTHORIZATION human_approver` for every statement here.
    Jarvis's own runtime never runs as ai_writer -> human_approver; that
    escalation is denied at the database (Phase 2C/2D security suite, still
    true here).
  * Jarvis (ai_writer) is not, and must never be, a member of human_approver.
    This module does not change that -- it uses a separate connection/role
    switch a human runs by hand.

Every read here runs as human_approver, not ai_reader, because that is what
the database actually grants: core.ai_action_proposal has NO table-level
grant to anyone but its owner (function_owner) -- not even a read one -- and
core.ai_get_pending_actions() is granted to human_approver only. There is no
controlled function that returns a DECIDED proposal's detail, so `inspect`
can only see PENDING proposals; this is a real, disclosed limitation of the
minimum surface, not a bug. `decide()` confirms its own effect by re-checking
that the action_id has left the pending list, since it cannot read the
proposal row back directly either.

APPROVE never causes an external action here: core.ai_decide_action only
inserts an ai_action_execution row when execution_enabled is true for the
action type, and the only thing that ever claims those rows is
action-worker.js, a FakeExecutor that handles REQUEST_HUMAN_REVIEW by writing
an audit record and fails every other action type closed
(see /opt/lcarlie/orchestrator/action-worker.js, F4 execution boundary).
"""
from __future__ import annotations

import json
import os
from jarvis.db_transport import run as db_run
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import re

from .action_contract import INTENT_TO_CANONICAL
from .coding_executor import CodingTaskSpec
from .memory import MemoryError

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

CODING_TASK_PENDING_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "coding_executor" / "pending"


@dataclass(frozen=True)
class OperatorResult:
    rows: list[dict[str, Any]]
    latency_ms: float


class OperatorSession:
    """Runs fixed statements against PostgreSQL as a human operator.

    Every statement here runs as human_approver -- the identity the database
    actually grants ai_get_pending_actions/ai_decide_action/ai_enqueue_task
    to. Reads are always wrapped in BEGIN...ROLLBACK. Nothing here ever runs
    as ai_writer.
    """

    def __init__(self, host: str | None = "lcarlie", timeout_s: int = 12):
        self.host = host
        self.timeout_s = timeout_s

    def _run(self, sql: str, stop_on_error: bool = True) -> list[dict[str, Any]]:
        flags = ["-v", "ON_ERROR_STOP=1"] if stop_on_error else []
        psql = ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q",
                *flags, "-U", "n8n", "-d", "n8n", "-Atc", sql]
        remote_flags = " ".join(flags)
        command = (["ssh", self.host, " ".join(
            [f"docker exec lcarlie-postgres psql -X -q {remote_flags} -U n8n -d n8n -Atc",
             f'"{sql}"']
        )] if self.host else psql)
        result = db_run(command, capture_output=True, text=True,
                                timeout=self.timeout_s, check=False)
        if result.returncode:
            raise MemoryError(result.stderr.strip() or "operator query failed")
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    # -- read-only, as human_approver (the only role granted this function),
    #    always rolled back -------------------------------------------------
    def list_pending(self) -> list[dict[str, Any]]:
        sql = ("BEGIN; SET SESSION AUTHORIZATION human_approver; "
               "SELECT row_to_json(x) FROM ("
               "SELECT p.action_id,p.task_id,p.action_type,p.payload,p.risk_class,"
               "p.policy_version,p.proposed_at,p.expires_at,"
               "r.payload_hash AS fingerprint FROM core.ai_get_pending_actions() p "
               "JOIN core.jarvis_action_registry r ON r.action_key='company:'||p.action_id "
               "ORDER BY proposed_at) x; ROLLBACK;")
        return self._run(sql)

    def inspect(self, action_id: int) -> dict[str, Any] | None:
        """Only PENDING proposals can be inspected: core.ai_action_proposal has
        no read grant for anyone but its owner, and no controlled function
        returns a single decided proposal's detail. Disclosed limitation."""
        action_id = int(action_id)  # reject anything that isn't an integer
        for row in self.list_pending():
            if int(row.get("action_id", -1)) == action_id:
                return row
        return None

    # -- the only write path, and only as human_approver ------------------
    def decide(self, action_id: int, decision: str, reason: str,
               expected_hash: str) -> dict[str, Any]:
        if decision not in ("APPROVED", "REJECTED"):
            raise ValueError("decision must be APPROVED or REJECTED")
        action_id = int(action_id)
        if not reason or not reason.strip():
            raise ValueError("a reason is required")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{32,64}", expected_hash):
            raise ValueError("invalid action fingerprint")
        escaped_reason = reason.replace("'", "''")
        # ai_action_proposal cannot be read back directly (owner-only table
        # grant), so the decision is confirmed by re-checking the pending
        # list in the SAME session: a successful APPROVE/REJECT always
        # removes the action_id from it.
        function_call = (f"core.jarvis_decide_company_action({action_id}, '{decision}', "
                         f"'{escaped_reason}', '{expected_hash}')")
        sql = (
            "BEGIN; SET SESSION AUTHORIZATION human_approver; "
            f"SELECT {function_call}; "
            "SELECT row_to_json(x) FROM (SELECT action_id FROM core.ai_get_pending_actions() "
            f"WHERE action_id={action_id}) x; COMMIT;"
        )
        rows = self._run(sql)
        still_pending = bool(rows)
        return {"action_id": action_id, "decision": decision, "reason": reason,
                "still_pending": still_pending, "confirmed": not still_pending}

    # -- creates a task for the operational loop to pick up ----------------
    def create_task(self, internal_intent: str, slug: str) -> dict[str, Any]:
        """Enqueue a MANUAL/PROPOSE_ACTION task as human_approver.

        Jarvis (ai_writer) cannot call core.ai_enqueue_task itself -- that
        grant is human_approver-only, by design (see jarvis/loop.py). This is
        the human-run counterpart: a person originates the task, the
        operational loop later claims and proposes against it.
        """
        if internal_intent not in INTENT_TO_CANONICAL:
            raise ValueError(f"unknown internal intent: {internal_intent!r}; "
                             f"known: {sorted(INTENT_TO_CANONICAL)}")
        if not _SLUG_RE.match(slug):
            raise ValueError("slug must match [A-Za-z0-9_.-]{1,80}")
        key = f"jarvis:{internal_intent}:{slug}"
        sql = (
            "BEGIN; SET SESSION AUTHORIZATION human_approver; "
            f"SELECT core.ai_enqueue_task('MANUAL', NULL, 'PROPOSE_ACTION', "
            f"'{key}', 'default', 100) AS task_id; COMMIT;"
        )
        rows = self._run(sql, stop_on_error=True)
        task_id = rows[0] if rows else None
        return {"task_id": task_id, "idempotency_key": key, "internal_intent": internal_intent}

    # -- CodingExecutor: a human originates a bounded coding task -----------
    def create_coding_task(self, slug: str, spec_path: str) -> dict[str, Any]:
        """Validate a coding task spec, stage it for the loop, and enqueue
        the CODE_CHANGE_REVIEW task that will pick it up.

        The spec (objective, allowed_files, optional test_command/test_cwd)
        is validated with the SAME CodingTaskSpec.from_dict the executor
        itself uses, so a spec that is rejected here would also be rejected
        at run time -- no separate, potentially-drifting validation path.
        ai_writer has no SELECT on core.ai_task, so the spec is staged on
        disk (not in the idempotency key) for jarvis/loop.py to read after
        claiming the task, exactly like every other intent's slug convention.
        """
        if not _SLUG_RE.match(slug):
            raise ValueError("slug must match [A-Za-z0-9_.-]{1,80}")
        raw = Path(spec_path).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"spec is not valid JSON: {exc}") from exc
        spec = CodingTaskSpec.from_dict(data)  # raises ValueError on an invalid spec

        CODING_TASK_PENDING_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(CODING_TASK_PENDING_DIR, 0o750)
        staged_path = CODING_TASK_PENDING_DIR / f"{slug}.json"
        staged_path.write_text(json.dumps({
            "objective": spec.objective, "allowed_files": list(spec.allowed_files),
            "test_command": list(spec.test_command), "test_cwd": spec.test_cwd,
            "timeout_s": spec.timeout_s,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(staged_path, 0o640)

        task = self.create_task("CODE_CHANGE_REVIEW", slug)
        return {**task, "spec_staged_at": str(staged_path), "allowed_files": list(spec.allowed_files)}
