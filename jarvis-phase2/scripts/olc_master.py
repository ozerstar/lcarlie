#!/usr/bin/env python3
"""MASTER-tabanli fiziksel sinir + urun bazinda TUR3 vs V2 karsilastirma.

Turev (cekim-kesim) otomatik source-of-truth DEGILDIR: turev daha dusuk
cozunurlukluyse bu urunun fiziksel siniri degil DERIVATIVE_LIMIT'tir.
Sinir her zaman en yuksek cozunurluklu MASTER uzerinden hesaplanir.
"""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from PIL import Image                                  # noqa: E402

from jarvis import katalog_urun_varligi as uv          # noqa: E402
from scripts.olc_varlik import (analiz, tur3_planlari,  # noqa: E402
                                v2_planlari, yerlesimler)
from jarvis import katalog_icerik_v2 as ic2            # noqa: E402

CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library/index-v2.json")
KESIM = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-kesim")

URUN = ["HYDRAVIE", "KINESIS+", "FEMISIA", "BABYSOL"]
ESLESME = {"HYDRAVIE": "hydravie", "KINESIS+": "kinesis",
           "FEMISIA": "private-care", "BABYSOL": "daily-care"}

# TYPE A lifestyle karesinde otomatik urun tespiti guvenilir degil.
# Bu kutu GOZLE dogrulandi (spor salonu karesi, lime kutu + amber sise
# alt-solda). Tahmin uretilmedi.
INSAN_DOGRULAMALI_BBOX = {
    "/opt/lcarlie/pilot-assets/kinesis-4f9e28543c.png":
        {"x": 0.055, "y": 0.560, "en": 0.300, "boy": 0.360,
         "kaynak": "HUMAN_VERIFIED_BBOX -- gozle olculdu"},
}


def _master_adaylari(kay, urun):
    ad = urun.replace("+", "").upper()
    out = []
    for r in kay:
        p = r["product"].replace("+", "").upper()
        if ad in p or p in ad:
            out.append(r)
    return out


