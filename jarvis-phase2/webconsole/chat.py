"""Chat: a thin router in front of the REAL, already-built Jarvis pipeline.

This does not implement a second Jarvis. Every answer comes from one of:

  * jarvis.shadow.ShadowRunner.handle(intent)  -- the exact SHADOW pipeline
    verified in Phase 2C/2D (planner -> ContextCompiler -> capability
    registry -> Action Firewall). ContextCompiler already deterministically
    resolves entity ("vireon"), task/proposal, agenda, and capability-gap
    questions from keywords; passing the operator's message straight into it
    reuses that exact routing rather than shortcutting it.
  * jarvis.operator.OperatorSession -- for "pending proposals" and
    "why was proposal N created", which need the human_approver-only
    ai_get_pending_actions() surface ShadowRunner does not call.

Which of these to use is decided by intents.classify() -- a small, explicit
Turkish/English capability table (see intents.py), not a growing pile of
if/elif substring checks. Only for JUDGEMENT-shaped requests with no
retrievable topic does this return REQUIRES_REASONING_CAPABILITY --
truthfully, never a fabricated answer.

`route()` returns the final, complete answer. `stream()` wraps it with the
real intermediate steps as status events, for the UI's streamed presentation
-- see app.py's /api/chat/stream. Both call the exact same underlying logic,
so the streamed and non-streamed paths can never disagree.
"""
from __future__ import annotations

import re
from typing import Any, Iterator

import intents
import conversation

from jarvis import conversation_memory

ACTION_ID_RE = re.compile(r"\b(\d{1,10})\b")

STAGE_LABELS = {
    "PROPOSALS": ("Bekleyen öneriler kontrol ediliyor",),
    "WHY": ("İlgili proposal aranıyor", "Kanıtlar okunuyor"),
    "JUDGEMENT_GROUNDED": ("Company Memory okunuyor", "Kanıtlar değerlendiriliyor"),
    "JUDGEMENT_UNGROUNDED": (),
    "INSPECT_OR_STATUS": ("Company Memory okunuyor", "Kanıtlar doğrulanıyor"),
    "UNCLASSIFIED": ("Company Memory okunuyor",),
    "TASARIM": ("Şablon kütüğü okunuyor", "Üretilebilirlik denetleniyor"),
}


def _answer(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, **fields}


