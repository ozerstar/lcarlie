#!/usr/bin/env python3
"""Urun gorsel envanterini siniflandirir ve rapor uretir. SALT OKUNUR.

Hicbir gorseli degistirmez, tasimaz, silmez. Yalniz okur ve ozetler.

Kullanim:
    python -m scripts.katalog_varlik_envanter            # yerlesimsiz
    python -m scripts.katalog_varlik_envanter --en 60 --boy 150
    python -m scripts.katalog_varlik_envanter --json rapor.json

NEDEN GEREKLI:
    TYPE D listesi bir bütce kalemidir -- yeniden cekim gerektiren
    urunleri sahibin karari icin gorunur kilar. Sessizce kucultup
    kullanmak yerine acikca listelenir.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_varlik as varlik  # noqa: E402

UZANTI = (".png", ".jpg", ".jpeg", ".webp")
VARSAYILAN_KOK = "/opt/lcarlie/jarvis-phase2/varliklar/urun"


def tara(kok: pathlib.Path, en_mm: float | None, boy_mm: float | None,
         azami: int | None = None) -> dict:
    sonuc: dict = {"kok": str(kok), "hedef_mm": [en_mm, boy_mm], "klasorler": {}}
    for d in sorted(p for p in kok.iterdir() if p.is_dir()):
        dosyalar = sorted(p for p in d.rglob("*") if p.suffix.lower() in UZANTI)
        if azami:
            dosyalar = dosyalar[:azami]
        if not dosyalar:
            continue
        sayim: collections.Counter = collections.Counter()
        d_listesi: list[dict] = []
        guvenli: list[float] = []
        for p in dosyalar:
            try:
                s = varlik.siniflandir(p, en_mm, boy_mm)
            except Exception as hata:            # noqa: BLE001 -- sebebi kaydediyoruz
                sayim["OKUNAMADI"] += 1
                d_listesi.append({"dosya": p.name, "hata": str(hata)[:80]})
                continue
            sayim[s.asset_type] += 1
            if s.max_safe_placement_mm[0]:
                guvenli.append(min(s.max_safe_placement_mm))
            if s.asset_type == "D":
                d_listesi.append({
                    "dosya": p.name,
                    "px": [s.source_quality.get("genislik_px"),
                           s.source_quality.get("yukseklik_px")],
                    "azami_guvenli_mm": list(s.max_safe_placement_mm),
                    "gerekce": s.evidence[0] if s.evidence else "",
                })
        # En/boy oranindan BAGIMSIZ gercek: buyutmeden basilabilecek olcu.
        # Hedef kutunun sekli D sonucunu etkiler, bu sayi etkilemez.
        guvenli_kisa = sorted(guvenli) if guvenli else []
        sonuc["klasorler"][d.name] = {
            "adet": len(dosyalar),
            "sinif_dagilimi": dict(sorted(sayim.items())),
            "azami_guvenli_kisa_kenar_mm": {
                "min": round(guvenli_kisa[0], 1) if guvenli_kisa else None,
                "medyan": round(guvenli_kisa[len(guvenli_kisa)//2], 1) if guvenli_kisa else None,
                "maks": round(guvenli_kisa[-1], 1) if guvenli_kisa else None,
            },
            "yeniden_cekim_adaylari": d_listesi,
        }
    return sonuc


def yazdir(rapor: dict) -> None:
    en, boy = rapor["hedef_mm"]
    hedef = "yerlesim hedefi yok" if en is None else "hedef %.0f x %.0f mm" % (en, boy)
    print("URUN VARLIK ENVANTERI -- %s" % hedef)
    print("kok: %s" % rapor["kok"])
    print()
    print("%-14s %5s  %s" % ("KLASOR", "ADET", "SINIF DAGILIMI"))
    print("-" * 64)
    toplam_d = 0
    for ad, k in rapor["klasorler"].items():
        g = k["azami_guvenli_kisa_kenar_mm"]
        print("%-14s %5d  %-28s guvenli kisa kenar min/medyan/maks: %s/%s/%s mm"
              % (ad, k["adet"], k["sinif_dagilimi"], g["min"], g["medyan"], g["maks"]))
        toplam_d += k["sinif_dagilimi"].get("D", 0)
    print("-" * 64)
    print("TYPE D toplam: %d  (yeniden cekim / yerlesim kucultme karari sahibe aittir)"
          % toplam_d)

    for ad, k in rapor["klasorler"].items():
        adaylar = k["yeniden_cekim_adaylari"]
        if not adaylar:
            continue
        print()
        print("  %s -- ilk 5 TYPE D:" % ad)
        for a in adaylar[:5]:
            if "hata" in a:
                print("    %-34s OKUNAMADI: %s" % (a["dosya"][:34], a["hata"]))
            else:
                print("    %-34s %sx%s px -> azami %.0fx%.0f mm"
                      % (a["dosya"][:34], a["px"][0], a["px"][1],
                         a["azami_guvenli_mm"][0], a["azami_guvenli_mm"][1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kok", default=VARSAYILAN_KOK)
    ap.add_argument("--en", type=float, default=None, help="hedef yerlesim genisligi (mm)")
    ap.add_argument("--boy", type=float, default=None, help="hedef yerlesim yuksekligi (mm)")
    ap.add_argument("--azami", type=int, default=None, help="klasor basina en fazla dosya")
    ap.add_argument("--json", default=None, help="raporu bu dosyaya yaz")
    a = ap.parse_args()

    kok = pathlib.Path(a.kok)
    if not kok.is_dir():
        print("kok bulunamadi: %s" % kok, file=sys.stderr)
        return 2
    if (a.en is None) != (a.boy is None):
        print("--en ve --boy birlikte verilmeli", file=sys.stderr)
        return 2

    rapor = tara(kok, a.en, a.boy, a.azami)
    yazdir(rapor)
    if a.json:
        pathlib.Path(a.json).write_text(
            json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\njson yazildi: %s" % a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