def main() -> int:
    kay = json.loads(CAL.read_text(encoding="utf-8"))

    print("=== 1 · MASTER TABANLI FIZIKSEL SINIR ===")
    print("%-9s %-26s %-9s %-11s %-11s %s"
          % ("urun", "master", "master px", "urun px", "@250 PPI", "@300 PPI"))
    print("-" * 96)
    sinir = {}
    for u in URUN:
        adaylar = _master_adaylari(kay, u)
        if not adaylar:
            print("%-9s MASTER BULUNAMADI" % u)
            continue
        en_iyi, en_px = None, -1
        for r in adaylar:
            a = analiz(r["source_path"])
            ov = INSAN_DOGRULAMALI_BBOX.get(r["source_path"])
            uk = ov or a.get("urun_kutusu") or {}
            if not uk:
                continue
            w, h = r["resolution"]
            upx, upy = float(uk["en"]) * w, float(uk["boy"]) * h
            if upx * upy > en_px:
                en_px = upx * upy
                en_iyi = (r, upx, upy, bool(ov))
        if not en_iyi:
            continue
        r, upx, upy, ov = en_iyi
        w, h = r["resolution"]
        sinir[u] = {
            "master_source": r["source_path"],
            "master_px": [w, h],
            "product_bbox_px": [round(upx), round(upy)],
            "bbox_kaynagi": "HUMAN_VERIFIED_BBOX" if ov else "olculdu",
            "max_w_250": round(upx * 25.4 / 250, 1),
            "max_h_250": round(upy * 25.4 / 250, 1),
            "max_w_300": round(upx * 25.4 / 300, 1),
            "max_h_300": round(upy * 25.4 / 300, 1),
        }
        print("%-9s %-26s %4dx%-4d %5dx%-5d %5.0fx%-5.0f %5.0fx%.0f mm%s"
              % (u, pathlib.Path(r["source_path"]).name[:26], w, h,
                 upx, upy, sinir[u]["max_w_250"], sinir[u]["max_h_250"],
                 sinir[u]["max_w_300"], sinir[u]["max_h_300"],
                 "  [GOZLE]" if ov else ""))

    print()
    print("=== 2 · TUREV SINIRI (bu urunun fiziksel siniri DEGILDIR) ===")
    tan = json.loads((KESIM / "tanima.json").read_text(encoding="utf-8"))
    tmap = {pathlib.Path(e["dosya"]).stem: e.get("urun") for e in tan}
    for u in URUN:
        en_iyi, best = None, -1
        for p in KESIM.glob("*.png"):
            if tmap.get(p.stem) != u:
                continue
            with Image.open(p) as im:
                w, h = im.size
            if w * h > best:
                best, en_iyi = w * h, (p, w, h)
        if not en_iyi:
            print("%-9s turev YOK" % u)
            continue
        p, w, h = en_iyi
        m = sinir.get(u)
        kayip = ""
        if m:
            o = m["product_bbox_px"][0]
            kayip = ("  DERIVATIVE_LIMIT: master urun %d px, turev %d px "
                     "(%%%.0f kayip)" % (o, w, 100 * (1 - w / o))) if w < o else ""
        print("%-9s %-24s %4dx%-4d  @250 PPI %5.0f mm%s"
              % (u, p.name[:24], w, h, w * 25.4 / 250, kayip))

    print()
    print("=== 3 · URUN BAZINDA TUR3 vs V2 (cover HARIC) ===")
    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    icerik = {a: ic2.yukle(a) for a in anahtar}
    planlar = {"TUR3": tur3_planlari(), "V2": v2_planlari(icerik)}

    def _olc(plan):
        y = yerlesimler(plan)
        an = {}
        for v in y:
            a = dict(analiz(v["source"]))
            ov = INSAN_DOGRULAMALI_BBOX.get(v["source"])
            if ov:
                a["urun_kutusu"] = {k: ov[k] for k in ("x", "y", "en", "boy")}
            an[v["source"]] = a
        return uv.olc(plan, y, an)

    print("%-9s %-5s %7s %7s %9s %7s %7s %7s %3s %-10s"
          % ("urun", "tur", "A_foto", "B_urun", "uzun_mm", "C_o/f",
             "D_kont", "F_sal", "G", "I_konum"))
    print("-" * 92)
    per = {}
    for u in URUN:
        slot = ESLESME[u]
        per[u] = {}
        for t in ("TUR3", "V2"):
            m = _olc(planlar[t][slot])
            kb = m.get("urun_kutusu_mm") or {}
            uzun = max(kb.get("en", 0), kb.get("boy", 0))
            per[u][t] = dict(m, urun_uzun_kenar_mm=round(uzun, 1))
            I = m["I_product_position"]
            print("%-9s %-5s %7.3f %7.3f %9.1f %7.3f %7s %7s %3s %-10s"
                  % (u, t, m["A_photo_area_page"], m["B_product_bbox_page"],
                     uzun, m["C_product_per_photo"], m["D_product_contrast"],
                     m["F_product_saliency"], m["G_background_competition"],
                     I["bolge"] if I else "-"))
        print()

    print("=== 4 · SORU: kuculdu mu, dominance mi kayboldu, ikisi mi? ===")
    for u in URUN:
        a, b = per[u]["TUR3"], per[u]["V2"]
        d_uzun = b["urun_uzun_kenar_mm"] - a["urun_uzun_kenar_mm"]
        d_bbox = b["B_product_bbox_page"] - a["B_product_bbox_page"]
        d_kont = ((b["D_product_contrast"] or 0) - (a["D_product_contrast"] or 0))
        d_sal = ((b["F_product_saliency"] or 0) - (a["F_product_saliency"] or 0))
        kucuk = d_bbox < -0.02
        dom = (d_kont < -0.02) or (d_sal < -0.02)
        if kucuk and dom:
            tani = "IKISI BIRDEN"
        elif kucuk:
            tani = "FIZIKSEL OLARAK KUCULDU (dominance korundu)"
        elif dom:
            tani = "DOMINANCE KAYBOLDU (boyut korundu)"
        else:
            tani = "GERILEME YOK"
        print("  %-9s uzun kenar %+6.1f mm · bbox %+.3f · kontrast %+.3f · "
              "saliency %+.3f  -> %s"
              % (u, d_uzun, d_bbox, d_kont, d_sal, tani))

    pathlib.Path("/opt/lcarlie/output/catalog-v2/master-sinir.json").write_text(
        json.dumps({"master_sinir": sinir, "urun_bazinda": per},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
