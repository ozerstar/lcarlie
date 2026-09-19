"""Deterministic-first conversational router for the existing chat endpoint."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from jarvis.execution_planner import STATUS_BLOCKED_EXTERNAL_ACTION, plan_request
from jarvis.model_layer import (LOCAL_MODEL as LOCAL_MODEL_NAME, ModelRouter,
                                ModelUnavailable, needs_escalation,
                                should_use_model)
from jarvis import conversation_memory, turkish
from jarvis.company_knowledge import shared as company_knowledge
from jarvis import answer_guard
from jarvis.agency import AgencyCapability, catalogue as product_catalogue
from jarvis.agency_proposal import screen as screen_agency
from jarvis.specialist_pool import SpecialistPool

SIMPLE_CONVERSATION = "SIMPLE_CONVERSATION"
COMPANY_QUERY = "COMPANY_QUERY"
ANALYSIS_REQUEST = "ANALYSIS_REQUEST"
RESEARCH_REQUEST = "RESEARCH_REQUEST"
ACTION_REQUEST = "ACTION_REQUEST"
GENERAL_REASONING = "GENERAL_REASONING"
AGENCY_REQUEST = "AGENCY_REQUEST"


_TR_CAPITALS = str.maketrans({"İ": "i", "I": "i", "Ş": "ş", "Ğ": "ğ",
                              "Ü": "ü", "Ö": "ö", "Ç": "ç"})


def _normalize(text: str) -> str:
    """Fold dotted/dotless i to one form.

    Applied to BOTH sides of every comparison. Folding only the message
    silently broke every lemma containing "ı": "satış" folds to "satiş", which
    matches neither "satış" nor "satis" in a table, so sales questions were
    never recognised and sales evidence was never gathered.
    """
    # "İ".casefold() is "i" plus a COMBINING DOT ABOVE, not "i", so a message
    # starting with a capital dotted I ("İyi akşamlar") matched no lemma at
    # all. Fold the Turkish capitals explicitly first.
    folded = (text or "").translate(_TR_CAPITALS).casefold().replace("ı", "i")
    return " ".join(folded.split())


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize(term) in text for term in terms)


_ANALYTICAL_OBJECTS = (
    "kontrol", "analiz", "inceleme", "değerlendirme", "degerlendirme", "test",
    "plan", "brief", "öneri", "oneri", "araştırma", "arastirma", "özet", "ozet",
    "rapor", "karşılaştırma", "karsilastirma", "red team", "kıyas", "kiyas",
)


# A Turkish imperative is the bare stem, optionally with a person suffix.
# Everything else built on the same stem is some other form: an ability, an
# infinitive, a past tense -- none of them an instruction.
_IMPERATIVE_SUFFIXES = frozenset((
    "", "ın", "in", "un", "ün", "ınız", "iniz", "unuz", "ünüz",
    # stems ending in a vowel take a buffer y: guncelle -> guncelleyin
    "yın", "yin", "yun", "yün", "yınız", "yiniz", "yunuz", "yünüz",
    # negated imperative, recognised here so the -ma/-me check below sees it
    "ma", "me", "mayın", "meyin", "mayınız", "meyiniz",
))


def _has_command(text: str, verbs: tuple[str, ...], raw: str = "") -> bool:
    """True only for verbs used as commands, not for their negated forms.

    Turkish negates an imperative with -ma/-me on the stem, so "yayınlama"
    ("do not publish") contains "yayınla" ("publish"). A plain substring test
    therefore read "Hiçbir şeyi yayınlama" as an instruction TO publish and
    sent a campaign brief to the action firewall. Same for "değiştirme",
    "gönderme", "artırma".
    """
    # Morphology first: "yap" is Verb+Imp, "yapabiliyoruz" is Verb+Able+Prog.
    # Only words that actually begin with one of the stems are analysed, so
    # the cost stays at a couple of lookups per message rather than one per
    # word.
    # Stems in their real Turkish spelling, because that is what the analyser
    # is given -- not the folded form the tables use.
    stems = frozenset(v.casefold() for v in verbs if " " not in v)
    if turkish.MORPHOLOGY_AVAILABLE and stems and raw:
        for word in turkish.words(raw):
            lowered = word.casefold()
            if not any(lowered.startswith(stem) for stem in stems):
                continue
            # Morphology answers the mood; the stem above already answered
            # which verb. Asking it for the verb too is what broke "değiştir".
            if turkish.is_positive_imperative(lowered):
                position = raw.casefold().find(lowered)
                head = _normalize(raw[max(0, position - 22):position])
                if not any(noun in head for noun in _ANALYTICAL_OBJECTS):
                    return True
        # A multi-word verb ("iptal et") still needs the substring pass below;
        # a single-word one has now been answered by morphology.
        verbs = tuple(v for v in verbs if " " in v)

    for term in verbs:
        lemma = _normalize(term)
        start = 0
        while True:
            index = text.find(lemma, start)
            if index < 0:
                break
            tail = text[index + len(lemma):index + len(lemma) + 2]
            head = text[max(0, index - 22):index]
            # The verb has to START a word. Without this, "sil" (delete) matches
            # inside "nasilsin" and a greeting was answered with the action
            # firewall notice; "indir" would match inside "indirim" the same way.
            before = text[index - 1] if index else " "
            if before.isalnum():
                start = index + len(lemma)
                continue
            # ... and the word has to BE the imperative, not merely begin with
            # it. "yapabiliyoruz" is a question about ability, not an order.
            end = index + len(lemma)
            while end < len(text) and (text[end].isalnum() or text[end] in "'’"):
                end += 1
            suffix = text[index + len(lemma):end]
            if suffix not in _IMPERATIVE_SUFFIXES:
                start = index + len(lemma)
                continue
            negated = tail in ("ma", "me")
            # "Red Team kontrolü yap", "analiz yap", "test planı yap" are
            # instructions to Jarvis about its own work. Only a verb aimed at a
            # business object is an action request.
            analytical = any(noun in head for noun in _ANALYTICAL_OBJECTS)
            if not negated and not analytical:
                return True
            start = index + len(lemma)
    return False


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    domain: str | None = None


_PERSONAL_MARKERS = (
    "kafam", "yorgunum", "yoruldum", "üzgünüm", "uzgunum", "moralim",
    "sıkıldım", "sikildim", "bunaldım", "bunaldim", "canım sıkkın",
    "canim sikkin", "stresliyim", "mutsuzum", "içimden", "icimden",
    "dertleş", "dertles", "kendimi", "hissediyorum",
)


def classify(message: str) -> RouteDecision:
    # "kampanyayi kapat" is the same instruction as "kampanyayı kapat"; the
    # operator types from a phone. Restoring the diacritics once here means
    # every table below sees real Turkish.
    raw = turkish.deasciify(message)
    text = _normalize(raw)
    # Someone talking about THEMSELVES is not asking for a company analysis.
    # "kafam çok dolu, ne yapmalıyım" contains "ne yap" and was being answered
    # with red-team objections over business signals.
    if _has(text, _PERSONAL_MARKERS):
        return RouteDecision(SIMPLE_CONVERSATION)
    if _has(text, ("merhaba", "selam", "sen nesin", "ne yapabiliyorsun", "kimsin", "hello",
                   "nasılsın", "nasilsin", "yardımcı olabilirsin", "yardimci olabilirsin",
                   "neler yapabilirsin", "ne yapabilirsin",
                   # Ordinary Turkish small talk. Without these a greeting fell
                   # through to reasoning and was answered from company data.
                   "naber", "napıyorsun", "napiyorsun", "naptın", "naptin",
                   "naptınız", "naptiniz", "ne yapıyorsun", "ne yapiyorsun",
                   "nasıl gidiyor", "nasil gidiyor",
                   "günaydın", "gunaydin", "iyi akşamlar", "iyi aksamlar",
                   "iyi günler", "iyi gunler", "teşekkür", "tesekkur", "sağ ol",
                   "sag ol", "eyvallah", "görüşürüz", "gorusuruz", "hey", "hi ")):
        return RouteDecision(SIMPLE_CONVERSATION)
    # A question ABOUT what to do is not an instruction to do it. Checked
    # first so "ne yapmalıyız" can never be read as the imperative "yap".
    # "plan çıkar" is a request FOR a plan, not an instruction to remove
    # something -- without it the management prompt would be read as an action.
    asks_for_advice = _has(text, ("ne yap", "ne öneriyorsun", "ne oneriyorsun",
                                  "ne yapmalı", "ne yapmali", "yapılması", "yapilmasi",
                                  "plan çıkar", "plan cikar"))
    verbs = ("değiştir", "degistir", "durdur", "başlat", "baslat", "gönder",
             "gonder", "yayınla", "yayinla", "publish", "yap", "ayarla",
             "güncelle", "guncelle", "artır", "artir", "azalt", "indir",
             "sil", "kapat", "iptal et",
             # "Ürünü siteden kaldır" reached the model instead of the
             # firewall: removal and activation verbs were missing entirely.
             "kaldır", "kaldir", "çıkar", "cikar", "ekle", "düşür", "dusur",
             "yükselt", "yukselt", "aktifleştir", "aktiflestir",
             "pasifleştir", "pasiflestir", "devre dışı", "devre disi")
    if not asks_for_advice and _has_command(text, verbs, raw):
        return RouteDecision(ACTION_REQUEST)
    if _has(text, ("kampanya hazırla", "kampanya hazirla", "kampanya kur",
                   "reklam kampanyası", "reklam kampanyasi", "kreatif", "creative",
                   "reklam metni", "copy yaz", "içerik planı", "icerik plani",
                   "instagram plan", "sosyal medya plan", "landing page",
                   "açılış sayfası", "acilis sayfasi", "cro",
                   "reklam performansımızı", "reklam performansimizi",
                   "reklam neden çalışmıyor", "reklam neden calismiyor",
                   "yeni kampanya", "kampanya hazır")):
        return RouteDecision(AGENCY_REQUEST)
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


# Kayıt basina gosterilecek en fazla satir. Panelde "16 acik dosya" yazip
# kayitlari atmak, okuyana tiklanacak hicbir sey birakmiyordu -- sayinin
# arkasindaki satirlar tasinmazsa detay ekrani yazilamaz.
DETAIL_LIMIT = 12


def _age_days(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(" ", "T", 1)
    text = re.sub(r"([+-]\d{2})$", r"\1:00", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0


def _line(*parts: Any) -> str:
    return " · ".join(str(p).strip() for p in parts if p not in (None, "", "None"))


def _detail_rows(name: str, records: list[dict[str, Any]]) -> list[str]:
    """Ozetin arkasindaki gercek satirlar.

    Kisisel veri tasinmaz: musteri adi ve ham mesaj metni hicbir sorguda yok,
    siparis satirinda customer_id yerine siparis_no gosterilir.
    """
    rows: list[str] = []
    for record in records[:DETAIL_LIMIT]:
        if name == "open_work":
            age = _age_days(record.get("zaman"))
            rows.append(_line(record.get("tur"), record.get("anahtar"),
                              record.get("yapilacak"),
                              f"{age:.0f} gun" if age is not None else None))
        elif name == "crm_unanswered":
            rows.append(_line(record.get("kanal"), record.get("musteri_takma"),
                              f"{record.get('mesaj_sayisi')} mesaj",
                              f"{record.get('bekleme_saat')} saat bekliyor"))
        elif name == "sales_orders":
            rows.append(_line(record.get("siparis_no"), record.get("gun"),
                              record.get("kanal"), record.get("odeme_durumu"),
                              record.get("toplam")))
        elif name == "operations_shipments":
            rows.append(_line(record.get("siparis_no"), record.get("durum"),
                              record.get("tasiyici"), record.get("sehir"),
                              "ALARM" if record.get("alarm") else None))
        elif name == "advertising_performance":
            rows.append(_line(record.get("kampanya_adi"), record.get("ad_adi"),
                              f"harcama {record.get('harcama')}",
                              f"CTR {record.get('ctr_yuzde')}"))
        elif name == "ecommerce_profitability":
            rows.append(_line(record.get("urun_adi"), f"ciro {record.get('ciro_net')}",
                              f"marj %{record.get('brut_marj_yuzde')}"))
        else:
            first = {k: v for k, v in list(record.items())[:4]
                     if k not in ("source", "entity_id", "source_record_id")}
            rows.append(_line(*first.values()))
    return [r for r in rows if r]


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
            evidence.append({"ref": got.source, "summary": _summarize(name, got.records),
                             "rows": _detail_rows(name, got.records),
                             "total": len(got.records)})
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


def _details_payload(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Panelin acilir listede gosterecegi bloklar. Satiri olmayan kanit atlanir."""
    return [{"ref": item["ref"], "summary": item.get("summary", ""),
             "total": item.get("total"), "rows": item.get("rows", [])}
            for item in evidence if item.get("rows")]


