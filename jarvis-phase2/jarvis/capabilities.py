"""Capability registry.

Phase 2C finding F-2: this module was a flat dict of six static strings, and
ContextCompiler never consulted it, so "is a capability missing?" silently
retrieved the decision summary instead. TEST D passed on safety alone.

This is the same registry, extended -- not a second one. Status is DERIVED
from live evidence wherever evidence exists (a database probe, measured host
memory, the loaded action contract) and only recorded as a static fact where
the fact genuinely is external and recorded, such as an upstream build being
blocked. Every entry says which of the two it is, in `source`.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# --- status vocabulary -------------------------------------------------
AVAILABLE = "AVAILABLE"
DEGRADED = "DEGRADED"
MISSING = "MISSING"
BLOCKED = "BLOCKED"
CONTROLLED = "CONTROLLED"
RESOURCE_BLOCKED = "RESOURCE_BLOCKED"
UPSTREAM_BLOCKED = "UPSTREAM_BLOCKED"
UNKNOWN = "UNKNOWN"

USABLE = {AVAILABLE, DEGRADED}

# --- recommendations ---------------------------------------------------
NO_ACTION = "NONE"
BENCHMARK_REQUIRED = "BENCHMARK_REQUIRED"
DEVELOPMENT_PROPOSAL_REQUIRED = "DEVELOPMENT_PROPOSAL_REQUIRED"
HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
REQUIRES_RESOURCE_UPGRADE = "REQUIRES_RESOURCE_UPGRADE"
UPSTREAM_BLOCKER_REPORT = "UPSTREAM_BLOCKER_REPORT"


@dataclass(frozen=True)
class Capability:
    capability_id: str
    capability_name: str
    status: str
    executor: str
    source: str
    evidence: tuple[str, ...] = ()
    last_verified_at: str = ""
    resource_requirement: dict[str, Any] | None = None
    blocker: str | None = None
    fallback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


# Which capabilities a request needs. Deterministic keyword resolution -- no
# model involved, and no attempt to be clever about unseen phrasings.
CAPABILITY_TOPICS: dict[str, tuple[str, ...]] = {
    "company_memory": (
        "deterministic_company_memory", "postgres_persistent_state",
        "semantic_memory_retrieval", "pgvector_retrieval_interface",
        "embedding_model_bge_m3",
    ),
    "external_action": ("external_business_action",),
    "research": ("external_model_provider", "semantic_memory_retrieval"),
}

_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "company_memory": ("company memory", "şirket hafıza", "sirket hafiza", "hafıza", "hafiza", "memory"),
    "external_action": ("whatsapp", "instagram", "gönder", "gonder", "send", "publish",
                        "yayınla", "yayinla", "fiyat değiştir", "kampanya"),
    "research": ("research", "araştır", "arastir", "benchmark", "model"),
}

GAP_STATUSES = {MISSING, BLOCKED, RESOURCE_BLOCKED, UPSTREAM_BLOCKED}

BGE_M3_REQUIREMENT = {
    "ram_gib_min": 32,
    "ram_gib_recommended_colocated": 64,
    "cpu_cores": 8,
    "disk_gib": 20,
    "gpu": "optional",
    "vram_gib_min": 12,
    "vram_gib_recommended": "16-24",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_resources() -> dict[str, Any]:
    """Measured, not declared."""
    total_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                    break
    except OSError:
        total_kb = 0
    return {
        "ram_gib": round(total_kb / 1024 / 1024, 2) if total_kb else None,
        "cpu_cores": os.cpu_count(),
    }


def _capability(**kwargs: Any) -> Capability:
    kwargs.setdefault("last_verified_at", _now())
    return Capability(**kwargs)


def build_registry(probe: dict[str, Any] | None = None,
                   contract: Any | None = None,
                   memory_ok: bool | None = None) -> dict[str, Capability]:
    """Assemble the registry from whatever evidence is available.

    `probe` is the record returned by CompanyMemory.get_capability_state().
    Absent evidence yields UNKNOWN -- never an optimistic guess.
    """
    probe = probe or {}
    resources = host_resources()
    registry: dict[str, Capability] = {}

    # --- derived from a live Company Memory call ----------------------
    if memory_ok is None:
        status, evidence = UNKNOWN, ("not probed",)
    elif memory_ok:
        status, evidence = AVAILABLE, ("probe:core.ai_orchestrator_health returned a record",)
    else:
        status, evidence = MISSING, ("probe:Company Memory query failed",)
    registry["deterministic_company_memory"] = _capability(
        capability_id="deterministic_company_memory",
        capability_name="Deterministic Company Memory retrieval",
        status=status, executor="postgres:ai_reader", source="probe",
        evidence=evidence,
    )

    # --- derived from pg_catalog --------------------------------------
    state_functions = int(probe.get("state_functions") or 0)
    registry["postgres_persistent_state"] = _capability(
        capability_id="postgres_persistent_state",
        capability_name="PostgreSQL persistent Jarvis task state",
        status=AVAILABLE if state_functions >= 2 else MISSING,
        executor="postgres:core.ai_{save,load}_jarvis_task_state",
        source="probe",
        evidence=(f"probe:controlled state functions present = {state_functions}/2",),
        blocker=None if state_functions >= 2 else "controlled state interface missing",
    )

    pgvector_version = probe.get("pgvector_version")
    semantic_table = int(probe.get("semantic_table") or 0)
    semantic_indexes = int(probe.get("semantic_indexes") or 0)
    interface_ready = bool(pgvector_version) and semantic_table >= 1
    registry["pgvector_retrieval_interface"] = _capability(
        capability_id="pgvector_retrieval_interface",
        capability_name="pgvector similarity retrieval interface",
        status=AVAILABLE if interface_ready else MISSING,
        executor="postgres:ai_semantic.memory_embedding",
        source="probe",
        evidence=(f"probe:pgvector={pgvector_version}",
                  f"probe:ai_semantic.memory_embedding tables={semantic_table}",
                  f"probe:ai_semantic indexes={semantic_indexes}"),
    )

    # --- derived from measured host memory ----------------------------
    ram = resources.get("ram_gib")
    cores = resources.get("cpu_cores")
    short_ram = ram is not None and ram < BGE_M3_REQUIREMENT["ram_gib_min"]
    short_cpu = cores is not None and cores < BGE_M3_REQUIREMENT["cpu_cores"]
    registry["embedding_model_bge_m3"] = _capability(
        capability_id="embedding_model_bge_m3",
        capability_name="BGE-M3 embedding model",
        status=RESOURCE_BLOCKED if (short_ram or short_cpu) else UNKNOWN,
        executor="none (not installed)", source="probe+recorded",
        evidence=(f"probe:measured host RAM = {ram} GiB (need >= {BGE_M3_REQUIREMENT['ram_gib_min']})",
                  f"probe:measured CPU cores = {cores} (need >= {BGE_M3_REQUIREMENT['cpu_cores']})",
                  "recorded:no embedding model is installed"),
        resource_requirement=BGE_M3_REQUIREMENT,
        blocker="WAITING_RESOURCE_UPGRADE",
        fallback="deterministic_company_memory",
    )

    # Semantic retrieval needs BOTH the interface and an embedding model.
    embedding = registry["embedding_model_bge_m3"]
    if interface_ready and embedding.status in USABLE:
        semantic_status, semantic_blocker = AVAILABLE, None
    elif interface_ready:
        semantic_status, semantic_blocker = RESOURCE_BLOCKED, "no embedding model; " + str(embedding.blocker)
    else:
        semantic_status, semantic_blocker = MISSING, "pgvector interface unavailable"
    registry["semantic_memory_retrieval"] = _capability(
        capability_id="semantic_memory_retrieval",
        capability_name="Semantic Company Memory retrieval",
        status=semantic_status, executor="postgres:pgvector + embedding model",
        source="derived",
        evidence=("derived:pgvector_retrieval_interface=" + registry["pgvector_retrieval_interface"].status,
                  "derived:embedding_model_bge_m3=" + embedding.status,
                  "recorded:ai_semantic.memory_embedding holds no embeddings"),
        resource_requirement=BGE_M3_REQUIREMENT if semantic_status == RESOURCE_BLOCKED else None,
        blocker=semantic_blocker,
        fallback="deterministic_company_memory",
    )

    # --- derived from the loaded action contract -----------------------
    if contract is None:
        action_status, action_evidence = UNKNOWN, ("not probed",)
    elif getattr(contract, "valid", False):
        action_status = CONTROLLED
        action_evidence = (f"probe:canonical action types = {contract.canonical_action_count}",
                           f"probe:contract_hash = {contract.contract_hash[:16]}",
                           "recorded:core.ai_propose_action is the authority")
    else:
        action_status = BLOCKED
        action_evidence = (f"probe:contract invalid - {getattr(contract, 'reason', 'unknown')}",)
    registry["external_business_action"] = _capability(
        capability_id="external_business_action",
        capability_name="External business action (send, publish, price change)",
        status=action_status, executor="postgres:core.ai_propose_action -> human approval",
        source="probe",
        evidence=action_evidence,
        blocker="HUMAN_APPROVAL_REQUIRED" if action_status == CONTROLLED else "CONTRACT_DRIFT",
    )

    # --- policy-derived -------------------------------------------------
    shadow = os.environ.get("JARVIS_MODE") == "SHADOW" or os.environ.get("EXTERNAL_ACTIONS") == "false"
    registry["external_model_provider"] = _capability(
        capability_id="external_model_provider",
        capability_name="External model provider calls",
        status=BLOCKED if shadow else UNKNOWN,
        executor="none", source="policy",
        evidence=("policy:SHADOW forbids external provider calls",
                  "recorded:no provider credential is configured"),
        blocker="SHADOW_MODE_NO_EXTERNAL_PROVIDER",
        fallback="deterministic_company_memory",
    )

    # --- recorded upstream facts (no live source exists) ----------------
    registry["ruflo_workflow_engine"] = _capability(
        capability_id="ruflo_workflow_engine",
        capability_name="Ruflo workflow engine",
        status=UPSTREAM_BLOCKED, executor="none", source="recorded",
        evidence=("recorded:upstream committed manifest/lock mismatch",),
        blocker="WAITING_UPSTREAM_REPRODUCIBILITY",
    )
    registry["yemaka_reference"] = _capability(
        capability_id="yemaka_reference",
        capability_name="Yemaka (architecture reference only)",
        status=UPSTREAM_BLOCKED, executor="none", source="recorded",
        evidence=("recorded:root build blocked by missing frontend/dist",),
        blocker="WAITING_REPRODUCIBLE_BUILD",
    )
    return registry


def required_capabilities(intent: str) -> tuple[str, ...]:
    """Deterministic: which capabilities does this request actually need?"""
    text = intent.casefold()
    needed: list[str] = []
    for topic, terms in _TOPIC_TERMS.items():
        if any(term in text for term in terms):
            for capability_id in CAPABILITY_TOPICS[topic]:
                if capability_id not in needed:
                    needed.append(capability_id)
    return tuple(needed)


def recommend(gap: Capability) -> str:
    if gap.status == RESOURCE_BLOCKED:
        return REQUIRES_RESOURCE_UPGRADE
    if gap.status == UPSTREAM_BLOCKED:
        return UPSTREAM_BLOCKER_REPORT
    if gap.status == BLOCKED:
        return HUMAN_DECISION_REQUIRED
    if gap.status == MISSING:
        return DEVELOPMENT_PROPOSAL_REQUIRED
    return NO_ACTION


def analyse(intent: str, registry: dict[str, Capability]) -> dict[str, Any]:
    """Capability-gap analysis. Only the capabilities this request needs enter
    the result -- the whole registry never reaches task context."""
    needed = required_capabilities(intent)
    selection_scope = "topic"
    if not needed:
        # No topic named: the question is "is anything missing?", so answer
        # with the capabilities that are in a gap state -- not the registry.
        needed = tuple(sorted(
            capability_id for capability_id, capability in registry.items()
            if capability.status in GAP_STATUSES
        ))
        selection_scope = "gaps_only"
    selected = [registry[name] for name in needed if name in registry]
    unregistered = [name for name in needed if name not in registry]

    buckets: dict[str, list[str]] = {
        "available_capabilities": [], "degraded_capabilities": [],
        "missing_capabilities": [], "blocked_capabilities": [],
        "resource_blocked_capabilities": [], "upstream_blocked_capabilities": [],
        "controlled_capabilities": [], "unknown_capabilities": [],
    }
    bucket_of = {
        AVAILABLE: "available_capabilities", DEGRADED: "degraded_capabilities",
        MISSING: "missing_capabilities", BLOCKED: "blocked_capabilities",
        RESOURCE_BLOCKED: "resource_blocked_capabilities",
        UPSTREAM_BLOCKED: "upstream_blocked_capabilities",
        CONTROLLED: "controlled_capabilities", UNKNOWN: "unknown_capabilities",
    }
    for capability in selected:
        buckets[bucket_of[capability.status]].append(capability.capability_id)

    gaps = [capability for capability in selected if capability.status in GAP_STATUSES]
    recommendations = sorted({recommend(capability) for capability in gaps}) or [NO_ACTION]
    fallbacks = sorted({
        capability.fallback for capability in gaps
        if capability.fallback and registry.get(capability.fallback)
        and registry[capability.fallback].status in USABLE
    })

    return {
        "required_capabilities": list(needed),
        "selection_scope": selection_scope,
        **buckets,
        "fallback_capabilities": fallbacks,
        "unregistered_capabilities": unregistered,
        "capability_gap": bool(gaps),
        "recommendations": recommendations,
        "gaps": [
            {
                "capability_id": capability.capability_id,
                "status": capability.status,
                "blocker": capability.blocker,
                "recommendation": recommend(capability),
                "resource_requirement": capability.resource_requirement,
                "fallback": capability.fallback,
                "evidence": list(capability.evidence),
            }
            for capability in gaps
        ],
        "registry_size": len(registry),
        "capabilities_in_context": len(selected),
    }


# --- backward compatible surface used by the Phase 1 bootstrap tests ----
def resolve(name: str, registry: dict[str, Capability] | None = None) -> dict[str, Any]:
    """A capability nobody has registered is not 'missing', it is unevaluated:
    benchmark it before proposing to build or adopt anything."""
    registry = registry if registry is not None else build_registry()
    capability = registry.get(name)
    if capability is None:
        return {"capability": name, "status": UNKNOWN, "next": BENCHMARK_REQUIRED}
    return {"capability": name, "status": capability.status, "next": recommend(capability)}
