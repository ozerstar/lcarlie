from __future__ import annotations


CAPABILITIES = {
    "safe_context": "available",
    "deterministic_planning": "available",
    "proposal_firewall": "available",
    "fake_benchmark": "available",
    "external_actions": "blocked",
    "production_self_modification": "blocked",
}


def resolve(name: str) -> dict[str, str]:
    status = CAPABILITIES.get(name, "proposed")
    return {"capability": name, "status": status, "next": "benchmark_plan" if status == "proposed" else "none"}
