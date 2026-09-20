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
from jarvis import answer_guard, consensus
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
    """Kalip metinde geciyor mu. Bosluklu yazilan kalip KELIME SINIRI ister.

    OLCULDU (20.09.2026): selamlasma tablosundaki "hi " kalibi Ingilizce
    is sorularini sohbet sayiyordu. Sebep _normalize'in son satiri --
    " ".join(text.split()) bastaki ve sondaki boslugu SILIYOR, yani "hi "
    kalibi "hi" oluyor ve w-hi-ch, t-hi-s icinde esleiyor. Kalibi yazan
    kisi tam bunu onlemek icin boslugu koymustu; kod onu siliyordu.

    Sonuc: "What are our sales this month?" SIMPLE_CONVERSATION'a dustu,
    kanit toplanmadi ve sirket rakamlari kanitsiz uretildi.

    Kalibi silmek yerine niyeti calistiriliyor: terimde bosluk varsa
    eslesme kelime sinirinda aranir. Boslugsuz kaliplarin davranisi
    DEGISMEDI -- tablodaki yuzlerce kalip aynen calismaya devam eder.
    """
    dolgulu = f" {text} "
    for term in terms:
        cekirdek = _normalize(term)
        if not cekirdek:
            continue
        if term != term.strip():          # yazar sinir istemis
            if f" {cekirdek} " in dolgulu:
                return True
        elif cekirdek in text:
            return True
    return False


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
    # Selamlasma kalibi IS SORUSUNUN ICINDE gecebilir: "satislarimiz nasil
    # gidiyor" cumlesi "nasil gidiyor" tasir ama sohbet degildir. OLCULDU --
    # o soru sohbet sayilinca sistem elindeki satis verisini kullanicidan
    # istedi. Mesaj bir is alani adi tasiyorsa kalip gecersizdir.
    if _is_pure_small_talk(raw) and _has(text, ("merhaba", "selam", "sen nesin", "ne yapabiliyorsun", "kimsin", "hello",
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
                   "yeni kampanya", "kampanya hazır")) or _wants_production(raw):
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
    # Cekimli bicimler: yukaridaki sabit dizgiler "sattik", "satildi",
    # "harcadik", "urunlerimiz" gibi bicimleri GORMEZ. OLCULDU: "Son 30
    # gunde kac adet urun sattik?" bu satira gelmeden GENERAL_REASONING'e
    # dusuyor ve veriye hic bakilmadan "erisimim yok" cevabi doniyordu.
    domains = _domains_of(raw)
    if domains:
        return RouteDecision(COMPANY_QUERY, domains[0])
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


# Sorunun hangi rakami istedigi. Turkce cekim tuzagina girmemek icin kok
# oneki kullanilir: "adedi", "adetler", "kac adet" hepsi "adet" ile baslar.
_ADET_ROOTS = ("adet", "kac urun", "kac tane", "miktar")
_CIRO_ROOTS = ("ciro", "gelir", "kazanc", "hasilat", "tl")


def _sales_answer(message: str, orders: list[dict[str, Any]], memory: Any) -> str:
    """Satış sorusuna gerçek rakamla, ölçüm çekincesiyle cevap verir.

    Onceki hali yalnizca `olcumde` satirlarini sayiyordu ve OLCULDU:
    64 adet / 68.394,59 TL gercek satis varken "0 siparis, 0.00 TL"
    yaziyordu. Bunu okuyan satis olmadigini sanir.

    Rakamı saklamak yerine cekincesiyle vermek dogru davranistir: sayi
    gercektir, "dogrulanmis ciro" sayilmamasinin sebebi ayrica soylenir.
    """
    try:
        items = memory._fetch("sales_items").records
    except Exception:  # noqa: BLE001 - kalem okunamazsa siparisle yetinilir
        items = []

    adet = sum(int(row.get("adet") or 0) for row in items)
    kalem_ciro = sum(float(row.get("satir_ciro_net") or 0) for row in items)
    beyan = sum(float(row.get("ciro_beyan_edilmis_net") or 0) for row in orders)
    dogrulanmis = sum(float(row.get("ciro_dogrulanmis_net") or 0) for row in orders)
    olcumde = sum(1 for row in orders if row.get("olcumde"))

    text = _ascii_fold(message)
    if any(root in text for root in _ADET_ROOTS) and items:
        bas = (f"{adet} adet ürün satıldı ({len(items)} sipariş kalemi, "
               f"{len(orders)} siparişte).")
    elif any(root in text for root in _CIRO_ROOTS) or not items:
        bas = f"{len(orders)} siparişte toplam {kalem_ciro:,.2f} TL net ciro var."
    else:
        bas = (f"{len(orders)} sipariş, {len(items)} kalem, {adet} adet ürün; "
               f"toplam {kalem_ciro:,.2f} TL net ciro.")

    parcalar = [bas]
    # Beyan ile dogrulanmis ayri durur: kayitli bir olcumde ciro %18,8
    # sisik cikmisti ve ikisini birlestirmek o hatayi geri getirirdi.
    if dogrulanmis and abs(dogrulanmis - beyan) > 0.01:
        parcalar.append(f"Bunun {dogrulanmis:,.2f} TL'si ödeme tarafından "
                        f"doğrulanmış, {beyan:,.2f} TL'si beyan.")
    if olcumde == 0 and orders:
        # SIFIR GOSTERMEK YERINE SEBEBINI SOYLE.
        parcalar.append("Siparişlerin hiçbiri ölçüm penceresinde değil, bu yüzden "
                        "resmî ölçümde 'doğrulanmış ciro' olarak sayılmıyorlar; "
                        "rakamlar yine de gerçek satışlardır.")
    elif orders:
        parcalar.append(f"{olcumde} sipariş ölçüm penceresinde.")
    return " ".join(parcalar)


