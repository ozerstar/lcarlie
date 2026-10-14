#!/usr/bin/env python3
"""PHASE 2D / F-1 -- real end-to-end proposal through the canonical boundary.

A dummy risky request travels the ACTUAL Jarvis path:

    request -> planner -> risk -> intent selection -> canonical contract
            -> firewall -> core.ai_propose_action -> PROPOSED -> STOP

No SQL is handcrafted to simulate success: the action type, risk class and
approval mode all come from the contract loaded out of PostgreSQL, and the
payload is handed to the controlled SECURITY DEFINER interface exactly as the
firewall produced it. If the Python layer and the database disagreed about
anything, the database would refuse -- which is the whole point of F-1.

Everything runs inside ONE transaction that is always rolled back. No external
action, no approval, no execution.
"""
from __future__ import annotations

import json
import os
import resource
import sys
from datetime import datetime, timezone
from time import perf_counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis.action_contract import load_contract, propose_intent_for  # noqa: E402
from jarvis.firewall import ContractDriftError, FirewallError, validate_proposal  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402
from jarvis.runtime import build_plan  # noqa: E402
from jarvis.transport import memory_host  # noqa: E402
from psql_session import PsqlError, PsqlSession, encode  # noqa: E402

WORKER = "test-phase2d-worker"
RUN_TAG = f"test-phase2d-{int(datetime.now(timezone.utc).timestamp())}"

# Payloads are supplied by the caller, as they would be in production. The
# SHAPE is the database's contract (see core.ai_propose_action); Jarvis does
# not mirror it, so an incorrect shape must be refused BY POSTGRESQL.
REQUESTS = [
    {
        "name": "risky_customer_action",
        # A genuinely risky external action: the planner must flag it.
        "expect_planner_risky": True,
        "request": "Bu müşteriye WhatsApp mesajı gönder.",
        "payload": {
            "recipient_ref": "conversation:test-phase2d",
            "template_ref": "template:shadow-only",
            "variables": {"note": "never sent"},
        },
    },
    {
        "name": "capability_gap_remediation",
        # Asking a human to decide is the SAFE path, not a risky action, so
        # the planner correctly leaves it PLANNED. It must still travel the
        # firewall and still land as PROPOSED awaiting approval -- that is
        # what proves a capability gap has no back door around F-1.
        "expect_planner_risky": False,
        "request": "Bu capability eksikliği için insana karar gerekiyor.",
        "payload": {
            "subject_ref": "capability:semantic_memory_retrieval",
            "reason": "RESOURCE_BLOCKED: BGE-M3 needs >= 32 GiB; host has less.",
        },
    },
]

checks: list[dict] = []
cases: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    checks.append({"check": name, "result": "PASS" if passed else "FAIL", "detail": detail})
    return passed


