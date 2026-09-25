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
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from .cache import QueryCache
from .memory import CompanyMemory
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
    SpecialistDefinition("meta_performance", "Meta Performance", (PERFORMANCE_ANALYSIS,), ("advertising",), ("advertising_performance", "advertising_spend"), ("ga4_site_traffic",)),
    SpecialistDefinition("creative_intelligence", "Creative Intelligence", (PERFORMANCE_ANALYSIS,), ("creative",), ("advertising_performance",)),
    SpecialistDefinition("social_media", "Social Media", (PERFORMANCE_ANALYSIS,), ("social",), ("advertising_performance",)),
    SpecialistDefinition("growth", "Growth", (DATA_ANALYSIS, PERFORMANCE_ANALYSIS), ("growth",), ("decision_summary",)),
    SpecialistDefinition("ecommerce_sales", "E-Commerce Sales", (DATA_ANALYSIS,), ("sales",), ("sales_orders", "sales_items"), ("gunluk_marj",)),
    SpecialistDefinition("crm_customer", "CRM / Customer", (CUSTOMER_ANALYSIS,), ("crm", "customer"), ("crm_customers", "crm_unanswered", "open_work")),
    SpecialistDefinition("field_b2b_sales", "Field / B2B Sales", (DATA_ANALYSIS,), ("b2b",), ("sales_orders", "sales_items")),
    SpecialistDefinition("product_portfolio", "Product / Portfolio", (DATA_ANALYSIS,), ("ecommerce", "product", "portfolio"), ("ecommerce_profitability", "ecommerce_price", "ecommerce_funnel"), ("ga4_site_traffic", "real_inventory", "gunluk_marj")),
    SpecialistDefinition("finance", "Finance", (FINANCIAL_ANALYSIS,), ("financial", "finance"), ("financial",), risk="MEDIUM"),
    SpecialistDefinition("accounting_control", "Accounting Control", (FINANCIAL_ANALYSIS,), ("accounting",), ("financial",), risk="MEDIUM"),
    SpecialistDefinition("operations", "Operations", (OPERATIONAL_ANALYSIS,), ("operations",), ("operations_shipments", "open_work", "system"), ("real_inventory",)),
    SpecialistDefinition("regulatory_quality", "Regulatory / Quality", (REGULATORY_REVIEW,), ("regulatory", "quality"), ("decision_summary",), risk="HIGH"),
    SpecialistDefinition("data_measurement", "Data / Measurement", (DATA_ANALYSIS,), ("measurement",), ("advertising_performance", "advertising_spend"), ("ga4_site_traffic",)),
    SpecialistDefinition("ai_prompt_engineering", "AI / Prompt Engineering", (DATA_ANALYSIS,), ("ai", "prompt"), ("capability_state",)),
    SpecialistDefinition("red_team", "Red Team", (RED_TEAM,), ("red_team",), risk="HIGH"),
    SpecialistDefinition("strategy", "Strategy", (STRATEGIC_SYNTHESIS,), ("strategy",), risk="MEDIUM"),
    SpecialistDefinition("managing_director", "Managing Director synthesis", (STRATEGIC_SYNTHESIS,), ("synthesis",), risk="HIGH"),
)
REGISTRY = {item.specialist_id: item for item in SPECIALISTS}

