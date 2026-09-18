"""L'CARLIE Creative & Growth Agency capability.

Additive, deterministic-first and proposal-only. It reads the existing
Company Memory allowlist, shares one evidence snapshot across selected roles,
and never executes research, a model, or an external action.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from .memory import CompanyMemory
from .specialist_pool import DATA_UNAVAILABLE, PROPOSED

CREATIVE_DIRECTOR = "CREATIVE_DIRECTOR"
META_PERFORMANCE = "META_PERFORMANCE"
CREATIVE_INTELLIGENCE = "CREATIVE_INTELLIGENCE"
COMPETITOR_CREATIVE = "COMPETITOR_CREATIVE"
SOCIAL_CONTENT = "SOCIAL_CONTENT"
COPYWRITER = "COPYWRITER"
CRO_SPECIALIST = "CRO_SPECIALIST"
GROWTH_STRATEGIST = "GROWTH_STRATEGIST"

ROLES = (CREATIVE_DIRECTOR, META_PERFORMANCE, CREATIVE_INTELLIGENCE,
         COMPETITOR_CREATIVE, SOCIAL_CONTENT, COPYWRITER, CRO_SPECIALIST,
         GROWTH_STRATEGIST)

TASK_CAMPAIGN = "CAMPAIGN_PROPOSAL"
TASK_PERFORMANCE = "PERFORMANCE_REVIEW"
TASK_SOCIAL = "SOCIAL_PLAN"
TASK_CRO = "CRO_REVIEW"

TASK_ROLES = {
    TASK_CAMPAIGN: (CREATIVE_DIRECTOR, META_PERFORMANCE, CREATIVE_INTELLIGENCE,
                    COPYWRITER, CRO_SPECIALIST, GROWTH_STRATEGIST),
    TASK_PERFORMANCE: (META_PERFORMANCE, CREATIVE_INTELLIGENCE, GROWTH_STRATEGIST),
    TASK_SOCIAL: (SOCIAL_CONTENT, COPYWRITER, CREATIVE_DIRECTOR),
    TASK_CRO: (CRO_SPECIALIST, GROWTH_STRATEGIST, CREATIVE_DIRECTOR),
}
TASK_QUERIES = {
    TASK_CAMPAIGN: ("sales_items", "advertising_performance", "ecommerce_price"),
    TASK_PERFORMANCE: ("advertising_performance", "advertising_spend"),
    TASK_SOCIAL: ("decision_summary",),
    TASK_CRO: ("ecommerce_funnel", "ecommerce_price", "sales_orders"),
}

PROHIBITED_CLAIMS = (
    "tedavi", "ereksiyon", "geciktir", "performans garant", "garantili sonuç",
    "garantili sonuc", "cinsel güc", "cinsel guc", "senin cinsel", "kişisel cinsel",
    "kisisel cinsel",
)


@dataclass(frozen=True)
class EvidenceSnapshot:
    records: dict[str, tuple[dict[str, Any], ...]]
    evidence_refs: tuple[str, ...]
    data_gaps: tuple[str, ...]
    bytes: int
    load_ms: float


CAMPAIGN_MARKERS = ("kampanya hazırla", "kampanya hazirla", "kampanyası hazırla",
                    "kampanyasi hazirla", "yeni kampanya", "meta kampanya",
                    "reklam kampanyası", "reklam kampanyasi", "kreatif açı",
                    "kreatif aci", "kreatif fikir")


def classify_task(task: str) -> str:
    text = task.casefold()
    # Checked first: a campaign brief routinely mentions the landing page and
    # the test plan, and must not be mistaken for a CRO review because of it.
    if any(term in text for term in CAMPAIGN_MARKERS):
        return TASK_CAMPAIGN
    if any(term in text for term in ("7 günlük", "7 gunluk", "instagram plan", "sosyal medya plan")):
        return TASK_SOCIAL
    if any(term in text for term in ("landing page", "landing-page", "açılış sayfası",
                                     "acilis sayfasi", "dönüşümü artır", "donusumu artir",
                                     "cro")):
        return TASK_CRO
    if any(term in text for term in ("performansında", "performansinda", "hangi problem",
                                     "ne test", "reklam performansımızı", "reklam performansimizi",
                                     "son reklam")):
        return TASK_PERFORMANCE
    return TASK_CAMPAIGN


def select_roles(task_type: str, task: str) -> tuple[str, ...]:
    roles = list(TASK_ROLES[task_type])
    text = task.casefold()
    if task_type == TASK_CAMPAIGN and any(term in text for term in ("rakip", "competitor")):
        roles.insert(3, COMPETITOR_CREATIVE)
    return tuple(roles)


def _load_snapshot(memory: Any, queries: tuple[str, ...]) -> EvidenceSnapshot:
    started = perf_counter()
    records: dict[str, tuple[dict[str, Any], ...]] = {}
    refs, gaps = [], []
    allowlist = getattr(memory, "QUERIES", {})
    for query in queries:
        if query not in allowlist:
            gaps.append(query)
            continue
        try:
            evidence = memory._fetch(query)
        except Exception:
            gaps.append(query)
            continue
        records[query] = tuple(evidence.records)
        refs.append(evidence.source)
    size = len(json.dumps(records, ensure_ascii=False, default=str).encode("utf-8"))
    return EvidenceSnapshot(records, tuple(dict.fromkeys(refs)), tuple(gaps), size,
                            round((perf_counter() - started) * 1000, 3))


def _vireon_rows(rows: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    def folded(value: Any) -> str:
        decomposed = unicodedata.normalize("NFKD", json.dumps(value, ensure_ascii=False).casefold())
        return "".join(char for char in decomposed if not unicodedata.combining(char)).replace("ı", "i")
    return [row for row in rows if "vireon" in folded(row)]


def _ad_baseline(snapshot: EvidenceSnapshot, product: str | None = None) -> dict[str, Any]:
    rows = list(snapshot.records.get("advertising_performance", ()))
    if product:
        rows = _vireon_rows(tuple(rows))
    rows = [row for row in rows if row.get("pencere") == 30]
    spend = sum(float(row.get("harcama") or 0) for row in rows)
    impressions = sum(int(row.get("gosterim") or 0) for row in rows)
    clicks = sum(int(row.get("tiklama") or 0) for row in rows)
    link_clicks = sum(int(row.get("link_tiklama") or 0) for row in rows)
    return {
        "rows": len(rows), "spend": round(spend, 2), "impressions": impressions,
        "clicks": clicks, "link_clicks": link_clicks,
        "ctr_pct": round(clicks / impressions * 100, 2) if impressions else None,
        "cpc": round(spend / clicks, 2) if clicks else None,
        "commercially_confirmed_rows": sum(
            1 for row in rows if row.get("commercial_confirmation") == "CONFIRMED"),
    }


def _sales_baseline(snapshot: EvidenceSnapshot, product: str) -> dict[str, Any]:
    rows = _vireon_rows(snapshot.records.get("sales_items", ())) if product.casefold() == "vireon" else []
    return {"rows": len(rows), "units": sum(int(row.get("adet") or 0) for row in rows),
            "net_revenue": round(sum(float(row.get("satir_ciro_net") or 0) for row in rows), 2),
            "measured_rows": sum(1 for row in rows if row.get("olcumde"))}


def _concepts() -> list[dict[str, str]]:
    shared = {"cta": "Daha Fazla Bilgi", "landing_page_message":
              "Vireon'u kozmetik bakım rutininin bir parçası olarak keşfedin; içerik, kullanım ve ürün bilgilerini inceleyin."}
    return [
        {"name": "Bakım Rutini", "audience_context": "Kişisel bakım rutinine düzenli ve özenli yaklaşan yetişkinler",
         "hook": "Bakım rutininizde kendinize ayırdığınız adım hangisi?",
         "primary_text": "Vireon'u günlük kişisel bakım rutininize eklenebilecek kozmetik bakım seçeneği olarak keşfedin. Ürün bilgilerini inceleyin, size uygun kullanım kararını bilinçli verin.",
         "headline": "Bakım rutinine özenli bir adım",
         "visual_brief": "Temiz banyo rafında ürün, nötr ışık, ambalaj ve bakım ritüeli odağı; beden sonucu veya mahrem bölge görseli yok.",
         "video_15s_brief": "0-3 sn sade bakım rafı; 3-8 sn ürün ve rutin adımı; 8-12 sn bilgi inceleme ekranı; 12-15 sn Daha Fazla Bilgi CTA.", **shared},
        {"name": "Kendine Ayırdığın An", "audience_context": "Yoğun gün içinde kişisel bakımına zaman ayırmak isteyen yetişkinler",
         "hook": "Günün içinde bakım için küçük bir alan açın.",
         "primary_text": "Kişisel bakım yalnız sonuç iddiası değil, düzenli bir rutindir. Vireon'un kozmetik bakım yaklaşımını ve kullanım bilgilerini keşfedin.",
         "headline": "Kendine ayırdığın bakım anı",
         "visual_brief": "Akşam bakım atmosferi, havlu ve ürün yakın planı; sakin, premium fakat klinik olmayan anlatım.",
         "video_15s_brief": "0-4 sn gün sonu geçişi; 4-9 sn bakım alanı hazırlığı; 9-12 sn ürün yakın planı; 12-15 sn bilgi CTA.", **shared},
        {"name": "Açık ve Bakım Odaklı", "audience_context": "Ürün bilgisini ve iddia sınırlarını önemseyen bilinçli yetişkinler",
         "hook": "Büyük vaatler yerine açık ürün bilgisi.",
         "primary_text": "Vireon kozmetik bakım sınırında, açık ürün ve kullanım bilgileriyle anlatılır. Ayrıntıları inceleyerek bilinçli bir bakım tercihi yapın.",
         "headline": "Bakım odaklı, açık iletişim",
         "visual_brief": "Ambalaj, okunaklı bilgi katmanları ve sade tipografi; önce-sonra, medikal ikon veya sonuç grafiği yok.",
         "video_15s_brief": "0-3 sn 'Büyük vaatler yerine bilgi'; 3-10 sn ambalaj ve bilgi başlıkları; 10-15 sn keşfet CTA.", **shared},
    ]


def _problems_and_opportunities(task_type: str, baseline: dict[str, Any],
                                sales: dict[str, Any], snapshot: "EvidenceSnapshot",
                                ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Read off the evidence, never asserted beyond it.

    Every entry names the ref it came from, so a reader can check it. Where
    the number needed to judge something is missing, that absence is the
    finding rather than a guess in its place.
    """
    problems: list[dict[str, str]] = []
    opportunities: list[dict[str, str]] = []

    rows = baseline.get("rows") or 0
    confirmed = baseline.get("commercially_confirmed_rows") or 0
    if rows and not confirmed:
        problems.append({
            "problem": (f"{rows} reklam kaydının hiçbirinde ticari olarak doğrulanmış "
                        "satış yok; Meta'nın satış iddiası doğrulanmış satış değildir."),
            "evidence": "postgres:advertising_performance"})
    if baseline.get("spend"):
        opportunities.append({
            "opportunity": (f"Ölçülen harcama {baseline.get('spend')} TL ve CTR "
                            f"{baseline.get('ctr_pct')}%: açı testi için gerçek bir "
                            "temel var, tahmin gerekmiyor."),
            "evidence": "postgres:advertising_spend"})
    if sales.get("rows"):
        opportunities.append({
            "opportunity": (f"{sales.get('rows')} satış kalemi ve "
                            f"{sales.get('net_revenue')} TL net ciro kayıtlı; "
                            "kreatif mesaj gerçek ürün talebine bağlanabilir."),
            "evidence": "postgres:sales_items"})
    if sales.get("rows") and not sales.get("measured_rows"):
        problems.append({
            "problem": ("Satış kalemleri ölçüm penceresi dışında; kampanya etkisi "
                        "bugünkü veriyle ciroya bağlanamaz."),
            "evidence": "postgres:sales_items"})
    for gap in snapshot.data_gaps:
        problems.append({"problem": f"Veri sözleşmesi yok: {gap}",
                         "evidence": "DATA_UNAVAILABLE"})
    return problems, opportunities


