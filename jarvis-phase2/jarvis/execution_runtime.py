"""Execution DAG runtime: runs a plan the ExecutionPlanner already produced.

    ExecutionPlan -> ExecutionRuntime -> RunRecord

The runtime executes ONLY read-only analysis. Every step that could act is
prepared and stopped:

  * a step whose route declares produces_action is never executed. It is
    validated through the UNCHANGED jarvis.firewall against the live contract
    and recorded as PROPOSED -- an envelope a human can approve, not an action
    that happened. Nothing here writes to core.ai_action_proposal; that stays
    on the existing operator/loop path, which is the only code holding the
    identities to do it.
  * a coding_task is ALWAYS REQUIRES_HUMAN_ORIGINATION. The runtime cannot
    create one: it never calls jarvis.coding_executor, and a test patches
    run_coding_task to raise to keep it that way. Jarvis originating its own
    coding task is exactly the boundary 35c6388 exists to prevent.
  * external_research is not executed while external_model_provider is
    blocked, which it is under EXTERNAL_ACTIONS=false.

A plan cannot start itself. `execute()` requires a non-empty `originator`,
so every run is traceable to a human who asked for it.

Nothing here calls a model. model_calls is reported per step and in the run
telemetry, and is 0 by construction rather than by policy.

Reuse, not reinvention: bounded concurrency is jarvis.governors.ResourceGovernor,
caching is jarvis.cache.QueryCache, fusion is jarvis.research.fuse, context is
jarvis.context.ContextCompiler, problem/opportunity detection is
jarvis.business_signals, and every read goes through the allowlisted
jarvis.memory.CompanyMemory. This module adds orchestration and nothing else.
"""
from __future__ import annotations

import json
import os
import fcntl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from . import business_signals, office_events
from .acceptance_contract import evaluate as evaluate_acceptance
from .cache import QueryCache
from .context import ContextCompiler
from .execution_planner import DATA_UNAVAILABLE, DOMAINS, ExecutionPlan
from .firewall import FirewallError, validate_proposal
from .governors import ResourceBudget, ResourceGovernor
from .research import SourceRecord, fuse

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
RUN_DIR = STATE_DIR / "execution_runtime"

MAX_FACTS_PER_STEP = int(os.environ.get("JARVIS_RUNTIME_MAX_FACTS", "10"))
DEFAULT_CONCURRENCY = int(os.environ.get("JARVIS_RUNTIME_CONCURRENCY", "3"))

# --- run status ---------------------------------------------------------
RUN_COMPLETED = "COMPLETED"
RUN_DEGRADED = "COMPLETED_DEGRADED"
RUN_FAILED = "FAILED"

# --- step status --------------------------------------------------------
STEP_PENDING = "PENDING"
STEP_SUCCEEDED = "SUCCEEDED"
STEP_FAILED = "FAILED"
STEP_PROPOSED = "PROPOSED"
STEP_DATA_UNAVAILABLE = DATA_UNAVAILABLE
STEP_BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
STEP_BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
STEP_REQUIRES_HUMAN_ORIGINATION = "REQUIRES_HUMAN_ORIGINATION"

# A downstream step is only stopped by an upstream that produced NOTHING
# usable. DATA_UNAVAILABLE and BLOCKED_CAPABILITY are degraded, not fatal:
# fusion must still run on the evidence that does exist and say plainly which
# inputs were missing, because silently dropping them is how a partial answer
# starts looking like a complete one.
FATAL_UPSTREAM = {STEP_FAILED, STEP_BLOCKED_UPSTREAM}
DEGRADED_STATUSES = {STEP_DATA_UNAVAILABLE, STEP_BLOCKED_CAPABILITY,
                     STEP_REQUIRES_HUMAN_ORIGINATION}


class ExecutionDenied(RuntimeError):
    """The runtime refused to start or to run a step. Never a crash path."""


@dataclass
class StepRecord:
    step_id: str
    capability: str
    status: str = STEP_PENDING
    inputs: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    block_reason: str | None = None
    queue_wait_ms: float = 0.0
    duration_ms: float = 0.0
    model_calls: int = 0
    cache_hits: int = 0
    acceptance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StepRecord":
        data = dict(data)
        data["evidence_refs"] = tuple(data.get("evidence_refs") or ())
        return StepRecord(**data)