def _synthesize(message: str, intent: str, memory: Any, started: float,
                escalate: bool | None = None) -> dict[str, Any]:
    if escalate is None:
        escalate = needs_escalation(message)
    evidence, missing = _gather(message, memory)
    try:
        result = _router().synthesize(message, evidence, missing_data=missing,
                                      escalate=escalate,
                                      history=conversation_memory.history(turns=3))
    except ModelUnavailable as exc:
        # Never speechless: the deterministic surface still answers.
        return _response(message, intent, "AI_PROVIDER_UNAVAILABLE",
            "Bu soru serbest muhakeme gerektiriyor; şu anda hiçbir model provider "
            "yanıt veremedi. Kanıtlar okundu ancak yorumlanamadı.",
            evidence_refs=tuple(item["ref"] for item in evidence),
            missing_data=tuple(missing), started=started,
            details=_details_payload(evidence),
            provider_states=_router().provider_states(), error_detail=str(exc))
    payload = result.to_dict()
    return _response(message, intent, "ANSWERED", result.answer,
                     evidence_refs=result.evidence_refs,
                     missing_data=result.missing_data, started=started,
                     model=result.model, model_calls=result.model_calls,
                     confidence=result.confidence, tier=result.tier,
                     details=_details_payload(evidence),
                     context_chars=result.context_chars,
                     prompt_tokens=payload["prompt_tokens"],
                     completion_tokens=payload["completion_tokens"],
                     provider_states=result.provider_states)