def main() -> int:
    started = perf_counter()
    timings: dict[str, float] = {}

    # ---- contract comes from PostgreSQL, not from Python ----------------
    load_started = perf_counter()
    contract = load_contract(CompanyMemory(host=memory_host()))
    timings["contract_load_ms"] = round((perf_counter() - load_started) * 1000, 3)
    check("D1_contract_loaded_from_postgres", contract.valid,
          f"{contract.reason}; source={contract.source} hash={contract.contract_hash[:16]} "
          f"canonical={contract.canonical_action_count} mapped={contract.mapped_action_count}")
    if not contract.valid:
        print(json.dumps({"test": "PHASE2D_PROPOSAL_E2E", "status": "FAIL",
                          "checks": checks}, ensure_ascii=False, indent=2))
        return 1

    session = PsqlSession()
    try:
        session.run("BEGIN")
        for index, case in enumerate(REQUESTS):
            tag = f"{RUN_TAG}-{index}"

            # -- planner ------------------------------------------------
            plan = build_plan(case["request"])
            planned_risky = plan.status == "PROPOSED"
            check(f"D2.{index}_planner_risk_matches_expectation",
                  planned_risky == case["expect_planner_risky"],
                  f"{case['name']}: plan.status={plan.status} "
                  f"expected_risky={case['expect_planner_risky']}")

            # -- intent selection + firewall ----------------------------
            firewall_started = perf_counter()
            internal_intent = propose_intent_for(case["request"])
            check(f"D3.{index}_internal_intent_selected", internal_intent is not None,
                  f"{case['name']}: intent={internal_intent}")
            validated = validate_proposal(internal_intent, case["payload"], contract,
                                          idempotency_key=f"action:{tag}")
            firewall_ms = round((perf_counter() - firewall_started) * 1000, 3)
            check(f"D4.{index}_firewall_returned_canonical_type",
                  validated["action_type"] in contract.actions,
                  f"{case['name']}: {internal_intent} -> {validated['action_type']} "
                  f"risk={validated['risk_class']} approval={validated['approval_mode']}")

            # -- controlled database boundary ---------------------------
            db_started = perf_counter()
            session.run("SET SESSION AUTHORIZATION human_approver")
            task_id = session.scalar(
                "SELECT core.ai_enqueue_task('MANUAL', NULL, 'PROPOSE_ACTION', "
                f"{encode(tag)}, 'default', 100)")
            session.run("RESET SESSION AUTHORIZATION")
            session.run("SET SESSION AUTHORIZATION ai_writer")
            claimed = session.fetch_one(
                f"SELECT task_id, lease_token FROM core.ai_claim_task({encode(WORKER)}, 300)")
            lease = claimed[1] if claimed else None

            proposal_id, proposal_error = None, ""
            session.run("SAVEPOINT propose")
            try:
                proposal_id = session.scalar(
                    f"SELECT core.ai_propose_action({task_id}, {encode(lease)}::uuid, "
                    f"{encode(validated['idempotency_key'])}, "
                    f"{encode(validated['action_type'])}, {encode(validated['payload'])}::jsonb)")
                session.run("RELEASE SAVEPOINT propose")
            except PsqlError as exc:
                proposal_error = str(exc)
                session.run("ROLLBACK TO SAVEPOINT propose")
            db_ms = round((perf_counter() - db_started) * 1000, 3)

            check(f"D5.{index}_postgres_accepted_the_proposal", proposal_id is not None,
                  f"{case['name']}: proposal_id={proposal_id} err={proposal_error}")

            session.run("RESET SESSION AUTHORIZATION")
            state = risk_class = None
            if proposal_id is not None:
                row = session.fetch_one(
                    "SELECT state, risk_class FROM core.ai_action_proposal "
                    f"WHERE action_id={proposal_id}")
                state, risk_class = (row[0], row[1]) if row else (None, None)
            check(f"D6.{index}_status_is_PROPOSED", state == "PROPOSED",
                  f"{case['name']}: state={state}")
            check(f"D7.{index}_risk_class_matches_contract", risk_class == validated["risk_class"],
                  f"{case['name']}: db={risk_class} contract={validated['risk_class']}")

            # Regardless of planner risk, nothing may be approved or executed.
            undecided = session.fetch_one(
                "SELECT decided_by, decided_at FROM core.ai_action_proposal "
                f"WHERE action_id={proposal_id}") if proposal_id is not None else None
            check(f"D7b.{index}_no_approval_and_no_execution",
                  undecided is None or (not undecided[0] and not undecided[1]),
                  f"{case['name']}: decided_by={undecided[0] if undecided else '-'} "
                  f"execution_enabled={validated['execution_enabled']}")

            cases.append({
                "name": case["name"], "request": case["request"],
                "internal_intent": internal_intent,
                "canonical_action_type": validated["action_type"],
                "risk_class": validated["risk_class"],
                "approval_mode": validated["approval_mode"],
                "schema_version": validated["schema_version"],
                "execution_enabled": validated["execution_enabled"],
                "task_id": task_id, "proposal_id": proposal_id,
                "proposal_status": state,
                "idempotency_key": validated["idempotency_key"],
                "evidence_refs": [contract.source, "postgres:core.ai_propose_action"],
                "external_action": False, "human_approval_required": True,
                "firewall_ms": firewall_ms, "proposal_path_ms": db_ms,
            })
            session.run("SET SESSION AUTHORIZATION ai_writer")

        # ---- adversarial: nothing may reach the database ---------------
        session.run("RESET SESSION AUTHORIZATION")
        for name, intent, payload in (
            ("unknown_python_action", "RUN_SHELL", {"reason": "x"}),
            ("retired_phase2c_name", "CRM_REPLY_DRAFT", {"reason": "x"}),
            ("canonical_name_used_directly", "REQUEST_HUMAN_REVIEW", {"reason": "x"}),
            ("case_manipulation", "price_change", {"reason": "x"}),
            ("whitespace_manipulation", " PRICE_CHANGE", {"reason": "x"}),
            ("forbidden_payload", "HUMAN_REVIEW_REQUEST", {"shell": "id"}),
            ("malformed_payload", "HUMAN_REVIEW_REQUEST", "not-an-object"),
        ):
            try:
                validate_proposal(intent, payload, contract, idempotency_key=f"action:{RUN_TAG}-adv")
                check(f"D8_{name}_blocked", False, "firewall ACCEPTED it")
            except (FirewallError, ContractDriftError) as exc:
                check(f"D8_{name}_blocked", True, f"blocked: {exc}")

        # contract drift must block even a legitimate intent
        from jarvis.action_contract import build_contract
        try:
            validate_proposal("HUMAN_REVIEW_REQUEST", {"subject_ref": "a", "reason": "b"},
                              build_contract([], "postgres:action_contract"))
            check("D8_contract_drift_blocked", False, "firewall ACCEPTED it")
        except ContractDriftError as exc:
            check("D8_contract_drift_blocked", True, f"blocked: {exc}")

        # direct database bypass must stay closed
        session.run("SET SESSION AUTHORIZATION ai_writer")
        session.run("SAVEPOINT bypass")
        try:
            session.run("INSERT INTO core.ai_action_proposal"
                        "(task_id,idempotency_key,action_type,payload,payload_hash,"
                        "risk_class,proposed_by,expires_at) VALUES "
                        "(1,'action:bypass','REQUEST_HUMAN_REVIEW','{}'::jsonb,'x','LOW',"
                        "'jarvis',clock_timestamp())")
            check("D9_direct_db_bypass_blocked", False, "raw INSERT ACCEPTED")
        except PsqlError as exc:
            check("D9_direct_db_bypass_blocked", "42501" in str(exc), f"denied: {exc}")
        session.run("ROLLBACK TO SAVEPOINT bypass")

        session.run("SAVEPOINT approve")
        try:
            session.run("SELECT core.ai_decide_action(1,'APPROVED','self approval')")
            check("D10_self_approval_blocked", False, "self approval ACCEPTED")
        except PsqlError as exc:
            check("D10_self_approval_blocked", "42501" in str(exc), f"denied: {exc}")
        session.run("ROLLBACK TO SAVEPOINT approve")

        session.run("SAVEPOINT execute")
        try:
            session.run("SELECT * FROM core.ai_claim_approved_action('adversary', 60)")
            check("D11_direct_execution_blocked", False, "execution claim ACCEPTED")
        except PsqlError as exc:
            check("D11_direct_execution_blocked", "42501" in str(exc), f"denied: {exc}")
        session.run("ROLLBACK TO SAVEPOINT execute")
        session.run("RESET SESSION AUTHORIZATION")
    except Exception as exc:  # noqa: BLE001
        check("D_UNEXPECTED_ERROR", False, f"{type(exc).__name__}: {exc}")
    finally:
        for statement in ("RESET SESSION AUTHORIZATION", "ROLLBACK"):
            try:
                session.run(statement)
            except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
                pass
        try:
            left_proposals = session.scalar(
                f"SELECT count(*) FROM core.ai_action_proposal WHERE idempotency_key LIKE {encode('action:test-phase2d-%')}")
            left_tasks = session.scalar(
                f"SELECT count(*) FROM core.ai_task WHERE idempotency_key LIKE {encode('test-phase2d-%')}")
            check("D12_rollback_left_no_proposal", left_proposals == 0, f"rows={left_proposals}")
            check("D13_rollback_left_no_task", left_tasks == 0, f"rows={left_tasks}")
        except Exception as exc:  # noqa: BLE001
            check("D12_rollback_verification", False, f"{type(exc).__name__}: {exc}")
        session.close()

    failed = [row for row in checks if row["result"] == "FAIL"]
    report = {
        "test": "PHASE2D_PROPOSAL_E2E",
        "status": "PASS" if not failed else "FAIL",
        "run_tag": RUN_TAG,
        "transaction": "BEGIN ... ROLLBACK (nothing committed)",
        "contract": contract.telemetry(),
        "cases": cases,
        "checks": checks,
        "telemetry": {
            **timings,
            "total_ms": round((perf_counter() - started) * 1000, 3),
            "model_calls": 0,
            "external_provider_calls": 0,
            "external_actions": 0,
            "human_approvals_fabricated": 0,
            "executions": 0,
            "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2),
            "success": not failed,
        },
        "sequence_note": ("PostgreSQL sequences are not transactional: the rolled-back "
                          "enqueues consumed core.ai_task ids. No row was committed."),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
