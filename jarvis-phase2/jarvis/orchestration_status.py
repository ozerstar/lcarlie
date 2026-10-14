"""Read-only, bounded operator view of persisted execution runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .execution_runtime import RUN_DIR, STEP_SUCCEEDED

EVIDENCE_CAPABILITIES = {
    "internal_data_analysis", "capability_analysis", "system_status",
    "evidence_fusion", "problem_opportunity_analysis",
}
MAX_RUN_BYTES = 2_000_000
STALE_SECONDS = 600


def _brief(value: object, limit: int = 160) -> str:
    return " ".join(str(value or "").split())[:limit]


def _run_summary(data: dict, modified: datetime, now: datetime) -> dict:
    steps = []
    stored_steps = data.get("steps") or {}
    if not isinstance(stored_steps, dict):
        stored_steps = {}
    for step_id, step in stored_steps.items():
        if not isinstance(step, dict):
            continue
        capability = str(step.get("capability") or "")
        status = str(step.get("status") or "PENDING")
        evidence = step.get("evidence_refs") or []
        needs_evidence = capability in EVIDENCE_CAPABILITIES or capability.endswith("_analysis")
        evidence_state = ("MISSING" if status == STEP_SUCCEEDED and needs_evidence and not evidence
                          else "PRESENT" if evidence else "NOT_REQUIRED")
        acceptance = step.get("acceptance") or {}
        steps.append({
            "step_id": _brief(step_id, 40), "capability": _brief(capability, 80),
            "status": status, "evidence_state": evidence_state,
            "evidence_count": len(evidence),
            "acceptance_status": acceptance.get("status", "NOT_RECORDED"),
            "failed_criteria": [item.get("criterion") for item in acceptance.get("checks", [])
                                if isinstance(item, dict) and item.get("passed") is False],
            "reason": ("Adım hata verdi; sunucu kaydını inceleyin." if step.get("error")
                       else _brief(step.get("block_reason"), 200)),
        })
    status = str(data.get("status") or "UNKNOWN")
    if status == "RUNNING" and (now - modified).total_seconds() > STALE_SECONDS:
        status = "INTERRUPTED"
    if status == "COMPLETED" and any(step["evidence_state"] == "MISSING" for step in steps):
        status = "UNVERIFIED"
    return {
        "run_id": _brief(data.get("run_id"), 100),
        "plan_id": _brief(data.get("plan_id"), 100),
        "request": _brief(data.get("request"), 180),
        "originator": _brief(data.get("originator"), 80),
        "status": status, "attempt": data.get("attempt", 1),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "steps": steps,
        "needs_attention": status in ("FAILED", "COMPLETED_DEGRADED", "INTERRUPTED", "UNVERIFIED")
            or any(step["evidence_state"] == "MISSING" for step in steps),
    }


def snapshot(run_dir: Path = RUN_DIR, limit: int = 20,
             now: datetime | None = None) -> dict:
    """No run execution, retries, proposal submission or raw payload exposure."""
    now = now or datetime.now(timezone.utc)
    if not run_dir.is_dir():
        return {"runs": [], "total": 0, "needs_attention": 0}
    candidates = []
    for path in run_dir.glob("run-*.json"):
        try:
            if not path.is_symlink() and path.stat().st_size <= MAX_RUN_BYTES:
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    candidates.sort(reverse=True)
    runs = []
    for _, path in candidates[:min(max(limit, 1), 50)]:
        try:
            if path.is_symlink() or path.stat().st_size > MAX_RUN_BYTES:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                runs.append(_run_summary(data, modified, now))
        except (OSError, ValueError, TypeError):
            continue
    return {"runs": runs, "total": len(runs),
            "needs_attention": sum(run["needs_attention"] for run in runs)}