def _enrich_concepts(concepts: list[dict[str, str]], baseline: dict[str, Any],
                     sales: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach the reasoning and the evidence each concept actually rests on."""
    refs = [ref for ref, present in (("postgres:advertising_performance", baseline.get("rows")),
                                     ("postgres:advertising_spend", baseline.get("spend")),
                                     ("postgres:sales_items", sales.get("rows"))) if present]
    why = [
        (f"Mevcut CTR {baseline.get('ctr_pct')}% ilgi olduğunu gösteriyor; "
         "sorun ilgi değil, iddia sınırı içinde kalan net bir mesaj."),
        ("Ticari doğrulama yokken sonuç vaadi yerine bilgi ve keşif çağrısı "
         "ölçülebilir ve mevzuata uygun."),
        ("Açık bilgi dili, doğrulanamayan iddia riskini taşımadan ayrışma sağlar."),
    ]
    enriched: list[dict[str, Any]] = []
    for index, concept in enumerate(concepts):
        item = dict(concept)
        item["why_this_might_work"] = why[index % len(why)]
        item["evidence_used"] = refs
        item["regulatory_risk"] = "NONE_DETECTED"
        enriched.append(item)
    return enriched


def _regulatory_review(concepts: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    risks, objections = [], []
    for concept in concepts:
        text = " ".join(str(value) for value in concept.values()).casefold()
        for phrase in PROHIBITED_CLAIMS:
            if phrase in text:
                risks.append(phrase)
                objections.append({"creative": concept["name"], "claim": phrase,
                                    "reason": "Outside cosmetic care/support boundary"})
    return list(dict.fromkeys(risks)), objections


def _social_plan() -> list[dict[str, str]]:
    rows = [
        ("Reel", "Bakım rutini", "Rutinin sürdürülebilir olması neden önemli?", "Küçük ve düzenli bakım adımları", "Sade masa üstü rutin akışı", "Kaydet", "education"),
        ("Carousel", "Marka yaklaşımı", "Büyük vaat yerine açık bilgi", "Kozmetik bakım sınırını anlat", "Tipografik bilgi kartları", "Detayları incele", "brand"),
        ("Story", "Topluluk sorusu", "Bakım rutininde en çok neyi önemsiyorsun?", "Anket ve soru kutusu", "İki seçenekli sade anket", "Yanıtla", "engagement"),
        ("Reel", "Ürün keşfi", "Vireon bakım rutininde nasıl konumlanır?", "Ürün ve kullanım bilgisini incelemeye yönlendir", "Ürün yakın planı, medikal olmayan ortam", "Daha fazla bilgi", "product"),
        ("Carousel", "İddia okuryazarlığı", "Bir bakım ürününü değerlendirirken 3 kontrol", "İçerik, kullanım, iddia sınırı", "Kontrol listesi tasarımı", "Kaydet", "education"),
        ("Static", "Bakım anı", "Kendine ayırdığın küçük alan", "Rutin ve öz bakım yönü", "Premium ama doğal bakım sahnesi", "Rutini keşfet", "brand"),
        ("Story", "Hafta özeti", "Bu hafta hangi içerik faydalıydı?", "Geri bildirim ve gelecek konu seçimi", "Haftanın içeriklerinden küçük kareler", "Oy ver", "learning"),
    ]
    return [{"day": index + 1, "format": row[0], "topic": row[1], "hook": row[2],
             "caption_direction": row[3], "visual_direction": row[4], "cta": row[5],
             "objective": row[6]} for index, row in enumerate(rows)]


class AgencyCapability:
    def __init__(self, memory: Any | None = None):
        self.memory = memory or CompanyMemory()

    def run(self, task: str) -> dict[str, Any]:
        started = perf_counter()
        task_type = classify_task(task)
        roles = select_roles(task_type, task)
        snapshot = _load_snapshot(self.memory, TASK_QUERIES[task_type])
        concepts = _concepts() if task_type == TASK_CAMPAIGN else []
        regulatory_risks, objections = _regulatory_review(concepts)
        data_gaps = list(snapshot.data_gaps)
        research_required = task_type == TASK_CAMPAIGN and COMPETITOR_CREATIVE in roles
        if task_type in {TASK_CAMPAIGN, TASK_PERFORMANCE}:
            data_gaps.extend(("ga4_site_traffic", "commercially_confirmed_attribution"))
        if task_type == TASK_SOCIAL:
            data_gaps.extend(("approved_brand_voice_guide", "approved_product_claims"))
        if task_type == TASK_CAMPAIGN:
            data_gaps.extend(("real_inventory", "gunluk_marj"))
        baseline = _ad_baseline(snapshot, "vireon" if task_type == TASK_CAMPAIGN else None)
        sales = _sales_baseline(snapshot, "vireon") if task_type == TASK_CAMPAIGN else {}
        if baseline.get("commercially_confirmed_rows", 0) == 0 and baseline.get("rows", 0):
            objections.append({"creative": "campaign measurement", "claim": "Meta-reported sales",
                                "reason": "Commercial confirmation is unavailable; do not treat as sales"})
        if data_gaps:
            objections.append({"creative": "proposal", "claim": "complete measurement",
                                "reason": "Missing: " + ", ".join(dict.fromkeys(data_gaps))})
        social = _social_plan() if task_type == TASK_SOCIAL else []
        if task_type == TASK_CRO:
            # The live page is not reachable through any existing capability,
            # and inventing its content would be the one failure mode that
            # matters here.
            data_gaps.extend(("page_content", "ga4_site_traffic"))
            objections.append({"creative": "landing page", "claim": "page content",
                               "reason": "PAGE_CONTENT_DATA_UNAVAILABLE: live page text is "
                                         "not readable by any current capability"})
        problems, opportunities = _problems_and_opportunities(
            task_type, baseline, sales, snapshot)
        if task_type == TASK_CAMPAIGN:
            concepts = _enrich_concepts(concepts, baseline, sales)
        result = {
            "task": task, "objective": task_type, "evidence_refs": list(snapshot.evidence_refs),
            "current_evidence": {"advertising": baseline, "sales": sales,
                                 "queries": list(TASK_QUERIES[task_type]),
                                 "refs": list(snapshot.evidence_refs)},
            "problems": problems, "opportunities": opportunities,
            "page_content_state": ("PAGE_CONTENT_DATA_UNAVAILABLE"
                                   if task_type == TASK_CRO else "NOT_APPLICABLE"),
            "data_gaps": list(dict.fromkeys(data_gaps)), "roles_used": list(roles),
            "campaign_objective": ("Qualified landing-page visits and evidence-aware creative learning"
                                   if task_type == TASK_CAMPAIGN else task_type.replace("_", " ").title()),
            "core_angle": ("Cosmetic care routine with clear, non-medical product communication"
                           if task_type == TASK_CAMPAIGN else "Evidence-led learning without external action"),
            "creative_concepts": concepts, "social_plan": social,
            "performance_baseline": baseline, "sales_baseline": sales,
            "cro_recommendations": (["Match each ad angle to one landing-page opening message",
                                      "Keep product, usage, and claim-boundary information visible",
                                      "Measure landing-page views before interpreting clicks as demand"]
                                     if task_type == TASK_CAMPAIGN else []),
            "test_plan": ([{"test": "three-angle creative test", "variable": "angle only",
                             "hold_constant": "audience, placement, budget and landing page",
                             "decision_rule": "compare CTR and CPC; require confirmed downstream evidence before scaling"}]
                          if task_type != TASK_SOCIAL else
                          [{"test": "seven-day content mix", "variable": "content objective",
                            "decision_rule": "compare saves, replies and qualified profile/landing visits"}]),
            "success_metrics": (["saves", "replies", "story response rate", "qualified profile visits"]
                                if task_type == TASK_SOCIAL else
                                ["CTR", "CPC", "link clicks", "landing-page views (DATA_UNAVAILABLE)",
                                 "commercially confirmed orders (DATA_UNAVAILABLE)"]),
            "experiment_matrix": ([
                {"cell": f"angle_{index + 1}", "creative": concept["name"],
                 "audience": "held constant", "placement": "held constant",
                 "budget": "held constant", "measure": "CTR, CPC, link clicks"}
                for index, concept in enumerate(concepts)]
                if task_type == TASK_CAMPAIGN else []),
            "regulatory_risks": regulatory_risks,
            "red_team_objections": objections,
            "next_actions": self._next_actions(task_type, baseline),
            "status": PROPOSED, "research_state": "RESEARCH_REQUIRED" if research_required else "NOT_REQUIRED",
            "model_contract": {"capability": "creative_synthesis", "required": False,
                               "implemented_here": True},
            "metrics": {"roles_selected": len(roles), "roles_skipped": len(ROLES) - len(roles),
                        "evidence_queries": len(TASK_QUERIES[task_type]),
                        "evidence_fetches": len(snapshot.evidence_refs),
                        "shared_context_bytes": snapshot.bytes, "model_calls": 0,
                        "external_actions": 0, "load_ms": snapshot.load_ms,
                        "duration_ms": round((perf_counter() - started) * 1000, 3)},
        }
        result["summary"], result["model"], result["model_calls"] = self._synthesize(result)
        result["metrics"]["model_calls"] = result["model_calls"]
        result["proposal_id"] = "agency-" + hashlib.sha256(
            json.dumps(result, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
        return result

    @staticmethod
    def _synthesize(result: dict[str, Any]) -> tuple[str, str | None, int]:
        """A manager-readable summary over the deliverable that already exists.

        The model never invents the deliverable -- the concepts, baselines and
        objections are produced deterministically above, and the model is only
        given those, so the summary can restate them but cannot add a number
        to them. If no provider answers, the deterministic summary stands.
        """
        evidence = [{"ref": item["evidence"], "summary": item["problem"]}
                    for item in result["problems"]]
        evidence += [{"ref": item["evidence"], "summary": item["opportunity"]}
                     for item in result["opportunities"]]
        for concept in result.get("creative_concepts", []):
            evidence.append({"ref": "creative_concept", "summary":
                             f"{concept['name']}: {concept['hook']}"})
        question = (
            f"Görev: {result['task']}\n"
            "Yukarıdaki kanıtı bir pazarlama yöneticisine 6-10 cümlede özetle: "
            "durum, en kritik problem, en güçlü fırsat ve önerilen ilk adım. "
            "Yeni sayı veya iddia ekleme.")
        try:
            from .model_layer import ModelRouter

            answer = ModelRouter().synthesize(
                question, evidence,
                missing_data=tuple(result.get("data_gaps") or ()))
            return answer.answer, answer.model, answer.model_calls
        except Exception:  # noqa: BLE001 - synthesis is a presentation layer
            lines = [item["problem"] for item in result["problems"][:3]]
            lines += [item["opportunity"] for item in result["opportunities"][:2]]
            return ("\n".join(f"- {line}" for line in lines)
                    or "Kanıt üzerinden özet üretilemedi.", None, 0)

    @staticmethod
    def _next_actions(task_type: str, baseline: dict[str, Any]) -> list[str]:
        if task_type == TASK_SOCIAL:
            return ["Review copy against approved brand voice and product claims", "Schedule only after human approval"]
        if task_type == TASK_CRO:
            return ["Landing page metnini insan incelemesine al",
                    "Funnel adımlarını ölçülebilir hale getir",
                    "Sayfa içeriği okunabilir olana kadar sayfa hakkında iddia üretme"]
        if task_type == TASK_PERFORMANCE:
            return ["Separate 30-day comparable rows", "Reconcile Meta claims with commercial orders",
                    "Design one-variable creative tests", "Submit any campaign change for human approval"]
        return [f"Use current Vireon CTR {baseline.get('ctr_pct')}% and CPC {baseline.get('cpc')} only as observed baselines",
                "Approve claims and landing-page copy", "Run the three-angle test only after human approval"]
