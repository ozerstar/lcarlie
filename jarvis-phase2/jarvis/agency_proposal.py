"""Ajans fikrini onaylanabilir öneriye çevirir.

KAPATILAN BOŞLUK
AgencyCapability kreatif konsept üretiyordu ama çıktısı bir metin bloğunda
kalıyordu: kimse onaylayamıyor, hiçbir şey kuyruğa düşmüyor, "fikir" ile
"yapılabilir iş" arasında köprü yoktu.

NE YAPAR
Her konseptin YAYIMLANACAK metnini birleştirir, gerçek mevzuat kapısından
geçirir ve geçenler için Action Firewall zarfı üretir. Zarf, mevcut
core.ai_propose_action yoluna olduğu gibi verilebilir.

NE YAPMAZ
Hiçbir şey yayımlamaz, hiçbir şey göndermez. Üretilen her zarf PROPOSED
durumundadır ve insan onayı bekler; EXTERNAL_ACTIONS bu modülden bağımsız
olarak kapalıdır ve bu modül onu okumaz bile.

NEDEN KONSEPT BAŞINA
Bir konseptin bloklu olması diğerlerini düşürmez. Tek tek denenir; bloklu
olan gerekçesiyle işaretlenir, geçen öneri olur. Toplu reddetmek, uyumlu
fikirleri de çöpe atardı.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .compliance import review
from .firewall import ContractDriftError, FirewallError, validate_proposal

# Konseptin yayımlanacak yüzü. name/id gibi iç alanlar denetlenmez: onlar
# müşteriye görünmez ve taranırsa yanlış alarm üretirler.
PUBLISHABLE_FIELDS = ("hook", "caption_direction", "headline", "body", "cta",
                      "visual_direction", "topic", "angle")

PROPOSABLE = "PROPOSABLE"
BLOCKED = "BLOCKED"
NO_TEXT = "NO_TEXT"


@dataclass(frozen=True)
class ScreenedConcept:
    name: str
    status: str
    text: str = ""
    blocked: tuple[dict[str, Any], ...] = ()
    verify: tuple[dict[str, Any], ...] = ()
    envelope: dict[str, Any] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgencyProposalSet:
    task: str
    objective: str
    concepts: tuple[ScreenedConcept, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()

    @property
    def proposable(self) -> tuple[ScreenedConcept, ...]:
        return tuple(c for c in self.concepts if c.status == PROPOSABLE)

    @property
    def blocked(self) -> tuple[ScreenedConcept, ...]:
        return tuple(c for c in self.concepts if c.status == BLOCKED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "objective": self.objective,
            "concepts": [c.to_dict() for c in self.concepts],
            "proposable_count": len(self.proposable),
            "blocked_count": len(self.blocked),
            "evidence_refs": list(self.evidence_refs),
            "data_gaps": list(self.data_gaps),
            "external_actions": 0,
            "human_approval_required": True,
            "note": ("Her öneri PROPOSED durumundadır. Onaylanmadan hiçbir şey "
                     "yayımlanmaz; yayımlama yetkisi bu modülde yoktur."),
        }


def publishable_text(concept: dict[str, Any]) -> str:
    """Konseptin müşteriye görünecek metni."""
    parts = [str(concept[field]).strip() for field in PUBLISHABLE_FIELDS
             if isinstance(concept.get(field), str) and concept[field].strip()]
    return "\n".join(parts)


def _intent_for(objective: str) -> str:
    # Sosyal plan ve kampanya farklı kanonik tiplere düşer; ikisi de mevzuat
    # kapısının kapsamındadır.
    return ("META_CAMPAIGN_CHANGE" if objective == "CAMPAIGN_PROPOSAL"
            else "CUSTOMER_REPLY_DRAFT")


def screen(result: dict[str, Any], contract: Any = None,
           checked_at: str = "") -> AgencyProposalSet:
    """Ajans çıktısını tarar ve geçen konseptler için öneri zarfı üretir."""
    objective = str(result.get("objective") or "")
    intent = _intent_for(objective)
    concepts_in = list(result.get("creative_concepts") or []) + \
        list(result.get("social_plan") or [])

    screened: list[ScreenedConcept] = []
    for index, concept in enumerate(concepts_in):
        name = str(concept.get("name") or concept.get("topic") or f"konsept-{index + 1}")
        text = publishable_text(concept)
        if not text:
            screened.append(ScreenedConcept(name=name, status=NO_TEXT))
            continue

        verdict = review(text, checked_at=checked_at)
        if verdict.blocked:
            screened.append(ScreenedConcept(
                name=name, status=BLOCKED, text=text,
                blocked=tuple(f.to_dict() for f in verdict.blocked),
                verify=tuple(f.to_dict() for f in verdict.verify)))
            continue

        envelope = None
        error = ""
        if contract is not None:
            payload = {"subject_ref": f"agency:{objective}:{index + 1}", "reason": text}
            try:
                envelope = validate_proposal(intent, payload, contract,
                                             idempotency_key=f"action:agency:{objective}:{index + 1}")
            except (FirewallError, ContractDriftError) as exc:
                # Kapı burada da devrede: firewall reddederse konsept önerilemez.
                screened.append(ScreenedConcept(
                    name=name, status=BLOCKED, text=text,
                    verify=tuple(f.to_dict() for f in verdict.verify),
                    error=str(exc)[:300]))
                continue
        screened.append(ScreenedConcept(
            name=name, status=PROPOSABLE, text=text,
            verify=tuple(f.to_dict() for f in verdict.verify),
            envelope=envelope, error=error))

    return AgencyProposalSet(
        task=str(result.get("task") or ""), objective=objective,
        concepts=tuple(screened),
        evidence_refs=tuple(result.get("evidence_refs") or ()),
        data_gaps=tuple(result.get("data_gaps") or ()))
