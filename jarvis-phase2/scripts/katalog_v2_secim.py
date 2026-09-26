#!/usr/bin/env python3
"""V2 SECIM ZINCIRI: 25 -> 10 finalist -> critic -> 5 kazanan -> 5 final.

G maddesi: MAKER != JUDGE. ECD eleme yapar (kendi tasarimini uretmez),
Independent Critic CRAFT ve CONCEPT icin AYRI hukum verir ve cozum
onermez, AD + Editorial Director kazananlari secer.
"""
from __future__ import annotations

import collections
import io
import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-v2")
TUR2 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v2")
TUR3 = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")

# --- ECD: 25 -> 10 (katalog dizisi acisindan) ---------------------------
ECD_ELEME = {
    "V-C1": ("FINALIST", "Fotografsiz tipografik indeks; kapakta hic "
                         "denenmemis bir davranis ve marka genisligini "
                         "dogrudan soyluyor."),
    "V-C2": ("ELENDI", "Makro kadrajda baska bir urunun logotype'i yan "
                       "yatmis okunuyor -- kapakta kaza gibi duruyor. "
                       "Ayrica makro sprey ucu jenerik."),
    "V-C3": ("FINALIST", "36 sayisi markanin OLCULEN farkidir (rakip 3-8 "
                         "urun). Kapak bir iddiayi tasiyor, estetik "
                         "alistirma degil."),
    "V-C4": ("ELENDI", "Kunye fikri durust ama sayfa gorsel olarak ince: "
                       "orta-sag genis alan islev tasimiyor -- DEAD "
                       "whitespace suphesi."),
    "V-C5": ("ELENDI", "TUR 3 KOPYASI RISKI: uc dikey pano, kesime kadar "
                       "bant, altta kategori etiketi -- tur 3 kapaginin "
                       "yapisi. Brief tur 3 duzenini kopyalamayi yasakliyor."),

    "V-H1": ("ELENDI", "Soluk mavi kutu soluk mavi zeminde kayboluyor; "
                       "urun sayfada zor secilir. Fikir iyi, aset yanlis."),
    "V-H2": ("FINALIST", "Kutu metnindeki 'sabah ve aksam' gercek ritmi "
                         "sayfa yapisina cevriliyor; iki kare tek urunun "
                         "iki zamanini kuruyor."),
    "V-H3": ("FINALIST", "Bilesen merdiveni katalogda hic olmayan bir "
                         "hiyerarsi getiriyor: TR adi + INCI adi, kahraman "
                         "bilesen en ustte. SIGNATURE adayi."),
    "V-H4": ("ELENDI", "Tam genislik foto bandi + alt metin -- tur 3'un "
                       "FEMISIA ve BABYSOL sayfalarinin yapisi."),
    "V-H5": ("ELENDI", "HYDRAVIE'nin elinde tanim, kullanim ve uyari VAR; "
                       "bu kadar bos bir sayfa mevcut bilgiyi ziyan ediyor. "
                       "REMOVE TEST tersine calisiyor: bilgi kaybi var."),

    "V-K1": ("FINALIST", "Bu urunun onayli TEK metni kullanim talimatidir. "
                         "Sayfa bunu gizlemek yerine kahraman yapiyor -- "
                         "eksik veriye durust cevap."),
    "V-K2": ("FINALIST", "Siki kadraj, koyu alan, tek insan karesi. "
                         "Dizinin isik omurgasi olabilecek tek aday."),
    "V-K3": ("ELENDI", "Sayi guclu ama K1 ile AYNI icerigi (kullanim) "
                       "kullaniyor ve K1 daha iyi tasiyor. "
                       "DUPLICATE_CONTENT."),
    "V-K4": ("ELENDI", "Iki kare yan yana ama ikisi de ayni urun dizilimi; "
                       "'iki kez' fikri gorsel olarak kurulmuyor."),
    "V-K5": ("ELENDI", "Ust foto bandi + koyu alt alan -- tur 3 BABYSOL "
                       "sayfasinin yapisi."),

    "V-F1": ("FINALIST", "Epimedium ve L-Arginin HER IKI formulde de var -- "
                         "olculen gercek. Sayfa ayrimi degil ORTAKLIGI "
                         "omurga yapiyor. Setin en ozgun fikri."),
    "V-F2": ("FINALIST", "Tam INCI 7 punto ve 10.2 pt satir araligiyla "
                         "tasarlanmis bir bilgi bolgesi; ne dipnot ne hero. "
                         "Q maddesinin karsiligi."),
    "V-F3": ("ELENDI", "TUR 3 KOPYASI: tam genislik bandi + altinda iki "
                       "kolon. Tur 3 FEMISIA sayfasinin birebir yapisi."),
    "V-F4": ("ELENDI", "Cok guzel ama FEMISIA'nin elinde tam INCI, tanim, "
                       "kullanim ve uyari VAR. Bu sayfa onlarin hicbirini "
                       "tasimiyor -- bilgi kaybi."),
    "V-F5": ("ELENDI", "Guclu; ancak F1 ile AYNI repertuari "
                       "(INGREDIENT_NOMENCLATURE) kullaniyor ve F1'in fikri "
                       "daha ozgun. Ayni urunde iki ayni kip alinmaz."),

    "V-B1": ("FINALIST", "%30 non-nano cinko oksit kutu metninin kendi "
                         "verisi. Iddia degil oran gosteriliyor."),
    "V-B2": ("FINALIST", "Zorunlu uyari sayfanin baskin tipografik ogesi. "
                         "Mevzuati yuk degil konu yapan tek sayfa."),
    "V-B3": ("ELENDI", "Iyi ama B1 ile ayni NUMBER_DRIVEN kipi; B1'in "
                       "sayisi (formul orani) daha esasli."),
    "V-B4": ("ELENDI", "Iki katman ayni kareden alinmis gibi okunuyor; "
                       "'filtre' fikri gorsel olarak kurulmuyor."),
    "V-B5": ("ELENDI", "BABYSOL'un zorunlu uyarisi uzun ve kritik; bu kadar "
                       "bos bir sayfa onu mikro metne itiyor."),
}