# --- specialist analysis -------------------------------------------------
_POOL: SpecialistPool | None = None


def _pool(memory: Any) -> SpecialistPool:
    global _POOL
    if _POOL is None:
        _POOL = SpecialistPool(memory)
    return _POOL


def _analysis(message: str, memory: Any, started: float) -> dict[str, Any]:
    """Planner shape -> minimum sufficient specialists -> fusion / red team /
    strategy / managing director -> AI synthesis over what they found.

    The pool selects the specialists; all twenty never run. Its findings are
    the evidence the model is given, so the narrative can only restate what a
    specialist actually concluded from a real query.
    """
    text = _normalize(message)
    domains = [d for d, terms in _DOMAIN_TERMS.items() if _has(text, terms)]
    if not domains:
        domains = ["sales", "ecommerce", "advertising", "crm", "operations"]
    entities = ("VIREON",) if "vireon" in text else ()

    plan = plan_request(message)
    try:
        report = _pool(memory).execute(message, tuple(domains), entities=entities)
    except Exception as exc:  # noqa: BLE001 - a pool failure must not end the turn
        return _response(message, ANALYSIS_REQUEST, "PROPOSED",
            "Analiz isteği Planner'a aktarıldı; uzman havuzu bu turda çalışamadı.",
            missing_data=tuple(plan.required_internal_data), started=started,
            model="deterministic-planner", plan=plan.to_dict(),
            execution_started=False, error_detail=f"{type(exc).__name__}: {exc}")

    evidence: list[dict[str, Any]] = []
    refs: list[str] = []
    for finding in report["findings"]:
        if not finding.get("claim"):
            continue
        evidence.append({"ref": finding["specialist_id"], "summary": finding["claim"]})
        refs.extend(finding.get("evidence_refs") or [])

    missing = tuple(sorted({finding["specialist_id"] for finding in report["findings"]
                            if finding.get("status") == "DATA_UNAVAILABLE"}))
    try:
        # Specialist findings are the hard case: weighing several domains and a
        # red-team pass against each other is what the stronger model is for.
        result = _router().synthesize(message, evidence, missing_data=missing,
                                      escalate=needs_escalation(message))
        answer, model, calls = result.answer, result.model, result.model_calls
        confidence, tier = result.confidence, result.tier
    except ModelUnavailable:
        # The specialists still did their work; report it plainly.
        answer = "\n".join(f"- [{f['specialist_id']}] {f['claim']}"
                            for f in report["findings"] if f.get("claim"))
        model, calls, confidence, tier = None, 0, "MEDIUM", "DETERMINISTIC"

    return _response(message, ANALYSIS_REQUEST, "PROPOSED", answer,
        evidence_refs=tuple(dict.fromkeys(refs)), missing_data=missing,
        started=started, model=model, model_calls=calls, confidence=confidence,
        tier=tier, plan=plan.to_dict(), execution_started=False,
        approval_required=True,
        specialists_selected=report["specialists_selected"],
        specialists_skipped=report["specialists_skipped"],
        fusion=report["fusion"], specialist_metrics=report["metrics"])


