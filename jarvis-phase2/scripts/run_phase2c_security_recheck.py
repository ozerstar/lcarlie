#!/usr/bin/env python3
"""PHASE 2C -- adversarial security recheck against the live database.

Every statement runs inside ONE transaction that is always rolled back, each
guarded by its own SAVEPOINT so a rejection does not poison the rest.

Two kinds of check:

  DENY  -- the statement MUST be rejected, and the rejection MUST be a
           privilege error. A rejection for any other reason (missing table,
           bad signature) is reported INCONCLUSIVE, never PASS -- otherwise a
           typo would look like a security guarantee.
  ALLOW -- a positive control that MUST succeed. Without these, a suite where
           everything fails for an unrelated reason would report all-green.
"""
from __future__ import annotations

import json
import os
import resource
import sys
from datetime import datetime, timezone
from time import perf_counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from psql_session import PsqlError, PsqlSession  # noqa: E402

PRIVILEGE_MARKERS = (
    "permission denied",
    "must be owner",
    "must be superuser",
    "denied to set role",
    "is not a member of role",
    "no privileges",
    "admin option",
    "must have admin",
)

# (id, role, kind, sql, note)
CHECKS = [
    # --- ai_writer: raw DML must never bypass the controlled interfaces ---
    ("raw_dml_truncate", "ai_writer", "DENY", "TRUNCATE core.ai_task", "raw TRUNCATE"),
    ("raw_dml_delete", "ai_writer", "DENY", "DELETE FROM core.ai_task", "raw DELETE"),
    ("raw_dml_update_task", "ai_writer", "DENY",
     "UPDATE core.ai_task SET state='DONE'", "raw UPDATE of task state"),
    ("raw_dml_insert_state", "ai_writer", "DENY",
     "INSERT INTO core.jarvis_task_state(task_id,state_json,version) VALUES (-1,'{}'::jsonb,1)",
     "raw write to persistent Jarvis state"),
    ("raw_dml_update_state", "ai_writer", "DENY",
     "UPDATE core.jarvis_task_state SET version=version+1", "raw version bump"),
    ("raw_dml_delete_proposal", "ai_writer", "DENY",
     "DELETE FROM core.ai_action_proposal", "raw proposal deletion"),

    # --- ai_writer: privilege escalation ---------------------------------
    ("set_role_human_approver", "ai_writer", "DENY",
     "SET ROLE human_approver", "self approval via role switch"),
    ("set_role_action_executor", "ai_writer", "DENY",
     "SET ROLE action_executor", "execution via role switch"),
    ("set_role_function_owner", "ai_writer", "DENY",
     "SET ROLE function_owner", "owning the SECURITY DEFINER boundary"),
    ("alter_role_superuser", "ai_writer", "DENY",
     "ALTER ROLE ai_writer SUPERUSER", "self promotion"),
    ("grant_approver", "ai_writer", "DENY",
     "GRANT human_approver TO ai_writer", "self grant"),
    ("create_role", "ai_writer", "DENY",
     "CREATE ROLE jarvis_escalation LOGIN", "new identity creation"),

    # --- ai_writer: approval / execution surfaces ------------------------
    ("self_approval", "ai_writer", "DENY",
     "SELECT core.ai_decide_action(1, 'APPROVED', 'self approval attempt')",
     "approving its own proposal"),
    ("direct_execution", "ai_writer", "DENY",
     "SELECT * FROM core.ai_claim_approved_action('adversarial-worker', 60)",
     "claiming an approved action for execution"),
    ("self_enqueue", "ai_writer", "DENY",
     "SELECT core.ai_enqueue_task('MANUAL', NULL, 'PROPOSE_DECISION', 'test-adversarial-enqueue')",
     "creating its own work"),

    # --- ai_writer: shell / secrets --------------------------------------
    ("shell_via_copy", "ai_writer", "DENY",
     "COPY (SELECT 1) TO PROGRAM 'id'", "shell execution from SQL"),
    ("read_n8n_credentials", "ai_writer", "DENY",
     "SELECT id FROM credentials_entity LIMIT 1", "reading stored credentials"),

    # --- ai_reader: read-only boundary -----------------------------------
    ("reader_insert", "ai_reader", "DENY",
     "INSERT INTO core.jarvis_task_state(task_id,state_json,version) VALUES (-2,'{}'::jsonb,1)",
     "reader writing state"),
    ("reader_propose", "ai_reader", "DENY",
     "SELECT core.ai_propose_action(1, gen_random_uuid(), 'k', 'CRM_REPLY_DRAFT', '{}'::jsonb)",
     "reader proposing an action"),
    ("reader_save_state", "ai_reader", "DENY",
     "SELECT core.ai_save_jarvis_task_state(1, 0, '{}'::jsonb)", "reader saving state"),
    ("reader_provider_allowed", "ai_reader", "DENY",
     "SELECT core.ai_provider_allowed('anthropic')",
     "grant deliberately NOT widened (see handoff section 9)"),
    ("reader_decide_action", "ai_reader", "DENY",
     "SELECT core.ai_decide_action(1, 'APPROVED', 'x')", "reader approving"),

    # --- Phase 2D: the action contract grant (migration 004) -------------
    ("contract_ungranted_column", "ai_reader", "DENY",
     "SELECT description FROM core.ai_action_type",
     "column-level grant must not expose description"),
    ("contract_star_select", "ai_reader", "DENY",
     "SELECT * FROM core.ai_action_type",
     "SELECT * must fail; only the six granted columns are readable"),
    ("contract_writer_cannot_read", "ai_writer", "DENY",
     "SELECT action_type FROM core.ai_action_type",
     "ai_writer proposes through the function, it never reads the table"),
    ("contract_reader_cannot_write", "ai_reader", "DENY",
     "UPDATE core.ai_action_type SET proposal_enabled=false",
     "the contract stays read-only for Jarvis"),
    ("contract_reader_cannot_insert", "ai_reader", "DENY",
     "INSERT INTO core.ai_action_type(action_type,risk_class,approval_mode,"
     "proposal_enabled,execution_enabled,schema_version,description) VALUES "
     "('EVIL','LOW','ONE_PERSON',true,true,'v1','x')",
     "Jarvis cannot add an action type to its own allowlist"),

    # --- positive controls: these MUST succeed ---------------------------
    ("allow_reader_health", "ai_reader", "ALLOW",
     "SELECT core.ai_orchestrator_health()", "approved health surface"),
    ("allow_reader_agenda", "ai_reader", "ALLOW",
     "SELECT count(*) FROM mart.sirket_gundemi", "approved mart read"),
    ("allow_reader_load_state", "ai_reader", "ALLOW",
     "SELECT count(*) FROM core.ai_load_jarvis_task_state(1)", "controlled state load"),
    ("allow_writer_model_policy", "ai_writer", "ALLOW",
     "SELECT core.ai_get_model_policy()", "approved policy surface"),
    ("allow_reader_action_contract", "ai_reader", "ALLOW",
     "SELECT action_type,risk_class,approval_mode,proposal_enabled,"
     "execution_enabled,schema_version FROM core.ai_action_type",
     "the granted projection the canonical contract loader uses"),
]


