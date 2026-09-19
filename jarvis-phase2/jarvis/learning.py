"""Geçmiş kararların sonucundan ders çıkarır. Sıfır model çağrısı.

NE ÖĞRENİR
Bir kararın hangi özelliklerle onaylandığını, hangileriyle iptal edildiğini
veya hiç karara bağlanmadığını sayar. Örüntü uydurulmaz: her ders kaç vakaya
dayandığını taşır ve örneklem küçükse ders üretilmez.

NEDEN DETERMİNİSTİK
Veri zaten yapılandırılmış (durum, risk sınıfı, red-team sonucu, kanıt
hazırlığı). Bunları saymak için modele ihtiyaç yok; model kullanmak hem
maliyet hem de sayının üstüne bir yorum katmanı koyup kesinliği bulandırmak
demek olurdu.

NE ÖĞRENEMEZ, DÜRÜSTÇE
Jarvis'in KENDİ önerilerinin sonucu burada yok: core.ai_action_proposal ve
ai_action_approval ai_reader'a kapalı (ölçüldü). Bu modül, şirketin karar
hattının (core.karar) sonuçlarından öğrenir. Jarvis'in kendi döngüsünü
kapatmak için ayrı bir okuma izni gerekir.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Bir dersin uretilmesi icin gereken en az vaka sayisi. Altinda kalan
# orintiler gurultu olabilir ve ders diye sunulmasi yaniltici olur.
MIN_SAMPLE = 3

# Karara baglanmis sayilan durumlar. PROPOSED bilerek disarida: henuz karar
# verilmemis demektir ve "sonuc" gibi sayilmasi basari oranini sisirir.
DECIDED = frozenset({"APPROVED", "REJECTED", "CANCELLED", "CONCLUDED", "DEFERRED"})
POSITIVE = frozenset({"APPROVED", "CONCLUDED"})
PENDING = frozenset({"PROPOSED"})


@dataclass(frozen=True)
class Lesson:
    code: str
    dimension: str
    value: str
    sample: int
    decided: int
    approved: int
    stuck: int
    approval_rate: float | None
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningReport:
    lessons: tuple[Lesson, ...] = ()
    skipped: tuple[dict[str, str], ...] = ()
    decisions: int = 0
    model_calls: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lessons": [lesson.to_dict() for lesson in self.lessons],
            "skipped": list(self.skipped),
            "decisions": self.decisions,
            "model_calls": self.model_calls,
            "external_actions": 0,
            "note": self.note,
        }


def _tally(rows: list[dict[str, Any]], dimension: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row.get(dimension)
        if key in (None, ""):
            continue
        key = str(key)
        # Serbest metin alanlari (risk gerekcesi gibi) boyut olamaz: her satir
        # kendi degeri olur ve sayim anlamsizlasir.
        if len(key) > 40:
            continue
        durum = str(row.get("durum") or "")
        bucket = out.setdefault(key, {"sample": 0, "decided": 0, "approved": 0, "stuck": 0})
        bucket["sample"] += 1
        if durum in DECIDED:
            bucket["decided"] += 1
        if durum in POSITIVE:
            bucket["approved"] += 1
        if durum in PENDING:
            bucket["stuck"] += 1
    return out


def _lessons_for(rows: list[dict[str, Any]], dimension: str, label: str,
                 skipped: list[dict[str, str]]) -> list[Lesson]:
    lessons: list[Lesson] = []
    for value, counts in sorted(_tally(rows, dimension).items(),
                                key=lambda item: -item[1]["sample"]):
        if counts["sample"] < MIN_SAMPLE:
            skipped.append({"dimension": dimension, "value": value,
                            "reason": f"{counts['sample']} vaka, en az {MIN_SAMPLE} gerekli"})
            continue
        decided = counts["decided"]
        rate = (counts["approved"] / decided) if decided else None
        if counts["stuck"] and not decided:
            summary = (f"{label} '{value}' olan {counts['sample']} kararın "
                       f"HİÇBİRİ karara bağlanmamış — hepsi beklemede.")
        elif rate is not None:
            summary = (f"{label} '{value}': karara bağlanan {decided} vakanın "
                       f"{counts['approved']}'i onaylanmış (%{rate * 100:.0f}).")
        else:
            summary = f"{label} '{value}': {counts['sample']} vaka, karar yok."
        lessons.append(Lesson(
            code=f"{dimension}:{value}", dimension=dimension, value=value,
            sample=counts["sample"], decided=decided, approved=counts["approved"],
            stuck=counts["stuck"],
            approval_rate=round(rate, 3) if rate is not None else None,
            summary=summary))
    return lessons


def analyze(decisions: list[dict[str, Any]]) -> LearningReport:
    """Karar kayıtlarından ders çıkarır."""
    skipped: list[dict[str, str]] = []
    lessons: list[Lesson] = []
    for dimension, label in (("red_team_sonucu", "Red-team sonucu"),
                             ("onay_hazirligi", "Onay hazırlığı"),
                             ("karar_tipi", "Karar tipi"),
                             ("kanit_kalitesi", "Kanıt kalitesi")):
        lessons.extend(_lessons_for(decisions, dimension, label, skipped))

    # En eyleme donuk ders once: hic karara baglanmayanlar, sonra dusuk
    # onay orani. Yuksek onay orani bir sorun degil, bilgi.
    def rank(lesson: Lesson) -> tuple[int, float]:
        if lesson.decided == 0 and lesson.stuck:
            return (0, -lesson.stuck)
        return (1, lesson.approval_rate if lesson.approval_rate is not None else 1.0)

    lessons.sort(key=rank)
    return LearningReport(
        lessons=tuple(lessons), skipped=tuple(skipped), decisions=len(decisions),
        model_calls=0,
        note=("Dersler yalnız sayımdır. Neden-sonuç iddia etmez; bir örüntü "
              "gördüğünde o örüntünün sebebini insan yorumlar."))


def provider_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sağlayıcı başına iş sonucu. Küçük örneklem açıkça işaretlenir."""
    out = []
    for row in rows:
        kararlar = int(row.get("karar_sayisi") or 0)
        out.append({
            "provider": row.get("provider"),
            "model": row.get("model"),
            "decisions": kararlar,
            "positive": row.get("olumlu"),
            "negative": row.get("olumsuz"),
            "business_score": row.get("is_puani"),
            "low_sample": kararlar < MIN_SAMPLE,
        })
    return sorted(out, key=lambda item: -(item["decisions"] or 0))


def run(memory: Any) -> dict[str, Any]:
    """Company Memory üzerinden dersleri üretir."""
    payload: dict[str, Any] = {"model_calls": 0, "external_actions": 0}
    try:
        decisions = memory.get_decision_outcomes().records
    except Exception as exc:  # noqa: BLE001
        return dict(payload, status="UNAVAILABLE", error=str(exc)[:250],
                    note="Karar sonuçları okunamadı; ders üretilmedi.")

    report = analyze(decisions)
    payload.update(report.to_dict())
    payload["status"] = "OK"

    try:
        payload["providers"] = provider_outcomes(memory.get_learning_loop().records)
    except Exception as exc:  # noqa: BLE001
        payload["providers"] = []
        payload["provider_error"] = str(exc)[:200]

    try:
        payload["evidence_readiness"] = [
            {"karar_tipi": row.get("karar_tipi"), "readiness": row.get("readiness"),
             "kanit_sinifi": row.get("kanit_sinifi")}
            for row in memory.get_evidence_readiness().records]
    except Exception:  # noqa: BLE001
        payload["evidence_readiness"] = []

    return payload