@dataclass
class RunRecord:
    run_id: str
    plan_id: str
    request: str
    originator: str
    status: str
    attempt: int
    started_at: str
    finished_at: str | None = None
    total_ms: float = 0.0
    steps: dict[str, StepRecord] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "plan_id": self.plan_id, "request": self.request,
            "originator": self.originator, "status": self.status, "attempt": self.attempt,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "total_ms": self.total_ms,
            "steps": {key: step.to_dict() for key, step in self.steps.items()},
            "telemetry": self.telemetry,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RunRecord":
        record = RunRecord(
            run_id=data["run_id"], plan_id=data["plan_id"], request=data["request"],
            originator=data["originator"], status=data["status"],
            attempt=data.get("attempt", 1), started_at=data["started_at"],
            finished_at=data.get("finished_at"), total_ms=data.get("total_ms", 0.0),
            telemetry=data.get("telemetry", {}),
        )
        record.steps = {key: StepRecord.from_dict(value)
                        for key, value in (data.get("steps") or {}).items()}
        return record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id_for(plan_id: str, attempt: int = 1) -> str:
    """Derived from the plan, which is itself derived from the request. Running
    the same plan twice therefore lands on the same run id and is deduplicated
    instead of silently doing the work again."""
    return f"run-{plan_id}" + (f"-a{attempt}" if attempt > 1 else "")


# --- step context passed to every executor -----------------------------
@dataclass
class StepContext:
    plan: ExecutionPlan
    step: Any                      # execution_planner.PlanStep
    memory: Any
    compiler: ContextCompiler
    cache: QueryCache
    contract: Any | None
    upstream: dict[str, StepRecord]
    counters: dict[str, int]
    # Every step recorded so far. The red-team pass needs the whole run, not
    # just its own parents: the gaps it must object to were created upstream
    # of the analysis it is reviewing, and would be invisible from S7 alone.
    all_steps: dict[str, StepRecord] = field(default_factory=dict)


@dataclass
class StepOutcome:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    error: str | None = None
    block_reason: str | None = None
    cache_hits: int = 0


# --- memory access, cached and allowlisted ------------------------------
def _read(ctx: StepContext, query: str) -> tuple[Any, bool]:
    """One allowlisted read, cached for the run.

    The allowlist is CompanyMemory.QUERIES itself, not a second table kept in
    step with it by hand. This module used to carry its own query -> reader
    map, and it drifted the moment the data fabric added queries: every new
    domain read failed as "not an allowlisted reader" while being perfectly
    allowlisted. That is the same duplicated-contract failure F-1 was about,
    so the duplicate is gone rather than extended.

    A name outside the allowlist is a denial, never a fallback to something
    broader.
    """
    allowlist = getattr(ctx.memory, "QUERIES", {})
    if query not in allowlist:
        raise ExecutionDenied(f"query is not allowlisted in CompanyMemory: {query}")
    return ctx.cache.get_or_load(f"memory:{query}", lambda: ctx.memory._fetch(query))


# --- executors ----------------------------------------------------------
def _execute_domain(ctx: StepContext) -> StepOutcome:
    domain_id = ctx.step.arguments.get("domain")
    queries = tuple(ctx.step.arguments.get("memory_queries") or ())
    if not queries:
        # Carried straight through from planning. The runtime does not get a
        # second opinion about whether the data exists, and must not answer
        # from something adjacent.
        return StepOutcome(
            status=STEP_DATA_UNAVAILABLE,
            output={"domain": domain_id, "records": 0},
            block_reason=ctx.step.arguments.get("unavailable_reason")
                         or f"no Company Memory data contract for {domain_id}",
        )
    records: list[dict[str, Any]] = []
    refs: list[str] = []
    hits = 0
    for query in queries:
        evidence, cached = _read(ctx, query)
        hits += 1 if cached else 0
        records.extend(evidence.records[:MAX_FACTS_PER_STEP])
        refs.append(evidence.source)
    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"domain": domain_id, "records": len(records),
                "sample": records[:3]},
        evidence_refs=tuple(dict.fromkeys(refs)), cache_hits=hits,
    )


def _execute_internal(ctx: StepContext) -> StepOutcome:
    compiled = ctx.compiler.compile(ctx.plan.request, contract=ctx.contract)
    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"entity": compiled.entity, "records": compiled.retrieved_records,
                "context_bytes": compiled.context_bytes},
        evidence_refs=tuple(compiled.evidence_refs),
    )