def classify(detail: str) -> str:
    low = detail.casefold()
    return "PRIVILEGE" if any(marker in low for marker in PRIVILEGE_MARKERS) else "OTHER"


def main() -> int:
    started = perf_counter()
    results = []
    session = PsqlSession()
    try:
        session.run("BEGIN")
        for check_id, role, kind, sql, note in CHECKS:
            session.run("SAVEPOINT sp")
            try:
                session.run(f"SET SESSION AUTHORIZATION {role}")
            except PsqlError as exc:
                results.append({"id": check_id, "role": role, "kind": kind, "note": note,
                                "result": "INCONCLUSIVE", "detail": f"cannot assume role: {exc}"})
                session.run("ROLLBACK TO SAVEPOINT sp")
                continue

            try:
                session.run(sql)
                outcome = ("PASS", "statement succeeded as required") if kind == "ALLOW" else \
                          ("FAIL", "statement was ACCEPTED but must be denied")
            except PsqlError as exc:
                detail = str(exc)
                if kind == "ALLOW":
                    outcome = ("FAIL", f"positive control failed: {detail}")
                elif classify(detail) == "PRIVILEGE":
                    outcome = ("PASS", f"denied: {detail}")
                else:
                    outcome = ("INCONCLUSIVE",
                               f"rejected, but NOT by a privilege check: {detail}")

            results.append({"id": check_id, "role": role, "kind": kind, "note": note,
                            "result": outcome[0], "detail": outcome[1]})
            session.run("ROLLBACK TO SAVEPOINT sp")
            session.run("RESET SESSION AUTHORIZATION")
    finally:
        try:
            session.run("RESET SESSION AUTHORIZATION")
            session.run("ROLLBACK")
        except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
            pass
        session.close()

    failed = [row for row in results if row["result"] == "FAIL"]
    inconclusive = [row for row in results if row["result"] == "INCONCLUSIVE"]
    report = {
        "test": "PHASE2C_SECURITY_RECHECK",
        "status": "FAIL" if failed else ("PARTIAL" if inconclusive else "PASS"),
        "transaction": "BEGIN ... ROLLBACK (nothing committed)",
        "counts": {
            "total": len(results),
            "pass": len(results) - len(failed) - len(inconclusive),
            "fail": len(failed),
            "inconclusive": len(inconclusive),
            "deny_checks": sum(1 for row in results if row["kind"] == "DENY"),
            "allow_controls": sum(1 for row in results if row["kind"] == "ALLOW"),
        },
        "checks": results,
        "telemetry": {
            "total_ms": round((perf_counter() - started) * 1000, 3),
            "model_calls": 0,
            "external_provider_calls": 0,
            "external_actions": 0,
            "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
