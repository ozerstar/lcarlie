"""Capability Adapter Factory: one contract every upstream must satisfy.

The point is to make the NEXT open-source integration cheap without making it
careless. The pipeline is fixed and the factory refuses to skip a stage:

    capability gap -> registry check -> candidate -> isolated clone/install
    -> manifest/dependency/license/security inspection -> smoke -> benchmark
    -> adapter -> contract tests -> regression -> capability registry
    -> PROPOSED integration -> human approval -> deploy

The factory NEVER installs, clones or deploys anything. It evaluates evidence
that already exists and emits a PROPOSED integration for a human. Installing
an upstream is a human act, exactly like originating a coding task.

Resource rule, taken from the existing handoff and not re-litigated here: the
current host (measured, not declared) is not an architectural limit. An
upstream that does not fit is NOT eliminated -- it is reported as
REQUIRES_RESOURCE_UPGRADE with the specific shortfall and a main-VDS-upgrade
vs dedicated-worker recommendation, so the decision stays a business one.

Upstream evidence is REUSED, never re-benchmarked: UPSTREAMS below is the
verified §23 record (RouteLabs Router, pgvector, Qwen-Agent, smolagents, Agno,
Kimi Code, BGE-M3, Ruflo, Yemaka). pgvector is already in production and Kimi
Code already sits inside the CodingExecutor; neither is reinstalled.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .capabilities import BGE_M3_REQUIREMENT, host_resources


class AdapterState(str, Enum):
    """Provider/capability states.

    Deliberately value-compatible with jarvis.routing.ProviderState -- the
    RouteLabs-compatible boundary already in the codebase -- so an adapter can
    be handed to the existing CapabilityRouter without a translation layer.
    REQUIRES_RESOURCE_UPGRADE is the one addition, and it exists precisely so
    "does not fit this host" never has to be recorded as UNAVAILABLE.
    """
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_LOW = "QUOTA_LOW"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_RESOURCE_UPGRADE = "REQUIRES_RESOURCE_UPGRADE"


INTEGRATION_STAGES: tuple[str, ...] = (
    "CAPABILITY_GAP", "REGISTRY_CHECK", "CANDIDATE_SELECTED", "ISOLATED_INSTALL",
    "MANIFEST_DEPENDENCY_LICENSE_SECURITY", "SMOKE", "BENCHMARK", "ADAPTER",
    "CONTRACT_TESTS", "REGRESSION", "REGISTRY_UPDATE", "PROPOSED",
    "HUMAN_APPROVAL", "DEPLOY",
)

# Stages the factory itself is allowed to perform. Everything after SMOKE
# needs a human to have actually installed and run something.
FACTORY_STAGES = INTEGRATION_STAGES[:INTEGRATION_STAGES.index("ISOLATED_INSTALL")]


@dataclass(frozen=True)
class ResourceRequirement:
    ram_gib_min: float
    ram_gib_recommended: float
    cpu_cores: int
    disk_gib: int
    gpu_required: bool = False
    vram_gib_min: float = 0.0
    vram_gib_recommended: str = ""
    concurrency_headroom: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceVerdict:
    fits: bool
    state: AdapterState
    current: dict[str, Any]
    requirement: dict[str, Any]
    shortfalls: tuple[str, ...]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["shortfalls"] = list(self.shortfalls)
        return data


MAIN_VDS_UPGRADE = "MAIN_VDS_UPGRADE"
DEDICATED_WORKER = "DEDICATED_WORKER"
NO_UPGRADE_NEEDED = "NONE"


def assess_resources(requirement: ResourceRequirement,
                     resources: dict[str, Any] | None = None) -> ResourceVerdict:
    """Measured host vs declared requirement. Never a rejection."""
    current = resources if resources is not None else host_resources()
    ram = current.get("ram_gib")
    cores = current.get("cpu_cores")
    shortfalls: list[str] = []
    if ram is not None and ram < requirement.ram_gib_min:
        shortfalls.append(f"RAM {ram} GiB < {requirement.ram_gib_min} GiB minimum")
    if cores is not None and cores < requirement.cpu_cores:
        shortfalls.append(f"CPU {cores} cores < {requirement.cpu_cores} required")
    if requirement.gpu_required and not current.get("gpu"):
        shortfalls.append(f"GPU required ({requirement.vram_gib_min} GiB VRAM minimum), none present")

    if not shortfalls:
        return ResourceVerdict(True, AdapterState.AVAILABLE, current,
                               requirement.to_dict(), (), NO_UPGRADE_NEEDED)
    # A GPU need, or a requirement far beyond the host, belongs on its own
    # machine rather than inflating the box that runs the business.
    needs_own_box = requirement.gpu_required or (
        ram is not None and requirement.ram_gib_recommended >= 2 * ram)
    return ResourceVerdict(
        False, AdapterState.REQUIRES_RESOURCE_UPGRADE, current,
        requirement.to_dict(), tuple(shortfalls),
        DEDICATED_WORKER if needs_own_box else MAIN_VDS_UPGRADE,
    )


# --- the adapter contract ----------------------------------------------
@dataclass(frozen=True)
class AdapterEvidence:
    source: str
    authority: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityAdapter(ABC):
    """Minimum contract every upstream integration must satisfy.

    `cancel` and `resume` are part of the contract rather than optional, so a
    long-running upstream can never be adopted without someone having decided
    what cancelling it means. An adapter that genuinely cannot do either says
    so by returning False; it does not omit the method and leave the caller to
    find out at runtime.
    """

    name: str = "unnamed"
    state: AdapterState = AdapterState.UNAVAILABLE

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Live state. Must never raise -- an unhealthy adapter reports, not throws."""

    @abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        """Capability ids this adapter can serve."""

    @abstractmethod
    def execute(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Do the work. Must refuse rather than act when the envelope is not
        authorized for it."""

    @abstractmethod
    def evidence(self) -> tuple[AdapterEvidence, ...]:
        """What this adapter's claims rest on."""

    @abstractmethod
    def metrics(self) -> dict[str, Any]:
        """Counters a caller can use for routing and telemetry."""

    def cancel(self, handle: str) -> bool:
        return False

    def resume(self, handle: str) -> bool:
        return False


REQUIRED_ADAPTER_METHODS = ("health", "capabilities", "execute", "evidence",
                            "metrics", "cancel", "resume")


# --- upstream evidence, reused ------------------------------------------
@dataclass(frozen=True)
class UpstreamCandidate:
    name: str
    version: str
    state: AdapterState
    evidence: str
    disposition: str
    requirement: ResourceRequirement | None = None
    constraint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "state": self.state.value,
                "evidence": self.evidence, "disposition": self.disposition,
                "requirement": self.requirement.to_dict() if self.requirement else None,
                "constraint": self.constraint}


