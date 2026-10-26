"""Ground a manager's office answer in the latest measured team activity."""
from __future__ import annotations

from typing import Any


def activity_evidence(
    department: str,
    member_keys: tuple[str, ...],
    report: dict[str, Any],
    active: dict[str, dict[str, Any]],
) -> dict[str, str] | None:
    """Describe observations without treating absence of an event as idleness."""
    cycle_at = str(report.get("generated_at") or "")
    activity = report.get("activity") or {}
    measured = []
    for key in member_keys:
        row = activity.get(key)
        if not isinstance(row, dict):
            continue
        measured.append(
            f"{key}: durum={str(row.get('status') or 'BİLİNMİYOR')[:30]}; "
            f"iş={str(row.get('task') or 'belirtilmedi')[:100]}; "
            f"sonuç={str(row.get('result') or 'kayıt yok')[:160]}; "
            f"bitiş={str(row.get('finished_at') or 'yok')[:40]}"
        )
    working = [
        f"{key}: {str(active[key].get('task') or 'görev sürüyor')[:100]}"
        for key in member_keys if key in active and isinstance(active[key], dict)
    ]
    if not cycle_at and not working:
        return None
    parts = [
        f"BİRİM FAALİYET KAYDI ({department}). Son ekip ölçümü: {cycle_at or 'yok'}. "
        "Bu bir anlık gözlem ve son ölçümdür; çalışma saati veya boş durma kanıtı değildir."
    ]
    parts.append("Şu anda kayıtlı çalışma: " + (" | ".join(working) if working else
                 "yok. Bu, ekibin boş durduğunu kanıtlamaz."))
    parts.append("Son ölçümdeki işler: " + (" | ".join(measured) if measured else "kayıt yok."))
    return {
        "ref": f"office:team-cycle:{department}:{cycle_at or 'live'}",
        "summary": "\n".join(parts)[:2500],
    }
