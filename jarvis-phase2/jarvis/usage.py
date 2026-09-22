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
demektir. Bu yüzden defter TOKEN sayar.

22.09.2026 — sahip fiyatların da görünmesini istedi. Gerekçe çürütülmedi,
ETKİSİZLEŞTİRİLDİ: fiyatlar `model_fiyat.py` içinde ALINDIĞI TARİH ve
KAYNAK URL'siyle durur, panel tarihi de gösterir, tablo eskirse uyarır ve
fiyatı tanımsız model için maliyet hesaplanmaz (sıfır da yazılmaz).
Rakam yine de ÖLÇÜM DEĞİL, liste fiyatı tahminidir; kesin rakam
sağlayıcının faturasıdır ve defter o faturayı doğrulamak için vardır.

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
           is_anahtari: str | None = None,
           kademe: str | None = None,
           prompt_tokens: int | None = None,
           completion_tokens: int | None = None,
           elapsed_s: float | None = None,
           tier: str = "", ok: bool = True, error: str = "") -> None:
    """Bir model çağrısını deftere yazar. Metin KAYDEDİLMEZ."""
    satir = {
        # Hangi is harcadi: maliyet ise gore ayrilabilsin.
        "is_anahtari": is_anahtari,
        "kademe": kademe,
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
        # 🔴 ANAHTAR (saglayici, model) CIFTIDIR. Yalniz saglayiciya gore
        # gruplamak, ayni saglayicinin farkli fiyatli iki modelini tek
        # satirda toplar ve grubun fiyatini ILK gorulen modelden alir.
        # Olculdu: gemini-3-pro-image (120 $/1M) ile gemini-3.5-flash-lite
        # (2,50 $/1M) arasinda 48 kat fark var.
        model_ad = str(kayit.get("model") or "?")
        kutu = saglayicilar.setdefault((ad, model_ad), {
            "provider": ad, "model": model_ad,
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

    # --- liste fiyatindan TAHMINI maliyet -------------------------------
    # 🔴 Defter hala para OLCMUYOR. Asagidaki rakam, `model_fiyat` icindeki
    # TARIHLI liste fiyatinin token sayisiyla carpimidir. Sahip 22.09.2026'da
    # "fiyatlarini da yanlarina yaz" dedi; gercegi gizlemeden yaziyoruz:
    # her satir hangi birim fiyattan hesaplandigini da tasir, fiyati
    # bilinmeyen model icin maliyet NONE kalir -- sifir degil.
    from . import model_fiyat

    for kutu in saglayicilar.values():
        birim = model_fiyat.fiyat(kutu["provider"], str(kutu.get("model") or ""))
        if birim is None:
            kutu["birim_girdi_usd_m"] = None
            kutu["birim_cikti_usd_m"] = None
            kutu["parali"] = None          # bilinmiyor; "ucretsiz" DEGIL
            kutu["maliyet_usd"] = None
            kutu["maliyet_try"] = None
            kutu["cagri_basi_try"] = None
            kutu["fiyat_notu"] = "liste fiyatı tanımlı değil"
            continue
        kutu["birim_girdi_usd_m"] = birim["girdi"]
        kutu["birim_cikti_usd_m"] = birim["cikti"]
        kutu["fiyat_notu"] = birim.get("not") or ""
        # 🔴 PARA HARCIYOR MU: fiyat tablosundan turetilir, `paid`den DEGIL.
        # `paid` zincirde "yalnizca derin modda dene" demektir; Gemini orada
        # False ama anahtari FATURALI, yani her cagri para harciyor.
        kutu["parali"] = bool(birim["girdi"] or birim["cikti"])
        m = model_fiyat.maliyet(kutu["provider"], str(kutu.get("model") or ""),
                                kutu["prompt_tokens"], kutu["completion_tokens"])
        if m is None:
            kutu["maliyet_usd"] = kutu["maliyet_try"] = None
            kutu["cagri_basi_try"] = None
            continue
        kutu["maliyet_usd"] = m["usd"]
        kutu["maliyet_try"] = m["try"]
        # 🔴 BOLEN `calls` DEGIL `tokens_known`. Token sayisi bilinmeyen
        # cagrilari da bolene katmak, ortalamayi oldugundan DUSUK gosterirdi.
        bilinen = kutu["tokens_known"] or 0
        kutu["cagri_basi_try"] = round(m["try"] / bilinen, 4) if bilinen else None

    # --- hic cagrilmamis ama KURULU saglayicilar --------------------------
    # 🔴 SAHIBIN SORUSUNDAN DOGDU (22.09.2026): "bizim model kullanimda neden
    # chat gpt yok?" Cevap: bagli ama zincirin sonuncusu ve ucretli oldugu
    # icin sirasi hic gelmiyor. Defter yalnizca CAGRILAN saglayiciyi
    # listeledigi surece bu soru her seferinde tekrar sorulur; panel
    # "kurulu, 0 cagri" satirini gostererek kendi cevabini vermeli.
    try:
        from .providers import PROVIDERS, available
        # 🔴 Anahtarlar `os.environ`da DEGIL, `load_env()` ile okunan
        # dosyada. `available()` zaten bu isi yapiyor; kendi kopyasini
        # yazmak, anahtar kaynagi degisince sessizce yanlis liste verirdi.
        kurulu = set(available())
        mevcut_adlar = {k[0] for k in saglayicilar}
        for p in PROVIDERS:
            if p.name in mevcut_adlar or p.name not in kurulu:
                continue
            birim = model_fiyat.fiyat(p.name, p.default_model)
            saglayicilar[(p.name, p.default_model)] = {
                "provider": p.name, "model": p.default_model, "paid": bool(p.paid),
                "calls": 0, "failed": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "tokens_known": 0,
                "total_s": 0.0, "avg_s": 0, "token_coverage": "0/0",
                "kullanilmadi": True,
                "birim_girdi_usd_m": birim["girdi"] if birim else None,
                "birim_cikti_usd_m": birim["cikti"] if birim else None,
                "parali": bool(birim["girdi"] or birim["cikti"]) if birim else None,
                "maliyet_usd": 0.0 if birim else None,
                "maliyet_try": 0.0 if birim else None,
                "cagri_basi_try": None,
                "fiyat_notu": (birim or {}).get("not", ""),
            }
    except Exception:  # noqa: BLE001 - liste zenginlestirme cagriyi bozamaz
        pass

    toplam_usd = sum(k["maliyet_usd"] or 0 for k in saglayicilar.values())
    fiyati_bilinmeyen = [k["provider"] for k in saglayicilar.values()
                         if k["maliyet_usd"] is None and k["calls"]]

    # 🔴 ESKIDEN `paid` sayiliyordu ve "1 ucretli cagri" yaziyordu; gercekte
    # 81 cagrinin 80'i para harcamisti (Gemini faturali). Sayac artik FIYATA
    # bakiyor. `paid` olan saglayici ayrica "yalniz derin modda" diye
    # isaretlenir -- bu bir MALIYET degil, YONLENDIRME bilgisidir.
    for kutu in saglayicilar.values():
        kutu["sadece_derin"] = bool(kutu.get("paid"))
    ucretli = [k for k in saglayicilar.values() if k.get("parali")]
    return {
        "days": days,
        "providers": sorted(saglayicilar.values(),
                            key=lambda k: (-k["calls"], k["provider"])),
        "total_calls": sum(k["calls"] for k in saglayicilar.values()),
        "paid_calls": sum(k["calls"] for k in ucretli),
        "ucretsiz_calls": sum(k["calls"] for k in saglayicilar.values()
                              if k.get("parali") is False),
        "tahmini_maliyet_usd": round(toplam_usd, 4),
        "tahmini_maliyet_try": round(toplam_usd * model_fiyat.USD_TRY, 2),
        "fiyati_bilinmeyen": fiyati_bilinmeyen,
        "fiyat_tablosu": model_fiyat.ozet_bilgisi(),
        "note": ("Defter TOKEN sayar. Yanındaki para rakamı ÖLÇÜM DEĞİL, "
                 "sağlayıcının ilan ettiği liste fiyatının token sayısıyla "
                 "çarpımıdır; indirim, önbellek ve toplu iş çarpanları "
                 "hesaba katılmaz. Gerçek rakam sağlayıcının faturasıdır, "
                 "bu tablo o faturayı DOĞRULAMAK içindir."),
    }