BGE_M3_RESOURCE = ResourceRequirement(
    ram_gib_min=float(BGE_M3_REQUIREMENT["ram_gib_min"]),
    ram_gib_recommended=float(BGE_M3_REQUIREMENT["ram_gib_recommended_colocated"]),
    cpu_cores=int(BGE_M3_REQUIREMENT["cpu_cores"]),
    disk_gib=int(BGE_M3_REQUIREMENT["disk_gib"]),
    gpu_required=False,
    vram_gib_min=float(BGE_M3_REQUIREMENT["vram_gib_min"]),
    vram_gib_recommended=str(BGE_M3_REQUIREMENT["vram_gib_recommended"]),
    concurrency_headroom="single model instance; no headroom for co-located Jarvis at 32 GiB",
)

DOCLING_RESOURCE = ResourceRequirement(
    ram_gib_min=2.0, ram_gib_recommended=4.0, cpu_cores=2, disk_gib=3,
    gpu_required=False, vram_gib_min=0.0, vram_gib_recommended="",
    concurrency_headroom=("measured 650 MB RSS per conversion; a CPU-only torch "
                          "wheel is required -- the default install pulls the CUDA "
                          "stack and costs 6.2 GB on a host with no GPU"),
)

LLAMACPP_RESOURCE = ResourceRequirement(
    ram_gib_min=2.0, ram_gib_recommended=8.0, cpu_cores=4, disk_gib=5,
    gpu_required=False, vram_gib_min=0.0, vram_gib_recommended="",
    concurrency_headroom=("CPU inference on 4 cores suits small classification / "
                          "extraction models only; anything larger needs a GPU worker"),
)


