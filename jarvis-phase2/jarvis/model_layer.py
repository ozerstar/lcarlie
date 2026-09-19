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

# The GPU box reaches the server through a reverse SSH tunnel, so from
# here it is just another loopback port. When the desktop is off the
# tunnel is gone, the health check fails, and the chain moves on.
GPU_URL = os.environ.get("JARVIS_GPU_MODEL_URL", "http://127.0.0.1:8098/v1")
LOCAL_URL = os.environ.get("JARVIS_LOCAL_MODEL_URL", "http://127.0.0.1:8099/v1")
LOCAL_MODEL = os.environ.get("JARVIS_LOCAL_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M")
GPU_MODEL = os.environ.get("JARVIS_GPU_MODEL", LOCAL_MODEL)
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
# Below this a reply is not an answer; it is the small model giving up.
MIN_USEFUL_ANSWER_CHARS = 24
# A knowledge-backed answer on this CPU can legitimately take a minute.
# Timing out and serving the canned fallback after that much work is the
# worst outcome available: slow is recoverable, discarded is not.
LOCAL_TIMEOUT_S = float(os.environ.get("JARVIS_LOCAL_MODEL_TIMEOUT_S", "240"))
EXTERNAL_TIMEOUT_S = 90.0

TIER_DETERMINISTIC = "DETERMINISTIC"
TIER_GPU = "LOCAL_GPU"
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


# Work the 4B local model is not the right tool for. Deterministic, like the
# model gate itself -- no model is consulted to decide which model to use.
_ESCALATION_TERMS = (
    # the user asking for it outright
    "detaylı", "detayli", "derin", "kapsamlı", "kapsamli", "daha iyi düşün",
    "daha iyi dusun", "uzun uzun", "büyük model", "buyuk model",
    # judgement that has to weigh things against each other
    "strateji", "karar ver", "kıyasla", "kiyasla", "karşılaştır", "karsilastir",
    "karşı çık", "karsi cik", "itiraz", "risk analizi", "senaryo",
    "avantaj ve dezavantaj", "artı ve eksi", "arti ve eksi",
)
# A long, multi-clause request is doing more than one thing at once.
_ESCALATION_CHARS = 280


def needs_escalation(message: str) -> bool:
    """Should this go to the stronger model first?

    Small talk, counting and single-domain lookups stay local; weighing
    options, arguing against a finding, or an explicitly deep request does
    not. Being wrong here is cheap: the chain tries the other provider next.
    """
    text = _fold(message)
    return bool(text) and (len(text) >= _ESCALATION_CHARS
                           or any(_fold(term) in text for term in _ESCALATION_TERMS))