def _company(message: str, domain: str, memory: Any, started: float) -> dict[str, Any]:
    try:
        if domain == "crm":
            evidence = memory._fetch("crm_unanswered")
            count = len(evidence.records)
            longest = max((float(row.get("bekleme_saat") or 0) for row in evidence.records), default=0)
            answer = (f"Evet, {count} cevapsız müşteri konuşması var. En uzun bekleme yaklaşık "
                      f"{longest:.1f} saat." if count else "Cevapsız müşteri konuşması görünmüyor.")
        elif domain == "brief":
            evidence = memory._fetch("gunluk_brief")
            answer = _brief_answer(evidence.records)
        elif domain == "gundem":
            evidence = memory._fetch("agenda")
            answer = _gundem_answer(evidence.records)
        elif domain == "advertising" and _kreatif_sorusu(message):
            evidence = memory._fetch("kreatif_performans")
            answer = _kreatif_answer(evidence.records)
        elif domain == "advertising":
            evidence = memory._fetch("advertising_performance")
            latest = [row for row in evidence.records if row.get("pencere") == 30]
            spend = sum(float(row.get("harcama") or 0) for row in latest)
            answer = (f"30 günlük görünümde {len(latest)} reklam kaydı ve toplam {spend:,.2f} TL "
                      "harcama var. Meta satış iddiaları ticari doğrulama olmadan kesin satış sayılmadı.")
        elif domain == "sales":
            evidence = memory._fetch("sales_orders")
            answer = _sales_answer(message, evidence.records, memory)
        elif domain == "ecommerce":
            evidence = memory._fetch("urun_karti")
            answer = _urun_karti_answer(message, evidence.records)
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
# Alan kokleri. Kelime bu koklerden biriyle BASLIYORSA o alana sayilir.
# Lemma tek basina yetmiyor: zeyrek "satan" ve "satildi" icin `unk` donuyor
# (olculdu), ama ikisi de acikca satisla ilgilidir.
_DOMAIN_ROOTS = {
    "crm": ("musteri", "cevapsiz", "konusma", "crm", "abone"),
    "advertising": ("reklam", "harca", "roas", "ctr", "cpa", "cpc", "kampanya",
                    "gosterim", "tiklama", "butce",
                    # Kreatif sorulari da reklam alanidir.
                    "kreatif", "metin", "baslik", "gorsel", "video",
                    "frekans", "yorgun"),
    "sales": ("sat", "siparis", "ciro", "gelir", "kazanc", "adet"),
    "ecommerce": ("urun", "fiyat", "marj", "stok", "katalog", "indirim",
                  "eticaret", "sepet", "donusum"),
    "operations": ("operasyon", "kargo", "gonderi", "teslimat", "iade"),
    # Gundem/bekleyen is sorulari. Bunlar olmadan "bekleyen isler neler"
    # sorusu yerel modele dusuyor ve model uyduruyordu.
    "gundem": ("gundem", "bekleyen", "hatirlat", "yapilacak", "acik is",
               "acik soru", "sirada", "onceli", "takip"),
    # Gunluk yonetici ozeti. Uretiliyordu ama kimse okuyamiyordu.
    "brief": ("brief", "brifing", "ozet", "gunluk rapor", "sabah",
              "yonetici", "durum raporu"),
}

# --- INGILIZCE KOKLER -------------------------------------------------
# NEDEN VAR
# Sirket sorusu Ingilizce sorulunca tablo onu tanimiyordu ve soru
# COMPANY_QUERY yerine GENERAL_REASONING'e dusuyordu: kanit hic
# toplanmiyor, cevabi model kendi uretiyor. OLCULDU -- "What are our
# sales this month?" evidence_refs [] ile cevaplandi; dogru rakam
# vermesi kanittan degil, o rakamin sohbet gecmisinde bulunmasindandi.
# Gecmiste olmasaydi uydururdu.
#
# Operator Turkce yaziyor; Ingilizce cumleler cogunlukla SES TANIMANIN
# yanlis cozmesiyle geliyor. Yine de veriye dayanan bir soru, hangi
# dilde gelirse gelsin veriye gitmeli.
#
# YANLIS POZITIF KONTROLU
# Esleme kok ONEKI ile yapiliyor ve kelime en az _MIN_ROOT_WORD (4) harf
# olmali. Bu yuzden kisa ve Turkce kelimelerin icine gizlenebilecek
# kokler BILEREK DISARIDA: "ad" (Turkce "adet"/"adres" ile carpisir),
# "sale" degil "sales" degil -- "sale" Turkce bir kelimeyi kesmiyor ama
# listeyi dar tutmak icin yalniz olculen sorularda gecen kokler alindi.
_INGILIZCE_KOKLER = {
    "sales": ("sale", "revenu", "order", "income", "earning"),
    "advertising": ("advertis", "campaign", "spend", "spent", "budget",
                    "impression", "click"),
    "ecommerce": ("product", "price", "pricing", "stock", "discount",
                  "catalog", "margin", "cart"),
    "crm": ("customer", "message", "unanswered", "subscriber"),
    "operations": ("shipping", "shipment", "delivery", "refund"),
}
for _alan, _kokler in _INGILIZCE_KOKLER.items():
    _DOMAIN_ROOTS[_alan] = _DOMAIN_ROOTS[_alan] + _kokler

# Bilinen lemmalar. "sattik" -> satmak, "harcadik" -> harcamak (olculdu).
_DOMAIN_LEMMAS = {
    "crm": ("müşteri", "konuşmak", "abone"),
    "advertising": ("harcamak", "reklam", "kampanya", "tıklamak", "göstermek"),
    "sales": ("satmak", "satış", "sipariş", "ciro", "gelir", "adet"),
    "ecommerce": ("ürün", "fiyat", "stok", "katalog", "indirim"),
    "operations": ("kargo", "gönderi", "teslimat", "iade"),
}

# Kok onekinin uygulanmasi icin en az kelime uzunlugu. "sat" koku 3 harf;
# 4 harften kisa kelimelerde ("sat" emri gibi) aramak gereksiz gurultu uretir.
_MIN_ROOT_WORD = 4

# Kisa para birimleri kok esigine takilir: _MIN_ROOT_WORD 4, "tl" ise 2 harf.
# Koke eklemek SESSIZCE ise yaramazdi. Bu yuzden ayri ve TAM KELIME olarak
# karsilastirilir -- alt dizgi degil, yoksa "tatli"/"hatlari" yanlis eslesir.
_PARA_KELIMELERI = frozenset((
    "tl", "try", "lira", "liraya", "liradan", "liralik", "liralık",
))
# Cok kelimeli tutar sorulari. Bunlar kelime degil KALIP oldugu icin
# birlesik metinde aranir; bir kelimenin icine gizlenemezler.
_TUTAR_KALIPLARI = ("ne kadar", "kac para", "kaca satiliyor", "kaca satiyoruz")