UPSTREAMS: tuple[UpstreamCandidate, ...] = (
    UpstreamCandidate(
        "RouteLabs Router", "verified", AdapterState.AVAILABLE,
        "138 upstream tests PASS", "ROUTING_BOUNDARY_ONLY",
        constraint="must never own truth, approval, the firewall, or business authorization",
    ),
    UpstreamCandidate(
        "pgvector", "0.8.6", AdapterState.AVAILABLE,
        "verified live in wave 1: pg_extension reports vector 0.8.6 in the production database",
        "ALREADY_INTEGRATED", constraint="do not reinstall",
    ),
    UpstreamCandidate(
        "Kimi Code", "2.0.1", AdapterState.AVAILABLE,
        "in production inside CodingExecutor (35c6388)", "ALREADY_INTEGRATED",
        constraint="human-originated coding tasks only; do not reinstall",
    ),
    UpstreamCandidate(
        "Qwen-Agent", "0.0.34", AdapterState.UNAVAILABLE,
        "wave 1: installs, then fails at import -- ModuleNotFoundError: numpy. "
        "The recorded 'four undeclared runtime dependencies' finding reproduced "
        "exactly; a package that cannot import from its own declared deps is a "
        "reproducibility risk, not a candidate",
        "REJECTED",
        constraint="undeclared runtime dependencies; broken install contract",
    ),
    UpstreamCandidate(
        "smolagents", "1.26.0", AdapterState.DEGRADED,
        "wave 1: installed (85 MB, 18 s) and ran the real CRM task. Import 1.12 s, "
        "59.9 MB RSS. Tools work deterministically; the CodeAgent loop needs a model",
        "SECONDARY",
        constraint="agent loop requires a model; Jarvis makes 0 model calls today",
    ),
    UpstreamCandidate(
        "Agno", "3.0.10", AdapterState.DEGRADED,
        "wave 1: installed (100 MB, 23 s) and ran the real CRM task. Import 1.06 s, "
        "45.3 MB RSS -- the lighter of the two working frameworks",
        "SECONDARY",
        constraint="agent loop requires a model; Jarvis makes 0 model calls today",
    ),
    UpstreamCandidate(
        "Docling", "2.129.0", AdapterState.AVAILABLE,
        "wave 1: installed and run on a real business document "
        "(/opt/lcarlie/durum/ticari.html, 27 KB) -- 8 tables, 273 text blocks, "
        "correct Turkish section headings, 0.43 s convert, 650 MB RSS",
        "ADMITTED_ISOLATED", requirement=DOCLING_RESOURCE,
        constraint=("install CPU-only torch: the default wheel set pulls the full "
                    "CUDA stack (6.2 GB) onto a GPU-less host. No document corpus "
                    "exists on this server yet, so ingestion has no production input"),
    ),
    UpstreamCandidate(
        "llama.cpp", "build 11028 (972d2313b)", AdapterState.AVAILABLE,
        "wave 1: server runtime pulled as a container image (839 MB) and verified "
        "running -- no host toolchain installed (the host has no cmake/g++)",
        "RUNTIME_READY_MODEL_PENDING", requirement=LLAMACPP_RESOURCE,
        constraint="no model on this host; nothing downloaded, by instruction",
    ),
    UpstreamCandidate(
        "Langfuse", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed. Jarvis makes 0 model calls -- measured across the "
        "operational loop and the real multi-domain run -- so LLM tracing has "
        "nothing to trace. Existing per-cycle and per-step telemetry already "
        "carries latency, queue wait, cache hits, capabilities and failure reasons",
        "DEFERRED_NO_MODEL_CALLS",
    ),
    UpstreamCandidate(
        "Opik", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed, same measurement as Langfuse", "DEFERRED_NO_MODEL_CALLS",
    ),
    UpstreamCandidate(
        "Phoenix", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed, same measurement as Langfuse", "DEFERRED_NO_MODEL_CALLS",
    ),
    UpstreamCandidate(
        "Promptfoo", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed. Evaluates model behaviour, and there is no model in "
        "the loop to evaluate; the host also has no node/npm. Current behavioural "
        "guarantees are deterministic and already covered by the unit suite",
        "DEFERRED_NO_MODEL_CALLS",
    ),
    UpstreamCandidate(
        "RouteLLM", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed. Routing between models presupposes models; the "
        "deterministic route is the whole path today",
        "DEFERRED_NO_MODEL_CALLS",
    ),
    UpstreamCandidate(
        "Uptime Kuma", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed. Host already runs saglik.sh, alarm.sh and 13 systemd "
        "timers covering service health and alerting; adding a monitoring service "
        "would duplicate that and wants a port this project may not open",
        "REJECTED_OVERLAP_EXISTING_MONITORING",
    ),
    UpstreamCandidate(
        "OpenBao", "n/a", AdapterState.UNAVAILABLE,
        "wave 1: not installed. The gap it addresses is real -- secrets live in at "
        "least 8 separate .env files across /etc/lcarlie, /opt/lcarlie and /root, "
        "with no rotation and no central inventory -- but migrating live credentials "
        "is not a side effect of a capability wave",
        "PROPOSED_MIGRATION_PLAN_ONLY",
    ),
    UpstreamCandidate(
        "BGE-M3", "n/a", AdapterState.REQUIRES_RESOURCE_UPGRADE,
        "WAITING_RESOURCE_UPGRADE", "HELD_FOR_RESOURCES",
        requirement=BGE_M3_RESOURCE,
        constraint="not a rejection; hardware shortfall only",
    ),
    UpstreamCandidate(
        "Ruflo", "n/a", AdapterState.UNAVAILABLE,
        "BLOCKED upstream (committed manifest/lock mismatch)", "DO_NOT_FORCE_INSTALL",
        constraint="reproducibility blocker unresolved",
    ),
    UpstreamCandidate(
        "Yemaka", "n/a", AdapterState.UNAVAILABLE, "root build blocked",
        "ARCHITECTURE_REFERENCE_ONLY",
    ),
)


