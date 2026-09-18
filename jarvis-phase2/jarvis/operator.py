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
import subprocess
from dataclasses import dataclass
from typing import Any

import re

from .action_contract import INTENT_TO_CANONICAL
from .memory import MemoryError

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


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
        result = subprocess.run(command, capture_output=True, text=True,
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
               "SELECT action_id,task_id,action_type,payload,risk_class,"
               "policy_version,proposed_at,expires_at FROM core.ai_get_pending_actions() "
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
    def decide(self, action_id: int, decision: str, reason: str) -> dict[str, Any]:
        if decision not in ("APPROVED", "REJECTED"):
            raise ValueError("decision must be APPROVED or REJECTED")
        action_id = int(action_id)
        if not reason or not reason.strip():
            raise ValueError("a reason is required")
        escaped_reason = reason.replace("'", "''")
        # ai_action_proposal cannot be read back directly (owner-only table
        # grant), so the decision is confirmed by re-checking the pending
        # list in the SAME session: a successful APPROVE/REJECT always
        # removes the action_id from it.
        sql = (
            "BEGIN; SET SESSION AUTHORIZATION human_approver; "
            f"SELECT core.ai_decide_action({action_id}, '{decision}', '{escaped_reason}'); "
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
