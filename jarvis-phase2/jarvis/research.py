from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    publisher: str
    entity: str
    claim: str
    observed_at: str
    authority: float


def fuse(records: list[SourceRecord]) -> dict[str, Any]:
    unique = {(r.publisher.casefold(), r.claim.casefold()): r for r in records}
    values = list(unique.values())
    claims = {r.claim.casefold() for r in values}
    publishers = {r.publisher.casefold() for r in values}
    contradiction = len(claims) > 1
    independent = len(publishers)
    confidence = min(1.0, sum(r.authority for r in values) / max(2, len(values)))
    if contradiction:
        confidence *= 0.5
    return {
        "records": [r.__dict__ for r in values], "independent_sources": independent,
        "contradiction": contradiction, "confidence": round(confidence, 3),
        "needs_more_sources": independent < 2 or contradiction,
    }