# --- research ------------------------------------------------------------
def _research(message: str, started: float) -> dict[str, Any]:
    """Research Controller as it stands, then synthesis over what it returned.

    Confidence travels through untouched: a thin result is reported as
    LOW_CONFIDENCE rather than dressed up as fact.
    """
    try:
        from jarvis.adapter_factory import default_factory
        from jarvis.research_controller import ResearchController
        from jarvis.research_sources import WebSearchCrawlAdapter

        # Point the adapter at the SearXNG instance that is already running on
        # this host. Without this it silently falls back to DuckDuckGo's
        # keyless HTML endpoint, which returned zero results here -- the
        # research stack was deployed but never actually connected.
        searxng = os.environ.get("RESEARCH_SEARXNG_URL", "http://127.0.0.1:8888")
        factory = default_factory()
        factory.register(WebSearchCrawlAdapter(searxng_url=searxng))
        report = ResearchController(factory).run(message)
    except Exception as exc:  # noqa: BLE001
        return _response(message, RESEARCH_REQUEST, "DATA_UNAVAILABLE",
            "Araştırma isteği tanındı ancak araştırma capability'si şu anda çalışmıyor.",
            missing_data=("fresh_research_source",), started=started,
            error_code="RESEARCH_CAPABILITY_UNAVAILABLE",
            error_detail=f"{type(exc).__name__}: {exc}")

    sources = report.get("sources") or []
    confidence_value = float(report.get("confidence") or 0.0)
    evidence = [{"ref": item.get("url") or item.get("source") or "unknown",
                 "summary": (item.get("title") or "")[:200]}
                for item in sources[:8]]
    refs = tuple(item["ref"] for item in evidence)
    low = confidence_value < 0.5 or len(sources) < 2

    if not sources:
        return _response(message, RESEARCH_REQUEST, "LOW_CONFIDENCE",
            "Araştırma çalıştı ancak doğrulanabilir kaynak bulunamadı. "
            "Bu konuda güvenilir bir sonuç üretmiyorum.",
            missing_data=("verified_research_source",), started=started,
            research_confidence=confidence_value,
            research_stop_reason=report.get("stop_reason"))

    try:
        result = _router().synthesize(
            message + ("\n\nNOT: kaynaklar sınırlı, kesin konuşma."if low else ""),
            evidence, missing_data=() if not low else ("independent_confirmation",))
        answer, model, calls = result.answer, result.model, result.model_calls
    except ModelUnavailable:
        answer = "Bulunan kaynaklar:\n" + "\n".join(f"- {item['ref']}" for item in evidence)
        model, calls = None, 0

    return _response(message, RESEARCH_REQUEST,
        "LOW_CONFIDENCE" if low else "ANSWERED", answer,
        evidence_refs=refs, started=started, model=model, model_calls=calls,
        confidence="LOW" if low else "MEDIUM",
        research_confidence=confidence_value,
        research_sources=len(sources),
        research_stop_reason=report.get("stop_reason"))


