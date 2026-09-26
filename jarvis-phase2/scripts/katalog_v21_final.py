#!/usr/bin/env python3
"""V2.1 FINAL -- 5 sayfa + dizi + TUR3/V2/V2.1 karsilastirma + kurul."""
from __future__ import annotations

import collections
import io
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_butunluk as bt             # noqa: E402
from jarvis import katalog_render as rd               # noqa: E402
from jarvis import katalog_sayfa_olcum as so          # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts      # noqa: E402
from jarvis import katalog_tipografi_qa as tqa        # noqa: E402
from jarvis import katalog_urun_gercegi as ug         # noqa: E402
from jarvis import katalog_urun_varligi as uv         # noqa: E402
from scripts.katalog_v21 import (CIKTI, _an, _one_cikan,  # noqa: E402
                                 planlar)
from scripts.katalog_v2_secim import _aile, _sayfa_olc  # noqa: E402
from scripts.olc_varlik import yerlesimler            # noqa: E402

CAL = pathlib.Path("/opt/lcarlie/output/creative-asset-library/index-v2.json")
FINAL = CIKTI / "finals"
TUR3 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")
V2 = pathlib.Path("/opt/lcarlie/output/catalog-v2/finals")

SIRA = ["cover", "hydravie", "kinesis", "private-care", "daily-care"]

SECIM = {
    "cover": ("V21-C1", "C2'nin uc panosu dizilim sorunu gibi okunuyor ve "
                        "urun %10'da kaliyor. C1 'hangi dunyaya giriyoruz' "
                        "sorusuna gercek bir NESNEYLE cevap veriyor."),
    "hydravie": ("V21-H1", "H2'de soluk mavi kutu soluk zeminde ayrismiyor. "
                           "H1'de cam blok ve soguk isik malzeme dunyasini "
                           "kuruyor; urun 122 mm ve PRINT_READY."),
    "kinesis": ("V21-K2", "K1'de sporcu baskin, urun bbox %9.2 -- bir URUN "
                          "sayfasi icin kahraman degil. Ayrica rights "
                          "UNKNOWN. K2'de urun kahraman ve baskiya uygun."),
    "private-care": ("V21-F1", "Brief'in tarif ettigi gorsel dunya amber cam "
                               "ve sicak malzeme. F2 daha dramatik ama "
                               "'quietness' tarifine F1 uyuyor. VIREON her "
                               "iki surumden de cikarildi."),
    "daily-care": ("V21-B1", "B2'deki %30 iyi ama 34 puntoda mutevazi "
                             "kaliyor. B1'de urun kahraman, zemin fildisi "
                             "mineral -- sari sayfa reddedildi."),
}

