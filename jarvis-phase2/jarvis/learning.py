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



# ----------------------------------------------------------------------
# 🔴 PANELDE İÇ KOD ADI GÖSTERİLİYORDU
#
# Ders satırları şöyle çıkıyordu:
#     "Onay hazırlığı 'EVIDENCE_OR_REVIEW_NEEDED' olan 6 kararın..."
#     "Karar tipi 'MEDIA_BUDGET': karara bağlanan 17 vakanın..."
# Sahip haklı olarak "ne demek istiyor, anlamıyorum" dedi. Bunlar
# veritabanının iç kodları; panelde okunacak metin DEĞİL.
#
# Sözlükte OLMAYAN bir kod olduğu gibi gösterilir -- uydurma bir Türkçe
# karşılık yazmak, kodu gizleyip yanlış anlam vermek olurdu.
TURKCE_DEGER: dict[str, str] = {
    # karar tipi
    "MEDIA_BUDGET": "reklam bütçesi",
    "CREATIVE_TEST": "kreatif testi",
    "PRODUCT_PRIORITY": "ürün önceliği",
    "OFFER_TEST": "teklif testi",
    "CRO_CHANGE": "site dönüşüm değişikliği",
    # onay hazırlığı
    "NO_ACTION": "eylem gerekmiyor",
    "EVIDENCE_OR_REVIEW_NEEDED": "kanıt ya da inceleme bekliyor",
    # red team
    "CHALLENGE": "itiraz etti",
    "SUPPORT": "destekledi",
    "INSUFFICIENT_EVIDENCE": "kanıtı yetersiz buldu",
    # kanıt kalitesi
    "LOW": "zayıf", "MEDIUM": "orta", "HIGH": "güçlü",
}


# 🔴 AYNI KOD, FARKLI ANLAM — ÜRETİMDE YAKALANDI
# `LOW` iki boyutta birden geçiyor ve ANLAMI AYNI DEĞİL:
#   kanit_kalitesi = LOW  -> "zayıf" (kanıt zayıf, kötü)
#   risk_class     = LOW  -> "düşük risk" (risk düşük, İYİ)
# Tek sözlük kullanınca panel "Jarvis önerisi — risk sınıfı — zayıf" yazdı;
# oysa o öneriler DÜŞÜK RİSKLİ, yani tam tersi. Sözlük artık boyutu da
# gözetir; boyuta özel karşılık yoksa genel sözlüğe düşer.
BOYUTA_GORE: dict[tuple[str, str], str] = {
    ("risk_class", "LOW"): "düşük risk",
    ("risk_class", "MEDIUM"): "orta risk",
    ("risk_class", "HIGH"): "yüksek risk",
    ("risk_class", "CRITICAL"): "kritik risk",
    ("action_type", "REQUEST_HUMAN_REVIEW"): "insan incelemesi talebi",
    ("action_type", "DRAFT_CUSTOMER_REPLY"): "müşteri yanıtı taslağı",
    ("action_type", "META_CAMPAIGN_CHANGE"): "Meta kampanya değişikliği",
    ("action_type", "PRICE_CHANGE"): "fiyat değişikliği",
    ("action_type", "WIX_PUBLISH"): "Wix yayını",
    ("action_type", "WHATSAPP_SEND_TEMPLATE"): "WhatsApp şablon gönderimi",
}


