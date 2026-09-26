#!/usr/bin/env python3
"""V2.1 -- 10 challenger render + urun bazinda kanit.

Urun-ozel sanat yonetimi: her urun icin AYRI soru soruldu --
"WHAT ACTUALLY NEEDS TO BECOME LARGER?" Tek recete uygulanmadi.

TUR2 / TUR3 / V2 korunur; cikti /opt/lcarlie/output/catalog-v21/
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_konsept_v21 as k21         # noqa: E402
from jarvis import katalog_render as rd               # noqa: E402
from jarvis import katalog_sayfa_olcum as so          # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts      # noqa: E402
from jarvis import katalog_tipografi_qa as tqa        # noqa: E402
from jarvis import katalog_urun_gercegi as ug         # noqa: E402
from jarvis import katalog_urun_varligi as uv         # noqa: E402
from scripts.olc_varlik import analiz, yerlesimler    # noqa: E402
from scripts.olc_master import INSAN_DOGRULAMALI_BBOX  # noqa: E402

CEKIM = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")
PILOT = pathlib.Path("/opt/lcarlie/pilot-assets")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-v21")
CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library/index-v2.json")

A = {
    "hyd_cam": str(PILOT / "hydravie-a3794e3f48.png"),   # master, urun 1210 px
    "hyd_std": str(CEKIM / "ham--DSC04307.jpg"),
    "kin_gym": str(PILOT / "kinesis-4f9e28543c.png"),
    "kin_std": str(CEKIM / "ham--DSC04508.jpg"),
    "fem_sise": str(CEKIM / "ham--DSC04314.jpg"),
    "fem_kutu": str(CEKIM / "ham--DSC04316.jpg"),   # FEMISIA + VIREON (kapak icin)
    "fem_tek": str(CEKIM / "ham--DSC04309.jpg"),    # FEMISIA TEK BASINA
    "bab_std": str(CEKIM / "ham--DSC04498.jpg"),
    "bab_std2": str(CEKIM / "ham--DSC04503.jpg"),
}

# Urun-ozel sanat yonetimi karari -- tek recete YOK
NE_BUYUMELI = {
    "HYDRAVIE": "Olcek gerilemesi pratikte YOK (-2.7 mm). Buyumesi gereken "
                "MALZEME DUNYASI ve odak kontrasti: cam blok ve soguk isik.",
    "KINESIS+": "Gercek fiziksel olcek kaybi var (-21.6 mm). Buyumesi "
                "gereken URUNUN KENDISI.",
    "FEMISIA": "Urun kuculdu ama V2 daha yuksek kontrastli bir aset "
               "kullaniyor. Tur 3'e donulmeyecek; urun olcegi olculu "
               "artirilacak, V2'nin izolasyon kazanimi KORUNACAK.",
    "BABYSOL": "Fiziksel kuculme var, izolasyon korunmus. Olculu olcek "
               "artisi + fildisi zeminle kontrast korunmasi.",
}

CHALLENGER = [
    ("V21-C1", "KAPAK", "NESNE VE GÖLGE", "cover"),
    ("V21-C2", "KAPAK", "ÜÇ NESNE", "cover"),
    ("V21-H1", "HYDRAVIE", "SU VE CAM", "hydravie"),
    ("V21-H2", "HYDRAVIE", "NESNE VE ŞEMA", "hydravie"),
    ("V21-K1", "KINESIS+", "SALON", "kinesis"),
    ("V21-K2", "KINESIS+", "NESNE", "kinesis"),
    ("V21-F1", "FEMISIA", "AMBER", "private-care"),
    ("V21-F2", "FEMISIA", "MAHREMİYET", "private-care"),
    ("V21-B1", "BABYSOL", "IŞIK", "daily-care"),
    ("V21-B2", "BABYSOL", "FİZİKSEL FİLTRE", "daily-care"),
]


def _an(yol):
    a = dict(analiz(yol))
    ov = INSAN_DOGRULAMALI_BBOX.get(yol)
    if ov:
        a["urun_kutusu"] = {k: ov[k] for k in ("x", "y", "en", "boy")}
        a["_bbox_kaynagi"] = "HUMAN_VERIFIED_BBOX"
    return a


def planlar(g):
    H, K, F, B = g["hydravie"], g["kinesis+"], g["femisia"], g["babysol"]
    return {
        "V21-C1": lambda: k21.vc1_nesne_ve_golge(H, A["hyd_cam"],
                                                 _an(A["hyd_cam"])),
        "V21-C2": lambda: k21.vc2_uc_nesne(H, [
            (A["bab_std"], _an(A["bab_std"]), "BEBEK · GÜNEŞ"),
            (A["fem_kutu"], _an(A["fem_kutu"]), "HASSAS BÖLGE"),
            (A["kin_std"], _an(A["kin_std"]), "SPOR VE MASAJ")]),
        "V21-H1": lambda: k21.vh1_su_ve_cam(H, A["hyd_cam"], _an(A["hyd_cam"])),
        "V21-H2": lambda: k21.vh2_nesne_ve_sema(H, A["hyd_std"],
                                                _an(A["hyd_std"])),
        "V21-K1": lambda: k21.vk1_salon(K, A["kin_gym"], _an(A["kin_gym"])),
        "V21-K2": lambda: k21.vk2_nesne(K, A["kin_std"], _an(A["kin_std"])),
        "V21-F1": lambda: k21.vf1_amber(F, A["fem_sise"], _an(A["fem_sise"])),
        "V21-F2": lambda: k21.vf2_mahremiyet(F, A["fem_tek"],
                                             _an(A["fem_tek"])),
        "V21-B1": lambda: k21.vb1_isik(B, A["bab_std"], _an(A["bab_std"])),
        "V21-B2": lambda: k21.vb2_fiziksel_filtre(B, A["bab_std2"],
                                                  _an(A["bab_std2"])),
    }


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    (CIKTI / "challengers").mkdir(exist_ok=True)
    indeks = {r["source_path"]: r
              for r in json.loads(CAL.read_text(encoding="utf-8"))}

    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    g = {a: ug.yukle(a) for a in anahtar}
    icerik = {}
    for a in anahtar:
        d = dict(g[a]["alanlar"])
        icerik[a] = {
            "one_cikan": _one_cikan(a),
            **{k: ug.deger(g[a], k) for k in
               ("tanim", "kullanim", "uyari", "inci", "net_miktar",
                "kategori")},
            "alanlar": d,
        }

    print("=== URUN-OZEL SANAT YONETIMI KARARI ===")
    for u, s in NE_BUYUMELI.items():
        print("  %-9s %s" % (u, s))
    print()

    P = planlar(icerik)
    kayit = []
    print("=== 10 CHALLENGER ===")
    for kid, urun, ad, slot in CHALLENGER:
        try:
            plan = P[kid]()
        except Exception as ex:          # noqa: BLE001
            print("  %-8s URETILEMEDI: %s" % (kid, str(ex)[:70]))
            continue
        pdf = CIKTI / "challengers" / ("%s.pdf" % kid)
        gk = rd.goruntu_katmani(plan, {"zemin": {}})
        rd.pdf_uret(plan, gk, pdf)
        qa = tqa.kapi(pdf, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
        kont = rd.metin_kontrast_denetimi(plan, gk)
        olc = so.sayfa_olcumleri(pdf)[0]
        y = yerlesimler(plan)
        an = {v["source"]: _an(v["source"]) for v in y}
        m = uv.olc(plan, y, an)
        kayit.append({
            "id": kid, "urun": urun, "ad": ad, "slot": slot,
            "konsept": plan.konsept, "meta": plan.olcumler,
            "qa": {"gecti": qa["gecti"], "durduran": qa["durduran_ihlal"]},
            "kontrast_ihlali": len(kont),
            "varlik": m,
            "yerlesim": [{**v, "asset_id": indeks.get(v["source"], {}).get(
                "asset_id", "MANIFESTTE_YOK"),
                "human_subject": indeks.get(v["source"], {}).get(
                    "human_subject", "?"),
                "rights_status": indeks.get(v["source"], {}).get(
                    "rights_status", "?"),
                "AI_status": "NO_AI -- gercek cekim/kayit, uretken model yok"}
                for v in y],
            "olcum": {"metin": olc.metin_alan_orani, "punto": olc.en_buyuk_punto,
                      "oge": olc.ogeler},
        })
        print("  %-8s %-9s %-16s QA=%-5s kont=%d ppi=%5.0f %-22s "
              "urun %5.1f x %5.1f mm (uzun %5.1f) bbox %%%.1f"
              % (kid, urun, ad[:16], qa["gecti"], len(kont),
                 y[0]["effective_ppi"] if y else 0,
                 plan.olcumler.get("baski_durumu", "?"),
                 m.get("bbox_width_mm") or 0, m.get("bbox_height_mm") or 0,
                 m.get("bbox_long_edge_mm") or 0,
                 (m.get("bbox_area_over_page") or 0) * 100))

    (CIKTI / "v21-challenger-kayit.json").write_text(
        json.dumps({"ne_buyumeli": NE_BUYUMELI, "challengers": kayit},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    # kontakt sayfasi
    import pymupdf
    from PIL import Image, ImageDraw
    S, C, B2, ET = 330, 5, 9, 52
    R = (len(kayit) + C - 1) // C
    im = Image.new("RGB", (C * S + (C + 1) * B2,
                           R * (S + ET) + (R + 1) * B2 + 26), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((B2, 8), "L CARLIE V2.1 -- 10 CHALLENGER -- gercek urun metni, "
                    "210x210 mm", fill=(0, 0, 0))
    for i, k in enumerate(kayit):
        rr, cc = divmod(i, C)
        x = B2 + cc * (S + B2)
        yy = 26 + B2 + rr * (S + ET + B2)
        doc = pymupdf.open(str(CIKTI / "challengers" / ("%s.pdf" % k["id"])))
        px = doc[0].get_pixmap(dpi=64)
        im.paste(Image.open(io.BytesIO(px.tobytes("png"))).convert("RGB")
                 .resize((S, S)), (x, yy))
        doc.close()
        d.rectangle([x, yy, x + S, yy + S], outline=(188, 186, 180))
        v = k["varlik"]
        d.text((x + 2, yy + S + 5), "%s  %s" % (k["id"], k["ad"]), fill=(0, 0, 0))
        d.text((x + 2, yy + S + 17), (k["meta"].get("fikir") or "")[:58],
               fill=(110, 108, 102))
        d.text((x + 2, yy + S + 29),
               "urun %.0fx%.0f mm · bbox %%%.1f · %s"
               % (v.get("bbox_width_mm") or 0, v.get("bbox_height_mm") or 0,
                  (v.get("bbox_area_over_page") or 0) * 100,
                  k["meta"].get("baski_durumu", "?")), fill=(140, 138, 132))
        d.text((x + 2, yy + S + 41), (k["meta"].get("takas") or "")[:58],
               fill=(160, 120, 110))
    im.save(str(CIKTI / "V21-10-CHALLENGER.png"))
    print("\nkontakt: %s" % (CIKTI / "V21-10-CHALLENGER.png"))
    return 0


def _one_cikan(a: str):
    from jarvis import katalog_icerik_v2 as ic2
    return ic2.ONE_CIKAN.get(a, [])


if __name__ == "__main__":
    raise SystemExit(main())