# Uretilecek sey. "kampanyasi", "kampanyasini" -> lemma "kampanya" (olculdu).
_PRODUCTION_OBJECTS = ("kampanya", "kreatif", "reklam metni", "reklam metin",
                       "icerik plan", "sosyal medya plan", "gonderi plan",
                       "aci", "konsept", "brief", "slogan", "basl")
_PRODUCTION_OBJECT_LEMMAS = ("kampanya", "kreatif", "konsept", "slogan", "başlık")

# Uretim fiilleri. Olculdu: hazirla/hazirlar -> hazirlamak,
# uretelim -> uretmek, onerir -> onermek, kurgula -> kurgulamak.
_PRODUCTION_VERBS = ("hazirla", "uret", "yaz", "kurgula", "oner", "olustur",
                     "tasarla", "gelistir", "cikar", "planla", "kur")
# CRO cumleleri uretim FIILI tasimayabilir ("donusumu artiralim") ama yine
# de ajans isidir. OLCULDU: "Acilis sayfamizin donusumunu artiralim" hicbir
# ajans kalibina takilmiyordu ve COMPANY_QUERY'e dusuyordu.
_CRO_ROOTS_AGENCY = ("acilis sayfa", "landing page", "urun sayfa", "sepet",
                     "donusum", "checkout")

_PRODUCTION_VERB_LEMMAS = ("hazırlamak", "üretmek", "yazmak", "kurgulamak",
                           "önermek", "oluşmak", "tasarlamak", "geliştirmek",
                           "planlamak", "kurmak")


def _wants_production(message: str) -> bool:
    """Bir şey ÜRETİLMESİ isteniyor mu? Nesne + fiil birlikte aranır.

    Sabit dizgi aramak Turkcede kirilgan: "kampanya hazir" kalibi
    "kampanyasi hazirla" cumlesini GORMEZ, cunku iyelik eki dizgiyi boler.
    OLCULDU -- ajans istekleri bu yuzden ajansa hic ulasmiyordu.

    Iki kosul birlikte arandigi icin asiri tetikleme olmaz: "Reklamlar nasil
    gidiyor?" uretim fiili tasimaz ve rapor sorusu olarak kalir.
    """
    try:
        from jarvis.turkish import lemmas as _lemmas, words as _words
        tokens = _words(message)
        lemma_set = {lem.casefold() for w in tokens for lem in _lemmas(w)}
    except Exception:  # noqa: BLE001 - bicimbilgisi istege baglidir
        tokens, lemma_set = message.split(), set()

    folded = " ".join(_ascii_fold(w) for w in tokens)
    # CRO konusu tek basina ajans isidir; ayri bir uretim fiili aramaz.
    if any(kok in folded for kok in _CRO_ROOTS_AGENCY):
        return True
    nesne = (any(o in folded for o in _PRODUCTION_OBJECTS)
             or bool(lemma_set & set(_PRODUCTION_OBJECT_LEMMAS)))
    fiil = (any(w.startswith(_PRODUCTION_VERBS) for w in folded.split())
            or bool(lemma_set & set(_PRODUCTION_VERB_LEMMAS)))
    return nesne and fiil


def _is_pure_small_talk(message: str) -> bool:
    """Mesaj gerçekten sohbet mi, yoksa iş sorusu içinde mi geçiyor?

    "nasil gidiyor" tek basina sohbettir; "satislarimiz nasil gidiyor"
    degildir. Alan adi tasiyan bir mesaj sohbet sayilmaz.
    """
    return not _domains_of(message)


def _domains_of(message: str) -> list[str]:
    """Mesajın dokunduğu veri alanları. Çekimli biçimleri de yakalar.

    Iki olcut birlikte calisir: kelimenin LEMMASI bilinen bir lemma mi, ya
    da kelime bilinen bir KOKLE mi basliyor. Ikisi de gerekli -- olculdu:
    lemma "sattik"i yakalar ama "satan"i kaciririr; kok oneki ikisini de
    yakalar ama "satir" gibi nadir bir yanlis pozitif uretir.
    """
    try:
        from jarvis.turkish import deasciify as _deasc, lemmas as _lemmas, words as _words
        raw = _deasc(message)
    except Exception:  # noqa: BLE001 - bicimbilgisi istege baglidir
        _lemmas = None  # type: ignore[assignment]
        raw = message
        _words = None  # type: ignore[assignment]

    tokens = _words(raw) if _words else raw.split()
    folded = [_ascii_fold(w) for w in tokens]
    lemma_set: set[str] = set()
    if _lemmas is not None:
        for word in tokens:
            lemma_set |= {lem.casefold() for lem in _lemmas(word)}

    found: list[str] = []
    for domain in _DOMAIN_ROOTS:
        roots = _DOMAIN_ROOTS[domain]
        hit = any(len(w) >= _MIN_ROOT_WORD and w.startswith(roots) for w in folded)
        if not hit and lemma_set:
            hit = bool(lemma_set & set(_DOMAIN_LEMMAS.get(domain, ())))
        if hit:
            found.append(domain)
    # Fiyat bir VERI sorusudur; modele degil veriye gitmeli. Kok taramasi
    # kisa para birimlerini ve cok kelimeli tutar kaliplarini yakalayamaz.
    if "ecommerce" not in found:
        birlesik = " ".join(folded)
        if (set(folded) & _PARA_KELIMELERI
                or any(k in birlesik for k in _TUTAR_KALIPLARI)):
            found.append("ecommerce")
    return found




def _tl(v) -> str:
    """Tutar biçimi. None ise '—' -- 0 yazmak 'bedava' demek olurdu."""
    if v is None:
        return "—"
    try:
        return f"{float(v):,.2f} TL".replace(",", "\u00a0")
    except (TypeError, ValueError):
        return "—"



