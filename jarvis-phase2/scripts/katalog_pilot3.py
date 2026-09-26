#!/usr/bin/env python3
"""TUR 3 orkestrasyonu -- katalog DIZISI olarak bes pilot + ticari katman.

Altyapi degismedi. Kapilar ayni. Eklenen tek denetim: SEQUENCE
RHYTHM -- bes sayfa birlikte olculur, tek tek degil.
"""
from __future__ import annotations

import json
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_butunluk as bt          # noqa: E402
from jarvis import katalog_foto_analiz as fa       # noqa: E402
from jarvis import katalog_konsept as kk           # noqa: E402
from jarvis import katalog_konsept3 as k3          # noqa: E402
from jarvis import katalog_render as rd            # noqa: E402
from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402
from jarvis import katalog_varlik as vr            # noqa: E402

CEKIM = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-ham")
PILOT = pathlib.Path("/opt/lcarlie/pilot-assets")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v3")

# --- aset secimleri (Creative Asset Library'den, board'lara bakarak) ------
A_HYDRAVIE = str(CEKIM / "ham--DSC04301.jpg")     # kutu, genis, neg 0.94
A_KINESIS = str(PILOT / "kinesis-4f9e28543c.png")  # KOYU salon + insan
A_FEMISIA = str(CEKIM / "ham--DSC04316.jpg")      # FEMISIA + VIREON birlikte
A_BABYSOL = str(CEKIM / "ham--DSC04498.jpg")      # sari kutu, mavi fon
# odak_x = o karedeki urun kutusunun olculen yatay merkezi
A_KAPAK = [(str(CEKIM / "ham--DSC04498.jpg"), "BEBEK VE ÇOCUK · GÜNEŞ", 0.39),
           (str(CEKIM / "ham--DSC04316.jpg"), "HASSAS BÖLGE · KADIN VE ERKEK", 0.38),
           (str(CEKIM / "ham--DSC04520.jpg"), "SPOR VE MASAJ", 0.33)]

HYDRAVIE_TABLO = [
    ("Niacinamide", "cildin görünümünü düzgünleştirmeye yardımcı olur"),
    ("Panthenol", "nem tutma hissini destekler"),
    ("Sodium Hyaluronate", "yüzeyde nem dengesinin korunmasına katkı sağlar"),
    ("Squalane", "yumuşaklık hissi bırakır, hızla yayılır"),
    ("Bakuchiol", "bitkisel kaynaklı bakım bileşeni"),
]

VIREON = dict(
    ad="VIREON", alt_ad="for MEN · ERKEK BAKIM KREMİ",
    govde="Erkeklere özel geliştirilmiş bitkisel bakım kremidir. "
          "Hassas bölgede nem ve ferahlık hissi bırakır; hafif yapılıdır.")

ICERIK = {
    "hydravie": dict(
        foto=A_HYDRAVIE, ad="HYDRAVIE",
        alt_ad="Yoğun Nemlendirici Yüz Kremi",
        ust_etiket="", manset="",
        govde="Kuru ve hassas ciltlerin günlük bakımına yönelik "
              "geliştirilmiş yoğun nemlendirici yüz kremidir.",
        hacim="50 ml", inci="", uyari="", mikro=""),
    "kinesis": dict(
        foto=A_KINESIS, ad="KINESIS +", alt_ad="SPORCU BAKIM KREMİ",
        ust_etiket="", manset="", govde="", hacim="150 ml", inci="", uyari="",
        mikro="Susam, avokado, hodan, tamanu ve kantaron yağları içeren "
              "formül; masajla birlikte uygulanır."),
    "femisia": dict(
        foto=A_FEMISIA, ad="FEMISIA", alt_ad="for WOMEN · İNTİM BAKIM KREMİ",
        ust_etiket="", manset="",
        govde="Hindistan cevizi yağı ve aloe vera tabanlı kozmetik bakım "
              "kremidir. Hassas bölgede nem ve yumuşaklık hissi bırakır.",
        hacim="50 ml",
        inci="INCI – Aqua – Cocos Nucifera Oil – Aloe Barbadensis Leaf "
             "Juice – Butyrospermum Parkii Butter – Borago Officinalis "
             "Seed Oil – L-Arginine",
        uyari="", mikro=""),
    "babysol": dict(
        foto=A_BABYSOL, ad="BABYSOL",
        alt_ad="BEBEK GÜNEŞ BAKIM KREMİ · NON-NANO ÇİNKO OKSİT",
        ust_etiket="", manset="", govde="", hacim="150 ml", inci="",
        uyari="Güneşe uzun süre maruz kalmak ciddi risk oluşturur. "
              "6 aydan küçük bebeklerde doktor önerisi ile kullanınız.",
        mikro=""),
}