# --- C13 Independent Critic: 10 finalist, CRAFT ve CONCEPT AYRI ---------
# Critic tasarim cozumu URETMEZ; yalnizca hukum ve gerekce verir.
CRITIC = {
    "V-C1": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "Dokuz satir esit araliklandirilmis, numaralar "
                          "sag hizali, cizgiler ince ve tutarli.",
             "concept_not": "Indeks bir iddiadir: marka genisligi. "
                            "Fotografsizlik kasitli ve tutarli."},
    "V-C3": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "Sayi ile urun karesi arasindaki bosluk olcegi "
                          "kuruyor; 96 punto sayi 20 punto marka adiyla "
                          "catismiyor.",
             "concept_not": "Sayi olculmus bir gercek; dekoratif degil."},
    "V-H2": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "Iki kare esit, aralarindaki oluk sayfa "
                          "ortasinda; alt metin iki kolona bolunmus.",
             "concept_not": "Ritim kutu metninden geliyor, tasarimciyi "
                            "degil urunu takip ediyor."},
    "V-H3": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "Merdiven girintisi 6 mm sabit; punto 10.5'ten "
                          "8.5'e dusuyor -- hiyerarsi olculebilir.",
             "concept_not": "Bilesen hiyerarsisi katalogda ilk kez "
                            "goruluyor; SIGNATURE adayi."},
    "V-K1": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "13 punto talimat, 18 pt satir araligi; okuma "
                          "yavaslatilmis.",
             "concept_not": "Eksik veriye durust cevap: uydurmak yerine "
                            "var olani buyutmek."},
    "V-K2": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "128 mm kare koyu alanda yuzuyor; ters tipografi "
                          "koyu zeminde, kontrast ihlali 0.",
             "concept_not": "Caba ani sikistirilmis; tur 3'un genis salon "
                            "planinin tersi."},
    "V-F1": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "Ortak bilesenler 14 punto, urun adlari 11 "
                          "punto -- hiyerarsi ters cevrilmis ve bu kasitli.",
             "concept_not": "Olculen gercege dayanan tek fikir: iki "
                            "formulun paylastigi cekirdek."},
    "V-F2": {"CRAFT": "REVISE", "CONCEPT": "PASS",
             "craft_not": "13 satirlik INCI blogu sayfanin sol yarisini "
                          "dolduruyor; sag alt kose gorece bos kaliyor. "
                          "Bosluk ACTIVE savunulabilir ama sinirda.",
             "concept_not": "INCI'yi ne dipnot ne hero yapmak Q maddesinin "
                            "tam karsiligi."},
    "V-B1": {"CRAFT": "PASS", "CONCEPT": "PASS",
             "craft_not": "%30 ile urun karesi arasinda gerilim var; "
                          "zorunlu uyari alt solda 6 satir.",
             "concept_not": "Oran iddiadan gucludur."},
    "V-B2": {"CRAFT": "REVISE", "CONCEPT": "PASS",
             "craft_not": "Uyari blogu 11 satir; sayfanin sol yarisi metin "
                          "duvari. Okunur ama nefes az.",
             "concept_not": "Mevzuati konu yapmak cesur ve dogru."},
}