# Wix aciklamalari kargo/teslimat bloguyla ACILIYOR; urun tanimi sonra
# geliyor. Cevabin ilk cumlesi urunun NE OLDUGUNU soylemeli.
_KARGO_ISARETI = ("kargo", "teslimat", "gonderim", "gönderim", "iade",
                  "siparis", "sipariş", "is gunu", "iş günü")
_HTML_VARLIK = {"&amp;": "&", "&nbsp;": " ", "&lt;": "<", "&gt;": ">",
                "&quot;": '"', "&#39;": "'", "&apos;": "'"}


def _urun_tanimi(ham: str) -> str:
    """Açıklamadan ürünün ne olduğunu anlatan ilk cümle.

    Kargo/teslimat cümleleri atlanır -- onlar her üründe aynı ve ürün
    hakkında hiçbir şey söylemez.
    """
    metin = ham
    for k, v in _HTML_VARLIK.items():
        metin = metin.replace(k, v)
    metin = " ".join(metin.split())
    if not metin:
        return ""
    for cumle in metin.replace("·", ".").split("."):
        c = cumle.strip()
        if len(c) < 40:
            continue
        dusuk = _ascii_fold(c)
        if any(_ascii_fold(k) in dusuk for k in _KARGO_ISARETI):
            continue
        return (c[:240].rstrip() + "…") if len(c) > 240 else c + "."
    # Hicbir cumle uymadiysa basi verilir -- bos donmek daha kotu olurdu.
    return metin[:200].rstrip() + "…"


# Kreatif sorusu mu, harcama sorusu mu? Ikisi de "reklam" alanindadir ama
# bambaska seyler sorar.
_KREATIF_ISARETI = ("kreatif", "metin", "baslik", "gorsel", "video", "cta",
                    "hangi reklam", "reklam metni", "yorgun", "frekans",
                    "tutuyor", "calisiyor")


def _kreatif_sorusu(message: str) -> bool:
    f = _ascii_fold(turkish.deasciify(message))
    return any(_ascii_fold(k) in f for k in _KREATIF_ISARETI)



# Uretim emri mi, analiz sorusu mu? "reklam metni YAZ" ile "hangi reklam
# metni TUTUYOR" ayni kelimeleri tasir ama bambaska seylerdir.
_KREATIF_URETIM = ("yaz", "hazirla", "uret", "olustur", "kurgula", "tasarla",
                   "onerir misin", "fikir ver")
_KREATIF_ANALIZ = ("hangi", "nasil", "ne durumda", "tutuyor", "calisiyor",
                   "performans", "karsilastir", "en iyi", "yorgun", "frekans")


def _kreatif_analiz_sorusu(message: str) -> bool:
    """Var olan kreatifler HAKKINDA soru mu?

    Üç koşul birlikte: kreatif konusu geçmeli, analiz işareti taşımalı,
    ve üretim fiili TAŞIMAMALI. Üçü birden aranır çünkü tek başına her
    biri yanılır -- "hangi ürün" kreatif sorusu değildir, "reklam metni"
    tek başına üretim isteği olabilir.
    """
    if not _kreatif_sorusu(message):
        return False
    f = _ascii_fold(turkish.deasciify(message))
    if any(_ascii_fold(k) in f for k in _KREATIF_URETIM):
        return False
    return any(_ascii_fold(k) in f for k in _KREATIF_ANALIZ)



def _brief_answer(rows: list[dict]) -> str:
    """Günlük yönetici özeti. Model çağrısı YOK -- brief zaten üretilmiş.

    İçerik JSON olarak saklanıyor (executive_summary / priorities / risks).
    Ayrıştırılamazsa ham metin verilir; sessizce boş dönmek, üretilmiş bir
    özeti kaybetmek olurdu.
    """
    if not rows:
        return ("Henüz günlük yönetici özeti üretilmemiş. "
                "lcarlie-executive-brief servisi günde bir kez çalışır.")

    r = rows[0]
    tarih = str(r.get("created_at") or "")[:16]
    saglayici = f"{r.get('provider') or '?'}/{r.get('model') or '?'}"
    parcalar = [f"**Günlük Yönetici Özeti** — {tarih} ({saglayici})"]

    ham = r.get("icerik")
    veri = None
    if isinstance(ham, dict):
        veri = ham
    elif isinstance(ham, str) and ham.strip().startswith("{"):
        try:
            import json as _json
            veri = _json.loads(ham)
        except (ValueError, TypeError):
            veri = None

    if veri:
        ozet = str(veri.get("executive_summary") or "").strip()
        if ozet:
            parcalar.append(ozet)
        for alan, baslik in (("priorities", "ÖNCELİKLER"), ("risks", "RİSKLER")):
            liste = veri.get(alan)
            if isinstance(liste, list) and liste:
                parcalar.append(
                    baslik + " — " + " · ".join(str(x) for x in liste[:4]))
    elif isinstance(ham, str) and ham.strip():
        parcalar.append(ham.strip()[:700])
    else:
        parcalar.append("Brief kaydı var ama içeriği okunamadı.")

    if len(rows) > 1:
        onceki = str(rows[1].get("created_at") or "")[:10]
        parcalar.append(f"(Bir önceki özet: {onceki}.)")
    return " ".join(parcalar)

