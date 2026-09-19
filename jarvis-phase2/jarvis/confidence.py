"""Güven skorunu parçalara ayırır — tek sayı neyin eksik olduğunu söylemez.

ÖLÇÜLEN SORUN
Research Controller tek bir `confidence` döndürüyordu. Gerçek benchmark'ta bu
sayı, kaynaklar alakasız e-ticaret kategori sayfalarıyken de (0.346) gerçek bir
sektör raporu bulunduğunda da (0.431) neredeyse aynıydı. Okuyan kişi iki durumu
ayırt edemiyor ve "0.4 düşükmüş" deyip geçiyor — ama NEDEN düşük olduğu, ne
yapılması gerektiğini belirleyen tek bilgi.

ALTI BOYUT
    evidence_completeness  sorulan iddialar gerçekten karşılandı mı
    source_independence    kaç GERÇEKTEN bağımsız kök kaynak var
    source_quality         kaynaklar konuya ne kadar hâkim
    recency                veri ne kadar taze
    claim_consistency      kaynaklar birbirini yalanlıyor mu
    model_uncertainty      model tahmini karıştı mı (deterministik yolda 0)

NEDEN EN ZAYIF HALKA
`overall` boyutların ORTALAMASI değil, EN DÜŞÜĞÜDÜR. Ortalama, bir boyuttaki
çöküşü diğerleriyle örter: beş kopya kaynak `source_quality`yi yükseltip
`source_independence` sıfıra yakınken bile toplamı iyi gösterir. Bir sonuç, onu
taşıyan en zayıf desteği kadar sağlamdır. Bu aynı zamanda skoru şişirmeyi
imkânsız kılar — bir boyutu doldurmak toplamı yükseltmez.

Ayrıca `limiting_factor` her zaman raporlanır: "0.25 çünkü bağımsız kaynak yok"
eyleme dönüşür, "0.4" dönüşmez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Kendi hakkında konuşan kaynak, kendisinin bağımsız doğrulaması sayılmaz.
NON_INDEPENDENT_TYPES = frozenset({"COMPANY", "RETAILER", "MARKETPLACE"})

# Konuyu bilmeyen kaynak türleri: bulunmaları iyi ama kanıt ağırlıkları düşük.
LOW_AUTHORITY_TYPES = frozenset({"UNKNOWN", "COMMUNITY"})

DIMENSIONS = ("evidence_completeness", "source_independence", "source_quality",
              "recency", "claim_consistency", "model_uncertainty")


@dataclass(frozen=True)
class Confidence:
    evidence_completeness: float
    source_independence: float
    source_quality: float
    recency: float
    claim_consistency: float
    model_uncertainty: float
    overall: float
    limiting_factor: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _completeness(sources, required_claims: tuple[str, ...]) -> tuple[float, str]:
    """Sorulan iddia yoksa, çıkarılan iddia sayısına bakılır.

    Eski davranış `coverage = 1.0 if not required` idi: hiç iddia çıkarılmamış bir
    araştırma tam kapsama görünüyordu. Sıfır iddia, tam kapsama değildir.
    """
    if required_claims:
        covered = {claim for source in sources for claim in source.claims
                   if claim in required_claims}
        ratio = len(covered) / len(required_claims)
        return _clamp(ratio), f"{len(covered)}/{len(required_claims)} istenen iddia karşılandı"
    total_claims = sum(len(source.claims) for source in sources)
    snippets = sum(len(getattr(source, "evidence_snippets", ()) or ()) for source in sources)
    carried = total_claims + snippets
    if not carried:
        return 0.0, "hiçbir kaynaktan doğrulanabilir iddia veya alıntı çıkarılamadı"
    # Üç somut kanıt parçası, tek bir soru için yeterli taban kabul edilir.
    return _clamp(carried / 3.0), f"{carried} kanıt parçası (iddia + alıntı) çıkarıldı"


def _independence(sources, minimum: int) -> tuple[float, str]:
    independent = {source.origin_id for source in sources
                   if getattr(source, "source_type", "UNKNOWN") not in NON_INDEPENDENT_TYPES}
    if minimum <= 0:
        return 1.0, "bağımsızlık eşiği tanımlı değil"
    ratio = len(independent) / minimum
    self_reported = len(sources) - len(
        [s for s in sources if getattr(s, "source_type", "UNKNOWN") not in NON_INDEPENDENT_TYPES])
    note = f"{len(independent)}/{minimum} bağımsız kök kaynak"
    if self_reported:
        note += f"; {self_reported} kaynak kendi hakkında konuşuyor, sayılmadı"
    return _clamp(ratio), note


def _quality(sources) -> tuple[float, str]:
    if not sources:
        return 0.0, "kaynak yok"
    scores = []
    weak = 0
    for source in sources:
        authority = _clamp(getattr(source, "authority", 0.0))
        if getattr(source, "source_type", "UNKNOWN") in LOW_AUTHORITY_TYPES:
            authority *= 0.6
            weak += 1
        scores.append(authority)
    mean = sum(scores) / len(scores)
    note = f"ortalama kaynak otoritesi {mean:.2f}"
    if weak:
        note += f"; {weak} kaynağın türü belirlenemedi veya topluluk içeriği"
    return _clamp(mean), note


def _recency(sources) -> tuple[float, str]:
    if not sources:
        return 0.0, "kaynak yok"
    values = [_clamp(getattr(source, "freshness", 0.0)) for source in sources]
    mean = sum(values) / len(values)
    undated = sum(1 for source in sources if not getattr(source, "observed_at", ""))
    note = f"ortalama tazelik {mean:.2f}"
    if undated:
        note += f"; {undated} kaynakta yayın tarihi yok"
    return mean, note


def _consistency(contradictions) -> tuple[float, str]:
    count = len(contradictions or ())
    if not count:
        return 1.0, "çelişki bulunmadı"
    # Her çelişki güveni yarıya indirir; iki çelişki 0.25.
    return _clamp(0.5 ** count), f"{count} çelişki açık"


def _model_uncertainty(model_calls: int) -> tuple[float, str]:
    if not model_calls:
        return 1.0, "model çağrısı yok, sonuç deterministik"
    # Model devredeyse belirsizlik ölçülmedi; ölçülmemişi 1.0 saymak skoru şişirir.
    return 0.7, f"{model_calls} model çağrısı var, belirsizliği ayrıca ölçülmedi"


def score(sources, contradictions=(), required_claims: tuple[str, ...] = (),
          min_independent_sources: int = 2, model_calls: int = 0) -> Confidence:
    """Altı boyutu ayrı ayrı hesaplar ve en zayıf halkayı bildirir."""
    sources = list(sources or ())
    parts = {
        "evidence_completeness": _completeness(sources, required_claims),
        "source_independence": _independence(sources, min_independent_sources),
        "source_quality": _quality(sources),
        "recency": _recency(sources),
        "claim_consistency": _consistency(contradictions),
        "model_uncertainty": _model_uncertainty(model_calls),
    }
    values = {name: round(value, 3) for name, (value, _) in parts.items()}
    limiting = min(values, key=lambda name: (values[name], name))
    overall = values[limiting]
    return Confidence(
        overall=overall, limiting_factor=limiting,
        explanation=f"{limiting} = {values[limiting]:.2f} — {parts[limiting][1]}",
        **values,
    )


def summary_line(confidence: Confidence) -> str:
    """Rapora tek satır: sayı tek başına asla verilmez, gerekçesiyle verilir."""
    return f"güven {confidence.overall:.2f} · sınırlayan: {confidence.explanation}"