def _tasarim_cevabi(text: str) -> dict[str, Any]:
    """Tasarım isteğine GERÇEK bir cevap üretir — kütüğe bakarak.

    Panelde "katalog istiyorum" yazıldığında bugüne kadar hiçbir şey
    olmuyordu: cümle hiçbir yeteneğe uymuyor, Company Memory'de "katalog"
    diye kanıt aranıyor, bulunamayınca boş dönüyordu.

    Artık cevap kütükten geliyor ve üç durumu ayırıyor. Hiçbirinde
    uydurma yok; eksik olan neyse adıyla söyleniyor.
    """
    from jarvis import tasarim

    tur = tasarim.is_turu_cikar(text)
    try:
        ozet = tasarim.kutuk_ozet()
        hepsi = tasarim.kutuk()
    except Exception as exc:  # noqa: BLE001
        return _answer("ERROR", message=f"şablon kütüğü okunamadı: {exc}")

    if not tur:
        # Ne istendiği çıkarılamadı: TAHMİN ETME, seçenekleri göster.
        uretilebilir = sorted({k["is_turu"] for k in hepsi if k["uretilebilir"]})
        tanimli = sorted({k["is_turu"] for k in hepsi})
        return _answer(
            "TASARIM",
            message=("Ne üretmemi istediğinizi cümleden çıkaramadım. "
                     f"Kütükte {ozet['toplam']} şablon tanımlı, "
                     f"{ozet['hazir']} tanesi bugün üretilebilir."),
            uretilebilir=uretilebilir, tanimli=tanimli)

    eslesen = [k for k in hepsi if k["is_turu"] == tur]
    hazir = [k for k in eslesen if k["uretilebilir"]]

    if hazir:
        k = hazir[0]
        alanlar = list((k.get("alan_haritasi") or {}).keys()) or k["beklenen_alanlar"]
        return _answer(
            "TASARIM",
            message=(f"«{k['ad']}» şablonu hazır ({k['sablon_kodu']}). "
                     "Üretmek için şu alanların içeriği gerekiyor."),
            is_turu=tur, sablon=k["sablon_kodu"], olcu=f"{k['en']}x{k['boy']}",
            gereken_alanlar=alanlar,
            marka_kurali=k.get("marka_kurallari"),
            mevzuat_kurali=k.get("mevzuat_kurallari"),
            not_=("Metin önce mevzuat kapısından geçer; geçemezse tasarım "
                  "üretilmez. Üretilen tasarımı yalnız siz onaylayabilirsiniz."))

    if eslesen:
        k = eslesen[0]
        olcu = (f"{k['en_mm']}x{k['boy_mm']} mm @{k['dpi']} dpi"
                if k.get("en_mm") else f"{k['en']}x{k['boy']} px")
        return _answer(
            "TASARIM",
            message=(f"«{k['ad']}» kütükte TANIMLI ama henüz üretilemiyor. "
                     "Şartnamesi hazır; eksik olan tek şey bu ölçüde bir "
                     "Canva tasarımı açıp alanlarını işaretlemek."),
            is_turu=tur, sablon=k["sablon_kodu"], olcu=olcu,
            gereken_alanlar=k["beklenen_alanlar"],
            motor=k.get("motor"),
            marka_kurali=k.get("marka_kurallari"),
            mevzuat_kurali=k.get("mevzuat_kurallari"))

    return _answer(
        "TASARIM",
        message=(f"'{tur}' kütükte hiç tanımlı değil. Önce şartnamesi "
                 "yazılmalı: ölçü, doldurulacak alanlar, marka ve mevzuat "
                 "kuralı."),
        is_turu=tur)


