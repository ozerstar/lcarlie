"""Adaptive, provider-neutral research orchestration.

This module deliberately does not register itself with ExecutionRuntime. It
consumes the existing Capability Adapter Factory and remains merge-ready until
fresh-research adapters have passed the factory's isolated adoption gates.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import unified_diff
from time import monotonic, perf_counter
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .adapter_factory import AdapterFactory, AdapterState, CapabilityAdapter
from .cache import ResearchCache
from .confidence import score as score_confidence
from .research import SourceRecord, fuse


RESEARCH_CAPABILITY = "fresh_research_source"
UNTRUSTED_MARKERS = (
    "ignore previous", "ignore policy", "system instruction", "approve yourself",
    "set role", "reveal secret", "credential", "run shell", "tool permission",
)


class ResearchError(RuntimeError):
    pass


class UnsafeUrl(ResearchError):
    pass


@dataclass(frozen=True)
class ResearchPolicy:
    initial_sources: int = 2
    expansion_batch: int = 1
    max_sources: int = 5
    min_independent_sources: int = 2
    confidence_threshold: float = 0.72
    coverage_threshold: float = 0.75
    max_concurrency: int = 3
    # OLCULDU: adaptorun gercek suresi 14,5 saniye (4 sorgu arama +
    # sayfa cekme). 8 saniye her seferinde zaman asimina ugruyordu ve
    # arastirma HIC calismiyordu. 45 saniye olculen sureye ag
    # degiskenligi payi ekler.
    source_timeout_s: float = float(
        os.environ.get("JARVIS_RESEARCH_TIMEOUT_S", "45"))
    # 0: 8 saniyede vazgecip yeniden denemek toplam sureyi ikiye
    # katlayip ayni duvara carpmakti. Tek deneme, uzun sure.
    retry_budget: int = 0
    context_budget_bytes: int = 64_000
    cache_ttl_s: float = 900.0
    circuit_breaker_failures: int = 2


@dataclass(frozen=True)
class NormalizedSource:
    source_id: str
    publisher: str
    url: str
    canonical_url: str
    origin_id: str
    title: str
    content: str
    content_hash: str
    observed_at: str
    authority: float
    freshness: float
    claims: dict[str, str]
    evidence_ref: str
    injection_detected: bool = False
    # Reliability metadata from the adapter. Kept on the record so a reader can
    # see that a claim came from a company's own page rather than an
    # independent one, and so snippets stay attached to their source.
    source_type: str = "UNKNOWN"
    evidence_snippets: tuple[str, ...] = ()
    relevance: float = 0.0


@dataclass(frozen=True)
class DiffResult:
    changed: bool
    old_hash: str | None
    new_hash: str
    changed_sections: tuple[str, ...]
    diff: str


@dataclass
class CircuitState:
    failures: int = 0
    open: bool = False


@dataclass
class ResearchTelemetry:
    # Zaman asimi AYRI sayilir: "kaynak yok" ile karistirilirsa
    # kullanici "internette yok" sanip konuyu kapatir.
    timeouts: int = 0
    duration_ms: float = 0.0
    fetch_ms: float = 0.0
    cache_hit: bool = False
    fetched_sources: int = 0
    failed_sources: int = 0
    expansion_rounds: int = 0
    retries: int = 0
    model_calls: int = 0
    cost: float = 0.0


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_url(url: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrl("only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrl("URL credentials are forbidden")
    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeUrl("local hostnames are forbidden")
    try:
        addresses = {entry[4][0] for entry in resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise UnsafeUrl("hostname could not be resolved safely") from exc
    if not addresses:
        raise UnsafeUrl("hostname resolved to no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise UnsafeUrl("local, private, reserved, or link-local targets are forbidden")
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", parsed.query, ""))


def normalize_source(raw: dict[str, Any], resolver: Callable[..., Any] = socket.getaddrinfo,
                     context_budget_bytes: int = 64_000) -> NormalizedSource:
    url = str(raw.get("url") or "")
    canonical = canonicalize_url(url, resolver)
    content = str(raw.get("content") or "")
    encoded = content.encode("utf-8")[:context_budget_bytes]
    content = encoded.decode("utf-8", errors="ignore")
    claims = raw.get("claims") if isinstance(raw.get("claims"), dict) else {}
    clean_claims = {str(key): str(value) for key, value in claims.items()}
    digest = _hash(content)
    publisher = str(raw.get("publisher") or urlsplit(canonical).hostname)
    origin_id = str(raw.get("origin_id") or raw.get("canonical_origin") or digest)
    marker_text = (content + " " + json.dumps(clean_claims, ensure_ascii=False)).casefold()
    return NormalizedSource(
        source_id=str(raw.get("source_id") or digest[:16]), publisher=publisher,
        url=url, canonical_url=canonical, origin_id=origin_id,
        title=str(raw.get("title") or ""), content=content, content_hash=digest,
        observed_at=str(raw.get("observed_at") or datetime.now(timezone.utc).isoformat()),
        authority=max(0.0, min(1.0, float(raw.get("authority", 0.5)))),
        freshness=max(0.0, min(1.0, float(raw.get("freshness", 0.5)))),
        claims=clean_claims, evidence_ref=str(raw.get("evidence_ref") or f"web:{digest[:16]}"),
        injection_detected=any(marker in marker_text for marker in UNTRUSTED_MARKERS),
        source_type=str(raw.get("source_type") or "UNKNOWN"),
        evidence_snippets=tuple(str(item) for item in (raw.get("evidence_snippets") or ())),
        relevance=max(0.0, min(1.0, float(raw.get("relevance", 0.0)))),
    )


def diff_content(previous: str | None, current: str) -> DiffResult:
    new_hash = _hash(current)
    if previous is None:
        return DiffResult(True, None, new_hash, tuple(current.splitlines()), current)
    old_hash = _hash(previous)
    if old_hash == new_hash:
        return DiffResult(False, old_hash, new_hash, (), "")
    delta = list(unified_diff(previous.splitlines(), current.splitlines(), lineterm=""))
    changed = tuple(line[1:] for line in delta if line.startswith("+") and not line.startswith("+++"))
    return DiffResult(True, old_hash, new_hash, changed, "\n".join(delta))


class ResearchController:
    def __init__(self, factory: AdapterFactory, policy: ResearchPolicy | None = None,
                 cache: ResearchCache | None = None,
                 resolver: Callable[..., Any] = socket.getaddrinfo):
        self.factory = factory
        self.policy = policy or ResearchPolicy()
        self.cache = cache or ResearchCache(ttl_s=self.policy.cache_ttl_s)
        self.resolver = resolver
        self._circuits: dict[str, CircuitState] = {}

    def available_adapters(self) -> list[CapabilityAdapter]:
        adapters = []
        for adapter in self.factory.for_capability(RESEARCH_CAPABILITY):
            state = str((adapter.health() or {}).get("state", AdapterState.UNAVAILABLE.value))
            circuit = self._circuits.setdefault(adapter.name, CircuitState())
            if state in {AdapterState.AVAILABLE.value, AdapterState.DEGRADED.value} and not circuit.open:
                adapters.append(adapter)
        return sorted(adapters, key=lambda item: item.name)

    def run(self, query: str, required_claims: tuple[str, ...] = ()) -> dict[str, Any]:
        clean = " ".join(query.split())
        if not clean:
            raise ValueError("query must not be empty")
        key = "research:" + _hash(json.dumps([clean.casefold(), sorted(required_claims)]))
        value, cache_hit = self.cache.get_or_load(key, lambda: self._run_uncached(clean, required_claims))
        result = dict(value)
        result["cache_hit"] = cache_hit
        return result

    async def run_async(self, query: str, required_claims: tuple[str, ...] = ()) -> dict[str, Any]:
        return await asyncio.to_thread(self.run, query, required_claims)

    def _run_uncached(self, query: str, required_claims: tuple[str, ...]) -> dict[str, Any]:
        started = perf_counter()
        telemetry = ResearchTelemetry()
        adapters = self.available_adapters()
        if not adapters:
            return self._result(query, [], required_claims, telemetry,
                                "NO_AVAILABLE_RESEARCH_ADAPTER", started)
        selected = adapters[:self.policy.initial_sources]
        remaining = adapters[self.policy.initial_sources:self.policy.max_sources]
        sources: list[NormalizedSource] = []
        while selected:
            fetched, elapsed = self._fetch_parallel(selected, query, telemetry)
            telemetry.fetch_ms += elapsed
            sources.extend(fetched)
            fused = self._fuse(sources, required_claims)
            enough = (fused["confidence"] >= self.policy.confidence_threshold
                      and fused["coverage"] >= self.policy.coverage_threshold
                      and fused["independent_source_count"] >= self.policy.min_independent_sources
                      and not fused["contradictions"])
            if enough:
                return self._result(query, sources, required_claims, telemetry,
                                    "SUFFICIENT_CONFIDENCE", started)
            if not remaining:
                reason = "MAX_SOURCES_REACHED" if len(sources) >= self.policy.max_sources else "NO_MORE_AVAILABLE_SOURCES"
                return self._result(query, sources, required_claims, telemetry, reason, started)
            telemetry.expansion_rounds += 1
            selected = remaining[:self.policy.expansion_batch]
            remaining = remaining[self.policy.expansion_batch:]
        return self._result(query, sources, required_claims, telemetry, "NO_RESULTS", started)

    def _fetch_parallel(self, adapters: list[CapabilityAdapter], query: str,
                        telemetry: ResearchTelemetry) -> tuple[list[NormalizedSource], float]:
        started = perf_counter()
        results: list[NormalizedSource] = []
        workers = max(1, min(self.policy.max_concurrency, len(adapters)))
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {pool.submit(self._fetch_one, adapter, query, telemetry): adapter for adapter in adapters}
            for future, adapter in futures.items():
                try:
                    raw = future.result(timeout=self.policy.source_timeout_s)
                    for item in raw:
                        results.append(normalize_source(item, self.resolver,
                                                        self.policy.context_budget_bytes))
                    self._circuits[adapter.name] = CircuitState()
                except FutureTimeout:
                    # Zaman asimi HEM basarisizliktir HEM zaman asimi.
                    # failed_sources dusurulurse mevcut devre kesici testi
                    # kirilir; timeouts ise AYRI sayilir cunku "kaynak yok"
                    # ile karistirilirsa kullanici "internette yok" sanip
                    # konuyu kapatir.
                    telemetry.failed_sources += 1
                    telemetry.timeouts = getattr(telemetry, "timeouts", 0) + 1
                    circuit = self._circuits.setdefault(adapter.name, CircuitState())
                    circuit.failures += 1
                    circuit.open = circuit.failures >= self.policy.circuit_breaker_failures
                except Exception:
                    telemetry.failed_sources += 1
                    circuit = self._circuits.setdefault(adapter.name, CircuitState())
                    circuit.failures += 1
                    circuit.open = circuit.failures >= self.policy.circuit_breaker_failures
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        telemetry.fetched_sources += len(results)
        return results, round((perf_counter() - started) * 1000, 3)

    def _fetch_one(self, adapter: CapabilityAdapter, query: str,
                   telemetry: ResearchTelemetry) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self.policy.retry_budget + 1):
            try:
                response = adapter.execute({
                    "capability": RESEARCH_CAPABILITY, "query": query,
                    "untrusted_content": True, "external_actions": False,
                    "max_bytes": self.policy.context_budget_bytes,
                })
                telemetry.model_calls += int(response.get("model_calls") or 0)
                telemetry.cost += float(response.get("cost") or 0.0)
                rows = response.get("sources") or []
                if not isinstance(rows, list):
                    raise ResearchError("adapter sources must be a list")
                return [row for row in rows if isinstance(row, dict)]
            except Exception as exc:  # adapter errors are contained
                last_error = exc
                if attempt < self.policy.retry_budget:
                    telemetry.retries += 1
        raise ResearchError(f"adapter {adapter.name} failed") from last_error

    def _fuse(self, sources: list[NormalizedSource], required_claims: tuple[str, ...]) -> dict[str, Any]:
        unique: dict[tuple[str, str], NormalizedSource] = {}
        for source in sources:
            unique[(source.origin_id.casefold(), source.content_hash)] = source
        values = list(unique.values())
        claim_values: dict[str, dict[str, list[str]]] = {}
        for source in values:
            for claim, value in source.claims.items():
                claim_values.setdefault(claim, {}).setdefault(value.casefold(), []).append(source.source_id)
        contradictions = [
            {"claim": claim, "values": sorted(groups), "source_ids": sorted({sid for ids in groups.values() for sid in ids})}
            for claim, groups in claim_values.items() if len(groups) > 1
        ]
        required = set(required_claims)
        covered = required.intersection(claim_values)
        coverage = 1.0 if not required else len(covered) / len(required)
        quality = sum(source.authority * source.freshness for source in values) / max(2, len(values))
        confidence = min(1.0, quality)
        if contradictions:
            confidence *= 0.5
        legacy = fuse([
            SourceRecord(source.source_id, source.publisher, "research",
                         json.dumps(source.claims, sort_keys=True), source.observed_at,
                         source.authority)
            for source in values
        ])
        return {
            "sources": values, "independent_source_count": len({source.origin_id for source in values}),
            "contradictions": contradictions, "confidence": round(confidence, 3),
            "coverage": round(coverage, 3), "legacy_fusion": legacy,
        }

    def _result(self, query: str, sources: list[NormalizedSource], required_claims: tuple[str, ...],
                telemetry: ResearchTelemetry, stop_reason: str, started: float) -> dict[str, Any]:
        fused = self._fuse(sources, required_claims)
        telemetry.duration_ms = round((perf_counter() - started) * 1000, 3)
        claims: dict[str, list[str]] = {}
        for source in fused["sources"]:
            for claim, value in source.claims.items():
                claims.setdefault(claim, [])
                if value not in claims[claim]:
                    claims[claim].append(value)
        return {
            "research_id": _hash(query + str(monotonic()))[:24], "query": query,
            "claims": claims, "sources": [asdict(source) for source in fused["sources"]],
            "independent_source_count": fused["independent_source_count"],
            "evidence_refs": list(dict.fromkeys(source.evidence_ref for source in fused["sources"])),
            "freshness": round(sum(source.freshness for source in fused["sources"]) / max(1, len(fused["sources"])), 3),
            "contradictions": fused["contradictions"], "confidence": fused["confidence"],
            # Tek sayı neyin eksik olduğunu söylemiyordu: ölçülen iki koşuda
            # (alakasız mağaza sayfaları / gerçek sektör raporu) skor neredeyse
            # aynıydı. Parçalı skor sınırlayan boyutu adıyla bildirir.
            "confidence_breakdown": score_confidence(
                fused["sources"], contradictions=fused["contradictions"],
                required_claims=required_claims,
                min_independent_sources=self.policy.min_independent_sources,
                model_calls=telemetry.model_calls).to_dict(),
            "coverage": fused["coverage"], "stop_reason": stop_reason,
            "duration": {"ms": telemetry.duration_ms, "fetch_ms": round(telemetry.fetch_ms, 3)},
            "cost": round(telemetry.cost, 6), "model_calls": telemetry.model_calls,
            "telemetry": asdict(telemetry), "cache_hit": False,
            "external_actions": 0,
        }
