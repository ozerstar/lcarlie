from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from .memory import CompanyMemory, Evidence


@dataclass(frozen=True)
class CompiledContext:
    intent: str
    entity: str | None
    capabilities: tuple[str, ...]
    facts: tuple[dict[str, Any], ...]
    evidence_refs: tuple[str, ...]
    retrieved_records: int
    context_bytes: int
    compile_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextCompiler:
    def __init__(self, memory: CompanyMemory):
        self.memory = memory

    @staticmethod
    def resolve_entity(intent: str) -> str | None:
        return "VIREON" if "vireon" in intent.casefold() else None

    def compile(self, intent: str) -> CompiledContext:
        started = perf_counter()
        entity = self.resolve_entity(intent)
        text = intent.casefold()
        if entity:
            evidence = self.memory.get_product_context(entity)
            capabilities = ("company_memory", "entity_resolution")
        elif any(term in text for term in ("task", "proposal", "sistem durumu")):
            evidence = self.memory.get_system_status()
            capabilities = ("company_memory", "system_status")
        elif "gündem" in text or "gundem" in text:
            evidence = self.memory.get_company_agenda()
            capabilities = ("company_memory", "agenda")
        else:
            evidence = self.memory.get_company_context()
            capabilities = ("company_memory",)
        facts = tuple(evidence.records[:10])
        size = len(json.dumps(facts, ensure_ascii=False).encode("utf-8"))
        return CompiledContext(
            intent=intent, entity=entity, capabilities=capabilities, facts=facts,
            evidence_refs=(evidence.source,), retrieved_records=len(facts),
            context_bytes=size, compile_ms=round((perf_counter() - started) * 1000, 3),
        )
