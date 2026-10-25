#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KINESIS + 2 GUNLUK ARASTIRMA ODAGI (29.09-01.10.2026).

Sahip talebi 29.09.2026: "2 gun boyunca tek konulari KINESIS olucak,
hersfeyini arastiracaklar."

🔴 KENDI ATIF INDEKSI: global known-hash havuzu kullanilmaz. Global havuz
verilince her bulgu "zaten biliniyor" diye elenir ve hat calismiyormus gibi
gorunur -- 29.09'da tam bu hataya dusuldu ve "0 bulgu" yanlis raporlandi.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")
from jarvis.adapter_factory import default_factory
from jarvis.research_controller import ResearchController
from jarvis.research_sources import WebSearchCrawlAdapter

CIKTI = Path("/opt/lcarlie/jarvis-phase2/state/kinesis_odak.jsonl")
ATIF  = Path("/opt/lcarlie/jarvis-phase2/state/kinesis_odak_hash.json")
BEKLE = int(os.environ.get("KINESIS_BEKLEME", "8"))

KONULAR = {
 "COMPETITOR_INT": (
   "Krauterhof isitici masaj kremi urun",
   "Zerobalm isitici masaj kremi urun",
   "VitNature isitici masaj kremi thermo",
   "Thermacare agri bandi Turkiye urun",
   "arnika masaj kremi marka urun sayfasi",
   "Performist isitici krem spor medikal",
 ),
 "MARKET_INT": (
   "sporcu masaj kremi Trendyol kategori",
   "masaj kremi fiyat karsilastirma cimri akakce",
   "magnezyum kremi urun fiyat Turkiye",
   "spor bakim urunleri pazar buyuklugu Turkiye",
 ),
 "CREATIVE_STRAT": (
   "sporcu bakim urunu reklam kampanya ornekleri",
   "spor kozmetik marka Instagram reklam",
 ),
 "REGULATORY": (
   "TITCK kozmetik masaj kremi iddia duyuru",
   "kozmetik urun saglik beyani yasak ifade yonetmelik",
 ),
 "B2B": (
   "spor salonu kozmetik urun tedarik Turkiye",
   "fizyoterapi merkezi masaj kremi tedarik",
 ),
 "SEO": (
   "sporcu bakim kremi arama sorgusu blog icerik",
   "magnezyum kremi ne ise yarar icerik sayfasi",
 ),
}

def _atif() -> set[str]:
    if ATIF.exists():
        try: return set(json.loads(ATIF.read_text(encoding="utf-8")))
        except Exception: pass  # noqa: BLE001 - tek kayit coktugunde tarama durmaz; hata rapora gecer
    return set()

def main() -> int:
    # 🔴 KENDINI DURDURAN BITIS: 2 gunluk odak. Bu tarihten sonra timer
    #    atesler ama betik hicbir sey yapmadan cikar -- unutulup surekli
    #    kosan bir arastirma hatti birakmamak icin.
    if datetime.now(timezone.utc) > datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc):
        print('KINESIS odagi SURESI DOLDU (01.10.2026) - calisilmadi'); return 0
    bilinen = _atif()
    f = default_factory()
    f.register(WebSearchCrawlAdapter(
        searxng_url=os.environ.get("RESEARCH_SEARXNG_URL", "http://127.0.0.1:8888")))
    c = ResearchController(f)
    simdi = datetime.now(timezone.utc).isoformat()
    yeni_toplam = 0
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("a", encoding="utf-8") as fh:
        for birim, konular in KONULAR.items():
            birim_yeni = 0
            for konu in konular:
                try:
                    r = c.run(konu)
                except Exception as exc:  # noqa: BLE001 - tek kayit coktugunde tarama durmaz; hata rapora gecer
                    print(f"  HATA {birim} · {konu}: {exc}", file=sys.stderr); continue
                for s in (r.get("sources") or []):
                    h = str(s.get("content_hash") or s.get("url") or "")
                    if not h or h in bilinen: continue
                    bilinen.add(h); birim_yeni += 1; yeni_toplam += 1
                    fh.write(json.dumps({
                        "zaman": simdi, "departman": birim, "konu": konu,
                        "baslik": s.get("title"), "url": s.get("url"),
                        "ozet": " ".join(str(x) for x in (s.get("evidence_snippets") or ()))[:700],
                    }, ensure_ascii=False) + "\n")
                time.sleep(BEKLE)
            print(f"  {birim:16s} {len(konular)} konu · {birim_yeni} yeni bulgu")
    ATIF.write_text(json.dumps(sorted(bilinen), ensure_ascii=False), encoding="utf-8")
    print(f"KINESIS odagi · {sum(len(v) for v in KONULAR.values())} konu · {yeni_toplam} yeni bulgu · toplam atif {len(bilinen)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