class AdapterFactory:
    """Registry of live adapters plus the evaluation half of the pipeline."""

    def __init__(self) -> None:
        self._adapters: dict[str, CapabilityAdapter] = {}

    def register(self, adapter: CapabilityAdapter) -> None:
        missing = [name for name in REQUIRED_ADAPTER_METHODS
                   if not callable(getattr(adapter, name, None))]
        if missing:
            raise TypeError(f"{adapter.name} does not satisfy the adapter contract: {missing}")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> CapabilityAdapter | None:
        return self._adapters.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def for_capability(self, capability_id: str) -> tuple[CapabilityAdapter, ...]:
        return tuple(adapter for adapter in self._adapters.values()
                     if capability_id in adapter.capabilities())

    @staticmethod
    def candidates() -> tuple[UpstreamCandidate, ...]:
        return UPSTREAMS

    @staticmethod
    def candidate(name: str) -> UpstreamCandidate | None:
        for entry in UPSTREAMS:
            if entry.name.casefold() == name.casefold():
                return entry
        return None

    def evaluate(self, name: str, resources: dict[str, Any] | None = None) -> dict[str, Any]:
        """Evidence-only evaluation. Reaches at most the SMOKE stage, because
        every later stage requires a human to have installed something."""
        candidate = self.candidate(name)
        if candidate is None:
            return {"name": name, "known": False, "state": AdapterState.UNAVAILABLE.value,
                    "stage": "CANDIDATE_SELECTED",
                    "next_action": "no reusable evidence; a human must run the isolated "
                                   "install and inspection stages before adoption"}
        verdict = (assess_resources(candidate.requirement, resources)
                   if candidate.requirement else None)
        state = verdict.state if verdict and not verdict.fits else candidate.state
        return {
            "name": candidate.name, "known": True, "state": state.value,
            "disposition": candidate.disposition, "evidence": candidate.evidence,
            "constraint": candidate.constraint,
            "already_integrated": candidate.disposition == "ALREADY_INTEGRATED",
            "resource_verdict": verdict.to_dict() if verdict else None,
            "stage": "SMOKE" if candidate.evidence else "CANDIDATE_SELECTED",
            "reused_evidence": True,
        }

    def propose_integration(self, name: str, capability_gap: str,
                            resources: dict[str, Any] | None = None) -> dict[str, Any]:
        """Emits a PROPOSED integration. Installs nothing, deploys nothing."""
        evaluation = self.evaluate(name, resources)
        blockers: list[str] = []
        if evaluation["state"] == AdapterState.UNAVAILABLE.value:
            blockers.append(evaluation.get("evidence") or "upstream unavailable")
        if evaluation["state"] == AdapterState.REQUIRES_RESOURCE_UPGRADE.value:
            verdict = evaluation.get("resource_verdict") or {}
            blockers.extend(verdict.get("shortfalls", []))
        return {
            "status": "PROPOSED",
            "capability_gap": capability_gap,
            "candidate": name,
            "evaluation": evaluation,
            "stages_completed": list(FACTORY_STAGES),
            "stages_remaining": list(INTEGRATION_STAGES[len(FACTORY_STAGES):]),
            "blockers": blockers,
            "approval_required": True,
            "installed": False,
            "deployed": False,
            "note": ("evidence-only proposal; isolated install, inspection, benchmark "
                     "and deploy are human-performed stages"),
        }


