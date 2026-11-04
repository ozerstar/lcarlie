#!/usr/bin/env python3
"""JARVIS_AGENT_CMD: Radar'ın beklediği rakip tarama ajanı (Jarvis venv'i ile çalışır).

  /opt/lcarlie/jarvis-phase2/venv/bin/python /opt/lcarlie/radar/deploy/jarvis_rakip_ajani.py \
      --mode tarama|teyit --task TASK.md --recheck scans/teyit.json --watch scans/izlenen.json --out <dosya>

Arama: Jarvis'in Gemini Google Search bağlantısı (program_baglantilari.grounded_arama).
Çıkarım: Jarvis'in ücretsiz model yönlendiricisi (yerel_model.yonlendirici; 'radar-cikar' işi
IS_URETICI_GUCLU_ISLER'e eklenirse önce OpenRouter'ın ücretsiz büyük modeline gider).
Sayfaları sunucu indirir; alıntı doğrulaması radar/ajan.py'de.
"""
import argparse
import json
import os
import sys
from pathlib import Path

RADAR = Path(__file__).resolve().parent.parent
JARVIS = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
sys.path[:0] = [str(RADAR), str(JARVIS), str(JARVIS / "scripts")]

from radar import ajan  # noqa: E402
from radar.kaynaklar import NazikGetir  # noqa: E402


def _oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def bilinen_markalar():
    """Liste sayfalarında marka doğrulaması için eczane + Gratis site haritası marka slug'ları (kaynak-tara yazar)."""
    from radar.ajan import slug
    from radar.kaynaklar import _gratis_marka_slug
    out = set()
    for ad, cevir in (("eczane", lambda u: u.rstrip("/").rsplit("/", 1)[-1]), ("gratis", _gratis_marka_slug)):
        for u in _oku(RADAR / "data" / f"{ad}_markalari.json") or {}:
            out.add(slug(cevir(u)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["tarama", "teyit"], required=True)
    ap.add_argument("--task")      # sözleşme gereği alınır; görev tanımı ajan.py'de kodlu
    ap.add_argument("--recheck", default="scans/teyit.json")
    ap.add_argument("--watch", default="scans/izlenen.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from jarvis import providers
    import program_baglantilari as pb
    import yerel_model

    sonuc = ajan.calistir(
        a.mode, ara=pb.grounded_arama(providers), getir=NazikGetir(ajan.akilli_getir), uret=yerel_model.yonlendirici(providers),
        teyit=_oku(a.recheck), izlenen=_oku(a.watch),
        sorgu_adedi=int(os.environ.get("RADAR_SORGU_ADEDI", "4")),
        sayfa_siniri=int(os.environ.get("RADAR_SAYFA_SINIRI", "12")), markalar=bilinen_markalar())
    gecici = a.out + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=1)
    os.replace(gecici, a.out)
    print(json.dumps({"marka": len(sonuc["brands"]), **sonuc["ajan"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
