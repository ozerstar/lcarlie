"""Model layer: local-first, evidence-grounded synthesis.

    DETERMINISTIC -> LOCAL_MODEL -> EXTERNAL_MODEL

Escalation is by need, not by habit. A question Company Memory can answer
exactly never reaches a model; `should_use_model()` is the gate and the
conversational router asks it before anything else. A question that genuinely
requires open-ended reasoning gets the local model first, and only a failure
or an explicit high-complexity request escalates outward.

Grounding is structural, not a request in the prompt. `evidence_refs` on the
answer are copied from the evidence the caller supplied -- they are never
parsed out of the model's text -- so a model cannot invent a source that was
not read. It can only interpret, relate, summarise and propose options over
evidence that already exists.

Provider states reuse jarvis.adapter_factory.AdapterState, so a model
provider is describable in the same vocabulary as every other capability and
can be handed to the existing routing boundary unchanged.

No new secret system: the external key is read at call time from the Kimi
config that is already on this host, and never logged, returned or persisted.
Nothing here can take an external business action; the layer has no path to
one.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .adapter_factory import AdapterState

LOCAL_URL = os.environ.get("JARVIS_LOCAL_MODEL_URL", "http://127.0.0.1:8099/v1")
LOCAL_MODEL = os.environ.get("JARVIS_LOCAL_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M")
EXTERNAL_URL = os.environ.get("JARVIS_EXTERNAL_MODEL_URL", "https://openrouter.ai/api/v1")
EXTERNAL_MODEL = os.environ.get("JARVIS_EXTERNAL_MODEL",
                                "nvidia/nemotron-3-super-120b-a12b:free")
KIMI_CONFIG = os.environ.get("JARVIS_KIMI_CONFIG", "/root/kimi-sandbox-home/config.toml")

# Context budget. The model gets the question and the evidence that bears on
# it -- never a Company Memory dump. These caps are what keep a 4B model on a
# 4-core host answering in seconds rather than minutes.
MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_CHARS = 6000
MAX_ANSWER_TOKENS = int(os.environ.get("JARVIS_MODEL_MAX_TOKENS", "320"))
LOCAL_TIMEOUT_S = float(os.environ.get("JARVIS_LOCAL_MODEL_TIMEOUT_S", "120"))
EXTERNAL_TIMEOUT_S = 90.0

TIER_DETERMINISTIC = "DETERMINISTIC"
TIER_LOCAL = "LOCAL_MODEL"
TIER_EXTERNAL = "EXTERNAL_MODEL"

GROUNDING_SYSTEM = (
    "Sen L'CARLIÉ şirketinin analiz asistanısın. Kurallar:\n"
    "1. Şirketle ilgili HER sayı ve olgu yalnızca sana verilen KANIT bölümünden "
    "gelebilir. Kanıtta olmayan bir rakam, tarih, ürün veya müşteri bilgisi ÜRETME.\n"
    "2. Bir şeyi bilmiyorsan 'bu veri yok' de. Tahmin etme.\n"
    "3. Genel ticari muhakeme yapabilirsin, ama onu şirket verisi gibi sunma.\n"
    "4. Hiçbir işlemi uygulayamazsın; öneri üretirsin, kararı insan verir.\n"
    "5. Kısa, net, Türkçe yaz."
)


class ModelUnavailable(RuntimeError):
    """No provider could answer. Always caught -- Jarvis falls back, never fails."""


@dataclass
class ModelResult:
    answer: str
    evidence_refs: tuple[str, ...]
    confidence: str
    missing_data: tuple[str, ...]
    model: str | None
    tier: str
    model_calls: int
    duration_ms: float
    first_token_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    context_chars: int = 0
    provider_states: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        data["missing_data"] = list(self.missing_data)
        return data


# --- deterministic gate -------------------------------------------------
# Wording that asks for a COUNT or a STATE has an exact answer in Company
# Memory; sending it to a model would be slower, less accurate and would
# invent precision. Wording that asks WHY, or for an assessment, does not.
_EXACT_ANSWER_TERMS = (
    "kaç", "kac", "ne kadar", "toplam", "sayısı", "sayisi", "listele",
    "how many", "total",
)
_REASONING_TERMS = (
    "neden", "niçin", "nicin", "niye", "değerlendir", "degerlendir", "yorumla",
    "öneri", "oneri", "tavsiye", "ne yapmalı", "ne yapmali", "karşı çık",
    "karsi cik", "itiraz", "risk", "strateji", "açıkla", "acikla", "karşılaştır",
    "karsilastir", "birlikte değerlendir", "birlikte degerlendir", "analiz et",
    "en önemli", "en onemli", "problem", "sorun", "fırsat", "firsat",
    "why", "assess", "evaluate", "recommend",
)


def _fold(text: str) -> str:
    return " ".join((text or "").casefold().replace("ı", "i").split())


def should_use_model(message: str) -> bool:
    """True only when the question genuinely needs open-ended reasoning.

    A counting question answered by a model is a regression, not a feature:
    Company Memory already knows the exact number.
    """
    text = _fold(message)
    if any(term in text for term in _REASONING_TERMS):
        return True
    if any(term in text for term in _EXACT_ANSWER_TERMS):
        return False
    return False


# --- providers ----------------------------------------------------------
def _post(url: str, body: dict[str, Any], timeout: float,
          headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class LocalProvider:
    """llama.cpp server on loopback. No key, no egress, no cost."""

    name = "local"
    tier = TIER_LOCAL

    def __init__(self, url: str = LOCAL_URL, model: str = LOCAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model

    def state(self) -> AdapterState:
        try:
            health = self.url.rsplit("/v1", 1)[0] + "/health"
            with urllib.request.urlopen(health, timeout=3) as response:
                ok = json.loads(response.read()).get("status") == "ok"
            return AdapterState.AVAILABLE if ok else AdapterState.DEGRADED
        except Exception:  # noqa: BLE001 - an unreachable provider is a state
            return AdapterState.UNAVAILABLE

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        data = _post(f"{self.url}/chat/completions",
                     {"messages": messages, "max_tokens": max_tokens,
                      "temperature": 0.3, "stream": False},
                     timeout=LOCAL_TIMEOUT_S)
        usage = data.get("usage") or {}
        return {"text": data["choices"][0]["message"]["content"],
                "model": self.model,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}


class ExternalProvider:
    """OpenRouter, using the key already on this host.

    The key is read from the existing Kimi config at call time and never
    logged, returned or written anywhere. This adds no secret store; if the
    file is absent the provider is simply UNAVAILABLE.
    """

    name = "external"
    tier = TIER_EXTERNAL

    def __init__(self, url: str = EXTERNAL_URL, model: str = EXTERNAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model

    def _key(self) -> str | None:
        try:
            text = open(KIMI_CONFIG, encoding="utf-8").read()
        except OSError:
            return None
        block = re.search(r"\[providers\.openrouter\](.*?)(\n\[|\Z)", text, re.S)
        if not block:
            return None
        found = re.search(r'api_key\s*=\s*"([^"]+)"', block.group(1))
        return found.group(1) if found else None

    def state(self) -> AdapterState:
        return AdapterState.AVAILABLE if self._key() else AdapterState.UNAVAILABLE

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        key = self._key()
        if not key:
            raise ModelUnavailable("no external provider credential available")
        try:
            data = _post(f"{self.url}/chat/completions",
                         {"model": self.model, "messages": messages,
                          "max_tokens": max_tokens, "temperature": 0.3},
                         timeout=EXTERNAL_TIMEOUT_S,
                         headers={"Authorization": f"Bearer {key}"})
        except urllib.error.HTTPError as exc:
            # 429 is the documented free-tier condition; it is a state, not a bug.
            state = "RATE_LIMITED" if exc.code == 429 else f"HTTP_{exc.code}"
            raise ModelUnavailable(f"external provider {state}") from None
        usage = data.get("usage") or {}
        return {"text": data["choices"][0]["message"]["content"],
                "model": self.model,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}


# --- context compilation ------------------------------------------------
def compile_context(evidence: Iterable[dict[str, Any]]) -> tuple[str, tuple[str, ...], int]:
    """Only what bears on the question, under a hard budget.

    Returns the rendered block, the refs it was built from, and its size.
    Refs travel separately from the text precisely so the answer's refs can be
    the ones we READ, not the ones a model wrote.
    """
    lines: list[str] = []
    refs: list[str] = []
    used = 0
    for item in list(evidence)[:MAX_EVIDENCE_ITEMS]:
        ref = str(item.get("ref") or item.get("source") or "unknown")
        summary = str(item.get("summary") or item.get("detail") or "")
        rendered = f"- {ref}: {summary}"
        if used + len(rendered) > MAX_EVIDENCE_CHARS:
            break
        lines.append(rendered)
        used += len(rendered)
        if ref not in refs:
            refs.append(ref)
    return "\n".join(lines), tuple(refs), used


class ModelRouter:
    """Local first, external only on failure or explicit escalation."""

    def __init__(self, local: Any | None = None, external: Any | None = None):
        self.local = local if local is not None else LocalProvider()
        self.external = external if external is not None else ExternalProvider()

    def provider_states(self) -> dict[str, str]:
        return {"local": self.local.state().value,
                "external": self.external.state().value}

    def _chain(self, escalate: bool) -> list[Any]:
        return [self.external, self.local] if escalate else [self.local, self.external]

    def generate(self, messages: list[dict[str, str]], max_tokens: int,
                 escalate: bool = False) -> tuple[dict[str, Any], str, int]:
        attempts = 0
        for provider in self._chain(escalate):
            if provider.state() != AdapterState.AVAILABLE:
                continue
            attempts += 1
            try:
                return provider.complete(messages, max_tokens), provider.tier, attempts
            except (ModelUnavailable, urllib.error.URLError, TimeoutError, OSError,
                    KeyError, ValueError):
                continue
        raise ModelUnavailable("no model provider could answer")

    # -- the two capabilities this layer exposes ------------------------
    def synthesize(self, question: str, evidence: Iterable[dict[str, Any]],
                   missing_data: Iterable[str] = (), escalate: bool = False,
                   max_tokens: int = MAX_ANSWER_TOKENS) -> ModelResult:
        started = time.perf_counter()
        block, refs, size = compile_context(evidence)
        missing = tuple(missing_data)
        user = (f"KANIT:\n{block or '(kanıt yok)'}\n\n"
                + (f"EKSİK VERİ: {', '.join(missing)}\n\n" if missing else "")
                + f"SORU: {question}")
        messages = [{"role": "system", "content": GROUNDING_SYSTEM},
                    {"role": "user", "content": user}]
        states = self.provider_states()
        try:
            result, tier, calls = self.generate(messages, max_tokens, escalate)
        except ModelUnavailable as exc:
            raise ModelUnavailable(str(exc)) from None

        # Confidence follows the EVIDENCE, not the model's self-assessment: a
        # fluent answer over one source is not more trustworthy than a terse
        # one over five.
        if not refs:
            confidence = "LOW"
        elif missing:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH" if len(refs) >= 3 else "MEDIUM"

        return ModelResult(
            answer=result["text"].strip(),
            evidence_refs=refs,               # what we read, never what it wrote
            confidence=confidence, missing_data=missing,
            model=result.get("model"), tier=tier, model_calls=calls,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            context_chars=size, provider_states=states,
        )

    def decompose_query(self, request: str, count: int = 3) -> list[str]:
        """Generic QUERY_DECOMPOSITION capability: one research request ->
        focused search queries. A contract only -- this layer runs no search."""
        messages = [
            {"role": "system", "content":
             "Araştırma isteklerini odaklı arama sorgularına bölersin. "
             "SADECE JSON dizisi döndür, başka metin yazma."},
            {"role": "user", "content":
             f'İsteği {count} odaklı arama sorgusuna böl. Format: ["sorgu1", ...]\n'
             f"İstek: {request}"},
        ]
        result, _tier, _calls = self.generate(messages, 220)
        text = result["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        queries: list[str] = []
        for item in parsed:
            if isinstance(item, str):
                queries.append(item)
            elif isinstance(item, dict):
                for key in ("sorgu", "query", "q"):
                    if isinstance(item.get(key), str):
                        queries.append(item[key])
                        break
        return queries[:count]