def _gundem_answer(rows: list[dict]) -> str:
    """Şirket gündemi: ne bekliyor, kimde, ne kadar süredir.

    Sıra veritabanından P0→P4 geliyor; burada bozulmaz. "Kimde" ayrımı
    ayrıca yazılır: gündemin en çok sorulan sorusu "bu bende mi sende mi".
    """
    if not rows:
        return "Gündemde açık madde yok."

    # Onceligi ACIKCA siralariz: yukaridan gelen siraya guvenip filtreleyince
    # P1, P0'in onune gecmisti. En acil madde en altta kalirsa hatirlatmanin
    # anlami kalmaz.
    def _onc(r):
        return str(r.get("oncelik") or "P3")

    rows = sorted(rows, key=_onc)
    insan = [r for r in rows if r.get("durum") == "BLOCKED_NEEDS_HUMAN"]
    devam = [r for r in rows if r.get("durum") == "IN_PROGRESS"]
    acik = [r for r in rows if r.get("durum") == "OPEN"]

    # Sayiya gore Turkce eki degisir (2'si, 18'i); ek kullanmayan ifade.
    parcalar = [f"Gündemde {len(rows)} madde var — {len(insan)} madde sizi "
                f"bekliyor, {len(devam)} madde devam ediyor, {len(acik)} madde açık."]

    def satir(r):
        onc = str(r.get("oncelik") or "P3")
        soru = str(r.get("soru") or "?")
        # Bekleme suresi varsa yazilir -- eskimis madde gundemde en
        # kolay gozden kacan seydir.
        bek = r.get("bekleme")
        gun = ""
        if bek:
            metin = str(bek)
            if "day" in metin:
                try:
                    gun = f" · {int(metin.split(' day')[0].strip())} gündür bekliyor"
                except (ValueError, IndexError):
                    gun = ""
        return f"[{onc}] {soru[:150]}{gun}"

    if insan:
        parcalar.append("SİZİ BEKLEYENLER — " + " || ".join(satir(r) for r in insan[:5]))
    kalan = [r for r in rows if r.get("durum") != "BLOCKED_NEEDS_HUMAN"]
    if kalan:
        parcalar.append("DİĞER AÇIK MADDELER — "
                        + " || ".join(satir(r) for r in kalan[:5]))
    if len(rows) > 10:
        parcalar.append(f"({len(rows) - 10} madde daha var.)")
    return " ".join(parcalar)

def _kreatif_answer(rows: list[dict]) -> str:
    """Hangi söz tutuyor? CTA ve biçim kıyaslaması + en iyiler.

    Yalnız ölçülebilir kreatifler sıralanır. 1000 gösterim altındakiler
    dışarıda bırakılır -- orada oran gürültüdür.
    """
    if not rows:
        return "Kreatif performans verisi okunamıyor."

    olculebilir = [r for r in rows if r.get("yeterli_ornek")]
    if not olculebilir:
        return (f"{len(rows)} kreatif var ama hiçbiri değerlendirilebilir "
                "örnek büyüklüğüne ulaşmamış (1000 gösterim altı).")

    def oran(grup):
        g = sum(float(r.get("gosterim") or 0) for r in grup)
        t = sum(float(r.get("link_tiklama") or 0) for r in grup)
        h = sum(float(r.get("harcama") or 0) for r in grup)
        return (100.0 * t / g if g else None, h / t if t else None, g)

    parcalar = []
    durumlar = {}
    for r in rows:
        d = str(r.get("olcum_durumu") or "?")
        durumlar[d] = durumlar.get(d, 0) + 1
    parcalar.append(
        f"{len(rows)} kreatifin {len(olculebilir)}'i değerlendirilebilir "
        f"({durumlar.get('YETERSIZ_ORNEK', 0)} tanesi 1000 gösterim altında, "
        f"{durumlar.get('PERFORMANS_KAYDI_YOK', 0)} tanesinin performans kaydı yok).")

    # --- CTA
    ctalar = {}
    for r in olculebilir:
        ctalar.setdefault(r.get("cta") or "(CTA yok)", []).append(r)
    sirali = sorted(((ad, *oran(g)) for ad, g in ctalar.items()),
                    key=lambda x: (x[1] is None, -(x[1] or 0)))
    if sirali:
        satir = "; ".join(
            f"{ad} %{ctr:.1f} ({maliyet:.2f} TL/link)" if ctr and maliyet
            else f"{ad} —"
            for ad, ctr, maliyet, _ in sirali[:5])
        parcalar.append("CTA'ya göre link CTR — " + satir + ".")

    # --- bicim
    bicimler = {}
    for r in olculebilir:
        bicimler.setdefault(r.get("bicim") or "?", []).append(r)
    bs = sorted(((ad, *oran(g)) for ad, g in bicimler.items()),
                key=lambda x: (x[1] is None, -(x[1] or 0)))
    if bs:
        parcalar.append("Biçim — " + "; ".join(
            f"{ad} %{ctr:.1f}" for ad, ctr, _, _ in bs if ctr) + ".")

    # --- en iyi tek kreatif
    en_iyi = max(olculebilir,
                 key=lambda r: float(r.get("link_ctr") or 0), default=None)
    if en_iyi:
        ad = str(en_iyi.get("baslik") or en_iyi.get("govde") or "(başlıksız)")[:70]
        parcalar.append(
            f"En yüksek link CTR: \"{ad}\" — %{en_iyi.get('link_ctr')}, "
            f"{en_iyi.get('gosterim')} gösterim, {en_iyi.get('bicim')}.")

    # --- yorgunluk
    yorgun = [r for r in olculebilir
              if float(r.get("en_yuksek_frekans") or 0) >= 2.5]
    if yorgun:
        parcalar.append(f"{len(yorgun)} kreatifte frekans 2,5'in üstüne çıkmış "
                        "— aynı kişi reklamı tekrar tekrar görüyor.")

    # --- ZORUNLU UYARI
    parcalar.append("Dikkat: farklı CTA'lar farklı şey satın alır. Profil "
                    "görüntüleme tıklaması ucuzdur ama satış değildir; "
                    "bu oranlar doğrudan kıyaslanamaz.")
    return " ".join(parcalar)

