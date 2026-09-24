"""Kademe telemetrisi: her model denemesi tek satir JSONL olarak yazilir.

NEDEN VAR. Model zinciri gpu -> local -> external calisiyordu ama HANGI
kademenin cevap verdigi hicbir yere yazilmiyordu. 24.09.2026'da olculdu:
sunucu yeniden baslayinca GPU ucunun ters tuneli dustu ve sistem dokuz kat
yavas kademede (7,45 jeton/sn) kosmaya devam etti -- panel de, alarm da bunu
goremedi, cunku kimse kaydetmiyordu. LiteLLM belgelerindeki ilke aynen
gecerli: yedek devreye girdiginde KAYDET, yoksa gercek ariza sessiz kalir.

KAPSAM. Bu modul yalniz yazar. Hicbir karar vermez, hicbir istegi engellemez,
hicbir seyi yeniden dener. Yazma hatasi cagirani ASLA etkilemez -- telemetri
kaybi, cevabin kaybindan iyidir.

BAGIMLILIK YOK. Uretim makinesinde psycopg kurulu degil (bkz.
scripts/psql_session.py basligi), o yuzden Postgres'e dogrudan yazilmaz.
Satirlar state/kademe.jsonl'e eklenir ve alan adlari core.ai_provider_attempt
sutunlariyla birebir eslesecek sekilde secilmistir, boylece sonradan yazilacak
bir aktarici satiri doneme donmeden INSERT edebilir.

DURUM AYRIMI. "sonuc" alani uc hali ayirir ve bunlar birbirinin yerine
gecmez:
    BASARILI  cevabi bu kademe uretti
    HATA      kademe denendi ve dustu (gerekce = istisna sinifi)
    ATLANDI   kademe hic denenmedi, cunku hazir degildi (gerekce = durum)
"ATLANDI" ile "HATA" ayni sey degildir: birincisi makine kapali, ikincisi
makine acik ama cevap veremedi. Karistirmak, yanlis teshise goturur.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

VARSAYILAN_YOL = "/opt/lcarlie/jarvis-phase2/state/kademe.jsonl"

SONUC_BASARILI = "BASARILI"
SONUC_HATA = "HATA"
SONUC_ATLANDI = "ATLANDI"
SONUC_ZINCIR_TUKENDI = "ZINCIR_TUKENDI"


def _yol() -> Path:
    """Yol her cagride okunur: testler JARVIS_KADEME_LOG ile yonlendirir."""
    return Path(os.environ.get("JARVIS_KADEME_LOG", VARSAYILAN_YOL))


def kaydet(**alanlar) -> None:
    """Tek satir ekle. Hicbir kosulda istisna firlatmaz."""
    try:
        satir = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **alanlar}
        yol = _yol()
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(satir, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - telemetri cagirani asla dusuremez
        pass


def son_kayitlar(limit: int = 50) -> list[dict]:
    """Son N satiri yeniden eskiye dogru dondur. Dosya yoksa bos liste."""
    try:
        yol = _yol()
        if not yol.exists():
            return []
        with yol.open("r", encoding="utf-8") as dosya:
            satirlar = dosya.readlines()[-limit:]
    except OSError:
        return []
    kayitlar = []
    for satir in reversed(satirlar):
        satir = satir.strip()
        if not satir:
            continue
        try:
            kayitlar.append(json.loads(satir))
        except json.JSONDecodeError:
            continue
    return kayitlar


def ozet(kayitlar: list[dict]) -> dict:
    """Kademe dagilimi. Sayi uretir, yorum uretmez.

    "bilinmiyor" ayri bir kovadir: kaydi olmayan bir kademeyi "calismadi"
    diye raporlamak, olculmemis olani olculmus gibi gostermek olurdu.
    """
    dagilim: dict[str, dict[str, int]] = {}
    gecikmeler: dict[str, list[float]] = {}
    for kayit in kayitlar:
        uc = str(kayit.get("uc") or "bilinmiyor")
        sonuc = str(kayit.get("sonuc") or "bilinmiyor")
        dagilim.setdefault(uc, {})
        dagilim[uc][sonuc] = dagilim[uc].get(sonuc, 0) + 1
        gecikme = kayit.get("gecikme_ms")
        if sonuc == SONUC_BASARILI and isinstance(gecikme, (int, float)):
            gecikmeler.setdefault(uc, []).append(float(gecikme))
    ortalama = {uc: round(sum(v) / len(v), 1) for uc, v in gecikmeler.items() if v}
    return {"toplam": len(kayitlar), "dagilim": dagilim,
            "ortalama_gecikme_ms": ortalama}