def _oku(deger: str, boyut: str = "") -> str:
    """İç kodu Türkçeye çevirir. Bilinmiyorsa OLDUĞU GİBİ bırakır."""
    ozel = BOYUTA_GORE.get((boyut, str(deger)))
    if ozel:
        return ozel
    return TURKCE_DEGER.get(str(deger), str(deger))


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
        # 🔴 SAYI EKİ KODDA ÜRETİLMEZ — CÜMLE YENİDEN KURULUR.
        # Eski biçim "{approved}'i onaylanmış" yazıyordu ve Türkçe'de bu
        # sayıya göre değişir: 3'ü, 12'si, 14'ü, 20'si, 6'sı. Panelde
        # "12'i onaylanmış", "6'i onaylanmış" diye YANLIŞ çıkıyordu.
        # Ek üretmeye çalışmak yerine "N tanesi" kalıbı kullanılır; bu
        # kalıp HER sayıyla doğrudur.
        #
        # 🔴 AYRICA İKİ SAYI BİRDEN YAZILIR. Cümle "karara bağlanan 17
        # vaka" derken rozette "21 vaka" yazıyordu ve ikisinin farkı
        # hiçbir yerde açıklanmıyordu. Artık toplam da, karara bağlanan
        # da aynı cümlede.
        okunur = _oku(value, dimension)
        if counts["stuck"] and not decided:
            summary = (f"{label} — {okunur}: {counts['sample']} kararın "
                       f"tamamı hâlâ beklemede, hiçbiri karara bağlanmamış. "
                       f"Bunlar sizin kararınızı bekliyor.")
        elif rate is not None:
            bekleyen = (f" {counts['stuck']} tanesi hâlâ bekliyor."
                        if counts["stuck"] else "")
            summary = (f"{label} — {okunur}: toplam {counts['sample']} karardan "
                       f"{decided} tanesi karara bağlanmış, bunlardan "
                       f"{counts['approved']} tanesi onaylanmış "
                       f"(%{rate * 100:.0f}).{bekleyen}")
        else:
            summary = (f"{label} — {okunur}: {counts['sample']} karar var, "
                       f"henüz hiçbiri karara bağlanmamış.")
        lessons.append(Lesson(
            code=f"{dimension}:{value}", dimension=dimension, value=value,
            sample=counts["sample"], decided=decided, approved=counts["approved"],
            stuck=counts["stuck"],
            approval_rate=round(rate, 3) if rate is not None else None,
            summary=summary))
    return lessons


# 🔴 İKİ AYRI KAYNAK, AYNI PANODA — KARIŞTIRILMADAN
# `core.karar`  : şirketin karar defteri (reklam bütçesi, kreatif testi…)
# `mart.ai_oneri_sonuc` : Jarvis'in KENDİ önerilerinin sonucu
# İkisini tek havuza atmak "onay oranı" sayısını anlamsız kılardı: biri
# insanın işletme kararı, öteki makinenin önerisi. Ders satırı hangi
# kaynaktan geldiğini SÖYLER.
KAYNAK_ETIKET = {
    "sirket": "Şirket kararları",
    "jarvis": "Jarvis'in kendi önerileri",
}


def analyze(decisions: list[dict[str, Any]],
            own_proposals: list[dict[str, Any]] | None = None) -> LearningReport:
    """Karar kayıtlarından ders çıkarır.

    `own_proposals` verilirse Jarvis'in kendi önerileri de AYRI boyutlar
    olarak eklenir; verilmezse davranış eskisiyle birebir aynıdır.
    """
    skipped: list[dict[str, str]] = []
    lessons: list[Lesson] = []
    for dimension, label in (("red_team_sonucu", "Red-team sonucu"),
                             ("onay_hazirligi", "Onay hazırlığı"),
                             ("karar_tipi", "Karar tipi"),
                             ("kanit_kalitesi", "Kanıt kalitesi")):
        lessons.extend(_lessons_for(decisions, dimension, label, skipped))

    # Jarvis'in kendi önerileri -- ayrı etiketle, aynı sayma mantığıyla.
    if own_proposals:
        for dimension, label in (("action_type", "Jarvis önerisi — eylem tipi"),
                                 ("risk_class", "Jarvis önerisi — risk sınıfı")):
            lessons.extend(_lessons_for(own_proposals, dimension, label, skipped))

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

    # 🔴 Kendi önerileri OKUNAMAZSA ders yine üretilir, sessizce değil.
    # Migration 024 öncesinde bu görünüm yoktu; eski bir kurulumda ya da
    # geri alma sonrası burada patlamak, ŞİRKET derslerini de yok ederdi.
    kendi_oneri: list = []
    kendi_hata = ""
    try:
        kendi_oneri = list(memory._fetch("own_proposals").records)
    except Exception as exc:  # noqa: BLE001
        kendi_hata = str(exc)[:200]

    report = analyze(decisions, kendi_oneri)
    payload.update(report.to_dict())
    payload["status"] = "OK"
    payload["kendi_oneri_sayisi"] = len(kendi_oneri)
    if kendi_hata:
        payload["kendi_oneri_hatasi"] = kendi_hata
        payload["kendi_oneri_notu"] = (
            "Jarvis'in kendi önerileri okunamadı; dersler yalnız şirket "
            "karar defterinden çıkarıldı.")

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

    try:
        from .improvement import Store
        payload["improvement"] = Store().snapshot()
    except Exception as exc:  # noqa: BLE001
        payload["improvement"] = {"error_type": type(exc).__name__}
    return payload
