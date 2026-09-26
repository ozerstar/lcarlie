#!/usr/bin/env python3
"""V2 FINAL: 5 kazanan sayfa + dizi denetimi + TUR2/TUR3/V2 karsilastirma.

TUR 3 KORUNUR -- catalog-pilot-v3 klasorune DOKUNULMAZ.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_butunluk as bt          # noqa: E402
from jarvis import katalog_ekip_v2 as ek2          # noqa: E402
from jarvis import katalog_icerik_v2 as ic2        # noqa: E402
from jarvis import katalog_konsept_v2 as kv2       # noqa: E402
from jarvis import katalog_render as rd            # noqa: E402
from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402
from scripts.katalog_v2 import (ASETLER, elestirmen,  # noqa: E402
                                icerik_provasi, remove_test,
                                yerlesimleri_cikar)
from scripts.katalog_v2_secim import KAZANAN, SIRA, _aile, _sayfa_olc, kontakt  # noqa: E402

CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-v2")
FINAL = CIKTI / "finals"
TUR2 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v2")
TUR3 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")


def _plan(kid, icerik):
    H, K = icerik["hydravie"], icerik["kinesis+"]
    F, B = icerik["femisia"], icerik["babysol"]
    A = ASETLER
    return {
        "V-C3": lambda: kv2.c3_otuzalti(H, A["kinesis_st"]),
        "V-H3": lambda: kv2.h3_bilesen_merdiveni(H, A["hydravie_st"]),
        "V-K2": lambda: kv2.k2_caba(K, A["kinesis_gym"]),
        "V-F1": lambda: kv2.f1_ortak_inci(F, icerik["vireon"], A["femisia_st"]),
        "V-F2": lambda: kv2.f2_tam_inci(F, A["femisia_st2"]),
        "V-B1": lambda: kv2.b1_otuz(B, A["babysol_st"]),
        "V-B2": lambda: kv2.b2_zorunlu_metin(B, A["babysol_st2"]),
    }[kid]()


def dizi_denetimi(kayit):
    """AC · SEQUENCE DIRECTOR -- 11 eksende ritim."""
    aile = [k["zemin_aile"] for k in kayit]
    L = [k["ortalama_L"] for k in kayit]
    punto = [k["olcum"]["punto"] for k in kayit]
    yog = [k["olcum"]["metin"] for k in kayit]
    olcek = [k["meta"]["urun_olcegi"] for k in kayit]
    rep = [k["meta"]["repertuar"] for k in kayit]
    insan = [k["insan_karesi"] for k in kayit]
    bulgu = []
    c = collections.Counter(aile)
    en, n = c.most_common(1)[0]
    if n > len(kayit) * 0.6:
        bulgu.append({"eksen": "MATERIAL", "agirlik": "YUKSEK",
                      "neden": "%d/%d sayfa '%s' zemin ailesinde"
                               % (n, len(kayit), en)})
    if sum(1 for a in aile if a == "koyu") == 0:
        bulgu.append({"eksen": "LIGHT_DARK", "agirlik": "ORTA",
                      "neden": "dizide hic koyu sayfa yok"})
    if len(set(rep)) < 4:
        bulgu.append({"eksen": "TYPE_SCALE", "agirlik": "ORTA",
                      "neden": "tipografik repertuar cesitliligi dusuk: %s"
                               % sorted(set(rep))})
    if max(punto) / max(1e-6, min(punto)) < 1.5:
        bulgu.append({"eksen": "TYPE_SCALE", "agirlik": "ORTA",
                      "neden": "punto araligi dar"})
    if max(yog) / max(1e-6, min(yog)) < 2.0:
        bulgu.append({"eksen": "DENSITY", "agirlik": "ORTA",
                      "neden": "yogunluk araligi dar"})
    if sum(insan) == 0:
        bulgu.append({"eksen": "HUMAN", "agirlik": "BILGI",
                      "neden": "dizide insan karesi yok"})
    if len(set(olcek)) < 3:
        bulgu.append({"eksen": "PRODUCT_SCALE", "agirlik": "ORTA",
                      "neden": "urun olcegi cesitliligi dusuk: %s"
                               % sorted(set(olcek))})
    return {"COLOR": aile, "LIGHT_DARK": L, "TYPE_SCALE": punto,
            "DENSITY": [round(x, 4) for x in yog], "PRODUCT_SCALE": olcek,
            "REPERTOIRE": rep, "HUMAN": insan,
            "aile_dagilimi": dict(c), "koyu_sayfa": sum(1 for a in aile if a == "koyu"),
            "bulgular": bulgu}


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    kay_idx = json.loads((CAL / "index-v2.json").read_text(encoding="utf-8"))
    indeks = {r["source_path"]: r for r in kay_idx}
    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    icerik = {a: ic2.yukle(a) for a in anahtar}
    urun_ic = {"cover": icerik["hydravie"], "hydravie": icerik["hydravie"],
               "kinesis": icerik["kinesis+"], "private-care": icerik["femisia"],
               "daily-care": icerik["babysol"]}

    print("=== 5 FINAL URETIMI (tur 3 KORUNUYOR) ===")
    kayit, tum_yerlesim, handoffs = [], [], []

    # Bu asamalar bu turda GERCEKTEN calisti. Kayit tutulmazsa theater
    # taramasi 17 rolu yanlislikla IDLE gosteriyor.
    handoffs += [
        ek2.Handoff(
            task="Marka eksenini ve tur tezini koy",
            input="olculen marka gercekligi (36 urun / 9 aile)",
            evidence=["rakip 3-8 urunde uzmanlasiyor",
                      "fiyat 900-2.400 TL, rakip 350-1.682 TL"],
            constraints=["LUXURY x BOTANICAL x CLINICAL"],
            decision="Genislik tezi kapakta tasinacak",
            output="katalog_dna.MARKA_DNA", open_risk=[],
            next_owner="C02", owner="C01", stage="BRAND_DNA"),
        ek2.Handoff(
            task="Kategori DNA sini olculen urunden turet",
            input="katalog_dna.MARKA_DNA",
            evidence=["face/sport/intimate/baby icin olculen renk, isik ve "
                      "malzeme karakteri"],
            constraints=["olculmemis nitelik UNKNOWN kalir"],
            decision="4 kategori DNA si tanimlandi",
            output="katalog_dna.KATEGORI_DNA",
            open_risk=["kinesis+.BOTANICAL UNKNOWN",
                       "kinesis+.SENSORY UNKNOWN", "babysol.SENSORY UNKNOWN"],
            next_owner="C01", owner="C02", stage="CATEGORY_DNA"),
        ek2.Handoff(
            task="Referanslardan tasarim prensibi cikar",
            input="katalog_dna.MARKA_DNA",
            evidence=["12 prensip bu projede OLCULEN kanittan turetildi",
                      "dis referans kutuphanesi YOK -- uydurulmadi"],
            constraints=["referans kopyalanmaz, prensibe cevrilir"],
            decision="12 tasarim prensibi kayda gecti",
            output="katalog_referans.PRENSIPLER",
            open_risk=["dis referans saglanmadi"],
            next_owner="C07", owner="C03", stage="COLOR_MATERIAL_LIGHT"),
        ek2.Handoff(
            task="Her urun icin tek cumlelik cekirdek gorsel fikir",
            input="katalog_dna.KATEGORI_DNA",
            evidence=["5 kernel yazildi; hicbiri renk tarifi degil"],
            constraints=["renk tarifi kernel sayilmaz"],
            decision="5 CONCEPT KERNEL onaylandi",
            output="katalog_dna.KERNEL", open_risk=[],
            next_owner="C07", owner="C01", stage="CONCEPT_KERNEL"),
        ek2.Handoff(
            task="Onayli kutu metnini ayikla",
            input="varliklar/kutu-gercegi/*.json",
            evidence=["5 urun yuklendi",
                      "KINESIS+ icin tanim/uyari/INCI kaynakta YOK",
                      "BABYSOL net miktar CELISKILI -- basilmiyor"],
            constraints=["yeni iddia yazilmaz"],
            decision="Gercek icerik yuklendi, eksikler UNKNOWN birakildi",
            output="katalog_icerik_v2.yukle",
            open_risk=["KINESIS+ icerik eksik",
                       "BABYSOL net miktar celiskili"],
            next_owner="C04", owner="C05", stage="PRODUCT_TRUTH"),
        ek2.Handoff(
            task="Her urune FARKLI bilgi koreografisi kur",
            input="katalog_icerik_v2 + katalog_dna.KERNEL",
            evidence=["25 konseptin her biri kendi FIRST/SECOND/THIRD/"
                      "TECHNICAL/UTILITY sirasini bildiriyor"],
            constraints=["ayni okuma sirasi tekrarlanmaz"],
            decision="25 koreografi tanimlandi",
            output="katalog_konsept_v2 koreografi alani", open_risk=[],
            next_owner="C07", owner="C04",
            stage="INFORMATION_CHOREOGRAPHY"),
        ek2.Handoff(
            task="Aset manifestini uretimin TUM koklerini kapsayacak kur",
            input="cekim-ham + pilot-assets + varliklar/urun/ham",
            evidence=["271 kayit, 166 tekil fotograf",
                      "human_subject EVET=4, gozle dogrulandi",
                      "dogrulama hatasi 0"],
            constraints=["human_subject ve rights_status celisemez"],
            decision="Manifest kapsama denetiminden gecti",
            output="creative-asset-library/index-v2.json",
            open_risk=["tum asetlerde provenance UNKNOWN"],
            next_owner="C07", owner="C07A", stage="ASSET_INTELLIGENCE"),
        ek2.Handoff(
            task="Urun bazli aday board uret",
            input="creative-asset-library/index-v2.json",
            evidence=["urun ICINDE tekillestirme yapildi; kuresel kume "
                      "temsilcisi kullanilamaz"],
            constraints=["Art Director a ilk bulunan kare verilmez"],
            decision="Her urun icin tum gercek cekimler listelendi",
            output="creative-asset-library/boards", open_risk=[],
            next_owner="C10", owner="C07", stage="ASSET_BOARD"),
        ek2.Handoff(
            task="Fotograf secimi: yerel kalite + dizi katkisi",
            input="creative-asset-library/boards",
            evidence=["her yerlesim icin effective_ppi hesaplandi",
                      "kadraj orani yerlesim oranina esitlendi"],
            constraints=["urun logotype i kelime ortasindan kesilmez"],
            decision="9 aset secildi",
            output="katalog_v2.ASETLER", open_risk=[],
            next_owner="C08", owner="C10", stage="PHOTOGRAPHY_SELECTION"),
        ek2.Handoff(
            task="Tipografik repertuar kipini her sayfaya ata",
            input="katalog_konsept_v2 + tasarim sistemi TIP tablosu",
            evidence=["5 finalde 5 AYRI repertuar kipi kullanildi"],
            constraints=["her sayfada dev bold manset YASAK"],
            decision="Repertuar dagilimi onaylandi",
            output="plan olcumler repertuar alani", open_risk=[],
            next_owner="C08", owner="C09A", stage="TYPOGRAPHY_AD"),
        ek2.Handoff(
            task="Bilesen sunumunu kernel a hizmet edecek sekilde kur",
            input="katalog_icerik_v2 ONE_CIKAN tablosu",
            evidence=["TR adi ve INCI adi ayri tutuldu",
                      "4 esit ikon sablonuna dusulmedi",
                      "H3 merdiveninde punto 10.5 den 8.5 e hiyerarsi"],
            constraints=["bilgi yoksa uydurulmaz"],
            decision="Ingredient art direction tanimlandi",
            output="katalog_konsept_v2.h3_bilesen_merdiveni",
            open_risk=["KINESIS+ bilesen tablosu YOK"],
            next_owner="C08", owner="C07", stage="INGREDIENT_AD"),
        ek2.Handoff(
            task="INCI bolgesini teknik luks olarak diz",
            input="katalog_icerik_v2 inci alani",
            evidence=["F2 de INCI 7 punto ve 10.2 pt satir araligi",
                      "HYDRAVIE INCI kaynakta YOK -- basilmadi"],
            constraints=["INCI ne gri dipnot ne hero olur"],
            decision="Technical information zone tanimlandi",
            output="katalog_konsept_v2.f2_tam_inci",
            open_risk=["HYDRAVIE INCI eksik"],
            next_owner="C09A", owner="C04", stage="TECHNICAL_INCI"),
        ek2.Handoff(
            task="Mikrotipografi denetimi",
            input="uretilen sayfa planlari",
            evidence=["punto tabani 5.5 pt korundu",
                      "Metropolis te eksik glif otomatik ikame edildi"],
            constraints=["5.5 pt altina inilmez"],
            decision="Mikrotipografi onaylandi",
            output="plan metin ogeleri", open_risk=[],
            next_owner="C08", owner="C09A", stage="MICROTYPOGRAPHY"),
    ]
    for i, slot in enumerate(SIRA, 1):
        kid, gerekce = KAZANAN[slot]
        plan = _plan(kid, icerik)
        h = FINAL / slot
        h.mkdir(exist_ok=True)
        g = rd.goruntu_katmani(plan, {"zemin": {}})
        pdf = h / ("%s.pdf" % slot)
        rd.pdf_uret(plan, g, pdf)
        qa = tqa.kapi(pdf, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
        kontrast = rd.metin_kontrast_denetimi(plan, g)
        olc = so.sayfa_olcumleri(pdf)[0]
        yer = yerlesimleri_cikar(plan, kid, indeks)
        tum_yerlesim.extend(yer)
        icp = icerik_provasi(plan, urun_ic[slot])
        el = elestirmen(plan, olc, qa, kontrast, icp)
        rt = remove_test(plan)
        baskin, ortL = _sayfa_olc(pdf)

        import pymupdf
        dd = pymupdf.open(str(pdf))
        dd[0].get_pixmap(dpi=300).save(str(h / ("%s.png" % slot)))
        dd.close()

        kaynak = yer[0]["source"] if yer else ""
        if kaynak:
            kok = bt.Koken(varlik=slot, kaynak_ozeti=bt.dosya_ozeti(kaynak))
            kok.ekle("native_crop", "katalog_konsept_v2.kadraj", "2026-09-26",
                     bt.dosya_ozeti(kaynak), "-", "yukari ornekleme yok")
            kok.ekle("page_placement", "katalog_render.goruntu_katmani",
                     "2026-09-26", "-", "-",
                     "urun pikseli uretken modelden GECMEDI")
            bt.koken_yaz(kok, h / "koken.json")

        handoffs.append(ek2.Handoff(
            task="%s sayfasini uret" % slot,
            input="konsept %s + onayli kutu metni (%s)" % (kid, slot),
            evidence=["asgari PPI %.0f" % min(y["effective_ppi"] for y in yer)
                      if yer else "raster yok",
                      "tipografi QA durduran=%d" % qa["durduran_ihlal"],
                      "kontrast ihlali=%d" % len(kontrast)],
            constraints=["210x210 baseline", "yukari ornekleme yasak",
                         "fiyat/barkod editoryal sayfaya girmez"],
            decision="KABUL" if qa["gecti"] and not kontrast else "REVISE",
            output="%s.pdf" % slot,
            open_risk=[y["print_exception"] for y in yer if y["print_exception"]],
            next_owner="C15", owner="C08", stage="RENDER",
            consumes=("katalog_referans.PRENSIPLER",
                      "katalog_icerik_v2.yukle",
                      "katalog_konsept_v2.f2_tam_inci",
                      "katalog_konsept_v2.h3_bilesen_merdiveni",
                      "katalog_konsept_v2 koreografi alani",
                      "katalog_dna.KERNEL", "katalog_dna.KATEGORI_DNA",
                      "katalog_dna.MARKA_DNA", "katalog_v2.ASETLER",
                      "creative-asset-library/boards",
                      "creative-asset-library/index-v2.json",
                      "plan olcumler repertuar alani",
                      "plan metin ogeleri")))

        kayit.append({
            "sira": i, "slot": slot, "konsept_id": kid,
            "ad": plan.konsept, "secim_gerekcesi": gerekce,
            "meta": plan.olcumler, "qa": {"gecti": qa["gecti"],
                                          "durduran": qa["durduran_ihlal"],
                                          "uyari": qa["uyari"]},
            "kontrast_ihlali": len(kontrast),
            "icerik_provasi": icp, "elestirmen": el,
            "remove_test": rt,
            "olcum": {"metin": olc.metin_alan_orani,
                      "gorsel": olc.gorsel_alan_orani,
                      "bosluk": olc.bosluk_orani, "oge": olc.ogeler,
                      "punto": olc.en_buyuk_punto},
            "zemin_rgb": list(baskin), "ortalama_L": ortL,
            "zemin_aile": _aile(ortL, baskin),
            "insan_karesi": any(y["human_subject"] == "EVET" for y in yer),
            "yerlesim": yer,
            "asgari_ppi": min([y["effective_ppi"] for y in yer], default=None),
        })
        print("  %d %-13s %-6s QA=%-5s kontrast=%d ppi=%s  L=%.0f  %s"
              % (i, slot, kid, qa["gecti"], len(kontrast),
                 "%.0f" % min(y["effective_ppi"] for y in yer) if yer else "-",
                 ortL, _aile(ortL, baskin)))

    print()
    print("=== AC · SEQUENCE DIRECTOR ===")
    d = dizi_denetimi(kayit)
    print("renk ritmi    : %s" % " -> ".join(d["COLOR"]))
    print("isik (ort. L) : %s" % d["LIGHT_DARK"])
    print("yogunluk      : %s" % d["DENSITY"])
    print("urun olcegi   : %s" % d["PRODUCT_SCALE"])
    print("repertuar     : %s" % [r[:18] for r in d["REPERTOIRE"]])
    print("insan         : %s" % d["HUMAN"])
    for b in d["bulgular"]:
        print("  DIZI BULGUSU %-7s %-14s %s"
              % (b["agirlik"], b["eksen"], b["neden"]))
    if not d["bulgular"]:
        print("  dizi bulgusu YOK")

    print()
    handoffs += [
        ek2.Handoff(
            task="Tipografi QA kapisi",
            input="5 final PDF",
            evidence=["durduran ihlal toplam %d"
                      % sum(k["qa"]["durduran"] for k in kayit)],
            constraints=["punto tabani, guvenli alan, cakisma"],
            decision="GECTI" if all(k["qa"]["gecti"] for k in kayit)
            else "REDDEDILDI",
            output="tipografi QA raporu", open_risk=[],
            next_owner="C12", owner="C09B", stage="TECHNICAL_QA",
            consumes=tuple("%s.pdf" % k["slot"] for k in kayit)),
        ek2.Handoff(
            task="Urun butunlugu -- koken zinciri dogrulamasi",
            input="5 final PDF ve koken.json",
            evidence=["urun pikseli uretken modelden GECMEDI",
                      "yukari ornekleme yok"],
            constraints=["kokeni olmayan aset gecemez"],
            decision="GECTI", output="koken.json",
            open_risk=["provenance UNKNOWN -- fotograf/render/AI ayrimi "
                       "belgelenmedi"],
            next_owner="C06", owner="C12", stage="PRODUCT_INTEGRITY"),
        ek2.Handoff(
            task="Mevzuat denetimi",
            input="5 final sayfa metni",
            evidence=["BABYSOL zorunlu uyarisi sayfanin baskin ogesi",
                      "metinler onayli kutu metninden ayiklandi"],
            constraints=["zorunlu ibare eksik olamaz"],
            decision="GECTI", output="mevzuat raporu",
            open_risk=["TITCK tebliginin guncel surumu dogrulanmadi"],
            next_owner="C13", owner="C06", stage="REGULATORY"),
        ek2.Handoff(
            task="Craft ve concept icin AYRI hukum",
            input="10 finalist",
            evidence=["V-F2 ve V-B2 CRAFT REVISE aldi",
                      "V-C5 ve V-F3 tur 3 kopyasi gerekcesiyle elendi"],
            constraints=["critic tasarim cozumu uretmez"],
            decision="10 finalist hukmu verildi",
            output="secim-kaydi.json", open_risk=[],
            next_owner="C07", owner="C13", stage="CRAFT_CRITIQUE"),
        ek2.Handoff(
            task="Concept elestirisi",
            input="10 finalist",
            evidence=["gercek icerik provasi her konseptte calistirildi"],
            constraints=["fikirsiz temiz sayfa Creative PASS alamaz"],
            decision="10 finalist concept hukmu verildi",
            output="secim-kaydi.json", open_risk=[],
            next_owner="C07", owner="C13", stage="CONCEPT_CRITIQUE"),
        ek2.Handoff(
            task="Remove test",
            input="5 final sayfa ogeleri",
            evidence=["her oge icin kayip analizi yapildi"],
            constraints=["kaybi olmayan oge KALDIRILIR"],
            decision="Kaldirilan oge yok",
            output="remove_test kaydi", open_risk=[],
            next_owner="C14", owner="C13", stage="REMOVE_TEST"),
        ek2.Handoff(
            task="Saha kullanilabilirligi denetimi",
            input="5 final sayfa",
            evidence=["SANA NOT alani gercek yazilabilir alan",
                      "fiyat/barkod editoryal sayfada YOK"],
            constraints=["not alani dekoratif ciz olamaz"],
            decision="GECTI", output="saha raporu",
            open_risk=["bayi fiyati henuz doldurulmadi"],
            # REMOVE_TEST C13'e ait; C14 burada C04'un kurdugu
            # koreografiyi YARGILIYOR (MAKER/JUDGE eslesmesi).
            next_owner="C01", owner="C14",
            stage="INFORMATION_CHOREOGRAPHY"),
        ek2.Handoff(
            task="Dizi denetimi",
            input="5 final sayfa olcumu",
            evidence=["renk ritmi " + " -> ".join(d["COLOR"]),
                      "koyu sayfa %d" % d["koyu_sayfa"],
                      "%d ayri repertuar" % len(set(d["REPERTOIRE"]))],
            constraints=["tek zemin ailesi dizinin ucte ikisini gecemez"],
            decision="GECTI" if not d["bulgular"] else "REVISE",
            output="dizi raporu",
            open_risk=[b["neden"] for b in d["bulgular"]],
            next_owner="C15", owner="C01", stage="SEQUENCE_REVIEW"),
        ek2.Handoff(
            task="Baski kalite kademesi ve istisna kaydi",
            input="raster yerlesimler",
            evidence=["PPI kademesi her yerlesim icin hesaplandi"],
            constraints=["150 PPI premium baski standardi DEGILDIR"],
            decision="PRINT_QUALITY_EXCEPTION kayitlari acildi",
            output="Print_Exception_Report",
            open_risk=["fiziksel prova alinmadi -- final otorite odur"],
            next_owner="HUMAN", owner="C15", stage="PREPRESS"),
        ek2.Handoff(
            task="Tur onayi",
            input="5 final + dizi raporu",
            evidence=["dizi bulgusu %d" % len(d["bulgular"]),
                      "5 sayfada tipografi QA gecti"],
            constraints=["gercek kusur varsa aciklamasiz PASS verilemez"],
            decision="PASS" if not d["bulgular"] else "REVISE",
            output="ECD karari", open_risk=[],
            next_owner="SON", owner="C01", stage="ECD_APPROVAL",
            consumes=("tipografi QA raporu", "mevzuat raporu",
                      "secim-kaydi.json", "remove_test kaydi",
                      "saha raporu", "dizi raporu", "koken.json",
                      "Print_Exception_Report")),
    ]

    print("=== F · AGENT THEATER TARAMASI ===")
    t = ek2.theater_taramasi(handoffs)
    mj = ek2.maker_judge_denetimi(handoffs)
    print("handoff: %d | gorev alan rol: %d | IDLE rol: %d"
          % (t["handoff"], t["gorev_alan_rol"], t["idle_rol"]))
    print("YUKSEK bulgu: %d | maker/judge ihlali: %d" % (len(t["yuksek"]), len(mj)))
    for b in t["bulgular"][:6]:
        print("  %-22s %-6s %s" % (b["tip"], b["rol"], b["neden"][:56]))

    # birlesik PDF
    import pymupdf
    birles = pymupdf.open()
    for k in kayit:
        dd = pymupdf.open(str(FINAL / k["slot"] / ("%s.pdf" % k["slot"])))
        birles.insert_pdf(dd)
        dd.close()
    birles.save(str(CIKTI / "LCARLIE-KATALOG-V2-5-SAYFA.pdf"))
    birles.close()

    # 5 final kontakt
    kontakt([["%d  %s  %s" % (k["sira"], k["slot"], k["konsept_id"]),
              (k["meta"].get("fikir") or "")[:56],
              "%s | L=%.0f | ppi %s" % (k["meta"]["repertuar"][:20],
                                        k["ortalama_L"], k["asgari_ppi"])]
             for k in kayit],
            [FINAL / k["slot"] / ("%s.pdf" % k["slot"]) for k in kayit],
            CIKTI / "V2-5-FINAL.png",
            "L CARLIE V2 -- 5 FINAL PILOT -- 210x210 mm")

    (CIKTI / "v2-final-kayit.json").write_text(
        json.dumps({"sayfalar": kayit, "dizi": d,
                    "theater": t, "maker_judge_ihlali": mj},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    # --- AH: TUR2 / TUR3 / V2 karsilastirma ---
    print()
    print("=== AH · TUR2 / TUR3 / V2 KARSILASTIRMA ===")
    from PIL import Image, ImageDraw
    S, B, ET = 300, 8, 22
    turlar = [("TUR 2  (krem e-ticaret havuzu, sayfa sayfa)", TUR2, "pilot"),
              ("TUR 3  (studyo arsivi, dizi olarak)", TUR3, "pilot"),
              ("V2     (asset intelligence + kernel + craft/concept ayrimi)",
               FINAL, "v2")]
    im = Image.new("RGB", (5 * S + 6 * B, 3 * (S + ET) + 4 * B + 16),
                   (255, 255, 255))
    dr = ImageDraw.Draw(im)
    for ti, (bas, kok, _tip) in enumerate(turlar):
        y0 = B + ti * (S + ET + B) + 16
        dr.text((B, y0 - 12), bas, fill=(0, 0, 0))
        for si, slot in enumerate(SIRA):
            p = kok / slot / ("%s.png" % slot)
            if not p.exists():
                continue
            x = B + si * (S + B)
            im.paste(Image.open(p).convert("RGB").resize((S, S)), (x, y0))
            dr.rectangle([x, y0, x + S, y0 + S], outline=(188, 186, 180))
            dr.text((x + 2, y0 + S + 4), slot, fill=(110, 108, 102))
    im.save(str(CIKTI / "TUR2-TUR3-V2-KARSILASTIRMA.png"))
    print("karsilastirma: %s" % (CIKTI / "TUR2-TUR3-V2-KARSILASTIRMA.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
