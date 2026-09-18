"""Deterministic-first conversational router for the existing chat endpoint."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from jarvis.execution_planner import STATUS_BLOCKED_EXTERNAL_ACTION, plan_request
from jarvis.model_layer import ModelRouter, ModelUnavailable, should_use_model

SIMPLE_CONVERSATION = "SIMPLE_CONVERSATION"
COMPANY_QUERY = "COMPANY_QUERY"
ANALYSIS_REQUEST = "ANALYSIS_REQUEST"
RESEARCH_REQUEST = "RESEARCH_REQUEST"
ACTION_REQUEST = "ACTION_REQUEST"
GENERAL_REASONING = "GENERAL_REASONING"


def _normalize(text: str) -> str:
    """Fold dotted/dotless i to one form.

    Applied to BOTH sides of every comparison. Folding only the message
    silently broke every lemma containing "ı": "satış" folds to "satiş", which
    matches neither "satış" nor "satis" in a table, so sales questions were
    never recognised and sales evidence was never gathered.
    """
    return " ".join((text or "").casefold().replace("ı", "i").split())


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize(term) in text for term in terms)


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    domain: str | None = None


def classify(message: str) -> RouteDecision:
    text = _normalize(message)
    if _has(text, ("merhaba", "selam", "sen nesin", "ne yapabiliyorsun", "kimsin", "hello")):
        return RouteDecision(SIMPLE_CONVERSATION)
    # A question ABOUT what to do is not an instruction to do it. Checked
    # first so "ne yapmalıyız" can never be read as the imperative "yap".
    asks_for_advice = _has(text, ("ne yap", "ne öneriyorsun", "ne oneriyorsun",
                                  "ne yapmalı", "ne yapmali", "yapılması", "yapilmasi"))
    verbs = ("değiştir", "degistir", "durdur", "başlat", "baslat", "gönder",
             "gonder", "yayınla", "yayinla", "publish", "yap", "ayarla",
             "güncelle", "guncelle", "artır", "artir", "azalt", "indir",
             "sil", "kapat", "iptal et")
    if not asks_for_advice and _has(text, verbs):
        return RouteDecision(ACTION_REQUEST)
    if _has(text, ("rakip", "pazar araştır", "pazar arastir", "research", "araştır", "arastir")):
        return RouteDecision(RESEARCH_REQUEST)
    if _has(text, ("analiz", "problem", "sorunları", "sorunlari", "en önemli",
                   "en onemli", "ne yap", "yapılması", "yapilmasi", "fırsat", "firsat")):
        return RouteDecision(ANALYSIS_REQUEST)
    if _has(text, ("cevapsız", "cevapsiz", "müşteri", "musteri", "crm")):
        return RouteDecision(COMPANY_QUERY, "crm")
    if _has(text, ("reklam", "meta", "harcama", "roas", "ctr", "cpa")):
        return RouteDecision(COMPANY_QUERY, "advertising")
    if _has(text, ("satış", "satis", "sipariş", "siparis", "ciro")):
        return RouteDecision(COMPANY_QUERY, "sales")
    if _has(text, ("bugün şirket", "bugun sirket")):
        return RouteDecision(COMPANY_QUERY, "company")
    return RouteDecision(GENERAL_REASONING)


def _response(message: str, intent: str, status: str, answer: str,
              evidence_refs: tuple[str, ...] = (), missing_data: tuple[str, ...] = (),
              started: float = 0.0, model: str | None = None,
              model_calls: int = 0, **extra: Any) -> dict[str, Any]:
    payload = {
        "request_id": "chat-" + hashlib.sha256(message.encode()).hexdigest()[:16],
        "intent": intent, "status": status, "answer": answer,
        "evidence_refs": list(evidence_refs), "missing_data": list(missing_data),
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "first_token_ms": None, "model": model, "model_calls": model_calls,
        "external_actions": 0, **extra,
    }
    payload["kind"] = ("ANSWER" if status in {"ANSWERED", "PROPOSED"}
                       else "REQUIRES_REASONING_CAPABILITY"
                       if status == "AI_PROVIDER_UNAVAILABLE" else status)
    payload["text"] = answer
    return payload


def _memory(runtime: Any) -> Any:
    return runtime.runtime.compiler.memory


def _company(message: str, domain: str, memory: Any, started: float) -> dict[str, Any]:
    try:
        if domain == "crm":
            evidence = memory._fetch("crm_unanswered")
            count = len(evidence.records)
            longest = max((float(row.get("bekleme_saat") or 0) for row in evidence.records), default=0)
            answer = (f"Evet, {count} cevapsız müşteri konuşması var. En uzun bekleme yaklaşık "
                      f"{longest:.1f} saat." if count else "Cevapsız müşteri konuşması görünmüyor.")
        elif domain == "advertising":
            evidence = memory._fetch("advertising_performance")
            latest = [row for row in evidence.records if row.get("pencere") == 30]
            spend = sum(float(row.get("harcama") or 0) for row in latest)
            answer = (f"30 günlük görünümde {len(latest)} reklam kaydı ve toplam {spend:,.2f} TL "
                      "harcama var. Meta satış iddiaları ticari doğrulama olmadan kesin satış sayılmadı.")
        elif domain == "sales":
            evidence = memory._fetch("sales_orders")
            measured = [row for row in evidence.records if row.get("olcumde")]
            revenue = sum(float(row.get("ciro_dogrulanmis_net") or row.get("ciro_beyan_edilmis_net") or 0)
                          for row in measured)
            answer = (f"Company Memory'de {len(evidence.records)} sipariş var; ölçüm kapsamındaki "
                      f"{len(measured)} siparişin görünen net cirosu {revenue:,.2f} TL.")
        else:
            evidence = memory.get_executive_brief()
            row = evidence.records[0] if evidence.records else {}
            answer = (f"Şirket görünümünde {row.get('proposed', 0)} öneri, {row.get('approved', 0)} "
                      f"onaylı kayıt ve {row.get('red_team_pending', 0)} bekleyen Red Team incelemesi var. "
                      f"Güvensiz dış işlem sayısı {row.get('unsafe_external_actions', 0)}.")
        return _response(message, COMPANY_QUERY, "ANSWERED", answer, (evidence.source,),
                         started=started, model="deterministic-local")
    except Exception as exc:
        return _response(message, COMPANY_QUERY, "DATA_UNAVAILABLE",
                         "İlgili Company Memory verisi şu anda okunamıyor.",
                         missing_data=(domain,), started=started, error_type=type(exc).__name__)



# --- evidence gathering for synthesis -----------------------------------
# Which Company Memory queries bear on a question. Deliberately narrow: the
# model gets the evidence for the domains the question names, never the whole
# fabric. An unnamed domain contributes nothing rather than everything.
_DOMAIN_TERMS = {
    "crm": ("cevapsız", "cevapsiz", "müşteri", "musteri", "crm", "konuşma", "konusma"),
    "advertising": ("reklam", "meta", "harcama", "roas", "ctr", "kampanya"),
    "sales": ("satış", "satis", "sipariş", "siparis", "ciro", "gelir"),
    "ecommerce": ("e-ticaret", "eticaret", "ürün", "urun", "fiyat", "marj", "funnel"),
    "operations": ("operasyon", "kargo", "gönderi", "gonderi", "teslimat"),
}

_ROUTER: ModelRouter | None = None


def _router() -> ModelRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = ModelRouter()
    return _ROUTER


def _summarize(name: str, records: list[dict[str, Any]]) -> str:
    """A compact, factual line per source. No interpretation happens here --
    that is the model's job, and it must not be fed conclusions as if they
    were data."""
    if not records:
        return "kayıt yok"
    if name == "crm_unanswered":
        longest = max((float(r.get("bekleme_saat") or 0) for r in records), default=0)
        channels = sorted({str(r.get("kanal")) for r in records if r.get("kanal")})
        return (f"{len(records)} cevapsız konuşma, en uzun bekleme {longest:.1f} saat, "
                f"kanallar: {', '.join(channels) or 'bilinmiyor'}")
    if name == "advertising_performance":
        window = [r for r in records if r.get("pencere") == 30] or records
        spend = sum(float(r.get("harcama") or 0) for r in window)
        unconfirmed = sum(1 for r in window
                          if r.get("commercial_confirmation") == "NOT_AVAILABLE")
        return (f"{len(window)} reklam kaydı, toplam harcama {spend:,.2f} TL, "
                f"{unconfirmed} kaydın satış iddiası ticari olarak doğrulanmamış")
    if name == "sales_orders":
        paid = sum(1 for r in records if r.get("odeme_durumu") == "PAID")
        cancelled = sum(1 for r in records if r.get("ciro_sinifi") == "IPTAL")
        return f"{len(records)} sipariş, {paid} ödenmiş, {cancelled} iptal"
    if name == "ecommerce_profitability":
        top = max(records, key=lambda r: float(r.get("ciro_net") or 0), default=None)
        return (f"{len(records)} ürün karlılık kaydı; en yüksek net ciro "
                f"{top.get('urun_adi')} ({float(top.get('ciro_net') or 0):,.2f} TL, "
                f"brüt marj %{top.get('brut_marj_yuzde')})" if top else f"{len(records)} kayıt")
    if name == "operations_shipments":
        alarms = sum(1 for r in records if r.get("alarm"))
        return f"{len(records)} gönderi, {alarms} alarmlı"
    if name == "open_work":
        return f"{len(records)} açık iş kaydı"
    return f"{len(records)} kayıt"


def _gather(message: str, memory: Any) -> tuple[list[dict[str, Any]], list[str]]:
    text = _normalize(message)
    domains = [d for d, terms in _DOMAIN_TERMS.items() if _has(text, terms)]
    queries: list[str] = []
    for domain in domains:
        for name in getattr(memory, "DOMAIN_QUERIES", {}).get(domain, ()):
            if name not in queries:
                queries.append(name)

    evidence: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in queries:
        try:
            got = memory._fetch(name)
            evidence.append({"ref": got.source, "summary": _summarize(name, got.records)})
        except Exception:
            missing.append(name)

    # No domain named, or none readable: fall back to the company-wide
    # deterministic signals rather than to nothing.
    if not evidence:
        try:
            from jarvis import business_signals

            report = business_signals.run(memory)
            for signal in report.signals:
                evidence.append({"ref": "jarvis.business_signals",
                                 "summary": f"[{signal.severity}] {signal.summary}"})
            if not report.signals:
                missing.append("business_signals")
        except Exception:
            missing.append("business_signals")
    return evidence, missing


def _synthesize(message: str, intent: str, memory: Any, started: float,
                escalate: bool = False) -> dict[str, Any]:
    evidence, missing = _gather(message, memory)
    try:
        result = _router().synthesize(message, evidence, missing_data=missing,
                                      escalate=escalate)
    except ModelUnavailable as exc:
        # Never speechless: the deterministic surface still answers.
        return _response(message, intent, "AI_PROVIDER_UNAVAILABLE",
            "Bu soru serbest muhakeme gerektiriyor; şu anda hiçbir model provider "
            "yanıt veremedi. Kanıtlar okundu ancak yorumlanamadı.",
            evidence_refs=tuple(item["ref"] for item in evidence),
            missing_data=tuple(missing), started=started,
            provider_states=_router().provider_states(), error_detail=str(exc))
    payload = result.to_dict()
    return _response(message, intent, "ANSWERED", result.answer,
                     evidence_refs=result.evidence_refs,
                     missing_data=result.missing_data, started=started,
                     model=result.model, model_calls=result.model_calls,
                     confidence=result.confidence, tier=result.tier,
                     context_chars=result.context_chars,
                     prompt_tokens=payload["prompt_tokens"],
                     completion_tokens=payload["completion_tokens"],
                     provider_states=result.provider_states)


def _action(message: str, started: float) -> dict[str, Any]:
    plan = plan_request(message)
    # The conversational classifier recognises inflected Turkish action
    # wording more broadly than the existing planner. Fail closed at this
    # boundary if the planner did not recognise that exact inflection.
    if plan.status != STATUS_BLOCKED_EXTERNAL_ACTION:
        plan = plan_request("fiyat değiştir: " + message)
    return _response(message, ACTION_REQUEST, "PROPOSED",
        "İşlem uygulanmadı. Action Firewall ve insan onayı yoluna gönderilmek üzere "
        "proposal olarak durduruldu.",
        started=started, model="deterministic-planner", plan=plan.to_dict(),
        approval_required=True, execution_started=False)


def route(message: str, runtime: Any) -> dict[str, Any]:
    started = perf_counter()
    decision = classify(message)
    if decision.intent == SIMPLE_CONVERSATION:
        return _response(message, decision.intent, "ANSWERED",
            "Merhaba, ben Jarvis. Şirket verilerini kanıtlarıyla okuyabilir, analiz planı hazırlayabilir, "
            "araştırma ihtiyacını belirleyebilir ve işlem taleplerini insan onayına yönlendirebilirim. "
            "Onay olmadan dış işlem yapmam.", started=started, model="deterministic-local")
    # The action boundary is settled before any model can be reached. A
    # request to change something must land on the firewall path whatever
    # else it looks like.
    if decision.intent == ACTION_REQUEST:
        return _action(message, started)
    # The deterministic gate comes next: a question Company Memory answers
    # exactly must never cost a model call. Only genuinely open-ended wording
    # gets past this line.
    if decision.intent in (COMPANY_QUERY, ANALYSIS_REQUEST, GENERAL_REASONING) \
            and should_use_model(message):
        return _synthesize(message, decision.intent, _memory(runtime), started)
    if decision.intent == COMPANY_QUERY:
        return _company(message, decision.domain or "company", _memory(runtime), started)
    if decision.intent == ANALYSIS_REQUEST:
        plan = plan_request(message)
        return _response(message, decision.intent, "PROPOSED",
            "Analiz isteği Planner'a aktarıldı ve çalıştırılmadan bir plan hazırlandı.",
            missing_data=tuple(plan.required_internal_data), started=started,
            model="deterministic-planner", model_calls=plan.model_calls,
            plan=plan.to_dict(), execution_started=False)
    if decision.intent == RESEARCH_REQUEST:
        return _response(message, decision.intent, "DATA_UNAVAILABLE",
            "Araştırma isteği tanındı ancak production'da kullanılabilir araştırma capability'si yok.",
            missing_data=("fresh_research_source",), started=started,
            error_code="RESEARCH_CAPABILITY_UNAVAILABLE")
    return _synthesize(message, decision.intent, _memory(runtime), started)
