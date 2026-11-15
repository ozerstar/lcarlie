#!/usr/bin/env python3
"""Finans merkezinin ürün maliyetini tek kaynağa aktarır (sahip, 15.11.2026).

Sahip: "Maliyet nasıl bilinmiyor, ürün maliyetleri Jarvis'in finans merkezinde
kayıtlı, her ürün için yazılı. Bu bağlantıları kuralım."

    product_profit.report()  ->  core.finans_maliyet_yaz(jsonb)
        -> core.finans_maliyet_anlik (değişince yeni anlık)
        -> core.urun_maliyet (kaynak FINANS, KDV HARİÇ, zamana göre sürüm)
        -> core.maliyet_bul() -> mart.* marj görünümleri
    okuma yüzü: SELECT * FROM core.urun_maliyet_guncel;

Hesap burada YAPILMAZ: finans sayfası neyi gösteriyorsa (product_profit.build)
o aktarılır; iki yerde iki hesap olmaz. Saatlik timer (lcarlie-finans-maliyet)
ve elle:  finans-maliyet-aktar.py [--kuru]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webconsole"))

ALANLAR = ("product", "produced", "production", "general", "special", "total_cost",
           "unit_cost", "unit_production", "first_made", "sold")


def yuk(rapor: dict) -> dict:
    """product_profit.report() çıktısından core.finans_maliyet_yaz girdisi.

    Birim maliyeti olmayan ürün DÜŞÜRÜLMEZ: unit_cost None gider, fonksiyon
    onu 'veri_yok' listesine koyar (VERI_YOK != 0).
    """
    urunler = []
    for x in rapor.get("products") or []:
        ad = (x.get("product") or "").strip()
        if not ad:
            continue
        urunler.append({k: x.get(k) for k in ALANLAR})
    if not urunler:
        raise ValueError("finans merkezi hiç ürün döndürmedi; aktarım yapılmadı")
    return {"dagitim": rapor.get("allocation") or "esit", "urunler": urunler}


def main(argv: list[str]) -> int:
    import product_profit
    from personal_action_store import _connect

    sahip = os.environ.get("JARVIS_FINANS_SAHIBI", "operator")
    govde = yuk(product_profit.report(sahip, "esit"))
    if "--kuru" in argv:
        print(json.dumps(govde, ensure_ascii=False, indent=1))
        return 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT core.finans_maliyet_yaz(%s::jsonb) AS s", (json.dumps(govde),))
        sonuc = cur.fetchone()["s"]
    print(json.dumps(sonuc, ensure_ascii=False))
    # eşleşmeyen ad = kimlik köprüsünde eksik satır; sessiz geçmesin
    return 2 if sonuc.get("eslesmeyen") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
