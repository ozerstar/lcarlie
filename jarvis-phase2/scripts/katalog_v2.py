#!/usr/bin/env python3
"""CREATIVE DEPARTMENT V2 -- pipeline, izlenebilirlik, uretim.

Tur 3 KORUNUR (BASELINE_CHALLENGER); uzerine yazilmaz.
Cikti: /opt/lcarlie/output/catalog-v2/
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_aset_v2 as av2          # noqa: E402
from jarvis import katalog_dna as dna              # noqa: E402
from jarvis import katalog_icerik_v2 as ic2        # noqa: E402
from jarvis import katalog_konsept_v2 as kv2       # noqa: E402
from jarvis import katalog_render as rd            # noqa: E402
from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402

CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-v2")
TUR3 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")
TUR2 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v2")

CEKIM = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")
PILOT = pathlib.Path("/opt/lcarlie/pilot-assets")

# --- C: uc kademeli baski kalitesi --------------------------------------
PROTOTIP = 150.0
BASKI = 250.0
YUKSEK = 300.0


def baski_kademesi(ppi: float) -> dict:
    """PPI kademesi + PRINT_QUALITY_EXCEPTION kaydi."""
    if ppi >= YUKSEK - 1:
        return {"tier": "PREFERRED_HIGH_QUALITY", "exception": None,
                "final_print_ready": True}
    if ppi >= BASKI:
        return {"tier": "PRINT_QUALITY_TARGET", "exception": None,
                "final_print_ready": True}
    if ppi >= PROTOTIP:
        return {"tier": "DESIGN_PROTOTYPE_FLOOR",
                "exception": "PRINT_QUALITY_EXCEPTION: %.0f PPI, baski "
                             "hedefi %.0f PPI'nin altinda" % (ppi, BASKI),
                "final_print_ready": False}
    return {"tier": "BELOW_PROTOTYPE_FLOOR",
            "exception": "REDDEDILDI: %.0f PPI, prototip tabani %.0f PPI'nin "
                         "altinda" % (ppi, PROTOTIP),
            "final_print_ready": False}


def yerlesimleri_cikar(plan, konsept_id: str, indeks: dict) -> list[dict]:
    """B: her raster yerlesimi tek tek izlenebilir olsun."""
    out = []
    for oge in plan.ogeler:
        if oge.tur != "foto":
            continue
        v = oge.veri
        k = v["kadraj"]
        pw, ph = k["piksel"]
        ppi = min(pw * 25.4 / v["en"], ph * 25.4 / v["boy"])
        r = indeks.get(v["kaynak"])
        kad = baski_kademesi(ppi)
        out.append({
            "concept_id": konsept_id,
            "asset_id": r["asset_id"] if r else "MANIFESTTE_YOK",
            "source": v["kaynak"],
            "source_root": r["source_root"] if r else "?",
            "photo_role": r["photo_role"] if r else "?",
            "placement_size_mm": [round(v["en"], 1), round(v["boy"], 1)],
            "crop": {"x": k["x"], "y": k["y"], "en": k["en"], "boy": k["boy"],
                     "piksel": [pw, ph]},
            "effective_ppi": round(ppi, 1),
            "print_tier": kad["tier"],
            "print_exception": kad["exception"],
            "final_print_ready": kad["final_print_ready"],
            "upscaled": False,
            "rights_status": r["rights_status"] if r else "MANIFESTTE_YOK",
            "human_subject": r["human_subject"] if r else "MANIFESTTE_YOK",
        })
    return out


# --- 25 konsept tanimi ---------------------------------------------------

def konsept_tablosu(icerik: dict, aset: dict) -> list[dict]:
    H = icerik["hydravie"]
    K = icerik["kinesis+"]
    F = icerik["femisia"]
    V = icerik["vireon"]
    B = icerik["babysol"]
    A = aset
    return [
        # KAPAK
        ("V-C1", "KAPAK", "DOKUZ AİLE", lambda: kv2.c1_dokuz_aile(H)),
        ("V-C2", "KAPAK", "TEK MALZEME", lambda: kv2.c2_tek_malzeme(H, A["makro"])),
        ("V-C3", "KAPAK", "36", lambda: kv2.c3_otuzalti(H, A["kinesis_st"])),
        ("V-C4", "KAPAK", "KÜNYE", lambda: kv2.c4_kunye(H, A["hydravie_st"])),
        ("V-C5", "KAPAK", "ÜÇ IŞIK",
         lambda: kv2.c5_uc_isik(H, [A["babysol_st"], A["femisia_st"],
                                    A["kinesis_st"]])),
        # HYDRAVIE
        ("V-H1", "HYDRAVIE", "ASKI", lambda: kv2.h1_aski(H, A["hydravie_st"])),
        ("V-H2", "HYDRAVIE", "İKİ ZAMAN",
         lambda: kv2.h2_iki_zaman(H, A["hydravie_st"], A["hydravie_st2"])),
        ("V-H3", "HYDRAVIE", "BİLEŞEN MERDİVENİ",
         lambda: kv2.h3_bilesen_merdiveni(H, A["hydravie_st"])),
        ("V-H4", "HYDRAVIE", "GÖLGE ÖLÇÜSÜ",
         lambda: kv2.h4_golge_olcusu(H, A["hydravie_st"])),
        ("V-H5", "HYDRAVIE", "TEMİZ YÜZEY",
         lambda: kv2.h5_temiz_yuzey(H, A["hydravie_st2"])),
        # KINESIS+
        ("V-K1", "KINESIS+", "TEK TALİMAT",
         lambda: kv2.k1_tek_talimat(K, A["kinesis_st"])),
        ("V-K2", "KINESIS+", "ÇABA", lambda: kv2.k2_caba(K, A["kinesis_gym"])),
        ("V-K3", "KINESIS+", "5–10 POMPA",
         lambda: kv2.k3_bes_on_pompa(K, A["kinesis_st"])),
        ("V-K4", "KINESIS+", "İKİ KEZ",
         lambda: kv2.k4_iki_kez(K, A["kinesis_st"], A["kinesis_st2"])),
        ("V-K5", "KINESIS+", "EKSİK VERİ",
         lambda: kv2.k5_eksik_veri(K, A["kinesis_st2"])),
        # FEMISIA / VIREON
        ("V-F1", "FEMISIA", "ORTAK İNCİ",
         lambda: kv2.f1_ortak_inci(F, V, A["femisia_st"])),
        ("V-F2", "FEMISIA", "TAM İNCİ",
         lambda: kv2.f2_tam_inci(F, A["femisia_st2"])),
        ("V-F3", "FEMISIA", "GEÇİŞ",
         lambda: kv2.f3_gecis(F, V, A["femisia_st"])),
        ("V-F4", "FEMISIA", "KETUM",
         lambda: kv2.f4_ketum(F, A["femisia_st2"])),
        ("V-F5", "FEMISIA", "BİLEŞEN PORTRESİ",
         lambda: kv2.f5_bilesen_portresi(F, A["femisia_st2"])),
        # BABYSOL
        ("V-B1", "BABYSOL", "%30", lambda: kv2.b1_otuz(B, A["babysol_st"])),
        ("V-B2", "BABYSOL", "ZORUNLU METİN",
         lambda: kv2.b2_zorunlu_metin(B, A["babysol_st2"])),
        ("V-B3", "BABYSOL", "15 DAKİKA",
         lambda: kv2.b3_onbes_dakika(B, A["babysol_st"])),
        ("V-B4", "BABYSOL", "FİLTRE",
         lambda: kv2.b4_filtre(B, A["babysol_st"], A["babysol_st2"])),
        ("V-B5", "BABYSOL", "GÜNDEN SONRA",
         lambda: kv2.b5_gunden_sonra(B, A["babysol_st2"])),
    ]


ASETLER = {
    "hydravie_st": str(CEKIM / "ham--DSC04301.jpg"),
    "hydravie_st2": str(CEKIM / "ham--DSC04307.jpg"),
    "kinesis_st": str(CEKIM / "ham--DSC04520.jpg"),
    "kinesis_st2": str(CEKIM / "ham--DSC04516.jpg"),
    "kinesis_gym": str(PILOT / "kinesis-4f9e28543c.png"),
    "femisia_st": str(CEKIM / "ham--DSC04316.jpg"),
    "femisia_st2": str(CEKIM / "ham--DSC04314.jpg"),
    "babysol_st": str(CEKIM / "ham--DSC04498.jpg"),
    "babysol_st2": str(CEKIM / "ham--DSC04507.jpg"),
    "makro": str(CEKIM / "detay--DSC04597.jpg"),
}


# --- AE: gercek icerik provasi ------------------------------------------

def icerik_provasi(plan, icerik_kaydi: dict) -> dict:
    """Konseptin ihtiyac duydugu her alan kutu gerceginde VAR mi."""
    gerekli = plan.olcumler.get("gerekli_icerik", [])
    eksik = [g for g in gerekli
             if icerik_kaydi.get(g) in (None, ic2.BILINMIYOR, [], "")]
    return {"gerekli": gerekli, "eksik": eksik,
            "sonuc": "REAL_CONTENT_FAIL" if eksik else "REAL_CONTENT_PASS"}


# --- Z: craft ve concept AYRI hukum -------------------------------------

def elestirmen(plan, olc, qa, kontrast, icerik_p) -> dict:
    """C13 -- tasarim cozumu URETMEZ, iki ayri hukum verir."""
    craft, concept = [], []
    if not qa["gecti"]:
        craft.append("tipografi QA %d durduran ihlal" % qa["durduran_ihlal"])
    if kontrast:
        craft.append("%d metin blogu okunmuyor" % len(kontrast))
    if olc.bosluk_orani > 0.66 and olc.ogeler < 9:
        craft.append("bosluk %.2f / oge %d -- olu bosluk suphesi"
                     % (olc.bosluk_orani, olc.ogeler))
    m = plan.olcumler
    if icerik_p["sonuc"] == "REAL_CONTENT_FAIL":
        concept.append("gercek icerik gelince cokuyor: %s eksik"
                       % ",".join(icerik_p["eksik"]))
    if not m.get("fikir"):
        concept.append("beyan edilmis bir fikir yok")
    if not m.get("tur3_farki"):
        concept.append("tur 3'ten farki beyan edilmemis")
    if m.get("bosluk_sinifi", "").startswith("DEAD"):
        concept.append("bosluk DEAD olarak siniflandirilmis")
    return {
        "CRAFT": "PASS" if not craft else "FAIL",
        "CRAFT_gerekce": craft,
        "CONCEPT": "PASS" if not concept else "FAIL",
        "CONCEPT_gerekce": concept,
        # Z: craft PASS + concept FAIL -> Creative PASS VERILMEZ
        "CREATIVE": "PASS" if not craft and not concept else "REVISE"
        if not concept else "REJECT",
    }


# --- AA: remove test -----------------------------------------------------

def remove_test(plan) -> list[dict]:
    """Her elemani kaldirinca ne kaybediliyor."""
    out = []
    for oge in plan.ogeler:
        if oge.tur == "alan":
            continue
        v = oge.veri
        if oge.tur == "foto":
            out.append({"oge": "foto", "kayip": ["INFORMATION", "CONCEPT",
                                                 "COMPOSITIONAL_FUNCTION"],
                        "karar": "KEEP"})
        elif oge.tur == "not_alani":
            out.append({"oge": "not_alani", "kayip": ["UTILITY"],
                        "karar": "KEEP"})
        elif oge.tur == "cizgi":
            out.append({"oge": "cizgi", "kayip": ["HIERARCHY"],
                        "karar": "KEEP"})
        else:
            m = (v.get("metin") or "").strip()
            if not m:
                out.append({"oge": "metin(bos)", "kayip": [], "karar": "REMOVE"})
            else:
                out.append({"oge": "metin:%s" % v.get("stil"),
                            "kayip": ["INFORMATION"], "karar": "KEEP"})
    return out


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    (CIKTI / "proofs").mkdir(exist_ok=True)

    print("=== A · MEVCUT DURUM DOGRULAMA ===")
    kay = json.loads((CAL / "index-v2.json").read_text(encoding="utf-8"))
    indeks = {r["source_path"]: r for r in kay}
    hata = av2.dogrula(kay)
    print("manifest kayit: %d | tekil: %d | dogrulama hatasi: %d"
          % (len(kay), len({r["cluster_id"] for r in kay}), len(hata)))
    eksik_kapsama = av2.kapsama_denetimi(kay, list(ASETLER.values()))
    print("kullanilacak aset kapsama disi: %s" % (eksik_kapsama or "YOK"))
    if eksik_kapsama:
        print("DURDURULDU: manifest disinda aset kullanilamaz")
        return 1

    print()
    print("=== I · DNA + K · KERNEL ===")
    d = dna.dna_ozet()
    print("marka ekseni: %s" % d["marka_ekseni"])
    print("UNKNOWN DNA alani: %s" % d["UNKNOWN_alanlar"])
    for k, v in d["kernel"].items():
        print("  %-10s %s" % (k, v))

    print()
    print("=== L · GERCEK ICERIK ===")
    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    icerik = {a: ic2.yukle(a) for a in anahtar}
    rap = ic2.icerik_raporu(anahtar)
    for a in anahtar:
        print("  %-10s var=%s yok=%s"
              % (a, ",".join(rap[a]["var"]), ",".join(rap[a]["yok"]) or "-"))

    print()
    print("=== AD · 25 KONSEPT URETIMI ===")
    tablo = konsept_tablosu(icerik, ASETLER)
    kayitlar = []
    yerlesimler = []
    urun_icerik = {"KAPAK": icerik["hydravie"], "HYDRAVIE": icerik["hydravie"],
                   "KINESIS+": icerik["kinesis+"], "FEMISIA": icerik["femisia"],
                   "BABYSOL": icerik["babysol"]}
    for kid, urun, ad, uretici in tablo:
        try:
            plan = uretici()
        except (ValueError, OSError, KeyError, IndexError,
                ArithmeticError) as ex:
            # Bir konseptin uretilememesi turu durdurmaz; sebebi
            # kayda gecer ve digerleri uretilir.
            print("  %-6s %-22s URETILEMEDI: %s" % (kid, ad, str(ex)[:60]))
            kayitlar.append({"id": kid, "urun": urun, "ad": ad,
                             "durum": "URETILEMEDI", "hata": str(ex)})
            continue
        pdf = CIKTI / "proofs" / ("%s.pdf" % kid)
        g = rd.goruntu_katmani(plan, {"zemin": {}})
        rd.pdf_uret(plan, g, pdf)
        qa = tqa.kapi(pdf, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
        kontrast = rd.metin_kontrast_denetimi(plan, g)
        olc = so.sayfa_olcumleri(pdf)[0]
        yer = yerlesimleri_cikar(plan, kid, indeks)
        yerlesimler.extend(yer)
        icp = icerik_provasi(plan, urun_icerik[urun])
        el = elestirmen(plan, olc, qa, kontrast, icp)
        m = plan.olcumler
        kayitlar.append({
            "id": kid, "urun": urun, "ad": ad, "durum": "URETILDI",
            "konsept": plan.konsept, "kernel": m.get("kernel"),
            "fikir": m.get("fikir"), "koreografi": m.get("koreografi"),
            "iliski": m.get("iliski"), "repertuar": m.get("repertuar"),
            "bosluk_sinifi": m.get("bosluk_sinifi"),
            "urun_olcegi": m.get("urun_olcegi"), "enerji": m.get("enerji"),
            "tur3_farki": m.get("tur3_farki"),
            "icerik_provasi": icp, "elestirmen": el,
            "qa": {"gecti": qa["gecti"], "durduran": qa["durduran_ihlal"],
                   "uyari": qa["uyari"]},
            "kontrast_ihlali": len(kontrast),
            "olcum": {"metin": olc.metin_alan_orani,
                      "gorsel": olc.gorsel_alan_orani,
                      "bosluk": olc.bosluk_orani, "oge": olc.ogeler,
                      "punto": olc.en_buyuk_punto},
            "yerlesim": yer,
            "asgari_ppi": min([y["effective_ppi"] for y in yer], default=None),
        })
        print("  %-6s %-10s %-20s QA=%-5s kontrast=%d icerik=%s craft=%s "
              "concept=%s ppi=%s"
              % (kid, urun, ad[:20], qa["gecti"], len(kontrast),
                 icp["sonuc"].replace("REAL_CONTENT_", ""), el["CRAFT"],
                 el["CONCEPT"],
                 "%.0f" % min([y["effective_ppi"] for y in yer])
                 if yer else "-"))

    (CIKTI / "v2-konsept-kayit.json").write_text(
        json.dumps(kayitlar, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    (CIKTI / "trace-manifest.json").write_text(
        json.dumps({
            "unique_assets_in_manifest": len({r["cluster_id"] for r in kay}),
            "manifest_records": len(kay),
            "concepts": len([k for k in kayitlar if k["durum"] == "URETILDI"]),
            "raster_placements": len(yerlesimler),
            "placements": yerlesimler,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print("=== B · IZLENEBILIRLIK ===")
    uretilen = [k for k in kayitlar if k["durum"] == "URETILDI"]
    print("%d tekil aset -> %d konsept -> %d raster yerlesim"
          % (len({r["cluster_id"] for r in kay}), len(uretilen),
             len(yerlesimler)))
    kade = collections.Counter(y["print_tier"] for y in yerlesimler)
    for t, n in kade.most_common():
        print("  %-26s %d yerlesim" % (t, n))
    istisna = [y for y in yerlesimler if y["print_exception"]]
    print("PRINT_QUALITY_EXCEPTION: %d yerlesim" % len(istisna))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