def route(message: str, runtime, operator) -> dict[str, Any]:
    """runtime: jarvis.shadow.ShadowRunner instance. operator: jarvis.operator.OperatorSession."""
    text = (message or "").strip()
    if not text:
        return _answer("ERROR", message="empty message")

    capability = intents.classify(text)

    if capability == "TASARIM":
        # 🔴 Model çağrısı YOK. Cevap tamamen kütükten; uydurma imkânsız.
        sonuc = _tasarim_cevabi(text)
        _remember(text, sonuc)
        return sonuc

    if capability == "WHY":
        match = ACTION_ID_RE.search(text)
        if not match:
            return _answer("ERROR", message="proposal id not found in message")
        proposal = operator.inspect(int(match.group(1)))
        if proposal is None:
            return _answer("ANSWER", source="operator.inspect", data=None,
                           text=f"Proposal {match.group(1)} bekleyenler arasında bulunamadı "
                                "(zaten karara bağlanmış olabilir).")
        return _answer("ANSWER", source="operator.inspect", data=proposal,
                       text=(f"Proposal {proposal['action_id']} ({proposal['action_type']}, "
                            f"risk {proposal['risk_class']}): {proposal['payload'].get('reason', '')}"))

    if capability == "PROPOSALS":
        pending = operator.list_pending()
        return _answer("ANSWER", source="operator.list_pending", data=pending,
                       text=(f"{len(pending)} bekleyen proposal var." if pending
                             else "Bekleyen proposal yok."))

    # Every intent goes to the conversational router, GENERAL_REASONING
    # included. It used to be the one exception, and it fell through to the
    # Phase 2 shadow path below, which answers a chat message with whatever
    # Company Memory happened to return -- "Naber" came back as
    # "1 kayıt bulundu (kaynak: postgres:decision_summary)".
    result = conversation.route(text, runtime)
    _remember(text, result)
    return result

    if capability == "JUDGEMENT":
        # A judgement question with no grounded topic word cannot be answered
        # from retrievable data. If it DOES carry a topic, fall through to
        # the real Jarvis pipeline below -- e.g. "Vireon için ne öneriyorsun?"
        # still has an entity to resolve.
        has_topic = any(term in intents.normalize(text) for term in
                        ("vireon", "durum", "sistem", "gündem", "gundem", "task", "proposal"))
        if not has_topic:
            return _answer("REQUIRES_REASONING_CAPABILITY",
                           message=("Bu soru bir KONUYA bağlanmadığı için şirket verisinden "
                                    "cevaplanamıyor. Model bağlı ve çalışıyor; eksik olan "
                                    "hangi ürün, kanal ya da dönem hakkında konuştuğumuz. "
                                    "Konuyu yazın, aynı soruyu kanıta bağlayıp cevaplayayım "
                                    "(ör. \"HYDRAVIE için ne öneriyorsun?\")."))

    result = runtime.handle(text)
    envelope = result["envelope"]
    context = result["context"]
    facts = context.get("facts") or []
    capability_analysis = context.get("capability_analysis")

    summary_parts = []
    if context.get("entity"):
        summary_parts.append(f"Varlık: {context['entity']}")
    if capability_analysis:
        gaps = capability_analysis.get("gaps") or []
        summary_parts.append(
            f"{len(capability_analysis.get('required_capabilities', []))} yetenek incelendi, "
            f"{len(gaps)} eksik/bloke." if gaps else "İncelenen yeteneklerde eksik yok."
        )
    elif facts:
        summary_parts.append(f"{len(facts)} kayıt bulundu (kaynak: {', '.join(envelope['evidence_refs'])}).")
    else:
        summary_parts.append("İlgili kayıt bulunamadı.")

    return _answer("ANSWER", source="jarvis.shadow",
                   text=" ".join(summary_parts),
                   data={"envelope": envelope, "context": context, "shadow": result.get("shadow"),
                        "capability": result.get("capability")})


def _remember(message: str, result: dict[str, Any]) -> None:
    """One place records the thread, so every surface -- streamed or not --
    remembers the same conversation."""
    conversation_memory.record(message, result.get("answer") or result.get("text") or "",
                               intent=str(result.get("intent") or ""))


def stream(message: str, runtime, operator) -> Iterator[dict[str, Any]]:
    """Yields {"type": "stage", "label": ...} events, then exactly one
    {"type": "done", "result": <route() output>} event.

    Coarse-grained by design: jarvis.shadow / jarvis.operator are not
    instrumented internally (they stay untouched), so stages describe the
    real step about to run, not a token-by-token trace. This is the same
    wire shape a future token-streaming model router would extend --
    additional {"type": "token", "delta": ...} events between stages and
    "done", nothing else changes.
    """
    text = (message or "").strip()
    capability = intents.classify(text) if text else "UNCLASSIFIED"
    if capability == "JUDGEMENT":
        has_topic = any(term in intents.normalize(text) for term in
                        ("vireon", "durum", "sistem", "gündem", "gundem", "task", "proposal"))
        capability = "JUDGEMENT_GROUNDED" if has_topic else "JUDGEMENT_UNGROUNDED"
    decision = conversation.classify(text)
    if decision.intent in (conversation.SIMPLE_CONVERSATION,
                           conversation.GENERAL_REASONING):
        # Conversation streams: the reply appears word by word instead of
        # after the whole thing is generated.
        for frame in conversation.stream_chat(text, decision.intent):
            if frame.get("type") == "done":
                _remember(text, frame.get("result") or {})
            yield frame
        return
    for label in STAGE_LABELS.get(capability, STAGE_LABELS["UNCLASSIFIED"]):
        yield {"type": "stage", "label": label}
    yield {"type": "done", "result": route(message, runtime, operator)}
