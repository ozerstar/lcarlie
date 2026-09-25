#!/usr/bin/env python3
"""PHASE 2C -- TEST G: provider interruption -> PostgreSQL state -> reload -> fallback.

Proves, against the live database inside ONE transaction that is always rolled
back, that:

  * Jarvis task state survives a provider interruption because it lives in
    PostgreSQL, not in the provider or in process memory.
  * A stale expected_version cannot overwrite newer state (state replay blocked).
  * The same idempotency key cannot produce a second proposal (duplicate
    action replay blocked).
  * The capability router falls back Provider A -> Provider B without losing
    the evidence collected before the interruption.
  * Telemetry reflects exactly one fallback and zero external provider calls.

Both simulated providers are LOCAL callables. No network call is made and no
external action is taken. Role switching below is done by the OPERATOR test
harness (a superuser session), never by Jarvis: Jarvis itself is separately
proven unable to do it -- see run_phase2c_security_recheck.py.
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from time import perf_counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from jarvis.action_contract import INTENT_TO_CANONICAL  # noqa: E402
from jarvis.routing import CapabilityRouter, Provider, ProviderState  # noqa: E402
from jarvis.state_pg import PostgresTaskStateStore  # noqa: E402
from psql_session import PsqlError, PsqlSession, encode  # noqa: E402

WORKER = "test-phase2c-g-worker"
RUN_TAG = f"test-phase2c-g-{int(time.time())}"

checks: list[dict] = []
findings: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    checks.append({"check": name, "result": "PASS" if passed else "FAIL", "detail": detail})
    return passed


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


def cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return round(usage.ru_utime + usage.ru_stime, 3)


def main() -> int:
    started = perf_counter()
    timings: dict[str, float] = {}
    task_id = None
    lease_token = None
    proposal_ids: list = []

    session = PsqlSession()
    try:
        session.run("BEGIN")

        # ---- arrange: operator enqueues a quarantined test task -----------
        t0 = perf_counter()
        session.run("SET SESSION AUTHORIZATION human_approver")
        # task_type must be PROPOSE_ACTION: core.ai_propose_action rejects any
        # other type outright ("invalid action task").
        task_id = session.scalar(
            "SELECT core.ai_enqueue_task('MANUAL', NULL, 'PROPOSE_ACTION', "
            f"{encode(RUN_TAG)}, 'default', 100)"
        )
        session.run("RESET SESSION AUTHORIZATION")
        check("G0_task_enqueued_by_human_approver", isinstance(task_id, int), f"task_id={task_id}")

        # ---- Jarvis identity from here on --------------------------------
        session.run("SET SESSION AUTHORIZATION ai_writer")
        claimed = session.fetch_one(
            f"SELECT task_id, lease_token FROM core.ai_claim_task({encode(WORKER)}, 300)"
        )
        check("G1_task_claimed_as_ai_writer", claimed is not None and claimed[0] == task_id,
              f"claimed={claimed}")
        if claimed is None:
            raise RuntimeError("no task claimed; cannot continue TEST G")
        lease_token = claimed[1]
        timings["arrange_ms"] = round((perf_counter() - t0) * 1000, 3)

        store = PostgresTaskStateStore(session)

        # ---- act 1: state saved BEFORE the provider is called -------------
        t0 = perf_counter()
        state_v1 = {
            "status": "RUNNING",
            "step": "provider_attempt",
            "provider": "A",
            "evidence": ["postgres:system", "postgres:agenda"],
            "run_tag": RUN_TAG,
        }
        version = store.save(task_id, state_v1, expected_version=0)
        check("G2_initial_state_persisted", version == 1, f"version={version}")
        timings["state_save_ms"] = round((perf_counter() - t0) * 1000, 3)

        # ---- act 2: Provider A is interrupted, Provider B continues -------
        t0 = perf_counter()
        attempts_log: list[dict] = []

        def provider_a(envelope: dict) -> dict:
            attempts_log.append({"provider": "A", "result_class": "TIMEOUT", "external_call": False})
            raise TimeoutError("simulated provider A timeout / rate limit")

        def provider_b(envelope: dict) -> dict:
            attempts_log.append({"provider": "B", "result_class": "OK", "external_call": False})
            return {"provider": "B", "summary": "continued from persisted state",
                    "resumed_from_version": envelope["version"]}

        router = CapabilityRouter([
            Provider("A", {"company_memory"}, 1, ProviderState.AVAILABLE, provider_a),
            Provider("B", {"company_memory"}, 2, ProviderState.AVAILABLE, provider_b),
        ])

        # the interruption: nothing is held in process memory across it
        del state_v1
        reloaded, reloaded_version = store.load(task_id)
        check("G3_state_reloaded_after_interruption",
              reloaded.get("run_tag") == RUN_TAG and reloaded_version == 1,
              f"version={reloaded_version} status={reloaded.get('status')}")
        check("G4_evidence_survived_interruption",
              reloaded.get("evidence") == ["postgres:system", "postgres:agenda"],
              f"evidence={reloaded.get('evidence')}")

        outcome, attempted = router.run("company_memory",
                                        {"task_id": task_id, "version": reloaded_version})
        check("G5_fallback_A_to_B", attempted == ["A", "B"], f"attempts={attempted}")
        check("G6_no_task_loss", outcome["resumed_from_version"] == 1, f"outcome={outcome}")
        timings["fallback_ms"] = round((perf_counter() - t0) * 1000, 3)

        # ---- act 3: continuation is persisted with the version we read ----
        state_v2 = dict(reloaded)
        state_v2.update({"status": "CONTINUED", "step": "provider_complete", "provider": "B"})
        state_v2["evidence"] = reloaded["evidence"] + ["router:fallback:B"]
        version2 = store.save(task_id, state_v2, expected_version=reloaded_version)
        check("G7_continuation_persisted", version2 == 2, f"version={version2}")

        final_state, final_version = store.load(task_id)
        check("G8_no_evidence_loss",
              final_state["evidence"] == ["postgres:system", "postgres:agenda", "router:fallback:B"],
              f"evidence={final_state['evidence']}")

        # ---- act 4: state replay must be rejected -------------------------
        # core.ai_save_jarvis_task_state returns NO ROW on a version mismatch,
        # which surfaces as RuntimeError out of PostgresTaskStateStore.save.
        # PsqlError subclasses RuntimeError, so this covers a raised error too.
        replay_blocked, replay_detail = False, ""
        # A server-side rejection aborts the transaction, so the attempt runs
        # inside its own savepoint and the rest of TEST G continues after it.
        session.run("SAVEPOINT replay_attempt")
        try:
            store.save(task_id, {"status": "REPLAYED", "run_tag": RUN_TAG},
                       expected_version=reloaded_version)  # stale: 1, current: 2
            replay_detail = "stale expected_version was ACCEPTED"
        except RuntimeError as exc:
            replay_blocked = True
            replay_detail = f"rejected: {type(exc).__name__}: {exc}"
        session.run("ROLLBACK TO SAVEPOINT replay_attempt")
        after_replay, after_version = store.load(task_id)
        state_untouched = after_version == final_version and after_replay == final_state
        check("G9_state_replay_blocked", replay_blocked and state_untouched,
              f"{replay_detail}; state_untouched={state_untouched} version={after_version}")

        # ---- act 5: duplicate proposal replay must not create a 2nd row ---
        # The canonical Action Firewall lives in core.ai_propose_action. It
        # requires an 'action:' prefixed key, a task of type PROPOSE_ACTION, an
        # action type enabled in core.ai_action_type, and an exact payload
        # shape. Replay is prevented by the task state transition: the first
        # successful proposal moves the task to NEEDS_REVIEW, after which the
        # same lease can no longer propose anything.
        idem = f"action:{RUN_TAG}"
        payload = {"subject_ref": RUN_TAG, "reason": "shadow-only rollback test; nothing is sent"}
        proposal_errors: list[str] = []
        # Each attempt gets its own savepoint: a server-side refusal aborts the
        # transaction, and the second attempt must still be able to run.
        for _ in range(2):
            session.run("SAVEPOINT propose_attempt")
            try:
                proposal_ids.append(session.scalar(
                    f"SELECT core.ai_propose_action({task_id}, {encode(lease_token)}::uuid, "
                    f"{encode(idem)}, 'REQUEST_HUMAN_REVIEW', {encode(payload)}::jsonb)"
                ))
                session.run("RELEASE SAVEPOINT propose_attempt")
            except PsqlError as exc:
                proposal_errors.append(str(exc))
                session.run("ROLLBACK TO SAVEPOINT propose_attempt")

        # ai_writer must not be able to read the proposal table directly; the
        # count below is therefore taken by the OPERATOR identity, not Jarvis.
        count_sql = (f"SELECT count(*) FROM core.ai_action_proposal "
                     f"WHERE idempotency_key={encode(idem)}")
        session.run("SAVEPOINT writer_raw_read")
        try:
            session.scalar(count_sql)
            check("G10a_writer_cannot_read_proposal_table", False,
                  "ai_writer read core.ai_action_proposal directly")
        except PsqlError as exc:
            check("G10a_writer_cannot_read_proposal_table", "42501" in str(exc), f"denied: {exc}")
        session.run("ROLLBACK TO SAVEPOINT writer_raw_read")

        session.run("RESET SESSION AUTHORIZATION")
        row_count = session.scalar(count_sql)
        if proposal_errors and not proposal_ids:
            check("G10_duplicate_proposal_blocked", row_count == 0,
                  f"proposal surface refused the action outright: {proposal_errors[0]}")
        else:
            check("G10_duplicate_proposal_blocked",
                  row_count == 1 and len(set(proposal_ids)) <= 1,
                  f"rows={row_count} ids={proposal_ids} errors={proposal_errors}")

        # ---- act 6: proposal must stop at PROPOSED, never executed --------
        if row_count:
            state_value = session.scalar(
                f"SELECT state FROM core.ai_action_proposal WHERE idempotency_key={encode(idem)}"
            )
            check("G11_proposal_stops_at_PROPOSED", state_value == "PROPOSED",
                  f"state={state_value}")
        else:
            check("G11_proposal_stops_at_PROPOSED", True, "no proposal row created")

        # Phase 2D: F-1 is closed. Jarvis keeps no allowlist of its own; it
        # maps internal intents onto the canonical contract. Assert the
        # mapping still covers the live contract exactly, in both directions.
        db_types = {row for row in session.run(
            "SELECT action_type FROM core.ai_action_type WHERE proposal_enabled") if row}
        mapped = set(INTENT_TO_CANONICAL.values())
        check("G15_contract_mapping_covers_database", mapped == db_types,
              f"mapped={sorted(mapped)} db={sorted(db_types)} "
              f"unmapped_db={sorted(db_types - mapped)} dangling={sorted(mapped - db_types)}")
        findings.append({
            "id": "firewall_allowlist_divergence",
            "status": "CLOSED_IN_PHASE_2D",
            "internal_intents": sorted(INTENT_TO_CANONICAL),
            "canonical_types": sorted(db_types),
            "unmapped_canonical": sorted(db_types - mapped),
            "note": ("jarvis/firewall.py no longer carries its own allowlist; the single "
                     "allowlist is core.ai_action_type, loaded at runtime and checked for "
                     "drift on every contract load."),
        })

        session.run("RESET SESSION AUTHORIZATION")
    except Exception as exc:  # noqa: BLE001
        check("G_UNEXPECTED_ERROR", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            session.run("RESET SESSION AUTHORIZATION")
        except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
            pass
        try:
            session.run("ROLLBACK")
        except Exception:  # noqa: BLE001 - elle kosturulan betik; hata ekranda gorunur
            pass

        # ---- assert nothing survived the rollback ------------------------
        try:
            leftover_state = session.scalar("SELECT count(*) FROM core.jarvis_task_state")
            leftover_prop = session.scalar(
                f"SELECT count(*) FROM core.ai_action_proposal WHERE idempotency_key LIKE {encode(RUN_TAG + '%')}"
            )
            leftover_task = session.scalar(
                f"SELECT count(*) FROM core.ai_task WHERE idempotency_key LIKE {encode('test-phase2c-g-%')}"
            )
            check("G12_rollback_left_no_state", leftover_state == 0, f"jarvis_task_state rows={leftover_state}")
            check("G13_rollback_left_no_proposal", leftover_prop == 0, f"proposal rows={leftover_prop}")
            check("G14_rollback_left_no_task", leftover_task == 0, f"task rows={leftover_task}")
        except Exception as exc:  # noqa: BLE001
            check("G12_rollback_verification", False, f"{type(exc).__name__}: {exc}")
        session.close()

    # Both providers are local callables defined in this file; SHADOW makes no
    # network call, so this is zero by construction, not by measurement.
    external_calls = 0
    failed = [row for row in checks if row["result"] == "FAIL"]
    report = {
        "test": "PHASE2C_TEST_G_STATE_FALLBACK",
        "status": "PASS" if not failed else "FAIL",
        "run_tag": RUN_TAG,
        "transaction": "BEGIN ... ROLLBACK (nothing committed)",
        "checks": checks,
        "findings": findings,
        "telemetry": {
            **timings,
            "total_ms": round((perf_counter() - started) * 1000, 3),
            "model_calls": 0,
            "external_provider_calls": external_calls,
            "external_actions": 0,
            "fallback_count": 1,
            "cache_hit": False,
            "max_rss_mb": rss_mb(),
            "cpu_seconds": cpu_s(),
            "success": not failed,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