# --- C07 Art Director + C04 Editorial Director: 10 -> 5 -----------------
# Secim tek sayfa kalitesiyle DEGIL katalog dizisiyle yapildi.
KAZANAN = {
    "cover": ("V-C3", "Dizinin acilisi bir IDDIA olmali. 36 sayisi markanin "
                      "olculen farki; C1 daha sessiz ve ikinci sayfanin "
                      "(H3) yogunluguyla catisiyor."),
    "hydravie": ("V-H3", "Dizinin yogunluk tepesi burada olmali. H2 guzel "
                         "ama QUIET_EDITORIAL kipi K2 ile ayni sessizlik "
                         "bolgesine dusuyor; H3 bilimsel kipi getiriyor."),
    "kinesis": ("V-K2", "Dizinin ISIK OMURGASI: tek koyu sayfa, tek insan "
                        "karesi, en dusuk yogunluk. K1 guclu ama dizide "
                        "ucuncu sirada bir NEFES gerekiyor, metin duvari "
                        "degil."),
    # OLCULDU (ilk secimden sonra): 10 finalistin 9'u 'notr' zemin
    # ailesinde -- studyo arsivinin tamami ayni mavi-gri fonda. Ilk
    # secim (C3/H3/K2/F1/B1) dizi denetiminden YUKSEK itiraz aldi:
    # 4/5 sayfa notr + repertuar tekrari (NUMBER x2, INGREDIENT x2).
    # Secim ritim kisitiyla YENILENDI; F2 ve B2 critic'in CRAFT REVISE
    # gerekcesi giderilerek alindi.
    "private-care": ("V-F2", "F1 ile H3 AYNI repertuari kullaniyordu "
                             "(INGREDIENT_NOMENCLATURE). F2 "
                             "TECHNICAL_TYPOGRAPHY getiriyor ve zemini "
                             "ambalaj malzemesinden turetilerek dizinin "
                             "tek SICAK sayfasi oluyor. Critic'in craft "
                             "itirazi (sag alt kose bos) giderildi."),
    "daily-care": ("V-B2", "B1 ile C3 AYNI repertuari kullaniyordu "
                           "(NUMBER_DRIVEN). B2 MONUMENTAL_DISPLAY "
                           "getiriyor, zorunlu uyariyi konu yapiyor ve "
                           "zemini fotografin fonundan surdurerek dizinin "
                           "ikinci SOGUK sayfasi oluyor. Critic'in craft "
                           "itirazi (nefes az) satir araligi acilarak "
                           "giderildi."),
}

SIRA = ["cover", "hydravie", "kinesis", "private-care", "daily-care"]


def _aile(L: float, rgb) -> str:
    if L < 128:
        return "koyu"
    r, g, b = rgb
    if b > r + 8:
        return "soguk"
    if r > b + 14:
        return "sicak"
    return "notr"


def _sayfa_olc(pdf: pathlib.Path):
    import pymupdf
    from PIL import Image
    d = pymupdf.open(str(pdf))
    px = d[0].get_pixmap(dpi=40)
    im = Image.open(io.BytesIO(px.tobytes("png"))).convert("RGB")
    d.close()
    q = im.quantize(colors=4).convert("RGB")
    baskin = collections.Counter(q.getdata()).most_common(1)[0][0]
    g = im.convert("L")
    return baskin, round(sum(g.getdata()) / (g.width * g.height), 1)