def should_use_model(message: str) -> bool:
    """True only when the question genuinely needs open-ended reasoning.

    A counting question answered by a model is a regression, not a feature:
    Company Memory already knows the exact number.
    """
    text = _fold(message)
    if any(_fold(term) in text for term in _REASONING_TERMS):
        return True
    if any(_fold(term) in text for term in _EXACT_ANSWER_TERMS):
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
    # A dead tunnel must be discovered fast: the GPU box being off is the
    # normal case at night, not an exception worth waiting on.
    health_timeout_s = 3.0

    def __init__(self, url: str = LOCAL_URL, model: str = LOCAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model

    def state(self) -> AdapterState:
        try:
            health = self.url.rsplit("/v1", 1)[0] + "/health"
            with urllib.request.urlopen(health, timeout=self.health_timeout_s) as response:
                ok = json.loads(response.read()).get("status") == "ok"
            return AdapterState.AVAILABLE if ok else AdapterState.DEGRADED
        except Exception:  # noqa: BLE001 - an unreachable provider is a state
            return AdapterState.UNAVAILABLE

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        data = _post(f"{self.url}/chat/completions",
                     # cache_prompt: the system prompt is identical every turn.
                     # Re-evaluating it cost 4485 ms; cached it costs 159 ms.
                     {"messages": messages, "max_tokens": max_tokens,
                      "temperature": 0.3, "stream": False, "cache_prompt": True},
                     timeout=LOCAL_TIMEOUT_S)
        usage = data.get("usage") or {}
        return {"text": data["choices"][0]["message"]["content"],
                "model": self.model,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}


    def stream(self, messages: list[dict[str, str]], max_tokens: int):
        """Yield text deltas as they are produced.

        Generation speed is unchanged -- about 7 tokens a second on this host.
        What changes is that the first words arrive in well under a second
        instead of after the whole answer is finished.
        """
        body = json.dumps({"messages": messages, "max_tokens": max_tokens,
                           "temperature": 0.3, "stream": True,
                           "cache_prompt": True}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=LOCAL_TIMEOUT_S) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                text = delta.get("content")
                if text:
                    yield text


class ExternalProvider:
    """OpenRouter, using the key already on this host.

    The key is read from the existing Kimi config at call time and never
    logged, returned or written anywhere. This adds no secret store; if the
    file is absent the provider is simply UNAVAILABLE.
    """

    name = "external"
    tier = TIER_EXTERNAL

    # A 429 is not a per-call accident, it is a quota that stays exhausted.
    # Remembering it keeps every later escalation from paying seconds to
    # rediscover the same answer.
    RATE_LIMIT_COOLDOWN_S = 900

    def __init__(self, url: str = EXTERNAL_URL, model: str = EXTERNAL_MODEL):
        self.url = url.rstrip("/")
        self.model = model
        self._rate_limited_until = 0.0

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
        if not self._key():
            return AdapterState.UNAVAILABLE
        if time.time() < self._rate_limited_until:
            return AdapterState.RATE_LIMITED
        return AdapterState.AVAILABLE

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
            if exc.code == 429:
                self._rate_limited_until = time.time() + self.RATE_LIMIT_COOLDOWN_S
                raise ModelUnavailable("external provider RATE_LIMITED") from None
            raise ModelUnavailable(f"external provider HTTP_{exc.code}") from None
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

    def __init__(self, local: Any | None = None, external: Any | None = None,
                 gpu: Any | None = None):
        # Same class, different endpoint: the GPU box is reached over the
        # reverse tunnel and is otherwise an ordinary llama.cpp server.
        if gpu is not None:
            self.gpu = gpu
        else:
            self.gpu = LocalProvider(url=GPU_URL, model=GPU_MODEL)
            self.gpu.name = "gpu"
            self.gpu.tier = TIER_GPU
        self.local = local if local is not None else LocalProvider()
        self.external = external if external is not None else ExternalProvider()

    def provider_states(self) -> dict[str, str]:
        return {"gpu": self.gpu.state().value,
                "local": self.local.state().value,
                "external": self.external.state().value}

    def _chain(self, escalate: bool) -> list[Any]:
        """GPU first because it is ten times faster, the VDS next because it is
        always on, the external provider last -- or first when the task needs a
        stronger model rather than a faster one."""
        fast = [self.gpu, self.local]
        return [self.external, *fast] if escalate else [*fast, self.external]

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
                   max_tokens: int = MAX_ANSWER_TOKENS,
                   system: str | None = None,
                   history: list[dict[str, str]] | None = None) -> ModelResult:
        started = time.perf_counter()
        block, refs, size = compile_context(evidence)
        missing = tuple(missing_data)
        if not block and system is not None:
            # Conversation, not analysis: no evidence block to wrap around it.
            user = question
        else:
            user = (f"KANIT:\n{block or '(kanıt yok)'}\n\n"
                    + (f"EKSİK VERİ: {', '.join(missing)}\n\n" if missing else "")
                    + f"SORU: {question}")
        # Prior turns sit between the system prompt and the new question, so
        # "onu değil, diğerini" has something to refer back to.
        messages = ([{"role": "system", "content": system or GROUNDING_SYSTEM}]
                    + list(history or [])
                    + [{"role": "user", "content": user}])
        states = self.provider_states()
        try:
            result, tier, calls = self.generate(messages, max_tokens, escalate)
        except ModelUnavailable as exc:
            raise ModelUnavailable(str(exc)) from None

        # An empty or stub-length answer from the small model is a failure, not
        # an answer. Try the stronger one before returning it.
        if (not escalate and tier in (TIER_GPU, TIER_LOCAL)
                and len((result.get("text") or "").strip()) < MIN_USEFUL_ANSWER_CHARS
                and self.external.state() == AdapterState.AVAILABLE):
            try:
                retry = self.external.complete(messages, max_tokens)
                result, tier, calls = retry, TIER_EXTERNAL, calls + 1
            except (ModelUnavailable, urllib.error.URLError, TimeoutError, OSError,
                    KeyError, ValueError):
                pass

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

    def stream_text(self, question: str, system: str, max_tokens: int = 160,
                    history: list[dict[str, str]] | None = None):
        """Stream a conversational reply. Falls back to a single block when the
        local provider is not the one answering."""
        messages = ([{"role": "system", "content": system}]
                    + list(history or [])
                    + [{"role": "user", "content": question}])
        streamer = (self.gpu if self.gpu.state() == AdapterState.AVAILABLE
                    else self.local)
        if streamer.state() == AdapterState.AVAILABLE:
            produced = False
            try:
                for delta in streamer.stream(messages, max_tokens):
                    produced = True
                    yield delta
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                if produced:
                    return
            else:
                return
        result, _tier, _calls = self.generate(messages, max_tokens)
        yield result["text"]

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