# One source of truth: exactly the allowlist used by Company Memory and the
# current Execution Runtime. No second SQL or query-name registry is created.
ALLOWLISTED_QUERIES = frozenset(CompanyMemory.QUERIES)


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
        if query not in ALLOWLISTED_QUERIES or self.memory is None:
            return None, (), DATA_UNAVAILABLE
        try:
            value = self.memory._fetch(query)
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
        constraints = ["PROPOSED_ONLY", "NO_EXTERNAL_ACTION"]
        per_query_budget = max(2, (self.max_bytes - 512) // max(1, len(definition.required_data)))
        for query in definition.required_data:
            value, query_refs, query_freshness = self.gateway.read(query)
            if value is not None:
                serial = getattr(value, "records", value)
                bounded = serial
                if isinstance(serial, list):
                    bounded = []
                    for row in serial:
                        candidate = [*bounded, row]
                        if len(json.dumps(candidate, ensure_ascii=False, default=str).encode("utf-8")) > per_query_budget:
                            constraints.append(f"TRUNCATED:{query}:{len(serial)}")
                            break
                        bounded = candidate
                results[query] = bounded
                refs.extend(query_refs)
                freshness = query_freshness
        size = len(json.dumps(results, ensure_ascii=False, default=str).encode("utf-8"))
        if size > self.max_bytes:
            results, refs = {}, []
            constraints.append("CONTEXT_BUDGET_EXHAUSTED")
            size = 2
        return SpecialistContext(task, domain, entities, results, tuple(dict.fromkeys(refs)),
                                 freshness, tuple(constraints), size)


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


def _rows(context: SpecialistContext, query: str) -> list[dict[str, Any]]:
    value = context.query_results.get(query) or []
    return value if isinstance(value, list) else []


def _domain_claim(context: SpecialistContext) -> str:
    """Deterministic facts only; every number comes from the supplied rows."""
    if context.domain == "sales":
        orders, items = _rows(context, "sales_orders"), _rows(context, "sales_items")
        measured = [row for row in orders if row.get("olcumde")]
        revenue = sum(float(row.get("ciro_dogrulanmis_net") or row.get("ciro_beyan_edilmis_net") or 0)
                      for row in measured)
        return (f"Sales bounded context: {len(orders)} orders and {len(items)} line items; "
                f"{len(measured)} measured orders represent a {revenue:.2f} net-revenue subtotal.")
    if context.domain == "ecommerce":
        products = _rows(context, "ecommerce_profitability")
        prices = _rows(context, "ecommerce_price")
        funnels = _rows(context, "ecommerce_funnel")
        revenue = sum(float(row.get("ciro_net") or 0) for row in products)
        unknown_cost = sum(1 for row in products if float(row.get("kapsama_yuzde") or 0) < 100)
        return (f"E-commerce bounded context: {len(products)} product profitability rows, {len(prices)} price rows "
                f"and {len(funnels)} funnel transitions; net revenue is {revenue:.2f}, "
                f"with {unknown_cost} product rows below full cost coverage.")
    if context.domain == "advertising":
        performance = _rows(context, "advertising_performance")
        latest = [row for row in performance if row.get("pencere") == 30]
        spend = sum(float(row.get("harcama") or 0) for row in latest)
        unconfirmed = sum(1 for row in latest if row.get("commercial_confirmation") != "CONFIRMED")
        return (f"Advertising bounded context: {len(latest)} 30-day ad rows with a {spend:.2f} spend subtotal; "
                f"{unconfirmed} rows lack commercial confirmation.")
    if context.domain == "crm":
        customers = _rows(context, "crm_customers")
        unanswered = _rows(context, "crm_unanswered")
        longest = max((float(row.get("bekleme_saat") or 0) for row in unanswered), default=0)
        return (f"CRM bounded context: {len(customers)} customer records and {len(unanswered)} unanswered "
                f"conversations; longest wait is {longest:.1f} hours.")
    if context.domain == "operations":
        shipments = _rows(context, "operations_shipments")
        alarms = sum(1 for row in shipments if row.get("alarm"))
        open_work = _rows(context, "open_work")
        return (f"Operations bounded context: {len(shipments)} shipment records, {alarms} shipment alarms "
                f"and {len(open_work)} open-work records.")
    count = sum(len(value) for value in context.query_results.values() if isinstance(value, list))
    return f"{context.domain}: deterministic analysis covered {count} allowlisted records."


class DeterministicSpecialist(Specialist):
    def __init__(self, definition: SpecialistDefinition):
        self.definition = definition
        self._evidence: tuple[str, ...] = ()
        self._confidence = 0.0
        self._metrics = {"deterministic_operations": 0, "model_calls": 0}

    def analyze(self, context: SpecialistContext) -> Finding:
        started = perf_counter()
        missing = tuple(q for q in (*self.definition.required_data, *self.definition.optional_data)
                        if q not in context.query_results)
        self._evidence = context.evidence_refs
        completeness = 1.0 if not self.definition.required_data else 1 - len(missing) / len(self.definition.required_data)
        self._confidence = deterministic_confidence(len(self._evidence), completeness)
        self._metrics["deterministic_operations"] += 1
        if not self._evidence:
            kind, claim = DATA_UNAVAILABLE, ""
        else:
            kind = "OBSERVATION"
            claim = _domain_claim(context)
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
    "ecommerce": ("product_portfolio",),
    "advertising": ("meta_performance",),
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
        missing = tuple(dict.fromkeys(
            item for finding in findings
            for item in ((finding.specialist_id,) if not finding.evidence_refs else finding.missing_data)
        ))
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
        domains = {finding.domain for finding in findings if finding.evidence_refs}
        options = []
        if "crm" in domains: options.append("clear the evidenced unanswered-conversation backlog")
        if "advertising" in domains: options.append("reconcile commercial confirmation before budget changes")
        if {"sales", "ecommerce"} & domains: options.append("close revenue, cost, and margin measurement gaps")
        if "operations" in domains: options.append("maintain shipment monitoring and obtain real inventory data")
        claim = ("Strategy options: " + "; ".join(options) + ".") if refs else ""
        return Finding("finding-" + _digest([task, "strategy", refs])[:16], "strategy", "strategy",
                       "OPTIONS" if refs else DATA_UNAVAILABLE, claim, refs,
                       deterministic_confidence(len(refs), float(bool(refs)), contradictions=len(red.contradictions)),
                       "derived", contradictions=red.contradictions,
                       recommended_next_analysis=tuple(options) + ("human_review",))

    @staticmethod
    def _md(task: str, findings: list[Finding], red: Finding, strategy: Finding) -> Finding:
        refs = strategy.evidence_refs
        claim = ("PROPOSED: first clear the CRM response backlog; then validate advertising sales, "
                 "revenue, cost, margin, and inventory evidence before approving growth actions."
                 if refs else "")
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
