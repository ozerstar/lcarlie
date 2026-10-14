from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from time import perf_counter
from typing import Any


class Mode(str, Enum):
    FAST = "FAST"
    SMART = "SMART"
    DEEP = "DEEP"


RISKY_TERMS = {
    "send", "publish", "pay", "delete", "drop", "truncate", "deploy",
    "whatsapp", "instagram", "meta budget", "wix price", "webhook", "shell",
}


@dataclass(frozen=True)
class Plan:
    intent: str
    mode: Mode
    route: str
    status: str
    steps: tuple[str, ...]
    reason: str
    idempotency_key: str


def choose_mode(intent: str) -> tuple[Mode, str]:
    text = intent.casefold()
    if any(word in text for word in ("deep", "research", "benchmark", "contradiction")):
        return Mode.DEEP, "Explicit research or benchmark depth is required."
    if any(word in text for word in ("plan", "compare", "analyse", "analyze", "risk")):
        return Mode.SMART, "Structured reasoning is required."
    return Mode.FAST, "A deterministic response is sufficient."


def build_plan(intent: str) -> Plan:
    clean = " ".join(intent.split())
    if not clean:
        raise ValueError("intent must not be empty")
    mode, reason = choose_mode(clean)
    risky = any(term in clean.casefold() for term in RISKY_TERMS)
    status = "PROPOSED" if risky else "PLANNED"
    steps = (
        "compile safe context",
        "apply policy and capability checks",
        "produce a validated proposal" if risky else "run deterministic local plan",
        "record route, latency, and provenance",
    )
    key = sha256(clean.casefold().encode("utf-8")).hexdigest()
    return Plan(clean, mode, "deterministic-local-first", status, steps, reason, key)


def respond(intent: str, safe_context: dict[str, Any] | None = None) -> dict[str, Any]:
    started = perf_counter()
    plan = build_plan(intent)
    context = safe_context or {}
    result = asdict(plan)
    result["mode"] = plan.mode.value
    result["context_keys"] = sorted(context)
    result["external_action_executed"] = False
    result["latency_ms"] = round((perf_counter() - started) * 1000, 3)
    result["provenance"] = ["caller_supplied_safe_context"] if context else []
    return result
