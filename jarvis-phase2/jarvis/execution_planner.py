"""Execution Planner V1: natural language -> a checked execution DAG.

    Web Console request -> ExecutionPlanner -> ExecutionPlan
    -> routed to EXISTING capabilities (Context Compiler, Company Memory,
       Capability Registry, CodingExecutor, proposal/action firewall)

The planner NEVER does the work. It produces a plan and names which existing
capability each step belongs to. It opens no database connection, spawns no
subprocess, calls no model, and emits no external action -- planning a
deterministic request costs zero model calls by construction, not by policy.

Three boundaries this module must never cross, and how each is enforced:

  1. External business actions. A request that asks to send, publish, or
     change a price never produces an executable step. It returns
     BLOCKED_EXTERNAL_ACTION plus a single human-review step. EXTERNAL_ACTIONS
     stays false; the planner has no code path that could set it otherwise.

  2. Coding tasks. A coding request plans exactly one `coding_task` step and
     marks it requires_human_origination. The CodingExecutor safety boundary
     built in 35c6388 is human-originated by design -- a task only exists
     because a human ran `jarvis-operator create-coding-task`. The planner
     produces the ARGUMENTS for that command; it can never enqueue the task
     itself, because it never touches the database.

  3. Approval. Any plan carrying a step that would produce an action is
     approval_required, and the step routes to the unchanged
     firewall -> core.ai_propose_action -> human approval path. The planner
     holds no human_approver credential and no route bypasses the firewall.

Mode selection is rule-based (see `select_mode`). An LLM is not required to
produce a plan and is not consulted; a future model-assisted refinement can
only narrow a plan, never widen its capability set, because the routing table
below is the only source of executable targets.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from . import capabilities as caps

# --- vocabulary --------------------------------------------------------
MODE_FAST = "FAST"
MODE_SMART = "SMART"
MODE_DEEP = "DEEP"

STATUS_PLANNED = "PLANNED"
STATUS_REJECTED_AMBIGUOUS = "REJECTED_AMBIGUOUS"
STATUS_BLOCKED_EXTERNAL_ACTION = "BLOCKED_EXTERNAL_ACTION"
STATUS_BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

EXEC_LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
EXEC_MODEL_ASSISTED = "MODEL_ASSISTED"
EXEC_CODING_SANDBOX = "CODING_SANDBOX"

_EXEC_ORDER = (EXEC_LOCAL_DETERMINISTIC, EXEC_MODEL_ASSISTED, EXEC_CODING_SANDBOX)

MIN_REQUEST_CHARS = 3
MAX_REQUEST_CHARS = 2000


# --- routing contract --------------------------------------------------
@dataclass(frozen=True)
class Route:
    """Where a planned step is allowed to go. This table is the ONLY source of
    executable targets: a step whose capability is not a key here cannot be
    built, so no plan can ever name a target that does not already exist."""
    capability: str
    target: str
    requires_capabilities: tuple[str, ...]
    execution_class: str
    produces_action: bool = False
    requires_human_origination: bool = False


ROUTES: dict[str, Route] = {
    "internal_data_analysis": Route(
        capability="internal_data_analysis",
        target="jarvis.context.ContextCompiler.compile -> jarvis.memory.CompanyMemory",
        requires_capabilities=("deterministic_company_memory",),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
    ),
    "capability_analysis": Route(
        capability="capability_analysis",
        target="jarvis.capabilities.analyse",
        requires_capabilities=("deterministic_company_memory",),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
    ),
    "system_status": Route(
        capability="system_status",
        target="jarvis.memory.CompanyMemory.get_system_status",
        requires_capabilities=("deterministic_company_memory",),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
    ),
    "external_research": Route(
        capability="external_research",
        target="capability:external_model_provider",
        requires_capabilities=("external_model_provider",),
        execution_class=EXEC_MODEL_ASSISTED,
    ),
    "evidence_fusion": Route(
        capability="evidence_fusion",
        target="jarvis.research.fuse",
        requires_capabilities=(),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
    ),
    "red_team_review": Route(
        capability="red_team_review",
        target="jarvis.research.fuse (contradiction + independent-source check)",
        requires_capabilities=(),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
    ),
    "coding_task": Route(
        capability="coding_task",
        target="jarvis.coding_executor via `jarvis-operator create-coding-task`",
        requires_capabilities=(),
        execution_class=EXEC_CODING_SANDBOX,
        produces_action=True,
        requires_human_origination=True,
    ),
    "human_review_proposal": Route(
        capability="human_review_proposal",
        target="jarvis.firewall.validate_proposal -> core.ai_propose_action -> human approval",
        requires_capabilities=("external_business_action",),
        execution_class=EXEC_LOCAL_DETERMINISTIC,
        produces_action=True,
    ),
}


# --- deterministic intent detection -----------------------------------
# Lemma substrings matched against the normalized form, exactly like the web
# console's own boundary: ordinary Turkish suffixes attached to a lemma still
# match without listing every inflected form.
_INTERNAL_LEMMAS = (
    "satış", "satis", "ciro", "gelir", "marj", "maliyet", "sipariş", "siparis",
    "müşteri", "musteri", "analiz", "incele", "performans", "dönüşüm", "donusum",
    "veri", "rapor", "durum", "sistem", "gündem", "gundem", "sales", "revenue",
    "analyze", "analyse", "internal",
)
_EXTERNAL_LEMMAS = (
    "rakip", "rakipler", "competitor", "pazar", "market", "sektör", "sektor",
    "trend", "dışarıda", "disarida", "güncel", "guncel", "piyasa", "benchmark",
    "araştır", "arastir", "research", "web", "haber",
)
_CODE_LEMMAS = (
    "kod", "code", "bug", "hata düzelt", "hata duzelt", "düzelt", "duzelt",
    "refactor", "implement", "modül", "modul", "fonksiyon", "test yaz",
    "script", "geliştir", "gelistir", "patch",
)
_RECOMMEND_LEMMAS = (
    "ne yapmalı", "ne yapmali", "ne yapmamız", "ne yapmamiz", "öneri", "oneri",
    "tavsiye", "ne öneriyorsun", "ne oneriyorsun", "strateji", "karar",
    "recommend", "what should", "yol haritası", "yol haritasi",
)
_DIAGNOSE_LEMMAS = (
    "neden", "niçin", "nicin", "niye", "sebep", "kök neden", "kok neden",
    "why", "root cause", "sorun", "problem", "düşük", "dusuk", "azaldı", "azaldi",
    "düştü", "dustu", "kötü", "kotu",
)
# An external business action: never planned as an executable step.
_EXTERNAL_ACTION_LEMMAS = (
    "gönder", "gonder", "yolla", "mesaj at", "yayınla", "yayinla", "publish",
    "fiyat değiştir", "fiyat degistir", "fiyatı güncelle", "fiyati guncelle",
    "kampanya başlat", "kampanya baslat", "reklam ver", "bütçe artır",
    "butce artir", "send", "post to", "paylaş", "paylas", "sipariş ver",
    "siparis ver", "iade et", "ödeme al", "odeme al",
)
_CAPABILITY_LEMMAS = ("yetenek", "capability", "neler yapabilirsin", "ne yapabilirsin")


def _normalize(text: str) -> str:
    """Turkish-safe normalization, reusing the web console's existing intent
    boundary rather than growing a second, drifting copy of it.

    Imported inside the function on purpose: `webconsole` depends on `jarvis`,
    so a module-level import here would make the dependency circular. The
    function-level import keeps the reuse without the cycle.
    """
    from webconsole.intents import normalize

    return normalize(text)


def _hits(normalized: str, lemmas: Iterable[str]) -> tuple[str, ...]:
    return tuple(lemma for lemma in lemmas if _normalize(lemma) in normalized)


# --- plan structures ---------------------------------------------------
@dataclass(frozen=True)
class PlanStep:
    step_id: str
    capability: str
    description: str
    target: str
    depends_on: tuple[str, ...] = ()
    parallel_group: int = 0
    execution_class: str = EXEC_LOCAL_DETERMINISTIC
    produces_action: bool = False
    requires_human_origination: bool = False
    capability_status: str = "NOT_EVALUATED"
    blocked_by: tuple[str, ...] = ()
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["depends_on"] = list(self.depends_on)
        data["blocked_by"] = list(self.blocked_by)
        return data


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    request: str
    intent: str
    risk: str
    mode: str
    steps: tuple[PlanStep, ...]
    dependencies: tuple[tuple[str, str], ...]
    parallel_groups: tuple[tuple[str, ...], ...]
    required_capabilities: tuple[str, ...]
    required_internal_data: tuple[str, ...]
    requires_fresh_research: bool
    context_requirements: dict[str, Any]
    approval_required: bool
    estimated_execution_class: str
    status: str
    reason: str = ""
    model_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "request": self.request,
            "intent": self.intent,
            "risk": self.risk,
            "mode": self.mode,
            "steps": [step.to_dict() for step in self.steps],
            "dependencies": [list(edge) for edge in self.dependencies],
            "parallel_groups": [list(group) for group in self.parallel_groups],
            "required_capabilities": list(self.required_capabilities),
            "required_internal_data": list(self.required_internal_data),
            "requires_fresh_research": self.requires_fresh_research,
            "context_requirements": self.context_requirements,
            "approval_required": self.approval_required,
            "estimated_execution_class": self.estimated_execution_class,
            "status": self.status,
            "reason": self.reason,
            "model_calls": self.model_calls,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _plan_id(normalized: str) -> str:
    """Derived from the request alone: the same request always yields the same
    plan_id, so a plan is reproducible and comparable across runs. No clock,
    no randomness -- both would make plans untestable and undiffable."""
    return "plan-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _rejected(request: str, normalized: str, status: str, reason: str,
              steps: tuple[PlanStep, ...] = (), approval_required: bool = False,
              risk: str = RISK_LOW, intent: str = "UNKNOWN") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=_plan_id(normalized), request=request, intent=intent, risk=risk,
        mode=MODE_FAST, steps=steps, dependencies=(),
        parallel_groups=((tuple(step.step_id for step in steps),) if steps else ()),
        required_capabilities=tuple(sorted({
            cap for step in steps for cap in ROUTES[step.capability].requires_capabilities
        })),
        required_internal_data=(), requires_fresh_research=False,
        context_requirements={"entity": None, "evidence_required": False},
        approval_required=approval_required,
        estimated_execution_class=EXEC_LOCAL_DETERMINISTIC,
        status=status, reason=reason,
    )


def select_mode(workstreams: tuple[str, ...], requires_fresh_research: bool,
                wants_recommendation: bool, is_diagnosis: bool) -> str:
    """Deterministic, in this order. No model is consulted.

    DEEP  -- more than one independent workstream, or fresh external research,
             or a coding task: all three need fusion/red-team before anything
             is proposed to a human.
    SMART -- a single workstream that still has to produce a judgement or find
             a root cause, so the evidence has to be reasoned over.
    FAST  -- a single retrieval answering a direct question.
    """
    if len(workstreams) >= 2 or requires_fresh_research or "coding_task" in workstreams:
        return MODE_DEEP
    if wants_recommendation or is_diagnosis:
        return MODE_SMART
    return MODE_FAST


def _assign_groups(steps: list[PlanStep]) -> tuple[list[PlanStep], tuple[tuple[str, ...], ...]]:
    """Longest-path level assignment: a step sits one level below its deepest
    dependency, so every step in a level is genuinely independent of the others
    and the levels are exactly the parallel groups."""
    by_id = {step.step_id: step for step in steps}
    level: dict[str, int] = {}

    def depth(step_id: str) -> int:
        if step_id in level:
            return level[step_id]
        parents = by_id[step_id].depends_on
        level[step_id] = 0 if not parents else 1 + max(depth(parent) for parent in parents)
        return level[step_id]

    for step in steps:
        depth(step.step_id)

    placed = [
        PlanStep(**{**asdict(step), "parallel_group": level[step.step_id],
                    "depends_on": step.depends_on, "blocked_by": step.blocked_by})
        for step in steps
    ]
    groups: dict[int, list[str]] = {}
    for step in placed:
        groups.setdefault(step.parallel_group, []).append(step.step_id)
    return placed, tuple(tuple(groups[key]) for key in sorted(groups))


def _apply_registry(steps: list[PlanStep],
                    registry: dict[str, caps.Capability] | None) -> tuple[list[PlanStep], bool]:
    """Annotate each step with the live status of the capabilities it needs.

    Without a registry the status stays NOT_EVALUATED -- the planner refuses to
    guess that something is available. A capability in a gap state blocks its
    step rather than silently downgrading the plan.
    """
    if registry is None:
        return steps, False

    usable = caps.USABLE | {caps.CONTROLLED}
    annotated: list[PlanStep] = []
    blocked_any = False
    for step in steps:
        needed = ROUTES[step.capability].requires_capabilities
        statuses = {name: registry[name].status for name in needed if name in registry}
        missing = tuple(sorted(
            name for name, status in statuses.items() if status not in usable
        ))
        unregistered = tuple(sorted(name for name in needed if name not in registry))
        blocked = missing + unregistered
        blocked_any = blocked_any or bool(blocked)
        status = "BLOCKED" if blocked else ("OK" if statuses else "NO_CAPABILITY_REQUIRED")
        annotated.append(PlanStep(**{**asdict(step), "depends_on": step.depends_on,
                                     "capability_status": status, "blocked_by": blocked}))
    return annotated, blocked_any


class ExecutionPlanner:
    """Turns one natural-language request into one ExecutionPlan.

    Stateless and side-effect free: `plan()` is a pure function of its inputs.
    Pass `registry` (from jarvis.capabilities.build_registry) to have the plan
    checked against live capability status; omit it for a pure structural plan.
    """

    def plan(self, request: str,
             registry: dict[str, caps.Capability] | None = None) -> ExecutionPlan:
        raw = request or ""
        normalized = _normalize(raw)

        # --- fail-safe on malformed input ------------------------------
        if len(normalized) < MIN_REQUEST_CHARS:
            return _rejected(raw, normalized, STATUS_REJECTED_AMBIGUOUS,
                             "request is empty or too short to plan")
        if len(raw) > MAX_REQUEST_CHARS:
            return _rejected(raw, normalized, STATUS_REJECTED_AMBIGUOUS,
                             f"request exceeds {MAX_REQUEST_CHARS} characters")

        # --- external business action: never planned as executable ------
        action_hits = _hits(normalized, _EXTERNAL_ACTION_LEMMAS)
        if action_hits:
            review = PlanStep(
                step_id="S1", capability="human_review_proposal",
                description="Escalate the requested external action to a human decision",
                target=ROUTES["human_review_proposal"].target,
                execution_class=EXEC_LOCAL_DETERMINISTIC, produces_action=True,
                arguments={"internal_intent": "HUMAN_REVIEW_REQUEST",
                           "detected_action_terms": list(action_hits)},
            )
            return _rejected(
                raw, normalized, STATUS_BLOCKED_EXTERNAL_ACTION,
                "request asks for an external business action; EXTERNAL_ACTIONS=false, "
                "so the planner emits no executable action step",
                steps=(review,), approval_required=True, risk=RISK_HIGH,
                intent="EXTERNAL_ACTION",
            )

        # --- workstream detection --------------------------------------
        internal_hits = _hits(normalized, _INTERNAL_LEMMAS)
        external_hits = _hits(normalized, _EXTERNAL_LEMMAS)
        code_hits = _hits(normalized, _CODE_LEMMAS)
        capability_hits = _hits(normalized, _CAPABILITY_LEMMAS)
        wants_recommendation = bool(_hits(normalized, _RECOMMEND_LEMMAS))
        is_diagnosis = bool(_hits(normalized, _DIAGNOSE_LEMMAS))

        steps: list[PlanStep] = []
        counter = 0

        def add(capability: str, description: str, depends_on: tuple[str, ...] = (),
                arguments: dict[str, Any] | None = None) -> str:
            nonlocal counter
            counter += 1
            route = ROUTES[capability]
            step_id = f"S{counter}"
            steps.append(PlanStep(
                step_id=step_id, capability=capability, description=description,
                target=route.target, depends_on=depends_on,
                execution_class=route.execution_class,
                produces_action=route.produces_action,
                requires_human_origination=route.requires_human_origination,
                arguments=arguments or {},
            ))
            return step_id

        entity = "VIREON" if "vireon" in normalized else None

        if capability_hits:
            _ = (add("capability_analysis",
                                   "Capability-gap analysis over the live registry"))
        if internal_hits or (not external_hits and not code_hits and not capability_hits):
            _ = (add(
                "internal_data_analysis",
                f"Retrieve and analyse internal evidence{f' for {entity}' if entity else ''}",
                arguments={"entity": entity, "matched_terms": list(internal_hits)},
            ))
        if external_hits:
            _ = (add(
                "external_research",
                "Gather fresh external evidence (competitors / market)",
                arguments={"matched_terms": list(external_hits)},
            ))
        if code_hits:
            _ = (add(
                "coding_task",
                "Bounded coding task in a disposable clone; HUMAN must originate it",
                arguments={
                    "originate_with": "jarvis-operator create-coding-task <slug> <spec.json>",
                    "spec_fields": ["objective", "allowed_files"],
                    "matched_terms": list(code_hits),
                },
            ))

        workstream_ids = tuple(step.step_id for step in steps)
        requires_fresh_research = bool(external_hits)

        # --- fusion / red-team / proposal -------------------------------
        last = workstream_ids
        if len(workstream_ids) >= 2:
            fusion = add("evidence_fusion",
                         "Fuse independent evidence; flag contradictions and weak sourcing",
                         depends_on=workstream_ids)
            last = (fusion,)
        mode = select_mode(tuple(step.capability for step in steps if step.step_id in workstream_ids),
                           requires_fresh_research, wants_recommendation, is_diagnosis)
        if mode == MODE_DEEP:
            red = add("red_team_review",
                      "Adversarial check of the fused evidence before anything is proposed",
                      depends_on=last)
            last = (red,)
        if wants_recommendation or mode == MODE_DEEP:
            add("human_review_proposal",
                "Submit findings for human review through the unchanged action firewall",
                depends_on=last,
                arguments={"internal_intent": "HUMAN_REVIEW_REQUEST"})

        placed, groups = _assign_groups(steps)
        placed, capability_blocked = _apply_registry(placed, registry)

        dependencies = tuple(
            (parent, step.step_id) for step in placed for parent in step.depends_on
        )
        required_capabilities = tuple(sorted({
            name for step in placed for name in ROUTES[step.capability].requires_capabilities
        }))
        approval_required = any(step.produces_action for step in placed)

        execution_class = EXEC_LOCAL_DETERMINISTIC
        for step in placed:
            if _EXEC_ORDER.index(step.execution_class) > _EXEC_ORDER.index(execution_class):
                execution_class = step.execution_class

        if code_hits:
            risk = RISK_HIGH
        elif requires_fresh_research or approval_required:
            risk = RISK_MEDIUM
        else:
            risk = RISK_LOW

        internal_data: list[str] = []
        if entity:
            internal_data.append(f"product_context:{entity}")
        if any(step.capability == "internal_data_analysis" for step in placed) and not entity:
            internal_data.append("company_context")
        if "durum" in normalized or "sistem" in normalized or "status" in normalized:
            internal_data.append("system_status")
        if capability_hits:
            internal_data.append("capability_state")

        intent = "COMPOSITE" if len(workstream_ids) >= 2 else (
            placed[0].capability.upper() if placed else "UNKNOWN"
        )
        if is_diagnosis and len(workstream_ids) < 2:
            intent = "DIAGNOSE_" + intent

        status = STATUS_BLOCKED_CAPABILITY if capability_blocked else STATUS_PLANNED
        reason = ""
        if capability_blocked:
            blocked_steps = [step.step_id for step in placed if step.blocked_by]
            reason = ("live capability status blocks step(s): "
                      + ", ".join(blocked_steps))

        return ExecutionPlan(
            plan_id=_plan_id(normalized), request=raw, intent=intent, risk=risk, mode=mode,
            steps=tuple(placed), dependencies=dependencies, parallel_groups=groups,
            required_capabilities=required_capabilities,
            required_internal_data=tuple(internal_data),
            requires_fresh_research=requires_fresh_research,
            context_requirements={
                "entity": entity,
                "evidence_required": bool(internal_data),
                "capability_analysis": bool(capability_hits),
                "max_facts": 10,
                "compiler": "jarvis.context.ContextCompiler",
            },
            approval_required=approval_required,
            estimated_execution_class=execution_class,
            status=status, reason=reason,
        )


def plan_request(request: str,
                 registry: dict[str, caps.Capability] | None = None) -> ExecutionPlan:
    return ExecutionPlanner().plan(request, registry=registry)


if __name__ == "__main__":  # pragma: no cover - convenience surface
    import sys

    if len(sys.argv) < 2:
        print('usage: python3 -m jarvis.execution_planner "<request>"')
        raise SystemExit(1)
    print(plan_request(" ".join(sys.argv[1:])).to_json())