def _urun_karti_answer(message: str, rows: list[dict]) -> str:
    """Ürün sorusuna dolu cevap.

    Fiyat tek başına yetmiyordu. Burada ürünün ne olduğu, nerede kaça
    satıldığı, stoğu, satış geçmişi ve platformlar arası tutarsızlığı
    birlikte verilir -- hepsi veriden, hiçbiri modelden.
    """
    if not rows:
        return "Ürün kartı şu anda okunamıyor."

    kelimeler = [_ascii_fold(w) for w in message.split()]
    kelimeler = [w for w in kelimeler if len(w) >= 4]
    eslesen = [r for r in rows
               if any(k in _ascii_fold(str(r.get("urun_adi") or ""))
                      for k in kelimeler)]

    if not eslesen:
        return (f"Sorudaki ürün katalogda bulunamadı. Katalogda {len(rows)} "
                "ürün var.")
    if len(eslesen) > 1:
        adlar = ", ".join(str(r.get("urun_adi") or "?")[:34] for r in eslesen[:6])
        return f"{len(eslesen)} ürün eşleşti: {adlar}. Soruyu tek ürüne daraltın."

    r = eslesen[0]
    ad = str(r.get("urun_adi") or "?")
    parcalar = [f"**{ad}**"]

    aciklama = _urun_tanimi(str(r.get("aciklama_duz") or ""))
    if aciklama:
        parcalar.append(aciklama)

    # --- fiyat
    fiyat = []
    if r.get("wix_satis") is not None:
        w = f"Wix {_tl(r['wix_satis'])}"
        if r.get("wix_liste") is not None and r["wix_liste"] != r["wix_satis"]:
            w += f" (liste {_tl(r['wix_liste'])})"
        fiyat.append(w)
    ty = r.get("trendyol_satis")
    if ty is not None and float(ty) > 0:
        fiyat.append(f"Trendyol {_tl(ty)}")
    elif ty is not None:
        # Sifir bir FIYAT DEGIL, ariza isareti. Fiyat gibi gostermek
        # yaniltici olurdu.
        parcalar.append("⚠ Trendyol'da fiyatı 0 görünüyor — listeleme eksik.")
    if fiyat:
        parcalar.append("Fiyat — " + " · ".join(fiyat) + ".")
    elif r.get("trendyolda_var") is False:
        parcalar.append("Fiyat kaydı yok.")

    # --- stok ve yayin
    durum = []
    if r.get("wix_stok") is not None:
        durum.append(f"Wix stok {r['wix_stok']}")
    if r.get("trendyol_stok") is not None:
        durum.append(f"Trendyol stok {r['trendyol_stok']}")
    if r.get("wix_yayinda") is False:
        durum.append("Wix'te YAYINDA DEĞİL")
    if not r.get("trendyolda_var"):
        durum.append("Trendyol'da listelenmemiş")
    if durum:
        parcalar.append(" · ".join(durum) + ".")

    # --- satis gecmisi. Satmamis urun icin 0 YAZILMAZ.
    if r.get("satilan_adet") is not None:
        try:
            _adet = f"{float(r['satilan_adet']):g}"
        except (TypeError, ValueError):
            _adet = str(r["satilan_adet"])
        s = f"Bugüne kadar {_adet} adet satıldı"
        if r.get("ciro") is not None:
            s += f", {_tl(r['ciro'])} ciro"
        if r.get("satis_marj_yuzde") is not None:
            s += f", brüt marj %{r['satis_marj_yuzde']}"
        parcalar.append(s + ".")
    else:
        parcalar.append("Henüz satış kaydı yok.")

    # --- maliyet ve marj uyarisi
    if r.get("birim_maliyet") is not None:
        kaynak = str(r.get("maliyet_kaynagi") or "")
        ek = (" (sahip beyanı, tüm ürünlere ortalama — gerçek ürün maliyeti değil)"
              if kaynak == "ELLE" else "")
        parcalar.append(f"Birim maliyet {_tl(r['birim_maliyet'])}{ek}.")

    # --- platformlar arasi tutarsizlik
    farkli = r.get("farkli_alan")
    if farkli:
        parcalar.append(f"Wix ile Trendyol arasında {farkli} alan farklı "
                        "(E-TİCARET sekmesinde satır satır görülebilir).")

    return " ".join(parcalar)

def _fiyat_answer(message: str, rows: list[dict]) -> str:
    """Ürün fiyatı -- KAYNAĞIYLA birlikte.

    Fiyatın nereden geldiği saklanmaz. İşletme beyanı ile Wix vitrini ayrı
    şeylerdir; 007 migration'ı bu ayrımı `fiyat_kaynagi` sütununda korudu ve
    cevap da onu taşır. "1.200 TL" demek yetmez, "kaynak Wix" demek gerekir.
    """
    if not rows:
        return "Fiyat tablosu şu anda okunamıyor."

    # Mesajdaki kelimeler ÜRÜN ADINDA aranır. Kısa kelimeler ("kac", "tl")
    # her ürüne değeceği için elenir.
    kelimeler = [_ascii_fold(w) for w in message.split()]
    kelimeler = [w for w in kelimeler if len(w) >= 4]

    eslesen = [r for r in rows
               if any(k in _ascii_fold(str(r.get("urun_adi") or ""))
                      for k in kelimeler)]

    def _satir(r: dict) -> str:
        ad = str(r.get("urun_adi") or "?")
        fiyat = r.get("musteriye_soylenecek_fiyat")
        kaynak = str(r.get("fiyat_kaynagi") or "YOK")
        if fiyat is None:
            return f"{ad}: fiyat kaydı yok."
        etiket = {"BEYAN": "işletme beyanı",
                  "WIX": "Wix vitrini"}.get(kaynak, kaynak)
        return f"{ad}: {float(fiyat):,.2f} TL (kaynak: {etiket})."

    if len(eslesen) == 1:
        return _satir(eslesen[0])
    if 1 < len(eslesen) <= 6:
        return "Birden fazla ürün eşleşti:\n" + "\n".join(
            "- " + _satir(r) for r in eslesen)
    if eslesen:
        return (f"{len(eslesen)} ürün eşleşti; soruyu tek ürüne daraltın. "
                "Örnek: 'VIREON kaç TL?'")

    beyan = sum(1 for r in rows if r.get("fiyat_kaynagi") == "BEYAN")
    return (f"Sorudaki ürün fiyat tablosunda bulunamadı. Tabloda {len(rows)} "
            f"ürün var; {beyan} tanesinin fiyatı işletme beyanı, kalanı "
            "Wix vitrininden alınıyor.")

def _ascii_fold(word: str) -> str:
    import unicodedata as _ud
    lowered = word.replace("İ", "i").replace("I", "ı").casefold()
    return "".join(c for c in _ud.normalize("NFKD", lowered)
                   if not _ud.combining(c)).replace("ı", "i")


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


# Dogrulama ornek sayisi. Tek sayi secilir ki cogunluk her zaman belirli olsun.
CONSENSUS_SAMPLES = int(os.environ.get("JARVIS_CONSENSUS_SAMPLES", "3"))
CONSENSUS_ON = os.environ.get("JARVIS_CONSENSUS", "1") != "0"