# 4 cumlelik resmi bir Turkce cevap ~180-220 token tutar; eski deger
# 160'ti ve cumle bitmeden doluyordu. Amac uzun cevap degil, TAM cevap.
CHAT_MAX_TOKENS = int(os.environ.get("JARVIS_CHAT_MAX_TOKENS", "380"))

CHAT_SYSTEM = (
    # Bu istem bir kez "sicak, sohbet eder gibi, dertlesme" tonu istiyordu ve
    # kullanici hakli olarak "fazla laubali" dedi. Ton modelin kusuru degildi,
    # buradaki talimatti. Yeni kayit: resmi, olculu, kisa.
    "Sen Jarvis'sin: L'CARLIÉ'nin analiz ve operasyon asistanısın. Resmî, ölçülü "
    "ve kısa Türkçe yazarsın.\n"
    "- Kullanıcıya 'siz' diye hitap et.\n"
    "- En fazla 4 cümle yaz. Önce cevabı ver; gerekçe gerekiyorsa tek cümle ekle.\n"
    "- Giriş ve kapanış cümlesi yazma: 'Tabii ki', 'Elbette', 'Umarım yardımcı "
    "olmuştur' gibi ifadeler kullanma.\n"
    "- Şaka, emoji, ünlem işareti ve 'harika', 'süper', 'muhteşem' gibi abartı "
    "sözcükler kullanma.\n"
    "- Gereksiz karşı soru sorma. Soru ancak görevi yapmak için gereken bir bilgi "
    "eksikse sorulur ve tek soru olur.\n"
    "- Cümleni yarım bırakma. Söyleyeceğin sığmıyorsa daha az şey söyle, "
    "cümlenin ortasında durma.\n"
    "Yeteneklerin: şirket verisini (satış, e-ticaret, reklam, CRM, operasyon) "
    "kanıtıyla okumak, analiz ve kampanya önerisi hazırlamak, web araştırması "
    "istemek. YAPAMADIKLARIN: kişisel veri veya telefon numarası bulmak, "
    "internette kişi aramak, sistemlere girmek, mesaj/reklam/fiyat değiştirmek. "
    "Böyle bir şey istenirse yapamayacağını açıkça söyle.\n"
    "Sınırlar: Şirketle ilgili sayı, tarih, ürün veya müşteri bilgisi UYDURMA -- "
    "böyle bir şey sorulursa verilere bakman gerektiğini söyle. Hiçbir işlemi "
    "kendin uygulayamazsın; onay insanındır."
)

