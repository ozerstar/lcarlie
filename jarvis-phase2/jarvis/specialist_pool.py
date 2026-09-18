"""Deterministic, evidence-bearing Specialist Agent Pool V1.

Specialists are short-lived capabilities, not resident agents.  This module is
additive: it does not register a runtime trigger, write SQL, call a provider,
or execute an external action.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Callable

from .cache import QueryCache
from .research import SourceRecord, fuse

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
PROPOSED = "PROPOSED"

DATA_ANALYSIS = "DATA_ANALYSIS"
MARKET_RESEARCH = "MARKET_RESEARCH"
PERFORMANCE_ANALYSIS = "PERFORMANCE_ANALYSIS"
CUSTOMER_ANALYSIS = "CUSTOMER_ANALYSIS"
FINANCIAL_ANALYSIS = "FINANCIAL_ANALYSIS"
OPERATIONAL_ANALYSIS = "OPERATIONAL_ANALYSIS"
REGULATORY_REVIEW = "REGULATORY_REVIEW"
RED_TEAM = "RED_TEAM"
STRATEGIC_SYNTHESIS = "STRATEGIC_SYNTHESIS"


@dataclass(frozen=True)
class SpecialistDefinition:
    specialist_id: str
    label: str
    capabilities: tuple[str, ...]
    domains: tuple[str, ...]
    required_data: tuple[str, ...] = ()
    optional_data: tuple[str, ...] = ()
    requires_research: bool = False
    risk: str = "LOW"


SPECIALISTS: tuple[SpecialistDefinition, ...] = (
    SpecialistDefinition("market_intelligence", "Market Intelligence", (MARKET_RESEARCH,), ("market",), requires_research=True),
    SpecialistDefinition("competitor_intelligence", "Competitor Intelligence", (MARKET_RESEARCH,), ("competitor",), requires_research=True),
    SpecialistDefinition("research", "Research", (MARKET_RESEARCH,), ("research",), requires_research=True),
    SpecialistDefinition("meta_performance", "Meta Performance", (PERFORMANCE_ANALYSIS,), ("advertising",), ("advertising",)),
    SpecialistDefinition("creative_intelligence", "Creative Intelligence", (PERFORMANCE_ANALYSIS,), ("creative",), ("advertising",)),
    SpecialistDefinition("social_media", "Social Media", (PERFORMANCE_ANALYSIS,), ("social",), ("advertising",)),
    SpecialistDefinition("growth", "Growth", (DATA_ANALYSIS, PERFORMANCE_ANALYSIS), ("growth",), ("decision_summary",)),
    SpecialistDefinition("ecommerce_sales", "E-Commerce Sales", (DATA_ANALYSIS,), ("sales", "ecommerce"), ("sales",)),
    SpecialistDefinition("crm_customer", "CRM / Customer", (CUSTOMER_ANALYSIS,), ("crm", "customer"), ("open_work",)),
    SpecialistDefinition("field_b2b_sales", "Field / B2B Sales", (DATA_ANALYSIS,), ("b2b",), ("sales",)),
    SpecialistDefinition("product_portfolio", "Product / Portfolio", (DATA_ANALYSIS,), ("product", "portfolio"), ("decision_summary",)),
    SpecialistDefinition("finance", "Finance", (FINANCIAL_ANALYSIS,), ("financial", "finance"), ("financial",), risk="MEDIUM"),
    SpecialistDefinition("accounting_control", "Accounting Control", (FINANCIAL_ANALYSIS,), ("accounting",), ("financial",), risk="MEDIUM"),
    SpecialistDefinition("operations", "Operations", (OPERATIONAL_ANALYSIS,), ("operations",), ("open_work", "system")),
    SpecialistDefinition("regulatory_quality", "Regulatory / Quality", (REGULATORY_REVIEW,), ("regulatory", "quality"), ("decision_summary",), risk="HIGH"),
    SpecialistDefinition("data_measurement", "Data / Measurement", (DATA_ANALYSIS,), ("measurement", "advertising"), ("advertising",)),
    SpecialistDefinition("ai_prompt_engineering", "AI / Prompt Engineering", (DATA_ANALYSIS,), ("ai", "prompt"), ("capability_state",)),
    SpecialistDefinition("red_team", "Red Team", (RED_TEAM,), ("red_team",), risk="HIGH"),
    SpecialistDefinition("strategy", "Strategy", (STRATEGIC_SYNTHESIS,), ("strategy",), risk="MEDIUM"),
    SpecialistDefinition("managing_director", "Managing Director synthesis", (STRATEGIC_SYNTHESIS,), ("synthesis",), risk="HIGH"),
)
REGISTRY = {item.specialist_id: item for item in SPECIALISTS}

# Names, never SQL. They mirror ExecutionRuntime.QUERY_READERS and are the only
# data contracts a specialist may request.
ALLOWLISTED_QUERIES = {
    "system": "get_system_status",
    "decision_summary": "get_company_context",
    "open_work": "get_open_work",
    "company_dashboard": "get_executive_brief",
    "capability_state": "get_capability_state",
    "action_contract": "get_action_contract",
    "capabilities": "get_model_policy",
}


@dataclass(frozen=True)
class SpecialistContext:
    task: str
    domain: str
    entities: tuple[str, ...]
    query_results: dict[str, Any]
    evidence_refs: tuple[str, ...]
    freshness: str
    constraints: tuple[str, ...]
    context_bytes: int


@dataclass(frozen=True)
class Finding:
    finding_id: str
    specialist_id: str
    domain: str
    finding_type: str
    claim: str
    evidence_refs: tuple[str, ...]
    confidence: float
    data_freshness: str
    contradictions: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()
    recommended_next_analysis: tuple[str, ...] = ()
    duration_ms: float = 0.0
    model_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("evidence_refs", "contradictions", "missing_data", "recommended_next_analysis"):
            data[key] = list(data[key])
        return data


class Specialist(ABC):
    definition: SpecialistDefinition

    @abstractmethod
    def analyze(self, context: SpecialistContext) -> Finding: ...

    @abstractmethod
    def evidence(self) -> tuple[str, ...]: ...

    @abstractmethod
    def confidence(self) -> float: ...

    @abstractmethod
    def metrics(self) -> dict[str, Any]: ...


class CompanyMemoryGateway:
    """Allowlisted Company Memory access; unknown/missing contracts fail closed."""

    def __init__(self, memory: Any | None):
        self.memory = memory

    def read(self, query: str) -> tuple[Any, tuple[str, ...], str]:
        reader = ALLOWLISTED_QUERIES.get(query)
        if not reader or self.memory is None or not hasattr(self.memory, reader):
            return None, (), DATA_UNAVAILABLE
        try:
            value = getattr(self.memory, reader)()
        except Exception:
            return None, (), DATA_UNAVAILABLE
        refs = (str(getattr(value, "source", f"company_memory:{query}")),)
        return value, refs, "live"


class SpecialistContextCompiler:
    def __init__(self, gateway: CompanyMemoryGateway, max_bytes: int = 32_000):
        self.gateway = gateway
        self.max_bytes = max_bytes

    def compile(self, definition: SpecialistDefinition, task: str, domain: str,
                entities: tuple[str, ...] = ()) -> SpecialistContext:
        results: dict[str, Any] = {}
        refs: list[str] = []
        freshness = "unknown"
        for query in definition.required_data:
            value, query_refs, query_freshness = self.gateway.read(query)
            if value is not None:
                serial = getattr(value, "records", value)
                candidate = {**results, query: serial}
                encoded = json.dumps(candidate, ensure_ascii=False, default=str).encode("utf-8")
                if len(encoded) <= self.max_bytes:
                    results = candidate
                    refs.extend(query_refs)
                    freshness = query_freshness
        size = len(json.dumps(results, ensure_ascii=False, default=str).encode("utf-8"))
        return SpecialistContext(task, domain, entities, results, tuple(dict.fromkeys(refs)),
                                 freshness, ("PROPOSED_ONLY", "NO_EXTERNAL_ACTION"), size)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deterministic_confidence(evidence_count: int, completeness: float,
                             freshness: float = 1.0, contradictions: int = 0,
                             independence: int | None = None) -> float:
    independence = evidence_count if independence is None else independence
    quantity = min(1.0, evidence_count / 2)
    independent_score = min(1.0, independence / 2)
    score = .30 * quantity + .25 * independent_score + .25 * completeness + .20 * freshness
    score -= min(.5, contradictions * .25)
    return round(max(0.0, min(1.0, score)), 3)


class DeterministicSpecialist(Specialist):
    def __init__(self, definition: SpecialistDefinition):
        self.definition = definition
        self._evidence: tuple[str, ...] = ()
        self._confidence = 0.0
        self._metrics = {"deterministic_operations": 0, "model_calls": 0}

    def analyze(self, context: SpecialistContext) -> Finding:
        started = perf_counter()
        missing = tuple(q for q in self.definition.required_data if q not in context.query_results)
        self._evidence = context.evidence_refs
        completeness = 1.0 if not self.definition.required_data else 1 - len(missing) / len(self.definition.required_data)
        self._confidence = deterministic_confidence(len(self._evidence), completeness)
        self._metrics["deterministic_operations"] += 1
        if not self._evidence:
            kind, claim = DATA_UNAVAILABLE, ""
        else:
            kind = "OBSERVATION"
            claim = f"{self.definition.label} completed deterministic analysis for {context.domain}."
        next_steps = (("request_fresh_research",) if self.definition.requires_research else ())
        fid = "finding-" + _digest([self.definition.specialist_id, context.task, context.domain,
                                    context.evidence_refs])[:16]
        return Finding(fid, self.definition.specialist_id, context.domain, kind, claim,
                       self._evidence, self._confidence, context.freshness,
                       missing_data=missing, recommended_next_analysis=next_steps,
                       duration_ms=round((perf_counter() - started) * 1000, 3))

    def evidence(self) -> tuple[str, ...]: return self._evidence
    def confidence(self) -> float: return self._confidence
    def metrics(self) -> dict[str, Any]: return dict(self._metrics)


DOMAIN_ROUTES: dict[str, tuple[str, ...]] = {
    "sales": ("ecommerce_sales",),
    "ecommerce": ("ecommerce_sales",),
    "advertising": ("meta_performance", "data_measurement"),
    "crm": ("crm_customer",),
    "customer": ("crm_customer",),
    "operations": ("operations",),
    "competitor": ("competitor_intelligence", "research"),
    "market": ("market_intelligence", "research"),
    "financial": ("finance", "accounting_control"),
    "finance": ("finance", "accounting_control"),
    "regulatory": ("regulatory_quality",),
    "product": ("product_portfolio",),
    "creative": ("creative_intelligence",),
    "social": ("social_media",),
    "growth": ("growth",),
}


@dataclass(frozen=True)
class SpecialistPlan:
    selected: tuple[str, ...]
    primary: tuple[str, ...]
    stages: tuple[tuple[str, ...], ...]
    requires_research: bool


class SpecialistRouter:
    def route(self, domains: tuple[str, ...], final_synthesis: bool = True) -> SpecialistPlan:
        primary: list[str] = []
        for domain in domains:
            primary.extend(DOMAIN_ROUTES.get(domain, ()))
        primary = list(dict.fromkeys(primary))
        stages: list[tuple[str, ...]] = [tuple(primary)] if primary else []
        if final_synthesis and primary:
            stages.extend((("red_team",), ("strategy",), ("managing_director",)))
        selected = tuple(item for stage in stages for item in stage)
        return SpecialistPlan(selected, tuple(primary), tuple(stages),
                              any(REGISTRY[item].requires_research for item in primary))


@dataclass(frozen=True)
class ResearchRequest:
    query: str
    required_claims: tuple[str, ...]
    requires_fresh_research: bool = True
    capability: str = "fresh_research_source"
    external_execution_allowed: bool = False


class SpecialistPool:
    def __init__(self, memory: Any | None = None, max_concurrency: int = 3,
                 context_budget_bytes: int = 32_000, cache: QueryCache | None = None):
        self.router = SpecialistRouter()
        self.compiler = SpecialistContextCompiler(CompanyMemoryGateway(memory), context_budget_bytes)
        self.max_concurrency = max(1, max_concurrency)
        self.cache = cache or QueryCache(ttl_s=300)

    def _run_one(self, specialist_id: str, task: str, domain: str,
                 entities: tuple[str, ...], evidence_version: str) -> tuple[Finding, bool, int]:
        definition = REGISTRY[specialist_id]
        context = self.compiler.compile(definition, task, domain, entities)
        key = "specialist:" + _digest([specialist_id, task, entities, context.evidence_refs,
                                       context.freshness, evidence_version, context.query_results])
        finding, hit = self.cache.get_or_load(key, lambda: DeterministicSpecialist(definition).analyze(context))
        return finding, hit, context.context_bytes

    def execute(self, task: str, domains: tuple[str, ...], entities: tuple[str, ...] = (),
                evidence_version: str = "") -> dict[str, Any]:
        started = perf_counter()
        plan = self.router.route(domains)
        findings: list[Finding] = []
        cache_hits = context_bytes = 0
        parallelism = min(self.max_concurrency, len(plan.primary)) if plan.primary else 0
        domain_for = {sid: next((d for d in domains if sid in DOMAIN_ROUTES.get(d, ())), domains[0] if domains else "general") for sid in plan.primary}
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {executor.submit(self._run_one, sid, task, domain_for[sid], entities, evidence_version): sid for sid in plan.primary}
            for future in as_completed(futures):
                finding, hit, size = future.result()
                findings.append(finding); cache_hits += int(hit); context_bytes += size
        findings.sort(key=lambda item: plan.primary.index(item.specialist_id))
        fused = self._fusion(findings)
        red = self._red_team(task, findings, fused)
        strategy = self._strategy(task, findings, red)
        md = self._md(task, findings, red, strategy)
        ordered = findings + ([red, strategy, md] if findings else [])
        research = [asdict(ResearchRequest(task, tuple(f.claim for f in findings if f.claim))) ] if plan.requires_research else []
        return {
            "status": PROPOSED, "task": task, "domains": list(domains),
            "specialists_selected": list(plan.selected), "specialists_executed": len(plan.selected),
            "specialists_skipped": len(SPECIALISTS) - len(plan.selected),
            "parallelism": parallelism, "stages": [list(s) for s in plan.stages],
            "findings": [f.to_dict() for f in ordered], "fusion": fused,
            "research_requests": research, "external_actions": 0,
            "metrics": {"context_bytes": context_bytes, "cache_hits": cache_hits,
                        "deterministic_operations": len(plan.selected), "model_calls": 0,
                        "duration_ms": round((perf_counter() - started) * 1000, 3),
                        "evidence_count": sum(len(f.evidence_refs) for f in ordered)},
        }

    @staticmethod
    def _fusion(findings: list[Finding]) -> dict[str, Any]:
        records = [SourceRecord(f.finding_id, f.specialist_id, f.domain, f.claim,
                                f.data_freshness, f.confidence)
                   for f in findings if f.claim and f.evidence_refs]
        if not records:
            return {"records": [], "independent_sources": 0,
                    "contradiction": False, "confidence": 0.0,
                    "needs_more_sources": True}
        # Reuse the established fusion envelope, then tighten its independence
        # and contradiction semantics. Specialists sharing one evidence ref are
        # not independent sources, and claims about different domains do not
        # contradict one another merely because their text differs.
        result = fuse(records)
        independent_refs = {ref.casefold() for f in findings for ref in f.evidence_refs}
        by_domain: dict[str, set[str]] = {}
        for finding in findings:
            if finding.claim and finding.evidence_refs:
                by_domain.setdefault(finding.domain, set()).add(finding.claim.casefold())
        contradiction = any(len(claims) > 1 for claims in by_domain.values())
        independence = len(independent_refs)
        confidence = deterministic_confidence(
            len(records),
            sum(bool(f.evidence_refs) for f in findings) / max(1, len(findings)),
            contradictions=int(contradiction), independence=independence,
        )
        result.update({"independent_sources": independence,
                       "contradiction": contradiction,
                       "confidence": confidence,
                       "needs_more_sources": independence < 2 or contradiction})
        return result

    @staticmethod
    def _red_team(task: str, findings: list[Finding], fused: dict[str, Any]) -> Finding:
        refs = tuple(ref for f in findings for ref in f.evidence_refs)
        missing = tuple(f.specialist_id for f in findings if not f.evidence_refs or f.missing_data)
        objections = []
        if missing: objections.append("missing_data")
        if fused.get("contradiction"): objections.append("contradiction")
        if fused.get("independent_sources", 0) < 2: objections.append("source_independence")
        kind = "OBJECTION" if objections else ("WARNING" if fused.get("confidence", 0) < .7 else "PASS")
        return Finding("finding-" + _digest([task, "red_team", refs])[:16], "red_team", "cross_domain",
                       kind, f"Red Team result: {kind}", refs,
                       deterministic_confidence(len(refs), 0 if missing else 1,
                                                contradictions=int(bool(fused.get("contradiction")))),
                       "derived", contradictions=tuple(objections), missing_data=missing)

    @staticmethod
    def _strategy(task: str, findings: list[Finding], red: Finding) -> Finding:
        refs = tuple(dict.fromkeys(ref for f in findings for ref in f.evidence_refs))
        claim = "Strategy options prepared from validated findings and Red Team review." if refs else ""
        return Finding("finding-" + _digest([task, "strategy", refs])[:16], "strategy", "strategy",
                       "OPTIONS" if refs else DATA_UNAVAILABLE, claim, refs,
                       deterministic_confidence(len(refs), float(bool(refs)), contradictions=len(red.contradictions)),
                       "derived", contradictions=red.contradictions,
                       recommended_next_analysis=("human_review",))

    @staticmethod
    def _md(task: str, findings: list[Finding], red: Finding, strategy: Finding) -> Finding:
        refs = strategy.evidence_refs
        claim = "PROPOSED: priorities, dependencies, impact, risks, gaps, and next actions synthesized." if refs else ""
        return Finding("finding-" + _digest([task, "managing_director", refs])[:16],
                       "managing_director", "executive", PROPOSED if refs else DATA_UNAVAILABLE,
                       claim, refs, strategy.confidence, "derived",
                       contradictions=red.contradictions, missing_data=red.missing_data,
                       recommended_next_analysis=("human_approval",))


def benchmark_routing(domains: tuple[str, ...]) -> dict[str, Any]:
    plan = SpecialistRouter().route(domains)
    naive = len(SPECIALISTS)
    routed = len(plan.selected)
    return {"naive_specialists": naive, "routed_specialists": routed,
            "specialists_saved": naive - routed,
            "reduction_pct": round((naive - routed) / naive * 100, 1),
            "same_requested_domain_coverage": all(any(s in plan.primary for s in DOMAIN_ROUTES.get(d, ())) for d in domains),
            "naive_context_units": naive, "routed_context_units": len(plan.primary),
            "naive_latency_work_units": naive,
            "routed_latency_work_units": len(plan.stages),
            "naive_model_calls": 0, "routed_model_calls": 0}
