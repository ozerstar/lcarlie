from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from . import capabilities as caps
from .memory import CompanyMemory, Evidence

CAPABILITY_TERMS = ("capability", "yetenek", "eksik capability", "capability gap")


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
    capability_analysis: dict[str, Any] | None = None
    registry_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextCompiler:
    def __init__(self, memory: CompanyMemory):
        self.memory = memory

    @staticmethod
    def resolve_entity(intent: str) -> str | None:
        return "VIREON" if "vireon" in intent.casefold() else None

    @staticmethod
    def is_capability_question(intent: str) -> bool:
        return any(term in intent.casefold() for term in CAPABILITY_TERMS)

    def _capability_context(self, intent: str, contract: Any | None) -> tuple[Evidence, dict[str, Any], float]:
        """Phase 2D / F-2: real capability-gap analysis.

        Probes the live system, builds the registry, and returns ONLY the
        capabilities this request actually needs.
        """
        started = perf_counter()
        # One round trip: the infrastructure facts and the health record come
        # from the same snapshot, so they cannot disagree with each other.
        try:
            probe_evidence = self.memory.get_capability_state()
            probe = probe_evidence.records[0] if probe_evidence.records else {}
            source = probe_evidence.source
        except Exception as exc:  # noqa: BLE001 - a failed probe is evidence, not a crash
            probe, source = {}, f"postgres:capability_state (failed: {type(exc).__name__})"
            probe_evidence = None

        health = probe.get("health")
        memory_ok = isinstance(health, dict) and "checked_at" in health

        registry = caps.build_registry(probe=probe, contract=contract, memory_ok=memory_ok)
        analysis = caps.analyse(intent, registry)
        analysis["evidence_refs"] = [source]
        analysis["health_checked_at"] = health.get("checked_at") if isinstance(health, dict) else None
        if contract is not None:
            analysis["contract_hash"] = getattr(contract, "contract_hash", "")
        if probe_evidence is None:
            from .memory import Evidence
            probe_evidence = Evidence(source, "CANONICAL_COMPANY_MEMORY", "live", [], 0.0)
        return probe_evidence, analysis, round((perf_counter() - started) * 1000, 3)

    def compile(self, intent: str, contract: Any | None = None) -> CompiledContext:
        started = perf_counter()
        entity = self.resolve_entity(intent)
        text = intent.casefold()
        analysis: dict[str, Any] | None = None
        registry_ms = 0.0

        if self.is_capability_question(intent):
            evidence, analysis, registry_ms = self._capability_context(intent, contract)
            capabilities = ("company_memory", "capability_analysis")
        elif entity:
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
        payload: Any = facts if analysis is None else {"facts": list(facts), "capability_analysis": analysis}
        size = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
        refs = (evidence.source,) if analysis is None else tuple(
            dict.fromkeys([evidence.source, *analysis.get("evidence_refs", [])])
        )
        return CompiledContext(
            intent=intent, entity=entity, capabilities=capabilities, facts=facts,
            evidence_refs=refs, retrieved_records=len(facts),
            context_bytes=size, compile_ms=round((perf_counter() - started) * 1000, 3),
            capability_analysis=analysis, registry_ms=registry_ms,
        )