FALLBACK_INTRO = (
    "Merhaba, ben Jarvis. Şirket verilerini kanıtlarıyla okuyabilir, analiz planı "
    "hazırlayabilir, araştırma ihtiyacını belirleyebilir ve işlem taleplerini insan "
    "onayına yönlendirebilirim. Onay olmadan dış işlem yapmam."
)


_KNOWLEDGE = company_knowledge()


def _system_for(message: str, internal_ok: bool = True) -> str:
    """Persona, then who we are, then only what this message actually needs.

    context() returns "" on a miss rather than dumping something adjacent: a
    prompt padded with the wrong document answers worse than one without it.
    """
    parts = [_chat_system()]
    identity = _KNOWLEDGE.identity()
    if identity:
        parts.append(identity)
    block = _KNOWLEDGE.context(message, internal_ok=internal_ok)
    if block:
        parts.append(block)
    return "\n\n".join(parts)


def _chat_system() -> str:
    """The persona, plus whatever the operator asked to be remembered.

    notes_block returns an empty string when nothing has been kept, so a
    fresh install pays nothing for this.
    """
    notes = conversation_memory.notes_block()
    return CHAT_SYSTEM + ("\n\n" + notes if notes else "")


# Urun listesi gun icinde degismez; her mesajda sorgu atmak gereksiz.
_CATALOGUE_TTL_S = float(os.environ.get("JARVIS_CATALOGUE_TTL_S", "3600"))
_catalogue_cache: dict[str, Any] = {"at": 0.0, "names": ()}


def _known_products(runtime: Any) -> tuple[str, ...]:
    """Katalogdaki ürün adları. Okunamazsa BOŞ döner ve ürün denetimi atlanır.

    Bos donmek burada dogru davranistir: liste yokken her buyuk harfli adi
    "uydurma" saymak, veri yoklugunu hataya cevirirdi.
    """
    import time as _time
    now = _time.time()
    if _catalogue_cache["names"] and now - _catalogue_cache["at"] < _CATALOGUE_TTL_S:
        return _catalogue_cache["names"]  # type: ignore[return-value]
    # DIKKAT: burada bir kez `sales_items` kullanildi ve bu bir HATAYDI.
    # O gorunum SATILAN urunleri verir (22 marka), katalogu degil (36).
    # Sonuc: denetim gercek bir urunu ("FEMISIA for WOMEN") uydurma sanip
    # dogru cumleyi silecekti. Bir hallusinasyon denetiminin en tehlikeli
    # hatasi yanlis pozitiftir: kullanici dogru cevabi da goremez ve
    # silinen sey ortada olmadigi icin fark edemez.
    names: tuple[str, ...] = ()
    try:
        memory = _memory(runtime)
        rows = tuple(memory._fetch("ecommerce_price").records)
        names = tuple(p.brand for p in product_catalogue(rows))
    except Exception:  # noqa: BLE001 - katalog yoklugu bir durumdur
        names = ()
    if not names:
        # Fiyat listesi okunamadi: satis kaydi eksik ama yanlis degildir.
        try:
            rows = tuple(_memory(runtime)._fetch("sales_items").records)
            names = tuple(p.brand for p in product_catalogue(rows))
        except Exception:  # noqa: BLE001
            names = ()
    _catalogue_cache.update({"at": now, "names": names})
    return names


def _guarded(answer: str, runtime: Any) -> tuple[str, dict[str, Any]]:
    """Model cevabını yayımlamadan önce denetler. Sıfır model çağrısı."""
    try:
        out = answer_guard.guard(answer, _known_products(runtime))
    except Exception:  # noqa: BLE001 - denetim cevabi engelleyemez
        return answer, {}
    meta: dict[str, Any] = {}
    if out["invented_products"]:
        meta["invented_products"] = out["invented_products"]
        meta["sentences_dropped"] = out["sentences_dropped"]
    return str(out["text"]) or answer, meta


def _chat(message: str, intent: str, started: float,
          runtime: Any = None) -> dict[str, Any]:
    """An ordinary conversational turn.

    No evidence block is assembled: this is talk, not analysis. The model is
    told plainly that it may not invent company facts, and it has no path to
    an action either way. If no provider answers, the deterministic
    introduction still stands so the user is never left without a reply.
    """
    try:
        result = _router().synthesize(message, (), system=_system_for(message), max_tokens=CHAT_MAX_TOKENS,
                                      escalate=needs_escalation(message),
                                      history=conversation_memory.history())
    except ModelUnavailable:
        return _response(message, intent, "ANSWERED", FALLBACK_INTRO,
                         started=started, model="deterministic-local")
    cevap, uyari = _guarded(result.answer, runtime)
    return _response(message, intent, "ANSWERED", cevap, started=started,
                     model=result.model, model_calls=result.model_calls,
                     tier=result.tier, **uyari)


