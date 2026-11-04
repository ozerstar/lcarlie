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


# Limit concurrent model work even when a provider stops responding.
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='office-answer')
_SLOTS = BoundedSemaphore(2)
def synthesize_bounded(call, timeout=45):
    if not _SLOTS.acquire(blocking=False):
        raise TimeoutError('Yanıt hizmeti meşgul')
    try:
        future = _POOL.submit(call)
    except Exception:
        _SLOTS.release()
        raise
    future.add_done_callback(lambda _: _SLOTS.release())
    return future.result(timeout=timeout)

def fallback_answer(code, name, evidence, unread):
    from .display_language import display
    refs = sorted({str(item.get('ref') or '') for item in evidence if item.get('ref')})
    answer = (f"{display(name)} için {len(evidence)} kanıt parçası okunabildi. "
              "Ancak yanıt hizmeti sorunu nedeniyle sorunuza özel değerlendirme tamamlanamadı. "
              "Bu bir yönetici değerlendirmesi değildir; yalnızca kaynak erişiminin durumudur. ")
    answer += (f"Ayrıca {len(unread)} kaynak okunamadı. Kaynak bağlantılarını kontrol edin. " if unread else
               "Bu denemede okunamayan kaynak kaydı oluşmadı. ")
    answer += "Biraz sonra sorunuzu yeniden gönderebilirsiniz. Yapılmayan bir işlem tamamlanmış sayılmadı."
    return {'kod':code,'departman':display(name),'cevap':answer,
            'uyari':'Yönetici yanıtı üretilemedi; kaynak durumu gösteriliyor.',
            'kanit_sayisi':len(evidence),'kanit_kaynaklari':refs,'okunamayan':unread,
            'dogrulanmayan_sayilar':[],'model_kullanildi':False}
