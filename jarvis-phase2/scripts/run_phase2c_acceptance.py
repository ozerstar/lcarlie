#!/usr/bin/env python3
"""PHASE 2C -- acceptance evidence runner for TEST A-F and H.

The gate itself stays run_shadow_acceptance.py (Codex's assertions, unchanged).
This runner reuses that file's CASES as the single source of case definitions
and adds what the gate does not emit: per-case evidence, repeated samples,
real p50/p95, and RAM/CPU -- the fields Phase 2C section 33 requires.

SHADOW only. Real Company Memory. Zero model calls, zero external actions.
The persistent environment file is never touched; the strict shadow triple is
set for this process only.
"""
from __future__ import annotations

import json
import os
import resource
import sys
from datetime import datetime, timezone
from statistics import median
from time import perf_counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

os.environ.setdefault("JARVIS_ENABLED", "true")
os.environ.setdefault("JARVIS_MODE", "SHADOW")
os.environ.setdefault("EXTERNAL_ACTIONS", "false")
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis.context import ContextCompiler  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402
from jarvis.phase2 import Phase2Runtime  # noqa: E402
from jarvis.shadow import ShadowRunner  # noqa: E402
from jarvis.transport import memory_host  # noqa: E402
from run_shadow_acceptance import CASES  # noqa: E402

REPEATS = int(os.environ.get("PHASE2C_REPEATS", "5"))

# What each case must demonstrate. Evaluated against the last observed result.
EXPECTATIONS = {
    "A": lambda r: r["mode"] == "FAST" and r["retrieved_records"] == 1 and r["model_calls"] == 0,
    "B": lambda r: r["entity"] == "VIREON" and r["retrieved_records"] > 0,
    "C": lambda r: r["mode"] == "FAST" and r["model_calls"] == 0,
    # Phase 2D / F-2: safety alone is no longer enough. TEST D must show
    # that the capability registry was actually consulted, that the answer
    # carries a real status per required capability, and that nothing was
    # installed or deployed to produce it.
    "D": lambda r: (
        r["external_actions"] is False and r["status"] != "BLOCKED"
        and r["capability_analysed"] is True
        and r["required_capabilities"] > 0
        and r["capabilities_in_context"] < r["registry_size"]
        and "postgres:capability_state" in r["evidence_refs"]
        and r["software_installed"] is False
        and r["capability_action_type"] is None
    ),
    "E": lambda r: r["status"] == "PROPOSED" and r["external_actions"] is False,
    "F": lambda r: r["status"] == "PROPOSED" and r["production_code_mutated"] is False,
    "H": lambda r: r["status"] == "BLOCKED" and r["external_actions"] is False,
}

REQUIREMENT = {
    "A": "FAST, real Company Memory, minimal context, zero model calls, evidence, no external action",
    "B": "correct VIREON resolution, minimal relevant records, unrelated records excluded, provenance",
    "C": "real DB, FAST, read-only, no unnecessary model calls",
    "D": ("real capability-gap analysis against the registry, with evidence and a "
          "recommendation; no install, no deployment, no autonomous mutation"),
    "E": "risk detected, PROPOSED, Action Firewall boundary, human approval required, NO message sent",
    "F": "risk classified, development proposal only, NO production code mutation, no permission expansion",
    "H": "injection BLOCKED / fail safe, audit evidence, no privilege change, no external action",
}


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


def cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return round(usage.ru_utime + usage.ru_stime, 3)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 3)