def stream_chat(message: str, intent: str):
    """A conversational turn, streamed.

    Yields {"type": "token", "delta": ...} frames and then exactly one
    {"type": "done", "result": ...} carrying the same payload the non-streamed
    path returns, so both surfaces stay identical.
    """
    started = perf_counter()
    chunks: list[str] = []
    model = None
    calls = 0
    try:
        for delta in _router().stream_text(message, _system_for(message), max_tokens=CHAT_MAX_TOKENS,
                                           history=conversation_memory.history()):
            chunks.append(delta)
            yield {"type": "token", "delta": delta}
        model, calls = LOCAL_MODEL_NAME, 1
    except ModelUnavailable:
        chunks = []

    answer = "".join(chunks).strip()
    if not answer:
        answer, model, calls = FALLBACK_INTRO, "deterministic-local", 0
    yield {"type": "done",
           "result": _response(message, intent, "ANSWERED", answer, started=started,
                               model=model, model_calls=calls)}


_AGENCY: AgencyCapability | None = None


def _agency(memory: Any) -> AgencyCapability:
    global _AGENCY
    if _AGENCY is None:
        _AGENCY = AgencyCapability(memory)
    return _AGENCY


def _agency_details(deliverable: dict[str, Any]) -> list[dict[str, Any]]:
    """Teslimatı panelin açılır bloklarına çevirir.

    Satiri olmayan blok eklenmez: bos bir "Konseptler" basligi, is yapilmis
    izlenimi verir ama icinde bir sey yoktur.
    """
    blocks: list[dict[str, Any]] = []

    concepts = deliverable.get("creative_concepts") or []
    if concepts:
        rows = []
        for c in concepts:
            risk = c.get("regulatory_risk") or ""
            rows.append(f"{c.get('name', '?')} — {c.get('headline', '')}"
                        + (f"  [{risk}]" if risk and risk != "NONE_DETECTED_TIER1" else ""))
            rows.append(f"    {str(c.get('primary_text', ''))[:220]}")
        blocks.append({"ref": "agency:concepts",
                       "summary": f"Kreatif konseptler ({len(concepts)})",
                       "total": len(concepts), "rows": rows})

    proposals = deliverable.get("proposals") or {}
    pconcepts = proposals.get("concepts") or []
    if pconcepts:
        rows = [f"{c.get('name', '?')} — {c.get('status')}"
                + ("  (zarf üretildi)" if c.get("envelope") else "")
                + (f"  hata: {str(c.get('error'))[:80]}" if c.get("error") else "")
                for c in pconcepts]
        rows.append(f"sözleşme: {proposals.get('contract_state')}")
        rows.append(str(proposals.get("note") or ""))
        blocks.append({"ref": "agency:proposals",
                       "summary": (f"Öneri zarfları — {proposals.get('proposable', 0)} "
                                   f"önerilebilir, {proposals.get('blocked', 0)} bloklu"),
                       "total": len(pconcepts), "rows": rows})

    risks = deliverable.get("regulatory_risks") or []
    if risks:
        blocks.append({"ref": "agency:regulatory",
                       "summary": f"Mevzuat bulguları ({len(risks)})",
                       "total": len(risks),
                       "rows": [str(r)[:220] for r in risks]})

    objections = deliverable.get("red_team_objections") or []
    if objections:
        blocks.append({"ref": "agency:redteam",
                       "summary": f"Kırmızı takım itirazları ({len(objections)})",
                       "total": len(objections),
                       "rows": [f"{o.get('creative', '')}: {o.get('reason', '')}"
                                for o in objections]})

    plan = deliverable.get("test_plan") or []
    if plan:
        blocks.append({"ref": "agency:test_plan",
                       "summary": f"Test planı ({len(plan)})", "total": len(plan),
                       "rows": [f"{s.get('test', '')} — değişken: {s.get('variable', '')}"
                                f" — sabit: {s.get('hold_constant', '')}" for s in plan]})

    social = deliverable.get("social_plan") or []
    if social:
        blocks.append({"ref": "agency:social",
                       "summary": f"Sosyal plan ({len(social)} gün)", "total": len(social),
                       "rows": [f"Gün {d.get('day', '?')} · {d.get('objective', '')}"
                                f" — {d.get('topic', d.get('hook', ''))}" for d in social]})
    return blocks