def _execute_capability_analysis(ctx: StepContext) -> StepOutcome:
    compiled = ctx.compiler.compile("capability gap", contract=ctx.contract)
    analysis = compiled.capability_analysis or {}
    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"capability_gap": analysis.get("capability_gap"),
                "gaps": [gap["capability_id"] for gap in analysis.get("gaps", [])],
                "recommendations": analysis.get("recommendations", [])},
        evidence_refs=tuple(compiled.evidence_refs),
    )


def _execute_fusion(ctx: StepContext) -> StepOutcome:
    """Fuses ONLY evidence upstream steps actually produced.

    Missing inputs are named, never imputed: a domain that came back
    DATA_UNAVAILABLE contributes nothing to the fused record set and appears in
    `missing_inputs` instead, so the confidence figure below is about evidence
    that exists rather than evidence that was assumed.
    """
    missing: list[dict[str, str]] = []
    refs: list[str] = []
    per_entity: dict[str, list[SourceRecord]] = {}
    for step_id, record in sorted(ctx.upstream.items()):
        if record.status in DEGRADED_STATUSES:
            missing.append({"step_id": step_id, "capability": record.capability,
                            "status": record.status,
                            "reason": record.block_reason or ""})
            continue
        if record.status != STEP_SUCCEEDED:
            continue
        entity = str(record.output.get("domain") or record.capability)
        for ref in record.evidence_refs:
            refs.append(ref)
            # One claim per entity, so `contradiction` can only become true if
            # two sources for the SAME domain disagree -- fuse() compares
            # claims, and comparing one domain's claim against another's would
            # report a contradiction that does not exist.
            per_entity.setdefault(entity, []).append(SourceRecord(
                source_id=f"{step_id}:{ref}", publisher=ref, entity=entity,
                claim=f"evidence present for {entity}",
                observed_at=_now(), authority=1.0,
            ))

    domains: list[dict[str, Any]] = []
    total = 0
    for entity in sorted(per_entity):
        fused = fuse(per_entity[entity])
        total += len(per_entity[entity])
        domains.append({
            "entity": entity,
            "sources": fused["independent_sources"],
            "contradiction": fused["contradiction"],
            "confidence": fused["confidence"],
            "single_source": fused["independent_sources"] < 2,
        })

    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"independent_sources": len(set(refs)),
                "contradiction": any(item["contradiction"] for item in domains),
                "confidence": (round(min(item["confidence"] for item in domains), 3)
                               if domains else 0.0),
                "needs_more_sources": any(item["single_source"] for item in domains),
                "fused_inputs": total,
                "domains": domains,
                "missing_inputs": missing},
        evidence_refs=tuple(dict.fromkeys(refs)),
    )


def _execute_problem_opportunity(ctx: StepContext) -> StepOutcome:
    """Reuses the intelligence layer's deterministic detector unchanged.

    It reads the three canonical views through the same allowlisted adapter;
    a rule it cannot evaluate is reported as skipped rather than downgraded
    into a finding, which is the property that makes it safe to route here.
    """
    report = business_signals.run(ctx.memory)
    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"signals": [{"code": signal.code, "severity": signal.severity,
                             "summary": signal.summary}
                            for signal in report.signals],
                "skipped": report.skipped, "content_hash": report.content_hash},
        evidence_refs=("postgres:decision_summary", "postgres:agenda", "postgres:open_work"),
    )


def _execute_red_team(ctx: StepContext) -> StepOutcome:
    """Adversarial pass over what the upstream steps actually produced.

    Deterministic and evidence-shaped: it looks for thin sourcing, declared
    contradictions and inputs that were never available. It does not re-derive
    the findings, and it cannot approve anything.
    """
    objections: list[dict[str, str]] = []
    reviewed = ctx.all_steps or ctx.upstream
    for step_id, record in sorted(reviewed.items()):
        if step_id == ctx.step.step_id:
            continue
        output = record.output or {}
        if record.status in DEGRADED_STATUSES:
            objections.append({"step_id": step_id, "code": "EVIDENCE_MISSING",
                               "detail": record.block_reason or record.status})
        if output.get("contradiction"):
            objections.append({"step_id": step_id, "code": "CONTRADICTION",
                               "detail": "fused evidence contradicts itself"})
        if output.get("needs_more_sources"):
            objections.append({"step_id": step_id, "code": "THIN_SOURCING",
                               "detail": f"independent sources = {output.get('independent_sources')}"})
        for entry in output.get("missing_inputs", []) or []:
            objections.append({"step_id": entry.get("step_id", step_id),
                               "code": "INPUT_UNAVAILABLE",
                               "detail": entry.get("reason") or entry.get("status", "")})
    return StepOutcome(
        status=STEP_SUCCEEDED,
        output={"objections": objections, "objection_count": len(objections),
                "clean": not objections},
    )