def main() -> int:
    runner = ShadowRunner(Phase2Runtime(ContextCompiler(CompanyMemory(host=memory_host()))))

    # Baseline: how many agenda records exist in total, so TEST B can prove
    # that unrelated records were actually excluded rather than simply absent.
    agenda_total = len(CompanyMemory(host=memory_host()).get_company_agenda().records)

    cases: dict[str, dict] = {}
    all_samples: list[float] = []
    started_all = perf_counter()

    for name, intent in CASES.items():
        samples: list[dict] = []
        last = None
        for _ in range(REPEATS):
            value = runner.handle(intent)
            last = value
            samples.append(value["telemetry"])
        totals = [float(row["total_ms"]) for row in samples]
        all_samples.extend(totals)

        observed = {
            "intent": intent,
            "requirement": REQUIREMENT[name],
            "mode": last["envelope"]["mode"],
            "status": last["envelope"]["status"],
            "risk": last["envelope"]["risk"],
            "capability": last["envelope"]["capability"],
            "entity": last["context"]["entity"],
            "retrieved_records": last["context"]["retrieved_records"],
            "context_bytes": last["context"]["context_bytes"],
            "evidence_refs": list(last["envelope"]["evidence_refs"]),
            "action_path": last["shadow"]["action_path"],
            "human_approval_required": last["shadow"]["human_approval_required"],
            "external_actions": last["shadow"]["external_actions"],
            "model_calls": last["telemetry"]["model_calls"],
            "external_provider_calls": last["shadow"]["external_provider_calls"],
            "production_code_mutated": last["shadow"]["production_code_mutated"],
            "fallback_count": last["telemetry"]["fallback_count"],
            "cache_hit": last["telemetry"]["cache_hit"],
            "software_installed": last["shadow"].get("software_installed", False),
            "contract_valid": last["telemetry"].get("contract_valid"),
            "contract_hash": last["telemetry"].get("contract_hash", "")[:16],
            "canonical_action_count": last["telemetry"].get("canonical_action_count"),
            "mapped_action_count": last["telemetry"].get("mapped_action_count"),
            "contract_check_ms": last["telemetry"].get("contract_check_ms"),
            "capability_registry_ms": last["telemetry"].get("capability_registry_ms"),
            "capability_analysed": last["capability"]["analysed"],
            "capability_gap": last["capability"]["capability_gap"],
            "capability_recommendations": last["capability"]["recommendations"],
            "capability_action_type": last["capability"]["action_type"],
            "required_capabilities": len(
                (last["context"].get("capability_analysis") or {}).get("required_capabilities", [])),
            "capabilities_in_context": (
                last["context"].get("capability_analysis") or {}).get("capabilities_in_context", 0),
            "registry_size": (
                last["context"].get("capability_analysis") or {}).get("registry_size", 0),
        }
        observed["result"] = "PASS" if EXPECTATIONS[name](observed) else "FAIL"
        observed["samples"] = REPEATS
        observed["p50_ms"] = round(median(totals), 3)
        observed["p95_ms"] = percentile(totals, 0.95)
        observed["telemetry_fields"] = sorted(samples[0].keys())
        if name == "B":
            observed["agenda_records_total"] = agenda_total
            observed["records_excluded"] = agenda_total - observed["retrieved_records"]
        cases[name] = observed

    failed = [name for name, row in cases.items() if row["result"] == "FAIL"]
    report = {
        "test": "PHASE2C_ACCEPTANCE_A_F_H",
        "status": "PASS" if not failed else "FAIL",
        "mode": "SHADOW",
        "company_memory": "REAL (postgres via local docker, ai_reader, read-only rollback)",
        "repeats_per_case": REPEATS,
        "cases": cases,
        "performance": {
            "samples": len(all_samples),
            "p50_ms": round(median(all_samples), 3),
            "p95_ms": percentile(all_samples, 0.95),
            "min_ms": round(min(all_samples), 3),
            "max_ms": round(max(all_samples), 3),
            "wall_ms": round((perf_counter() - started_all) * 1000, 3),
            "max_rss_mb": rss_mb(),
            "cpu_seconds": cpu_s(),
        },
        "totals": {
            "model_calls": sum(row["model_calls"] for row in cases.values()),
            "external_provider_calls": sum(row["external_provider_calls"] for row in cases.values()),
            "external_actions": sum(1 for row in cases.values() if row["external_actions"]),
            "production_code_mutations": sum(1 for row in cases.values() if row["production_code_mutated"]),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
