"""İŞ → KADEME kaydını okur. Kod atamayı gömülü tutmaz, buradan alır.

🔴 VERİTABANI DÜŞERSE SİSTEM SUSMAZ. Okuma başarısız olursa gömülü
varsayılana düşer ve bunu `kaynak` alanında söyler. Yanlış kademede
konuşmak kötüdür; hiç konuşamamak daha kötüdür.

🔴 ÖNBELLEK KISA TUTULUR. Atama değiştiğinde bir sonraki çağrıda değil,
en geç `ONBELLEK_SN` içinde yürürlüğe girsin isteniyor; ama her model
çağrısında veritabanına gitmek de gecikme ekler. 60 saniye ikisinin
ortası.
"""
from __future__ import annotations

import json
from jarvis.db_transport import run as db_run
import time

ONBELLEK_SN = 60.0

# 🔴 Gömülü varsayılan, tablonun KOPYASI değil EMNİYETİDİR. Tablo
# okunamadığında hangi işin nereye düşeceğini burada görmek gerekir;
# "bilinmiyorsa hızlı" demek, müşteriye giden metni sessizce küçük
# modele düşürmek olurdu -- o yüzden riskli işler burada da muhakemede.
GOMULU: dict[str, str] = {
    "satis_dialog": "muhakeme",
    "satis_ogrenme": "muhakeme",
    "guncel_olaylar": "muhakeme",
    "kreatif_brief": "muhakeme",
    "tasarim_gorevi": "muhakeme",
    "query_planner": "hizli",
    "sohbet": "hizli",
}
VARSAYILAN = "hizli"

_onbellek: dict[str, str] = {}
_onbellek_zaman = 0.0
_onbellek_kaynak = "henuz-okunmadi"


def _tablodan_oku() -> dict[str, str] | None:
    try:
        r = db_run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
             "-U", "n8n", "-d", "n8n", "-c",
             "SELECT row_to_json(x) FROM (SELECT is_anahtari, kademe"
             " FROM mart.model_kademe_guncel) x"],
            capture_output=True, text=True, timeout=8, check=False)
    except Exception:  # noqa: BLE001 - okuma hatasi cagriyi durdurmaz
        return None
    if r.returncode:
        return None
    out: dict[str, str] = {}
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if not satir:
            continue
        try:
            k = json.loads(satir)
        except json.JSONDecodeError:
            continue
        anahtar, kademe = k.get("is_anahtari"), k.get("kademe")
        if anahtar and kademe:
            out[str(anahtar)] = str(kademe)
    return out or None


def _tazele() -> None:
    global _onbellek, _onbellek_zaman, _onbellek_kaynak
    if time.time() - _onbellek_zaman < ONBELLEK_SN and _onbellek:
        return
    tablo = _tablodan_oku()
    if tablo:
        _onbellek, _onbellek_kaynak = tablo, "tablo"
    else:
        _onbellek, _onbellek_kaynak = dict(GOMULU), "gomulu (tablo okunamadi)"
    _onbellek_zaman = time.time()


def kademe(is_anahtari: str) -> str:
    """İşin kademesi. Tanımsız iş VARSAYILAN'a düşer."""
    _tazele()
    return _onbellek.get((is_anahtari or "").strip(), VARSAYILAN)


def durum() -> dict:
    """Panel ve motor sorumlusu için: atama nereden geldi, kaç kayıt."""
    _tazele()
    return {
        "kaynak": _onbellek_kaynak,
        "atama": dict(_onbellek),
        "muhakeme_isleri": sorted(k for k, v in _onbellek.items() if v == "muhakeme"),
        "hizli_isleri": sorted(k for k, v in _onbellek.items() if v == "hizli"),
    }