SKU = [
    dict(ad="HYDRAVIE", sku="8684869609233", hacim="50 ml",
         kod="LC-HYD-050", fiyat="—"),
    dict(ad="KINESIS +", sku="8684869609547", hacim="150 ml",
         kod="LC-KIN-150", fiyat="—"),
    dict(ad="FEMISIA for WOMEN", sku="8684869609127", hacim="50 ml",
         kod="LC-FEM-050", fiyat="—"),
    dict(ad="VIREON for MEN", sku="8684869609110", hacim="50 ml",
         kod="LC-VIR-050", fiyat="—"),
    dict(ad="BABYSOL", sku="8684869609530", hacim="150 ml",
         kod="LC-BAB-150", fiyat="—"),
]


def _icerik(slug: str):
    d = ICERIK[slug]
    a = fa.analiz(pathlib.Path(d["foto"])).sozluk()
    return kk.Icerik(
        slug=slug, ad=d["ad"], alt_ad=d["alt_ad"],
        ust_etiket=d["ust_etiket"], manset=d["manset"], govde=d["govde"],
        hacim=d["hacim"], inci=d["inci"], uyari=d["uyari"],
        mikro=d.get("mikro", ""), kaynak_foto=d["foto"], analiz=a), a


def _kapilar(plan, g, pdf_yolu, onceki):
    qa = tqa.kapi(pdf_yolu, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
    kontrast = rd.metin_kontrast_denetimi(plan, g)
    olc = so.sayfa_olcumleri(pdf_yolu)[0]
    itiraz = []
    if olc.bosluk_orani > 0.66 and olc.ogeler < 9:
        itiraz.append({"kusur_tipi": "olu_bosluk", "agirlik": "YUKSEK",
                       "neden": "bosluk %.2f, oge %d"
                                % (olc.bosluk_orani, olc.ogeler)})
    if olc.duzen_imzasi in onceki:
        itiraz.append({"kusur_tipi": "tekrar", "agirlik": "YUKSEK",
                       "neden": "duzen imzasi katalogda zaten var"})
    if kontrast:
        itiraz.append({"kusur_tipi": "zayif_hiyerarsi", "agirlik": "YUKSEK",
                       "neden": "%d metin blogu okunmuyor" % len(kontrast),
                       "kontrast_ihlalleri": kontrast})
    return qa, itiraz, olc


def dizi_ritmi(kayit: list[dict]) -> dict:
    """SEQUENCE ART DIRECTION -- bes sayfa BIRLIKTE olculur.

    Tur 2'nin kusuru sayfa kapilariyla yakalanamadi: bes sayfanin
    dordu ayni sicak krem zemin ailesine dusmustu. Burada zemin
    ailesi, isik, yogunluk ve olcek ritmi dizi duzeyinde denetlenir.
    """
    def aile(k):
        """OLCULDU: baskin renk yaniltiyor. KINESIS sayfasi gorsel olarak
        dizinin tek KOYU sayfasi ama baskin rengi spor salonu zemininin
        kahverengisi (L=107) -- 'koyu' esigini gecemiyordu. Dizi ritmi
        sayfanin ORTALAMA parlakligindan okunur."""
        L = k["ortalama_L"]
        if L < 128:
            return "koyu"
        r, g, b = k["zemin_rgb"]
        if b > r + 8:
            return "soguk"
        if r > b + 14:
            return "sicak"
        return "notr"

    aileler = [aile(k) for k in kayit]
    puntolar = [k["sayfa_olcumu"]["en_buyuk_punto"] for k in kayit]
    yogunluk = [k["sayfa_olcumu"]["metin"] for k in kayit]
    koyu = [a == "koyu" for a in aileler]
    insan = [bool(k["olcumler"].get("dizi", {}).get("insan")) for k in kayit]

    bulgu = []
    from collections import Counter
    c = Counter(aileler)
    en_cok, adet = c.most_common(1)[0]
    if adet > len(kayit) * 0.6:
        bulgu.append({"kusur_tipi": "tek_malzeme_dunyasi", "agirlik": "YUKSEK",
                      "neden": "%d/%d sayfa '%s' zemin ailesinde"
                               % (adet, len(kayit), en_cok)})
    if not any(koyu):
        bulgu.append({"kusur_tipi": "isik_ritmi_yok", "agirlik": "ORTA",
                      "neden": "dizide hic koyu sayfa yok"})
    if max(puntolar) / max(1e-6, min(puntolar)) < 1.5:
        bulgu.append({"kusur_tipi": "olcek_ritmi_dar", "agirlik": "ORTA",
                      "neden": "en buyuk/en kucuk punto orani %.2f"
                               % (max(puntolar) / min(puntolar))})
    if max(yogunluk) / max(1e-6, min(yogunluk)) < 2.0:
        bulgu.append({"kusur_tipi": "yogunluk_ritmi_dar", "agirlik": "ORTA",
                      "neden": "metin orani araligi dar"})
    return {"zemin_aileleri": aileler, "aile_dagilimi": dict(c),
            "koyu_sayfa": sum(koyu), "insan_sayfa": sum(insan),
            "punto_araligi": [min(puntolar), max(puntolar)],
            "yogunluk_araligi": [round(min(yogunluk), 4),
                                 round(max(yogunluk), 4)],
            "bulgular": bulgu}


def _zemin_rgb(pdf_yolu) -> tuple:
    import collections
    import io

    import pymupdf
    from PIL import Image
    d = pymupdf.open(str(pdf_yolu))
    px = d[0].get_pixmap(dpi=40)
    im = Image.open(io.BytesIO(px.tobytes("png"))).convert("RGB")
    d.close()
    q = im.quantize(colors=4).convert("RGB")
    baskin = collections.Counter(q.getdata()).most_common(1)[0][0]
    g = im.convert("L")
    ort = sum(g.getdata()) / (g.width * g.height)
    return baskin, round(ort, 1)


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    sonuc = []
    imzalar: list[str] = []

    isler = [
        ("cover", "babysol",
         lambda ic, pal: k3.kapak_uc_urun(ic, pal, A_KAPAK)),
        ("hydravie", "hydravie",
         lambda ic, pal: k3.hydravie_numune_foyu(ic, pal, HYDRAVIE_TABLO)),
        ("kinesis", "kinesis", k3.kinesis_salon),
        ("private-care", "femisia",
         lambda ic, pal: k3.femisia_cift(ic, pal, VIREON)),
        ("daily-care", "babysol", k3.babysol_alt_bant),
    ]

    for klasor, slug, uretici in isler:
        ic, a = _icerik(slug)
        sinif = vr.siniflandir(pathlib.Path(ic.kaynak_foto))
        palet = ts.sayfa_paleti(a)
        plan = uretici(ic, palet)

        hedef = CIKTI / klasor
        hedef.mkdir(parents=True, exist_ok=True)
        g = rd.goruntu_katmani(plan, a)
        pdf_yolu = hedef / ("%s.pdf" % klasor)
        rd.pdf_uret(plan, g, pdf_yolu)

        qa, itiraz, olc = _kapilar(plan, g, pdf_yolu, imzalar)
        imzalar.append(olc.duzen_imzasi)
        yuksek = [i for i in itiraz if i["agirlik"] == "YUKSEK"]

        import pymupdf
        d = pymupdf.open(str(pdf_yolu))
        d[0].get_pixmap(dpi=300).save(str(hedef / ("%s.png" % klasor)))
        d.close()

        _zr = _zemin_rgb(pdf_yolu)
        koken = bt.Koken(varlik=slug,
                         kaynak_ozeti=bt.dosya_ozeti(ic.kaynak_foto))
        koken.ekle("native_crop", "katalog_konsept3.kadraj", "2026-09-26",
                   bt.dosya_ozeti(ic.kaynak_foto), "-", "yukari ornekleme yok")
        koken.ekle("page_placement", "katalog_render.goruntu_katmani",
                   "2026-09-26", "-", "-",
                   "urun pikseli uretken modelden GECMEDI")
        bt.koken_yaz(koken, hedef / "koken.json")

        kayit = {
            "klasor": klasor, "slug": slug, "konsept": plan.konsept,
            "varlik_sinifi": sinif.asset_type,
            "kaynak_aset": ic.kaynak_foto,
            "olcumler": plan.olcumler,
            "zemin_rgb": list(_zr[0]), "ortalama_L": _zr[1],
            "tipografi_qa": {"gecti": qa["gecti"],
                             "durduran": qa["durduran_ihlal"],
                             "uyari": qa["uyari"]},
            "kontrast_ihlali": sum(1 for i in itiraz
                                   if "kontrast_ihlalleri" in i),
            "elestirmen": itiraz,
            "sayfa_olcumu": {
                "gorsel": olc.gorsel_alan_orani, "cizim": olc.cizim_alan_orani,
                "metin": olc.metin_alan_orani, "bosluk": olc.bosluk_orani,
                "oge": olc.ogeler, "en_buyuk_punto": olc.en_buyuk_punto,
                "yogunluk": olc.yogunluk},
            "sonuc": "KABUL" if (qa["gecti"] and not yuksek) else "REVISE",
        }
        sonuc.append(kayit)
        print("%-13s %-18s QA=%-5s kontrast=%d punto=%4.1f bosluk=%.2f "
              "dpi=%3.0f -> %s"
              % (klasor, plan.konsept, qa["gecti"], kayit["kontrast_ihlali"],
                 olc.en_buyuk_punto, olc.bosluk_orani,
                 plan.olcumler.get("urun_dpi", 0), kayit["sonuc"]))
        for i in itiraz:
            print("     ITIRAZ %s %s: %s"
                  % (i["agirlik"], i["kusur_tipi"], i["neden"][:70]))

    # --- ticari katman (editoryal sayfalardan AYRI) ---
    plan = k3.sku_indeksi(SKU)
    hedef = CIKTI / "sku-index"
    hedef.mkdir(parents=True, exist_ok=True)
    bos = {"zemin": {"ust_rgb": (247, 246, 243), "alt_rgb": (247, 246, 243),
                     "sol_rgb": (247, 246, 243), "sag_rgb": (247, 246, 243)}}
    g = rd.goruntu_katmani(plan, bos)
    pdf_yolu = hedef / "sku-index.pdf"
    rd.pdf_uret(plan, g, pdf_yolu)
    qa = tqa.kapi(pdf_yolu, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
    import pymupdf
    d = pymupdf.open(str(pdf_yolu))
    d[0].get_pixmap(dpi=300).save(str(hedef / "sku-index.png"))
    d.close()
    print("%-13s %-18s QA=%-5s durduran=%d -> TICARI KATMAN"
          % ("sku-index", plan.konsept, qa["gecti"], qa["durduran_ihlal"]))

    ritim = dizi_ritmi(sonuc)
    print("\n=== DIZI RITMI ===")
    print("zemin aileleri : %s" % " -> ".join(ritim["zemin_aileleri"]))
    print("ortalama L     : %s" % [k["ortalama_L"] for k in sonuc])
    print("dagilim        : %s" % ritim["aile_dagilimi"])
    print("koyu sayfa     : %d / %d" % (ritim["koyu_sayfa"], len(sonuc)))
    print("insan sayfa    : %d / %d" % (ritim["insan_sayfa"], len(sonuc)))
    print("punto araligi  : %s" % ritim["punto_araligi"])
    print("yogunluk       : %s" % ritim["yogunluk_araligi"])
    for b in ritim["bulgular"]:
        print("  DIZI ITIRAZI %s %s: %s"
              % (b["agirlik"], b["kusur_tipi"], b["neden"]))
    if not ritim["bulgular"]:
        print("  dizi itirazi YOK")

    (CIKTI / "pilot3-kayit.json").write_text(
        json.dumps({"sayfalar": sonuc, "dizi_ritmi": ritim, "sku": SKU},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
