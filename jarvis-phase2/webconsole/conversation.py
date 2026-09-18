"""Deterministic-first conversational router for the existing chat endpoint."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from jarvis.execution_planner import plan_request

SIMPLE_CONVERSATION = "SIMPLE_CONVERSATION"
COMPANY_QUERY = "COMPANY_QUERY"
ANALYSIS_REQUEST = "ANALYSIS_REQUEST"
RESEARCH_REQUEST = "RESEARCH_REQUEST"
ACTION_REQUEST = "ACTION_REQUEST"
GENERAL_REASONING = "GENERAL_REASONING"


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().replace("ı", "i").split())


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    domain: str | None = None


def classify(message: str) -> RouteDecision:
    text = _normalize(message)
    if any(term in text for term in ("merhaba", "selam", "sen nesin", "ne yapabiliyorsun", "kimsin", "hello")):
        return RouteDecision(SIMPLE_CONVERSATION)
    verbs = ("değiştir", "degistir", "durdur", "başlat", "baslat", "gönder",
             "gonder", "yayınla", "yayinla", "publish")
    if any(term in text for term in verbs):
        return RouteDecision(ACTION_REQUEST)
    if any(term in text for term in ("rakip", "pazar araştır", "pazar arastir", "research", "araştır", "arastir")):
        return RouteDecision(RESEARCH_REQUEST)
    if any(term in text for term in ("analiz", "problem", "sorunları", "sorunlari", "en önemli",
                                     "en onemli", "ne yap", "yapılması",
                                     "yapilmasi", "fırsat", "firsat")):
        return RouteDecision(ANALYSIS_REQUEST)
    if any(term in text for term in ("cevapsız", "cevapsiz", "müşteri", "musteri", "crm")):
        return RouteDecision(COMPANY_QUERY, "crm")
    if any(term in text for term in ("reklam", "meta", "harcama", "roas", "ctr", "cpa")):
        return RouteDecision(COMPANY_QUERY, "advertising")
    if any(term in text for term in ("satış", "satis", "sipariş", "siparis", "ciro")):
        return RouteDecision(COMPANY_QUERY, "sales")
    if any(term in text for term in ("bugün şirket", "bugun sirket")):
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


def route(message: str, runtime: Any) -> dict[str, Any]:
    started = perf_counter()
    decision = classify(message)
    if decision.intent == SIMPLE_CONVERSATION:
        return _response(message, decision.intent, "ANSWERED",
            "Merhaba, ben Jarvis. Şirket verilerini kanıtlarıyla okuyabilir, analiz planı hazırlayabilir, "
            "araştırma ihtiyacını belirleyebilir ve işlem taleplerini insan onayına yönlendirebilirim. "
            "Onay olmadan dış işlem yapmam.", started=started, model="deterministic-local")
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
    if decision.intent == ACTION_REQUEST:
        plan = plan_request(message)
        return _response(message, decision.intent, "PROPOSED",
            "İşlem uygulanmadı. Action Firewall ve insan onayı yoluna gönderilmek üzere proposal olarak durduruldu.",
            started=started, model="deterministic-planner", plan=plan.to_dict(),
            approval_required=True, execution_started=False)
    return _response(message, decision.intent, "AI_PROVIDER_UNAVAILABLE",
        "Bu soru serbest muhakeme gerektiriyor; yetkili bir konuşma modeli provider'ı henüz bağlı değil.",
        missing_data=("conversational_model_provider",), started=started)