def kontakt(basliklar, pdfler, yol, baslik, sutun=5, S=330):
    import pymupdf
    from PIL import Image, ImageDraw
    n = len(pdfler)
    r = (n + sutun - 1) // sutun
    ET, B = 40, 9
    im = Image.new("RGB", (sutun * S + (sutun + 1) * B,
                           r * (S + ET) + (r + 1) * B + 26), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((B, 8), baslik, fill=(0, 0, 0))
    for i, p in enumerate(pdfler):
        rr, cc = divmod(i, sutun)
        x = B + cc * (S + B)
        y = 26 + B + rr * (S + ET + B)
        doc = pymupdf.open(str(p))
        px = doc[0].get_pixmap(dpi=64)
        t = Image.open(io.BytesIO(px.tobytes("png"))).convert("RGB").resize((S, S))
        doc.close()
        im.paste(t, (x, y))
        d.rectangle([x, y, x + S, y + S], outline=(188, 186, 180))
        for j, s in enumerate(basliklar[i]):
            d.text((x + 2, y + S + 5 + j * 12),
                   s[:58], fill=(0, 0, 0) if j == 0 else (110, 108, 102))
    yol.parent.mkdir(parents=True, exist_ok=True)
    im.save(str(yol))
    return yol


def main() -> int:
    kay = json.loads((CIKTI / "v2-konsept-kayit.json").read_text(encoding="utf-8"))
    ind = {k["id"]: k for k in kay}

    print("=== AG · ECD ELEME: 25 -> 10 ===")
    finalist = [k for k, (d, _) in ECD_ELEME.items() if d == "FINALIST"]
    elenen = [k for k, (d, _) in ECD_ELEME.items() if d == "ELENDI"]
    print("finalist: %d  elenen: %d" % (len(finalist), len(elenen)))
    tur3_kopyasi = [k for k, (d, g) in ECD_ELEME.items() if "TUR 3 KOPYASI" in g]
    print("tur 3 kopyasi gerekcesiyle elenen: %s" % tur3_kopyasi)

    print()
    print("=== Z · INDEPENDENT CRITIC (CRAFT / CONCEPT AYRI) ===")
    for k in finalist:
        c = CRITIC[k]
        print("  %-6s CRAFT=%-7s CONCEPT=%-5s  %s"
              % (k, c["CRAFT"], c["CONCEPT"], ind[k]["ad"]))
    craft_revise = [k for k in finalist if CRITIC[k]["CRAFT"] == "REVISE"]
    print("craft REVISE alan: %s" % craft_revise)

    print()
    print("=== AG · AD + EDITORIAL DIRECTOR: 10 -> 5 ===")
    for slot in SIRA:
        kid, ger = KAZANAN[slot]
        print("  %-13s %-6s %s" % (slot, kid, ind[kid]["ad"]))

    # 10 finalist kontakt sayfasi
    fsira = ["V-C1", "V-C3", "V-H2", "V-H3", "V-K1", "V-K2", "V-F1", "V-F2",
             "V-B1", "V-B2"]
    kontakt(
        [[("%s  %s" % (k, ind[k]["ad"]))[:52],
          "CRAFT=%s  CONCEPT=%s" % (CRITIC[k]["CRAFT"], CRITIC[k]["CONCEPT"]),
          (ind[k]["repertuar"] or "")[:40]] for k in fsira],
        [CIKTI / "proofs" / ("%s.pdf" % k) for k in fsira],
        CIKTI / "V2-10-FINALIST.png",
        "L CARLIE V2 -- 10 FINALIST -- Independent Critic: CRAFT / CONCEPT ayri")
    print("10-finalist sayfasi: %s" % (CIKTI / "V2-10-FINALIST.png"))

    (CIKTI / "secim-kaydi.json").write_text(json.dumps({
        "ecd_eleme": {k: {"karar": v[0], "gerekce": v[1]}
                      for k, v in ECD_ELEME.items()},
        "critic": CRITIC,
        "kazanan": {k: {"id": v[0], "gerekce": v[1]}
                    for k, v in KAZANAN.items()},
        "tur3_kopyasi_gerekcesiyle_elenen": tur3_kopyasi,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