def _screen_agency(deliverable: dict[str, Any], memory: Any) -> dict[str, Any]:
    """Konseptleri firewall sözleşmesine karşı tarar ve zarfları döndürür.

    Sozlesme okunamazsa ajans cikti vermeye devam eder; yalnizca zarf
    uretilmez. Sozlesmesiz uydurulmus bir zarf, zarf olmamasindan kotudur --
    onaylanabilir gorunur ama arkasinda dogrulama yoktur.
    """
    contract = None
    contract_state = "CONTRACT_UNAVAILABLE"
    try:
        from jarvis.action_contract import ContractCache
        contract = ContractCache(memory).get()
        contract_state = "VALID" if getattr(contract, "valid", False) else "INVALID"
        if contract_state != "VALID":
            contract = None
    except Exception as exc:  # noqa: BLE001 - sozlesme yoklugu bir durumdur
        contract_state = f"CONTRACT_UNAVAILABLE: {type(exc).__name__}"

    try:
        screened = screen_agency(deliverable, contract)
    except Exception as exc:  # noqa: BLE001 - tarama ajansi durduramaz
        return {"contract_state": contract_state, "error": str(exc)[:200],
                "proposable": 0, "blocked": 0, "concepts": []}

    payload = screened.to_dict() if hasattr(screened, "to_dict") else {}
    rows = list(payload.get("concepts") or [])
    payload.update({
        "contract_state": contract_state,
        "proposable": sum(1 for c in rows if c.get("status") == "PROPOSABLE"),
        "blocked": sum(1 for c in rows if c.get("status") == "BLOCKED"),
        # Zarf uretildi demek "gonderildi" demek DEGILDIR. Bu ayrimi cikti
        # tasimazsa panel "onaya gitti" gibi okunur.
        "submitted": False,
        "note": ("Zarflar üretildi ve firewall doğrulamasından geçti; "
                 "veritabanına YAZILMADI. Gönderim ayrı bir adımdır."),
    })
    return payload


def _agency_request(message: str, memory: Any, started: float) -> dict[str, Any]:
    """The Agency produces a proposal and nothing else.

    It cannot publish an ad, change a budget, pause a campaign, publish to Wix
    or Instagram, send a message or change a price -- it has no path to any of
    them. Asking it to publish still lands on the action boundary, because
    that check runs before this one.
    """
    try:
        deliverable = _agency(memory).run(message)
    except Exception as exc:  # noqa: BLE001
        return _response(message, AGENCY_REQUEST, "DATA_UNAVAILABLE",
            "Agency talebi tanındı ancak kanıt okunamadığı için çıktı üretilmedi.",
            started=started, error_detail=f"{type(exc).__name__}: {exc}")

    # Kopru: her konsept mevzuat kapisindan ve firewall dogrulamasindan gecer.
    # Bu adim daha once YAZILMIS ama hic cagrilmamisti; fikir firewall'a
    # ugramadan cope gidiyordu. Zarf uretilir, veritabanina YAZILMAZ --
    # gonderim ayri ve bilincli bir adimdir.
    deliverable["proposals"] = _screen_agency(deliverable, memory)

    return _response(message, AGENCY_REQUEST, "PROPOSED",
        deliverable.get("summary") or "Agency önerisi hazırlandı.",
        evidence_refs=tuple(deliverable.get("evidence_refs") or ()),
        missing_data=tuple(deliverable.get("data_gaps") or ()),
        started=started, model=deliverable.get("model"),
        model_calls=deliverable.get("model_calls", 0),
        approval_required=True, execution_started=False,
        agency=deliverable, roles_used=deliverable.get("roles_used"),
        details=_agency_details(deliverable),
        product=deliverable.get("product"),
        product_state=deliverable.get("product_state"),
        objective=deliverable.get("objective"))


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
        return _chat(message, decision.intent, started, runtime)
    # The action boundary is settled before any model can be reached. A
    # request to change something must land on the firewall path whatever
    # else it looks like.
    if decision.intent == ACTION_REQUEST:
        return _action(message, started)
    # The deterministic gate comes next: a question Company Memory answers
    # exactly must never cost a model call. Only genuinely open-ended wording
    # gets past this line.
    if decision.intent in (COMPANY_QUERY, GENERAL_REASONING) \
            and should_use_model(message):
        return _synthesize(message, decision.intent, _memory(runtime), started)
    if decision.intent == AGENCY_REQUEST:
        return _agency_request(message, _memory(runtime), started)
    if decision.intent == RESEARCH_REQUEST:
        return _research(message, started)
    if decision.intent == ANALYSIS_REQUEST:
        return _analysis(message, _memory(runtime), started)
    if decision.intent == COMPANY_QUERY:
        return _company(message, decision.domain or "company", _memory(runtime), started)
    # Anything left is ordinary conversation, not company analysis.
    return _chat(message, decision.intent, started)
