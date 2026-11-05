"""Sahibin görsel tercihleri → yeni görsel istemine "kaçınılacaklar" (05.11.2026).

Sahip Görsel onayları ekranında görselleri sola kaydırıp nedenini yazar
(core.gorsel_onay). Bu modül en sık nedenleri ve son yorumları okur ve
ChatGPT görsel istemine eklenecek kısa bir blok üretir. Okuma başarısızsa
boş döner: tercih okunamadı diye görsel üretimi durmaz.
"""
from __future__ import annotations

import json

from .db_transport import run as db_run

EN_COK_BLOK = 1200
SORGU = (
    "SELECT row_to_json(x) FROM ("
    " SELECT 'neden' AS tur, n AS metin, count(*) AS adet FROM core.gorsel_onay, unnest(nedenler) n"
    " WHERE karar = 'BEGENMEDI' GROUP BY n ORDER BY count(*) DESC LIMIT 6) x"
    " UNION ALL "
    "SELECT row_to_json(y) FROM ("
    " SELECT 'yorum' AS tur, yorum AS metin, 1 AS adet FROM core.gorsel_onay"
    " WHERE karar = 'BEGENMEDI' AND length(btrim(yorum)) >= 3 ORDER BY karar_zamani DESC LIMIT 6) y")


def _oku() -> list[dict]:
    try:
        r = db_run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
                    "-U", "n8n", "-d", "n8n", "-c", SORGU],
                   capture_output=True, text=True, timeout=20, check=False)
    except Exception:  # noqa: BLE001 - tercih okunamazsa üretim sürer
        return []
    if r.returncode:
        return []
    satirlar = []
    for satir in (r.stdout or "").splitlines():
        try:
            satirlar.append(json.loads(satir))
        except ValueError:
            continue
    return satirlar


def kacinilacaklar_metni(satirlar: list[dict] | None = None) -> str:
    """İsteme eklenecek blok; veri yoksa boş."""
    satirlar = _oku() if satirlar is None else satirlar
    nedenler = [s for s in satirlar if s.get("tur") == "neden" and s.get("metin")]
    yorumlar = [s for s in satirlar if s.get("tur") == "yorum" and s.get("metin")]
    if not nedenler and not yorumlar:
        return ""
    parcalar = ["OWNER'S IMAGE FEEDBACK — the owner rejected earlier images for these reasons; "
                "do NOT repeat them (owner wrote in Turkish):"]
    parcalar += ["- %s (%d kez)" % (s["metin"], int(s.get("adet") or 1)) for s in nedenler]
    if yorumlar:
        parcalar.append("Owner's recent comments on rejected images:")
        parcalar += ["- \"%s\"" % " ".join(str(s["metin"]).split())[:220] for s in yorumlar]
    blok = "\n".join(parcalar)
    return blok if len(blok) <= EN_COK_BLOK else blok[:EN_COK_BLOK - 1].rsplit("\n", 1)[0]