def _prepare_proposal(ctx: StepContext) -> StepOutcome:
    """Prepares a proposal envelope and STOPS.

    Validated through the unchanged firewall against the live contract, so an
    envelope that would be refused at core.ai_propose_action is refused here
    too -- but nothing is written. Submitting it stays on the existing
    operator/loop path, which holds the identities this process does not.
    """
    intent = ctx.step.arguments.get("internal_intent", "HUMAN_REVIEW_REQUEST")
    objections = 0
    for record in ctx.upstream.values():
        objections += int((record.output or {}).get("objection_count") or 0)
    payload = {
        "subject_ref": f"execution-plan:{ctx.plan.plan_id}",
        "reason": (f"Execution plan {ctx.plan.plan_id} completed read-only analysis; "
                   f"{objections} red-team objection(s). Advisory only, awaiting human "
                   f"approval. No action was taken.")[:2000],
    }
    if ctx.contract is None:
        return StepOutcome(
            status=STEP_BLOCKED_CAPABILITY, output={"internal_intent": intent},
            block_reason="no action contract loaded; proposal cannot be validated",
        )
    try:
        envelope = validate_proposal(intent, payload, ctx.contract,
                                     idempotency_key=f"action:plan:{ctx.plan.plan_id}")
    except FirewallError as exc:
        return StepOutcome(status=STEP_FAILED, error=f"firewall rejected the proposal: {exc}")
    return StepOutcome(
        status=STEP_PROPOSED,
        output={"internal_intent": intent, "action_type": envelope["action_type"],
                "idempotency_key": envelope["idempotency_key"],
                "payload": envelope["payload"], "submitted": False,
                "submit_with": "jarvis-operator (human_approver) -> existing loop propose path"},
    )


def _refuse_coding(ctx: StepContext) -> StepOutcome:
    return StepOutcome(
        status=STEP_REQUIRES_HUMAN_ORIGINATION,
        output={"originate_with": ctx.step.arguments.get(
            "originate_with", "jarvis-operator create-coding-task <slug> <spec.json>")},
        block_reason=("a coding task is human-originated by design; the runtime "
                      "never creates or runs one"),
    )


def _refuse_external_research(ctx: StepContext) -> StepOutcome:
    return StepOutcome(
        status=STEP_BLOCKED_CAPABILITY,
        block_reason=(ctx.step.blocked_by[0] if ctx.step.blocked_by
                      else "external_model_provider is not available"),
    )


EXECUTORS: dict[str, Callable[[StepContext], StepOutcome]] = {
    "internal_data_analysis": _execute_internal,
    "capability_analysis": _execute_capability_analysis,
    "system_status": _execute_internal,
    "evidence_fusion": _execute_fusion,
    "problem_opportunity_analysis": _execute_problem_opportunity,
    "red_team_review": _execute_red_team,
    "action_plan": _prepare_proposal,
    "human_review_proposal": _prepare_proposal,
    "coding_task": _refuse_coding,
    "external_research": _refuse_external_research,
}
EXECUTORS.update({f"{domain.domain_id}_analysis": _execute_domain for domain in DOMAINS})