def _verify(message: str, first: str, evidence: list[dict[str, Any]],
            missing: list[str], escalate: bool) -> dict[str, Any]:
    """Cevabı birkaç kez tekrar üretip sayısal iddiaları karşılaştırır.

    KOSULLU: ilk cevapta sirket sayisi yoksa hic calismaz. Olculdu -- bir
    analiz cevabi 24,6 saniye suruyor; her cevabi uc kez uretmek sohbeti
    kullanilamaz yapardi ve sayisiz bir cevapta korunacak bir sey de yok.
    """
    if not CONSENSUS_ON or not consensus.has_company_numbers(first):
        return {}

    def ask() -> str:
        # Dogrulama YEREL modele sorulur, dis modele degil. Iki sebep:
        # (1) Ayni modele uc kez sormak kararliligi olcer; FARKLI modele
        #     sormak uydurmayi yakalar -- capraz kontrol daha guclu.
        # (2) Dis saglayicinin gunluk 50 isteklik kotasini dogrulama
        #     tuketmemeli; o kota asil cevaplar icindir.
        result = _router().synthesize(message, evidence, missing_data=missing,
                                      escalate=False)
        return result.answer

    out = consensus.run(ask, first=first, samples=CONSENSUS_SAMPLES)
    if out.samples < 2:
        return {}
    payload = out.to_dict()
    payload["selected_differs"] = out.answer.strip() != first.strip()
    return payload


# Buraya gelen her soru zaten should_use_model() suzgecinden gecmistir:
# sayim ve rapor sorulari veritabanindan, model cagrisi olmadan cevaplanir
# ve buraya HIC gelmez. Dolayisiyla buradaki her soru serbest muhakemedir
# ve guclu modeli hak eder.
#
# OLCULDU: eski kural (280 karakter veya 18 sabit kelime) neredeyse hic
# tetiklenmiyordu -- dis saglayici hesabinda usage: 0 idi. Ayni olcumde
# 550B model 2,6 saniyede yerel 4B'den daha iyi cevap verdi.
#
# Sahip karari (20.09.2026): muhakeme sorularinda kullanilsin. Bu, sirket
# kanitinin dis saglayiciya gitmesi demektir; sohbet yerel modelde kalir.
ESCALATE_REASONING = os.environ.get("JARVIS_ESCALATE_REASONING", "1") != "0"


def _synthesize(message: str, intent: str, memory: Any, started: float,
                escalate: bool | None = None) -> dict[str, Any]:
    if escalate is None:
        escalate = ESCALATE_REASONING or needs_escalation(message)
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

    cevap = result.answer
    dogrulama: dict[str, Any] = {}
    try:
        dogrulama = _verify(message, cevap, evidence, list(missing), bool(escalate))
    except Exception:  # noqa: BLE001 - dogrulama cevabi engelleyemez
        dogrulama = {}
    if dogrulama:
        cevap = str(dogrulama.get("answer") or cevap)
        if dogrulama.get("disputed_claims"):
            # Ayrisma GIZLENMEZ. Kararsizken kendinden emin konusmak, yanlis
            # cevaptan daha tehlikelidir: kullanici kontrol etmez.
            cekismeli = ", ".join(d["claim"] for d in dogrulama["disputed_claims"][:4])
            cevap = (cevap.rstrip()
                     + f"\n\n⚠ Doğrulama: {dogrulama['samples']} denemede şu rakamlar "
                       f"tutarsız çıktı ({cekismeli}). Bu sayılar kaynağından "
                       f"teyit edilmeden kullanılmamalıdır.")

    return _response(message, intent, "ANSWERED", cevap,
                     verification=dogrulama or None,
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
                                      escalate=ESCALATE_REASONING
                                      or needs_escalation(message))
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
# Derinlik istegi kokleri. Cekimli bicimleri yakalamak icin KOK oneki:
# "derinlemesine", "kapsamlica", "detaylica" hepsi tutar.
_DEPTH_ROOTS = ("derin", "kapsaml", "detayl", "her aci", "her yon",
                "ekip olarak", "uzmanlar", "coklu")


def _wants_depth(message: str) -> bool:
    return any(kok in _ascii_fold(message) for kok in _DEPTH_ROOTS)


def _research_team(message: str, controller: Any, started: float) -> dict[str, Any]:
    """Birden çok açıdan araştırma. Ölçüldü: üç açı ~70 saniye.

    Her aci ayri bir aramadir ve kendi sorgusunu kurar; olculdu, aci
    degistirince GERCEKTEN farkli kaynaklar geliyor (rakip acisi duz
    sorguda hic cikmayan lansman haberlerini buldu).
    """
    from jarvis import research_team as team

    out = team.investigate(message, controller)
    kaynaklar = out.get("sources") or []
    evidence = [{"ref": s.get("url") or "", "summary": str(s.get("title") or "")[:200]}
                for s in kaynaklar[:10]]

    if not kaynaklar:
        # Hangi acinin neden bos dondugu ayri ayri yazilir: zaman asimi ile
        # "sonuc yok" ayni sey degildir.
        detay = "; ".join(f"{a['name']}: {a['status']}" for a in out.get("angles") or [])
        return _response(message, RESEARCH_REQUEST, "LOW_CONFIDENCE",
            f"Ekip {len(out.get('angles') or [])} açıdan aradı, kaynak "
            f"bulunamadı. Açı durumları -- {detay}",
            missing_data=("verified_research_source",), started=started,
            research_team=out)

    satirlar = [team.summarize(out), ""]
    for s in kaynaklar[:8]:
        bulan = ", ".join(s.get("found_by") or [])
        tarih = str(s.get("observed_at") or "")[:10]
        satirlar.append(
            f"- [{s.get('source_type')}] {s.get('title') or s.get('url')}"
            + (f" ({tarih})" if tarih else "")
            + f"\n  {s.get('url')}\n  bulan: {bulan}")

    return _response(message, RESEARCH_REQUEST, "ANSWERED",
        "\n".join(satirlar),
        evidence_refs=tuple(e["ref"] for e in evidence),
        started=started, details=_details_payload(evidence),
        research_team=out, model_calls=0)


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
        controller = ResearchController(factory)
        # Kullanici DERINLIK istediyse ekip calisir: uc ayri arama, ~70
        # saniye. Her istekte calistirmak sohbeti kullanilamaz yapardi.
        if _wants_depth(message):
            return _research_team(message, controller, started)
        report = controller.run(message)
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
        # ZAMAN ASIMI "KAYNAK YOK" DEGILDIR. Olculdu: kaynak basina sure
        # 8 saniyeydi, adaptorun gercek suresi 14,5 saniye -- arastirma her
        # seferinde zaman asimina ugruyor ve kullaniciya "kaynak bulunamadi"
        # deniyordu. Kullanici buna inanip konuyu kapatir.
        zaman_asimi = int((report.get("telemetry") or {}).get("timeouts") or 0)
        if zaman_asimi:
            return _response(message, RESEARCH_REQUEST, "TIMEOUT",
                f"Araştırma tamamlanamadı: {zaman_asimi} kaynak zaman aşımına "
                "uğradı. Bu, konuda kaynak olmadığı anlamına GELMEZ; sorgu "
                "daraltılıp tekrar denenmeli.",
                missing_data=("research_timed_out",), started=started,
                research_confidence=confidence_value,
                research_stop_reason=report.get("stop_reason"),
                research_timeouts=zaman_asimi)
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
    # Dil SABIT. Istem zaten "Turkce yazarsin" diyordu, ama bunu ton
    # kaydinin icinde soyluyordu; kullanicinin dili degisince modelin
    # ona uymasi serbest kaliyordu. Sahip karari 20.09.2026:
    # "turkce konusmasini istiyorum" -- kural artik acik ve tek basina.
    "- Kullanıcı hangi dilde yazarsa yazsın, sen HER ZAMAN Türkçe cevap "
    "ver. İngilizce sorulsa bile cevap Türkçe olur.\n"
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


