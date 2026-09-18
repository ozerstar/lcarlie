from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from .context import ContextCompiler
from .runtime import build_plan


@dataclass(frozen=True)
class RuntimeEnvelope:
    task_id: str
    entity_id: str | None
    actor: str
    source: str
    intent: str
    mode: str
    risk: str
    capability: str
    correlation_id: str
    causation_id: str | None
    evidence_refs: tuple[str, ...]
    created_at: str
    status: str


class Phase2Runtime:
    def __init__(self, compiler: ContextCompiler):
        self.compiler = compiler

    def handle(self, intent: str, contract=None) -> dict:
        plan = build_plan(intent)
        context = self.compiler.compile(intent, contract=contract)
        task_id = sha256(intent.casefold().encode()).hexdigest()[:24]
        envelope = RuntimeEnvelope(
            task_id=task_id, entity_id=context.entity, actor="jarvis",
            source="text", intent=intent, mode=plan.mode.value,
            risk="RISKY" if plan.status == "PROPOSED" else "LOW",
            capability=context.capabilities[-1], correlation_id=str(uuid4()),
            causation_id=None, evidence_refs=context.evidence_refs,
            created_at=datetime.now(timezone.utc).isoformat(), status=plan.status,
        )
        return {"envelope": asdict(envelope), "plan": asdict(plan),
                "context": context.to_dict(), "external_action_executed": False}