class ExecutionRuntime:
    def __init__(self, memory: Any, contract: Any | None = None,
                 budget: ResourceBudget | None = None,
                 run_dir: Path | None = None, cache_ttl_s: float = 30.0):
        self.memory = memory
        self.contract = contract
        self.budget = budget or ResourceBudget(max_concurrency=DEFAULT_CONCURRENCY,
                                               timeout_s=60.0)
        self.governor = ResourceGovernor(self.budget)
        self.run_dir = run_dir or RUN_DIR
        self.cache_ttl_s = cache_ttl_s
        self.compiler = ContextCompiler(memory)

    # -- persistence ----------------------------------------------------
    def _path(self, run_id: str) -> Path:
        return self.run_dir / f"{run_id}.json"

    def load(self, run_id: str) -> RunRecord | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _save(self, record: RunRecord) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.run_dir, 0o750)
        path = self._path(record.run_id)
        tmp = path.with_suffix(".tmp")
        # Written whole then renamed: a run killed mid-write leaves the last
        # complete state on disk, which is what resume reads.
        tmp.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
        tmp.replace(path)
        os.chmod(path, 0o640)

    # -- execution ------------------------------------------------------
    def execute(self, plan: ExecutionPlan, originator: str,
                attempt: int = 1, resume: bool = True) -> RunRecord:
        if not (originator or "").strip():
            raise ExecutionDenied(
                "execution requires a named human originator; a plan cannot start itself")
        if not plan.steps:
            raise ExecutionDenied(f"plan {plan.plan_id} has no steps ({plan.status})")

        run_id = run_id_for(plan.plan_id, attempt)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.run_dir, 0o750)
        lock_path = self.run_dir / f"{run_id}.lock"
        with lock_path.open("a+b") as lock_file:
            os.chmod(lock_path, 0o640)
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ExecutionDenied(f"run {run_id} is already active") from exc
            return self._execute_locked(plan, originator, attempt, resume, run_id)

    def _execute_locked(self, plan: ExecutionPlan, originator: str,
                        attempt: int, resume: bool, run_id: str) -> RunRecord:
        existing = self.load(run_id)
        if (existing is not None and resume and existing.finished_at
                and existing.status in (RUN_COMPLETED, RUN_DEGRADED)):
            # Idempotency applies to a run that finished. A FAILED run is not
            # deduplicated -- it is resumed below, re-running only the steps
            # that failed and reusing the ones that already succeeded.
            existing.telemetry = dict(existing.telemetry, deduplicated=True)
            return existing

        record = existing if (existing is not None and resume) else RunRecord(
            run_id=run_id, plan_id=plan.plan_id, request=plan.request,
            originator=originator, status="RUNNING", attempt=attempt,
            started_at=_now(),
        )
        record.status = "RUNNING"
        record.finished_at = None
        office_events.emit("run", status="WORKING", task=plan.request, run_id=run_id)
        for step in plan.steps:
            record.steps.setdefault(step.step_id, StepRecord(
                step_id=step.step_id, capability=step.capability))

        cache = QueryCache(ttl_s=self.cache_ttl_s)
        counters: dict[str, int] = {"model_calls": 0}
        started = perf_counter()
        by_id = {step.step_id: step for step in plan.steps}

        for group in plan.parallel_groups:
            # A step blocked only because its upstream failed is retried too --
            # otherwise resuming a failed run would fix the failure and leave
            # the whole downstream permanently blocked.
            pending = [step_id for step_id in group
                       if record.steps[step_id].status in
                       (STEP_PENDING, STEP_FAILED, STEP_BLOCKED_UPSTREAM)]
            if not pending:
                continue
            for step_id in pending:
                office_events.emit("step", status="WORKING", task=plan.request,
                                   run_id=run_id, capability=by_id[step_id].capability)
            workers = max(1, min(self.budget.max_concurrency, len(pending)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(
                    lambda step_id: self._run_step(plan, by_id[step_id], record,
                                                   cache, counters),
                    pending,
                ))
            for step_record in results:
                record.steps[step_record.step_id] = step_record
                live_status = ("COMPLETED" if step_record.status == STEP_SUCCEEDED else
                               "FAILED" if step_record.status == STEP_FAILED else "WAITING")
                office_events.emit("step", status=live_status, task=plan.request,
                                   run_id=run_id, capability=step_record.capability)
            self._save(record)

        record.total_ms = round((perf_counter() - started) * 1000, 3)
        record.finished_at = _now()
        statuses = {step.status for step in record.steps.values()}
        if statuses & {STEP_FAILED}:
            record.status = RUN_FAILED
        elif statuses & (DEGRADED_STATUSES | {STEP_BLOCKED_UPSTREAM}):
            record.status = RUN_DEGRADED
        else:
            record.status = RUN_COMPLETED
        record.telemetry = self._telemetry(record, counters)
        self._save(record)
        office_events.emit("run", status=record.status, task=plan.request, run_id=run_id)
        return record

    def _run_step(self, plan: ExecutionPlan, step: Any, record: RunRecord,
                  cache: QueryCache, counters: dict[str, int]) -> StepRecord:
        current = record.steps[step.step_id]
        current.inputs = {"depends_on": list(step.depends_on),
                          "arguments": step.arguments}

        blocking = [parent for parent in step.depends_on
                    if record.steps[parent].status in FATAL_UPSTREAM]
        if blocking:
            current.status = STEP_BLOCKED_UPSTREAM
            current.block_reason = "upstream failed: " + ", ".join(blocking)
            return current

        if step.capability_status == DATA_UNAVAILABLE:
            current.status = STEP_DATA_UNAVAILABLE
            current.output = {"domain": step.arguments.get("domain"), "records": 0}
            current.block_reason = step.arguments.get("unavailable_reason") or "no data contract"
            return current
        if step.blocked_by and step.capability not in ("action_plan", "human_review_proposal"):
            current.status = STEP_BLOCKED_CAPABILITY
            current.block_reason = "blocked capability: " + ", ".join(step.blocked_by)
            return current

        executor = EXECUTORS.get(step.capability)
        if executor is None:
            current.status = STEP_FAILED
            current.error = f"no executor registered for capability {step.capability}"
            return current

        queued = perf_counter()
        try:
            with self.governor.slot():
                current.queue_wait_ms = round((perf_counter() - queued) * 1000, 3)
                started = perf_counter()
                ctx = StepContext(
                    plan=plan, step=step, memory=self.memory, compiler=self.compiler,
                    cache=cache, contract=self.contract,
                    upstream={parent: record.steps[parent] for parent in step.depends_on},
                    counters=counters, all_steps=dict(record.steps),
                )
                outcome = executor(ctx)
                current.duration_ms = round((perf_counter() - started) * 1000, 3)
        except TimeoutError as exc:
            current.status = STEP_FAILED
            current.error = f"resource backpressure: {exc}"
            current.queue_wait_ms = round((perf_counter() - queued) * 1000, 3)
            return current
        except ExecutionDenied as exc:
            current.status = STEP_FAILED
            current.error = str(exc)
            return current
        except Exception as exc:  # noqa: BLE001 - one bad step must not kill the run
            current.status = STEP_FAILED
            current.error = f"{type(exc).__name__}: {exc}"
            return current

        current.status = outcome.status
        current.output = outcome.output
        current.evidence_refs = outcome.evidence_refs
        current.error = outcome.error
        current.block_reason = outcome.block_reason
        current.cache_hits = outcome.cache_hits
        current.model_calls = 0
        current.acceptance = evaluate_acceptance(step.capability, current.status,
                                                 current.output, current.evidence_refs)
        if current.acceptance["status"] == "FAILED":
            failed = [item["criterion"] for item in current.acceptance["checks"]
                      if not item["passed"]]
            current.status = STEP_DATA_UNAVAILABLE if failed == ["source_traceable"] else STEP_FAILED
            current.block_reason = "acceptance failed: " + ", ".join(failed)
        return current

    @staticmethod
    def _telemetry(record: RunRecord, counters: dict[str, int]) -> dict[str, Any]:
        steps = list(record.steps.values())
        return {
            "steps": len(steps),
            "succeeded": sum(1 for step in steps if step.status == STEP_SUCCEEDED),
            "proposed": sum(1 for step in steps if step.status == STEP_PROPOSED),
            "data_unavailable": sum(1 for step in steps if step.status == STEP_DATA_UNAVAILABLE),
            "blocked": sum(1 for step in steps if step.status in
                           (STEP_BLOCKED_CAPABILITY, STEP_BLOCKED_UPSTREAM,
                            STEP_REQUIRES_HUMAN_ORIGINATION)),
            "failed": sum(1 for step in steps if step.status == STEP_FAILED),
            "queue_wait_ms_total": round(sum(step.queue_wait_ms for step in steps), 3),
            "step_duration_ms_total": round(sum(step.duration_ms for step in steps), 3),
            "total_ms": record.total_ms,
            "cache_hits": sum(step.cache_hits for step in steps),
            "model_calls": counters.get("model_calls", 0),
            "external_provider_calls": 0,
            "external_actions": 0,
            "capabilities_used": sorted({step.capability for step in steps}),
            "failure_reasons": [
                {"step_id": step.step_id, "reason": step.error or step.block_reason}
                for step in steps if step.error or step.block_reason
            ],
        }