# --- concrete adapters over things that already exist -------------------
class CompanyMemoryAdapter(CapabilityAdapter):
    """Read-only Company Memory, through the existing allowlisted adapter."""

    name = "company_memory"
    state = AdapterState.AVAILABLE

    def __init__(self, memory: Any):
        self.memory = memory
        self._calls = 0
        self._failures = 0

    def health(self) -> dict[str, Any]:
        try:
            evidence = self.memory.get_system_status()
            return {"state": AdapterState.AVAILABLE.value,
                    "records": len(evidence.records), "source": evidence.source}
        except Exception as exc:  # noqa: BLE001 - health reports, never raises
            self._failures += 1
            return {"state": AdapterState.UNAVAILABLE.value, "error": f"{type(exc).__name__}"}

    def capabilities(self) -> tuple[str, ...]:
        return ("deterministic_company_memory",)

    def execute(self, envelope: dict[str, Any]) -> dict[str, Any]:
        query = envelope.get("query")
        reader = {"system": "get_system_status", "agenda": "get_company_agenda",
                  "open_work": "get_open_work",
                  "decision_summary": "get_company_context"}.get(query)
        if reader is None:
            raise ValueError(f"query is not allowlisted for this adapter: {query}")
        self._calls += 1
        evidence = getattr(self.memory, reader)()
        return {"records": len(evidence.records), "source": evidence.source}

    def evidence(self) -> tuple[AdapterEvidence, ...]:
        return (AdapterEvidence("jarvis.memory.CompanyMemory", "CANONICAL_COMPANY_MEMORY",
                                {"allowlisted_queries": sorted(self.memory.QUERIES)}),)

    def metrics(self) -> dict[str, Any]:
        return {"calls": self._calls, "failures": self._failures, "model_calls": 0}


class CodingExecutorAdapter(CapabilityAdapter):
    """The CodingExecutor, behind its human-origination boundary.

    execute() refuses unless the envelope carries proof a human originated the
    task. This adapter exists mostly to prove the factory can wrap something
    dangerous without widening it: wrapping did not create a new way in.
    """

    name = "coding_executor"
    state = AdapterState.AVAILABLE

    def __init__(self) -> None:
        self._refusals = 0

    def health(self) -> dict[str, Any]:
        from pathlib import Path as _Path
        import os as _os
        binary = _os.environ.get("JARVIS_KIMI_BIN", "/root/kimi-sandbox/bin/kimi")
        # 🔴 is_file() SESSIZCE FIRLATIR. Varsayilan yol /root altinda ve
        # root olmayan bir kullanici stat() cagirinca PermissionError gelir.
        # 25.09.2026'da CI bunu yakaladi: sozlesmesi "asla firlatmaz" olan
        # health(), test_health_reports_and_never_raises testini DUSURDU.
        # Uretimde gorunmemisti cunku servis root olarak kosuyor -- yani
        # kusur vardi, yalnizca o makinede tetiklenmiyordu.
        #
        # 🔴 "BAKAMADIM" ILE "YOK" AYNI SEY DEGILDIR. Izin hatasini
        # UNAVAILABLE yazmak, var olan bir ikiliyi yok ilan etmek olurdu.
        # Bu ayrim bu projenin tekrar eden kok hatasidir; DEGRADED + acik
        # sebep ile ayri tutuluyor.
        try:
            present = _Path(binary).is_file()
        except OSError as hata:
            return {"state": AdapterState.DEGRADED.value,
                    "binary_present": None,
                    "reason": f"{type(hata).__name__}: bakilamadi ({binary})",
                    "boundary": "human-originated tasks only"}
        return {"state": (AdapterState.AVAILABLE if present
                          else AdapterState.UNAVAILABLE).value,
                "binary_present": present,
                "boundary": "human-originated tasks only"}

    def capabilities(self) -> tuple[str, ...]:
        return ("coding_task",)

    def execute(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if not envelope.get("human_originated"):
            self._refusals += 1
            raise PermissionError(
                "coding tasks are human-originated: run "
                "`jarvis-operator create-coding-task <slug> <spec.json>`")
        return {"status": "REQUIRES_OPERATOR_PATH",
                "originate_with": "jarvis-operator create-coding-task <slug> <spec.json>",
                "executed": False}

    def evidence(self) -> tuple[AdapterEvidence, ...]:
        return (AdapterEvidence("jarvis.coding_executor", "PRODUCTION_MODULE",
                                {"commit": "35c6388",
                                 "isolation": "disposable git clone, scope-gated, tests required"}),)

    def metrics(self) -> dict[str, Any]:
        return {"refusals": self._refusals, "model_calls": 0}


def default_factory(memory: Any | None = None) -> AdapterFactory:
    factory = AdapterFactory()
    if memory is not None:
        factory.register(CompanyMemoryAdapter(memory))
    factory.register(CodingExecutorAdapter())
    return factory
