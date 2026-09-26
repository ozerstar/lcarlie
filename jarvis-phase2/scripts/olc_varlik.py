#!/usr/bin/env python3
"""TUR3 ve V2 finallerini ON metrikle olcer. Tek skor uretmez."""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_foto_analiz as fa          # noqa: E402
from jarvis import katalog_icerik_v2 as ic2           # noqa: E402
from jarvis import katalog_konsept as kk              # noqa: E402
from jarvis import katalog_konsept3 as k3             # noqa: E402
from jarvis import katalog_konsept_v2 as kv2          # noqa: E402
from jarvis import katalog_urun_varligi as uv         # noqa: E402
from scripts.katalog_v2 import ASETLER                # noqa: E402

CEKIM = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")
PILOT = pathlib.Path("/opt/lcarlie/pilot-assets")

T3_ASET = {
    "cover": str(CEKIM / "ham--DSC04498.jpg"),
    "hydravie": str(CEKIM / "ham--DSC04301.jpg"),
    "kinesis": str(PILOT / "kinesis-4f9e28543c.png"),
    "private-care": str(CEKIM / "ham--DSC04316.jpg"),
    "daily-care": str(CEKIM / "ham--DSC04498.jpg"),
}

_ANALIZ: dict[str, dict] = {}


def analiz(yol: str) -> dict:
    if yol not in _ANALIZ:
        _ANALIZ[yol] = fa.analiz(pathlib.Path(yol)).sozluk()
    return _ANALIZ[yol]


def yerlesimler(plan) -> list[dict]:
    out = []
    for oge in plan.ogeler:
        if oge.tur != "foto":
            continue
        v = oge.veri
        k = v["kadraj"]
        pw, ph = k["piksel"]
        out.append({
            "source": v["kaynak"],
            "crop": {"x": k["x"], "y": k["y"], "en": k["en"], "boy": k["boy"]},
            "placement_xy_mm": [v["x"], v["y"]],
            "placement_size_mm": [v["en"], v["boy"]],
            "effective_ppi": round(min(pw * 25.4 / v["en"],
                                       ph * 25.4 / v["boy"]), 1),
        })
    return out


def _icerik_t3(slug, foto):
    D = {
        "hydravie": ("HYDRAVIE", "Yoğun Nemlendirici Yüz Kremi", "50 ml"),
        "kinesis": ("KINESIS +", "SPORCU BAKIM KREMİ", "150 ml"),
        "femisia": ("FEMISIA", "for WOMEN · İNTİM BAKIM KREMİ", "50 ml"),
        "babysol": ("BABYSOL", "BEBEK GÜNEŞ BAKIM KREMİ", "150 ml"),
    }[slug]
    return kk.Icerik(slug=slug, ad=D[0], alt_ad=D[1], ust_etiket="",
                     manset="", govde="x", hacim=D[2], inci="", uyari="u",
                     mikro="m", kaynak_foto=foto, analiz=analiz(foto))


def tur3_planlari():
    p = {}
    ic = _icerik_t3("babysol", T3_ASET["cover"])
    p["cover"] = k3.kapak_uc_urun(ic, {}, [
        (str(CEKIM / "ham--DSC04498.jpg"), "A", 0.39),
        (str(CEKIM / "ham--DSC04316.jpg"), "B", 0.38),
        (str(CEKIM / "ham--DSC04520.jpg"), "C", 0.33)])
    p["hydravie"] = k3.hydravie_numune_foyu(
        _icerik_t3("hydravie", T3_ASET["hydravie"]), {},
        [("a", "b"), ("c", "d"), ("e", "f"), ("g", "h"), ("i", "j")])
    p["kinesis"] = k3.kinesis_salon(
        _icerik_t3("kinesis", T3_ASET["kinesis"]), {})
    p["private-care"] = k3.femisia_cift(
        _icerik_t3("femisia", T3_ASET["private-care"]), {},
        {"ad": "VIREON", "alt_ad": "x", "govde": "y"})
    p["daily-care"] = k3.babysol_alt_bant(
        _icerik_t3("babysol", T3_ASET["daily-care"]), {})
    return p


def v2_planlari(icerik):
    H, K = icerik["hydravie"], icerik["kinesis+"]
    F, B = icerik["femisia"], icerik["babysol"]
    A = ASETLER
    return {
        "cover": kv2.c3_otuzalti(H, A["kinesis_st"]),
        "hydravie": kv2.h3_bilesen_merdiveni(H, A["hydravie_st"]),
        "kinesis": kv2.k2_caba(K, A["kinesis_gym"]),
        "private-care": kv2.f2_tam_inci(F, A["femisia_st2"]),
        "daily-care": kv2.b2_zorunlu_metin(B, A["babysol_st2"]),
    }


def main() -> int:
    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    icerik = {a: ic2.yukle(a) for a in anahtar}

    turlar = {"TUR3": tur3_planlari(), "V2": v2_planlari(icerik)}
    ozet = {}
    print("%-5s %-13s %7s %7s %7s %7s %7s %7s %3s %-9s %s"
          % ("tur", "sayfa", "A_foto", "B_urun", "C_o/f", "D_kont",
             "E_izol", "F_sal", "G", "I_konum", "J_kenar"))
    print("-" * 104)
    for t, planlar in turlar.items():
        liste = []
        for slot, plan in planlar.items():
            y = yerlesimler(plan)
            an = {v["source"]: analiz(v["source"]) for v in y}
            m = uv.olc(plan, y, an)
            liste.append(m)
            I = m["I_product_position"]
            J = m["J_edge_interaction"]
            print("%-5s %-13s %7.3f %7.3f %7.3f %7s %7s %7s %3s %-9s %s"
                  % (t, slot, m["A_photo_area_page"], m["B_product_bbox_page"],
                     m["C_product_per_photo"],
                     m["D_product_contrast"], m["E_product_isolation"],
                     m["F_product_saliency"], m["G_background_competition"],
                     I["bolge"] if I else "-",
                     ",".join(J["kenarlar"]) if J else "-"))
        ozet[t] = liste
        print()

    k = uv.karsilastir(list(ozet.items()))
    print("=== TUR KARSILASTIRMASI (tek skor URETILMEDI) ===")
    print("%-5s %12s %12s %12s %12s %12s"
          % ("tur", "A_ort", "B_ort", "B_min", "B_max", "C_ort"))
    for t, v in k.items():
        print("%-5s %12.4f %12.4f %12.4f %12.4f %12.4f"
              % (t, v["A_ortalama"], v["B_ortalama"], v["B_en_dusuk"],
                 v["B_en_yuksek"], v["C_ortalama"]))
    pathlib.Path("/opt/lcarlie/output/catalog-v2/varlik-olcumu.json").write_text(
        json.dumps({"turlar": {t: v for t, v in ozet.items()},
                    "karsilastirma": k}, ensure_ascii=False, indent=1,
                   default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