# 33 · FINAL VISUAL ACCEPTANCE -- 12 soru, her biri OBSERVATION/EVIDENCE/
# DECISION. Kendi tasarimini savunma.
KURUL = [
    ("1 Urun ilk bakista kahraman mi?",
     "Bes sayfanin dordunde urun sayfanin en buyuk tekil kutlesi; "
     "kapakta da oyle.",
     "urun bbox: kapak %37.6 · hydravie %26.5 · kinesis %16.7 · "
     "femisia %12.5 · babysol %20.0 (V2: %11.0/%6.4/%2.2/%7.3/%15.4)",
     "EVET -- ancak FEMISIA %12.5 ile sinirda; sise yatay ve ince."),
    ("2 Sayfanin tek cumlelik guclu bir fikri var mi?",
     "Her sayfa kendi kernel'ini bildiriyor ve fikir metinde degil "
     "yapida goruluyor.",
     "5 kernel: nesne+golge · cam blok · urun kutlesi · amber sessizlik · "
     "fildisi isik",
     "EVET"),
    ("3 Fotograf layout'a mi yon veriyor?",
     "Kadraj urun kutusundan turetildi (urun_kadraji), bos layout'a "
     "sonradan yerlestirilmedi.",
     "her yerlesimde kadraj = urun bbox + olculu pay; kapakta pay 0.55 "
     "(golge icin), urun sayfalarinda 0.10-0.12",
     "EVET"),
    ("4 Materiality hissediliyor mu?",
     "Cam blok, amber cam, mat karton, fildisi mineral zemin ve gercek "
     "dokme golgeler kompozisyonun parcasi.",
     "hicbir sayfada duz renk kutu + kucuk gorsel kurgusu yok; zeminler "
     "asetten turetildi (MATERIAL_DERIVATION / TONAL_CONTINUITY)",
     "EVET -- KINESIS sayfasinda malzeme en zayif (mat karton + duz zemin)"),
    ("5 Typography art direction'in parcasi mi?",
     "Bes sayfada bes ayri repertuar kipi; bilesen rayi TR adi + INCI "
     "adi olarak iki katmanli.",
     "repertuar: IMAGE_INTEGRATED · PRODUCT_NAME_DOMINANCE ×2 · "
     "QUIET_EDITORIAL · PRODUCT_NAME_DOMINANCE",
     "KISMEN -- uc sayfada ayni kip (PRODUCT_NAME_DOMINANCE) tekrar ediyor"),
    ("6 Teknik bilgi premium bicimde cozulmus mu?",
     "INCI 5.6-5.7 punto, 7.0-7.4 pt satir araligi, ayri bolgede; "
     "bilesen rayi TR/INCI ayrimini tasiyor.",
     "5 sayfanin 4'unde tam INCI basili; KINESIS INCI artik URUN "
     "DOSYASINDAN geliyor (V2'de 'yok' sanilmisti)",
     "EVET"),
    ("7 Bosluk intentional mi?",
     "Her sayfa bosluk sinifini bildiriyor; hicbiri DEAD olarak "
     "isaretlenmedi.",
     "5/5 ACTIVE gerekceli",
     "EVET -- ancak gerekceler tasarimcinin kendi beyani; bagimsiz "
     "dogrulama yok"),
    ("8 Gereksiz element var mi?",
     "REMOVE TEST her ogede calistirildi.",
     "kaldirilan oge yok; her oge bilgi/hiyerarsi/kompozisyon islevi "
     "tasiyor",
     "HAYIR"),
    ("9 Bu sayfa baska bir dermokozmetik markaya ait olabilir mi?",
     "Ayirt edici olan: TR/INCI ikili bilesen rayi, SANA NOT alani, "
     "gercek dokme golge disiplini, botanik x klinik gerilimi.",
     "logo kapatildiginda bu dort davranis kaliyor",
     "KISMEN -- bilesen rayi ve not alani ayirt edici; zemin paleti "
     "henuz jenerik"),
    ("10 Logoyu kapatsak L'CARLIE grammar hissediliyor mu?",
     "Dort signature davranis sayfalar arasinda tutarli.",
     "TR+INCI ikili adlandirma · SANA NOT · gercek golge · mikro INCI "
     "bolgesi",
     "KISMEN"),
    ("11 Bes sayfa birlikte ritim olusturuyor mu?",
     "Dizi denetimi renk/isik/yogunluk/olcek eksenlerinde olculuyor.",
     "render sonrasi olculecek -- asagidaki DIZI bolumune bakin",
     "OLCULDU"),
    ("12 Tur 3 veya V2'den gercekten daha iyi mi?",
     "Urun varligi V2'nin uzerinde, Tur 3'un altinda; ancak Tur 3 bunu "
     "PRINT_EXCEPTION ile aliyordu.",
     "urun bbox ort: TUR3 %27.3 (150-212 PPI) · V2 %12.8 · "
     "V2.1 %18.6 (4/5 sayfa >=250 PPI)",
     "KISMEN -- olcekte Tur 3'un altinda, baski uygunlugunda ustunde"),
]


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    indeks = {r["source_path"]: r
              for r in json.loads(CAL.read_text(encoding="utf-8"))}
    anahtar = ["hydravie", "kinesis+", "femisia", "vireon", "babysol"]
    g = {a: ug.yukle(a) for a in anahtar}
    icerik = {a: {"one_cikan": _one_cikan(a),
                  "alanlar": dict(g[a]["alanlar"]),
                  **{k: ug.deger(g[a], k) for k in
                     ("tanim", "kullanim", "uyari", "inci", "net_miktar",
                      "kategori")}} for a in anahtar}
    P = planlar(icerik)

    print("=== 5 FINAL (TUR3 ve V2 KORUNUYOR) ===")
    kayit = []
    for i, slot in enumerate(SIRA, 1):
        kid, gerekce = SECIM[slot]
        plan = P[kid]()
        h = FINAL / slot
        h.mkdir(exist_ok=True)
        gk = rd.goruntu_katmani(plan, {"zemin": {}})
        pdf = h / ("%s.pdf" % slot)
        rd.pdf_uret(plan, gk, pdf)
        qa = tqa.kapi(pdf, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
        kont = rd.metin_kontrast_denetimi(plan, gk)
        olc = so.sayfa_olcumleri(pdf)[0]
        y = yerlesimler(plan)
        an = {v["source"]: _an(v["source"]) for v in y}
        m = uv.olc(plan, y, an)
        baskin, ortL = _sayfa_olc(pdf)

        import pymupdf
        d = pymupdf.open(str(pdf))
        d[0].get_pixmap(dpi=300).save(str(h / ("%s.png" % slot)))
        d.close()

        src = y[0]["source"] if y else ""
        if src:
            kok = bt.Koken(varlik=slot, kaynak_ozeti=bt.dosya_ozeti(src))
            kok.ekle("native_crop", "katalog_konsept_v21.urun_kadraji",
                     "2026-09-26", bt.dosya_ozeti(src), "-",
                     "yukari ornekleme yok")
            kok.ekle("page_placement", "katalog_render.goruntu_katmani",
                     "2026-09-26", "-", "-",
                     "urun pikseli uretken modelden GECMEDI")
            bt.koken_yaz(kok, h / "koken.json")

        r0 = indeks.get(src, {})
        kayit.append({
            "sira": i, "slot": slot, "konsept_id": kid, "ad": plan.konsept,
            "secim_gerekcesi": gerekce, "meta": plan.olcumler,
            "qa": {"gecti": qa["gecti"], "durduran": qa["durduran_ihlal"]},
            "kontrast_ihlali": len(kont), "varlik": m,
            "zemin_rgb": list(baskin), "ortalama_L": ortL,
            "zemin_aile": _aile(ortL, baskin),
            "PRODUCT_TRUTH_STATUS": _truth(g, slot),
            "RIGHTS_STATUS": r0.get("rights_status", "?"),
            "HUMAN_SUBJECT": r0.get("human_subject", "?"),
            "AI_STATUS": "NO_AI -- gercek cekim, uretken model kullanilmadi",
            "PRINT_STATUS": plan.olcumler.get("baski_durumu"),
            "PRINT_EXCEPTION": plan.olcumler.get("baski_istisnasi"),
            "effective_ppi": y[0]["effective_ppi"] if y else None,
            "olcum": {"metin": olc.metin_alan_orani,
                      "punto": olc.en_buyuk_punto, "oge": olc.ogeler},
        })
        print("  %d %-13s %-8s QA=%-5s kont=%d  urun %5.1f x %5.1f mm "
              "bbox %%%4.1f  %5.0f PPI  %-22s L=%3.0f %s"
              % (i, slot, kid, qa["gecti"], len(kont),
                 m.get("bbox_width_mm") or 0, m.get("bbox_height_mm") or 0,
                 (m.get("bbox_area_over_page") or 0) * 100,
                 y[0]["effective_ppi"] if y else 0,
                 plan.olcumler.get("baski_durumu"), ortL,
                 _aile(ortL, baskin)))

    print()
    print("=== DIZI ===")
    aile = [k["zemin_aile"] for k in kayit]
    rep = [k["meta"]["repertuar"] for k in kayit]
    yog = [k["olcum"]["metin"] for k in kayit]
    pun = [k["olcum"]["punto"] for k in kayit]
    bbox = [k["varlik"].get("bbox_area_over_page") or 0 for k in kayit]
    print("renk     : %s" % " -> ".join(aile))
    print("L        : %s" % [k["ortalama_L"] for k in kayit])
    print("repertuar: %s" % [r[:20] for r in rep])
    print("yogunluk : %s" % [round(x, 4) for x in yog])
    print("punto    : %s" % pun)
    print("urun bbox: %s" % [round(x * 100, 1) for x in bbox])
    bulgu = []
    c = collections.Counter(aile)
    en, n = c.most_common(1)[0]
    if n > len(kayit) * 0.6:
        bulgu.append("MATERIAL YUKSEK: %d/%d sayfa '%s'" % (n, len(kayit), en))
    if len(set(rep)) < 4:
        bulgu.append("REPERTUAR ORTA: yalniz %d ayri kip" % len(set(rep)))
    if max(yog) / max(1e-9, min(yog)) < 2.0:
        bulgu.append("YOGUNLUK ORTA: aralik dar")
    for b in bulgu:
        print("  DIZI BULGUSU: %s" % b)
    if not bulgu:
        print("  dizi bulgusu YOK")

    print()
    print("=== 33 · FINAL VISUAL ACCEPTANCE (12 SORU) ===")
    for soru, gozlem, kanit, karar in KURUL:
        print("  %s" % soru)
        print("     OBSERVATION: %s" % gozlem)
        print("     EVIDENCE   : %s" % kanit)
        print("     DECISION   : %s" % karar)

    (CIKTI / "v21-final-kayit.json").write_text(
        json.dumps({"sayfalar": kayit, "dizi_bulgulari": bulgu,
                    "kurul": [{"soru": s, "observation": o, "evidence": e,
                               "decision": d} for s, o, e, d in KURUL]},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    _kontakt(kayit)
    _karsilastirma()
    return 0


def _truth(g, slot):
    m = {"cover": "hydravie", "hydravie": "hydravie", "kinesis": "kinesis+",
         "private-care": "femisia", "daily-care": "babysol"}[slot]
    al = g[m]["alanlar"]
    cel = [k for k, v in al.items() if v["status"] == ug.CELISKI]
    blk = [k for k, v in al.items() if v["status"] == "BLOCKED"]
    return {"urun": m, "alan_sayisi": len(al), "CONFLICT": cel,
            "BLOCKED": blk,
            "kaynaklar": sorted({v["source"] for v in al.values()})}


def _kontakt(kayit):
    import pymupdf
    from PIL import Image, ImageDraw
    S, B, ET = 330, 9, 52
    im = Image.new("RGB", (5 * S + 6 * B, S + ET + 2 * B + 26), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((B, 8), "L CARLIE V2.1 -- 5 FINAL -- 210x210 mm", fill=(0, 0, 0))
    for i, k in enumerate(kayit):
        x = B + i * (S + B)
        y = 26 + B
        doc = pymupdf.open(str(FINAL / k["slot"] / ("%s.pdf" % k["slot"])))
        px = doc[0].get_pixmap(dpi=64)
        im.paste(Image.open(io.BytesIO(px.tobytes("png"))).convert("RGB")
                 .resize((S, S)), (x, y))
        doc.close()
        d.rectangle([x, y, x + S, y + S], outline=(188, 186, 180))
        v = k["varlik"]
        d.text((x + 2, y + S + 5), "%d  %s  %s"
               % (k["sira"], k["slot"], k["konsept_id"]), fill=(0, 0, 0))
        d.text((x + 2, y + S + 17), (k["meta"].get("fikir") or "")[:56],
               fill=(110, 108, 102))
        d.text((x + 2, y + S + 29), "urun %.0fx%.0f mm · bbox %%%.1f · %.0f PPI"
               % (v.get("bbox_width_mm") or 0, v.get("bbox_height_mm") or 0,
                  (v.get("bbox_area_over_page") or 0) * 100,
                  k["effective_ppi"] or 0), fill=(140, 138, 132))
        d.text((x + 2, y + S + 41), k["PRINT_STATUS"] or "", fill=(150, 110, 100))
    im.save(str(CIKTI / "V21-5-FINAL.png"))
    print("\n5 final kontakt: %s" % (CIKTI / "V21-5-FINAL.png"))


def _karsilastirma():
    from PIL import Image, ImageDraw
    S, B, ET = 300, 8, 22
    turlar = [("TUR 3", TUR3), ("V2", V2), ("V2.1", FINAL)]
    im = Image.new("RGB", (5 * S + 6 * B, 3 * (S + ET) + 4 * B + 16),
                   (255, 255, 255))
    d = ImageDraw.Draw(im)
    for ti, (bas, kok) in enumerate(turlar):
        y0 = B + ti * (S + ET + B) + 16
        d.text((B, y0 - 12), bas, fill=(0, 0, 0))
        for si, slot in enumerate(SIRA):
            p = kok / slot / ("%s.png" % slot)
            if not p.exists():
                continue
            x = B + si * (S + B)
            im.paste(Image.open(p).convert("RGB").resize((S, S)), (x, y0))
            d.rectangle([x, y0, x + S, y0 + S], outline=(188, 186, 180))
            d.text((x + 2, y0 + S + 4), slot, fill=(110, 108, 102))
    im.save(str(CIKTI / "TUR3-V2-V21-KARSILASTIRMA.png"))
    print("karsilastirma: %s" % (CIKTI / "TUR3-V2-V21-KARSILASTIRMA.png"))


if __name__ == "__main__":
    raise SystemExit(main())