DIL_NOTU = "\n\n(Yanıtını Türkçe yaz.)"


def _dil_notlu(message: str) -> str:
    """Her soruya, soruya BITISIK bir dil notu ekler.

    NEDEN ISTEM YETMIYOR
    Kural hem CHAT_SYSTEM'de hem GROUNDING_SYSTEM'de acikca yazili. Yine de
    OLCULDU: "What are our sales this month?" Ingilizce cevaplandi.
    Qwen3-4B sorunun diline uyuyor; kucuk modeller istemin basindaki kurali
    degil, soruya en yakin talimati dinliyor. Not eklenince ayni soru
    Turkce cevaplandi (iki tur, ikisi de Turkce).

    NEDEN SINIFLANDIRICI YOK
    Once "yalniz yabanci soruya ekle" diye yazildi ve siniflandirici
    yanildi: "Which product should I promote?" Turkce sanildi, cevap
    Ingilizce geldi. Kelime listesini buyutmek ayni sinif hatayi erteler.
    Notu her soruya eklemenin bedeli ~25 karakter; yaniltmanin bedeli
    yanlis dilde cevap. Bu yuzden kosul yok.

    Not KAYDA GIRMEZ: conversation_memory'ye kullanicinin yazdigi cumle
    yazilir, bu eklenti degil -- cagri yerlerinde `message` degiskeni
    oldugu gibi duruyor.
    """
    metin = message or ""
    if metin.endswith(DIL_NOTU):
        return metin
    return metin + DIL_NOTU


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
        result = _router().synthesize(_dil_notlu(message), (), system=_system_for(message), max_tokens=CHAT_MAX_TOKENS,
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
        for delta in _router().stream_text(_dil_notlu(message), _system_for(message), max_tokens=CHAT_MAX_TOKENS,
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

    # Teslimat diske yazilir ve onerilebilir konseptler icin sartname
    # uretilir. Once bu yapilmiyordu: konseptler, test plani ve mevzuat
    # bulgulari HTTP yanitindan sonra cope gidiyordu. Kayit basarisiz olursa
    # cevap yine doner -- saklamak cevabi engellememeli.
    try:
        from jarvis import agency_store
        deliverable["stored"] = agency_store.save(deliverable)
    except Exception as exc:  # noqa: BLE001
        deliverable["stored"] = {"error": str(exc)[:200]}

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


def _urun_adi_gecen(message: str, runtime: Any) -> bool:
    """Mesaj katalogdaki bir ürün adını taşıyor mu?

    Marka adı TAM KELİME olarak aranır. Alt dizgi kullanılmaz: "CAL JAW"
    markasının "cal" parçası "calisma" içinde de geçer ve her soruyu ürün
    sorusu yapardı. Üç harften kısa parçalar da elenir.
    """
    try:
        adlar = _known_products(runtime)
    except Exception:  # noqa: BLE001 - katalog yoklugu bir durumdur
        return False
    if not adlar:
        return False
    kelimeler = {_ascii_fold(w).strip(".,;:!?()[]\"'")
                 for w in turkish.deasciify(message).split()}
    kelimeler.discard("")
    for ad in adlar:
        # Marka adi cok kelimeli olabilir ("FEMISIA for WOMEN"); ilk
        # parcasi ayirt edici olandir.
        bas = _ascii_fold(str(ad).split("(")[0].strip()).split(" ")[0]
        if len(bas) >= 4 and bas in kelimeler:
            return True
    return False


def route(message: str, runtime: Any) -> dict[str, Any]:
    started = perf_counter()
    decision = classify(message)
    # Ciplak bir urun adi ("Hydravie") sirket sorusudur, muhakeme sorusu
    # degil. Bu kontrol olmadan soru yerel modele dusuyor ve model
    # katalogda olan bir urun icin "katalogda yok" diyebiliyordu.
    if decision.intent == GENERAL_REASONING and _urun_adi_gecen(message, runtime):
        decision = RouteDecision(COMPANY_QUERY, "ecommerce")
    # Var olan kreatifler HAKKINDA soru, yeni kreatif ISTEGI degildir.
    # Ajans katmani "metin" kelimesini uretim sanip soruyu yutuyordu.
    if decision.intent == AGENCY_REQUEST and _kreatif_analiz_sorusu(message):
        decision = RouteDecision(COMPANY_QUERY, "advertising")
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
    # Geriye kalan siradan sohbettir. `runtime` GECILIR: gecilmedigi surece
    # cevap denetimi urun katalogunu okuyamiyor ve gercek urun adlarini
    # uydurma sanabiliyordu.
    return _chat(message, decision.intent, started, runtime)
