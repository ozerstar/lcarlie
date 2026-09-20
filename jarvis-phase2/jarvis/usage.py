"""Model kullanım defteri: hangi sağlayıcıya ne kadar gitti.

NEDEN VAR
20.09.2026'da ücretli sağlayıcılar (Claude, OpenAI) zincire bağlandı.
Harcamayı gösteren hiçbir şey yoktu: aylık fatura gelene kadar fark
edilmezdi. Ölçülmeyen maliyet, kontrol edilmeyen maliyettir.

NE KAYDEDER
Her dış model çağrısı için: sağlayıcı, model, ücretli mi, token sayıları,
süre, zaman. Cevabın METNİ KAYDEDİLMEZ -- defter bir maliyet kaydıdır,
konuşma arşivi değil; şirket verisi burada ikinci kez saklanmamalı.

MALİYET TAHMİNİ
Token başı fiyat sağlayıcıya ve modele göre değişir ve zamanla değişir.
Buraya sabit fiyat yazmak, bir gün sessizce yanlış rakam göstermek
demektir. Bu yüzden defter TOKEN sayar, para tahmin ETMEZ. Fiyat
öğrenilmek istenirse sağlayıcının kendi faturası bakılır; defter o
faturayı doğrulamak için kullanılır.

DEFTER BOZULURSA ÇAĞRIYI ENGELLEMEZ
Yazma hatası yutulur. Maliyet kaydı tutulamıyor diye Jarvis susmamalı.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
LEDGER = STATE_DIR / "model_usage.jsonl"

# Defter buyudukce okuma pahalanir. Ozet son N satirla sinirlanir.
MAX_READ_LINES = 20_000


def record(provider: str, model: str, paid: bool, *,
           prompt_tokens: int | None = None,
           completion_tokens: int | None = None,
           elapsed_s: float | None = None,
           tier: str = "", ok: bool = True, error: str = "") -> None:
    """Bir model çağrısını deftere yazar. Metin KAYDEDİLMEZ."""
    satir = {
        "at": round(time.time(), 3),
        "provider": provider, "model": model, "paid": bool(paid),
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "elapsed_s": elapsed_s, "tier": tier, "ok": bool(ok),
    }
    if error:
        satir["error"] = str(error)[:160]
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(satir, ensure_ascii=False) + "\n")
    except OSError:
        # Defter tutulamiyor diye cagri engellenmez.
        pass


def _read(since: float | None = None) -> list[dict[str, Any]]:
    try:
        satirlar = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for satir in satirlar[-MAX_READ_LINES:]:
        if not satir.strip():
            continue
        try:
            kayit = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if since and float(kayit.get("at") or 0) < since:
            continue
        out.append(kayit)
    return out


def summary(days: float = 7.0) -> dict[str, Any]:
    """Sağlayıcı başına kullanım. Para TAHMİN EDİLMEZ, token sayılır."""
    since = time.time() - days * 86400
    kayitlar = _read(since)
    saglayicilar: dict[str, dict[str, Any]] = {}
    for kayit in kayitlar:
        ad = str(kayit.get("provider") or "?")
        kutu = saglayicilar.setdefault(ad, {
            "provider": ad, "model": kayit.get("model"),
            "paid": bool(kayit.get("paid")), "calls": 0, "failed": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "tokens_known": 0,
            "total_s": 0.0,
        })
        kutu["calls"] += 1
        if not kayit.get("ok", True):
            kutu["failed"] += 1
        giris, cikis = kayit.get("prompt_tokens"), kayit.get("completion_tokens")
        if giris is not None or cikis is not None:
            kutu["tokens_known"] += 1
            kutu["prompt_tokens"] += int(giris or 0)
            kutu["completion_tokens"] += int(cikis or 0)
        kutu["total_s"] += float(kayit.get("elapsed_s") or 0)

    for kutu in saglayicilar.values():
        kutu["avg_s"] = round(kutu["total_s"] / kutu["calls"], 2) if kutu["calls"] else 0
        kutu["total_s"] = round(kutu["total_s"], 1)
        # Token sayisi her saglayicida gelmez; kac cagrida BILINDIGI yazilir
        # ki eksik veri tam veri gibi okunmasin.
        kutu["token_coverage"] = (f"{kutu['tokens_known']}/{kutu['calls']}")

    ucretli = [k for k in saglayicilar.values() if k["paid"]]
    return {
        "days": days,
        "providers": sorted(saglayicilar.values(), key=lambda k: -k["calls"]),
        "total_calls": sum(k["calls"] for k in saglayicilar.values()),
        "paid_calls": sum(k["calls"] for k in ucretli),
        "note": ("Defter TOKEN sayar, para tahmin etmez: birim fiyat "
                 "sağlayıcıya ve zamana göre değişir ve buraya sabit yazmak "
                 "bir gün sessizce yanlış rakam göstermek olurdu. Ücretli "
                 "çağrı sayısı ve token toplamı, sağlayıcının kendi "
                 "faturasını doğrulamak için kullanılır."),
    }
