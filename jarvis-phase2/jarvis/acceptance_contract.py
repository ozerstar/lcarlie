"""Deterministic handoff criteria for read-only execution steps."""
from __future__ import annotations

from typing import Any


def criteria_for(capability: str) -> tuple[str, ...]:
    if capability in ("action_plan", "human_review_proposal"):
        return ("validated_envelope", "not_submitted")
    if capability == "red_team_review":
        return ("read_only_completed", "objections_recorded", "clean_flag_consistent")
    if capability == "evidence_fusion":
        return ("read_only_completed", "fusion_shape", "source_traceable")
    if capability == "coding_task":
        return ("human_origination_required",)
    if capability == "external_research":
        return ("external_capability_required",)
    if capability.endswith("_analysis") or capability == "system_status":
        return ("read_only_completed", "source_traceable", "result_shape")
    return ()


def evaluate(capability: str, status: str, output: dict[str, Any],
             evidence_refs: tuple[str, ...]) -> dict[str, Any]:
    """Check an executor's delivered artifact, not its self-reported success."""
    criteria = criteria_for(capability)
    output = output if isinstance(output, dict) else {}
    if status not in ("SUCCEEDED", "PROPOSED"):
        return {"status": "NOT_APPLICABLE", "checks": []}
    if not criteria:
        return {"status": "NOT_APPLICABLE", "checks": []}
    checks: list[dict[str, Any]] = []
    traceable = bool(evidence_refs) and all(
        isinstance(reference, str) and bool(reference.strip()) for reference in evidence_refs)

    def check(name: str, passed: bool) -> None:
        checks.append({"criterion": name, "passed": bool(passed)})

    if "read_only_completed" in criteria:
        check("read_only_completed", status == "SUCCEEDED")
        if status != "SUCCEEDED":
            return {"status": "FAILED", "checks": checks}
    if capability in ("coding_task", "external_research"):
        check(criteria[0], False)
    elif capability in ("action_plan", "human_review_proposal"):
        check("validated_envelope", bool(output.get("idempotency_key") and output.get("payload")))
        check("not_submitted", status == "PROPOSED" and output.get("submitted") is False)
    elif capability == "red_team_review":
        objections = output.get("objections")
        check("objections_recorded", isinstance(objections, list))
        check("clean_flag_consistent", isinstance(objections, list)
              and isinstance(output.get("clean"), bool)
              and output["clean"] == (len(objections) == 0))
    elif capability == "evidence_fusion":
        sources = output.get("fused_inputs")
        check("fusion_shape", isinstance(sources, int) and sources >= 0
              and isinstance(output.get("missing_inputs"), list))
        check("source_traceable", traceable if isinstance(sources, int) and sources > 0
              else isinstance(sources, int) and sources == 0 and bool(output.get("missing_inputs")))
    elif criteria:
        check("source_traceable", traceable)
        if capability == "problem_opportunity_analysis":
            valid = isinstance(output.get("signals"), list) and isinstance(output.get("skipped"), list)
        elif capability == "capability_analysis":
            valid = isinstance(output.get("gaps"), list)
        else:
            valid = isinstance(output.get("records"), int) and output["records"] >= 0
        check("result_shape", valid)
    return {"status": "PASSED" if all(item["passed"] for item in checks) else "FAILED",
            "checks": checks}
