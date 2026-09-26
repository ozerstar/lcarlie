#!/usr/bin/env python3
"""TUR 2 orkestrasyonu -- secilen bes creative direction render edilir.

Altyapi degismedi: ayni siniflandirici, ayni analiz, ayni render
motoru, ayni kapilar. Degisen tek sey CREATIVE DIRECTION.
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
from jarvis import katalog_konsept2 as k2          # noqa: E402
from jarvis import katalog_render as rd            # noqa: E402
from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402
from jarvis import katalog_varlik as vr            # noqa: E402

GORSEL = pathlib.Path("/opt/lcarlie/pilot-assets")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-pilot-v2")

# Kapak bantlari: uc ayri malzeme dunyasi -- tek kategori degil
KAPAK_BANTLARI = [
    ("kinesis-b56d0560c0.png", "JEL · VÜCUT"),
    ("femisia-for-women-c35cd72cf2.png", "BOTANİK · HASSAS BÖLGE"),
    ("babysol-396011a519.png", "SU · GÜNEŞ"),
]

HYDRAVIE_TABLO = [
    ("Niacinamide", "cildin görünümünü düzgünleştirmeye yardımcı olur"),
    ("Panthenol", "nem tutma hissini destekler"),
    ("Sodium Hyaluronate", "yüzeyde nem dengesinin korunmasına katkı sağlar"),
    ("Squalane", "yumuşaklık hissi bırakır, hızla yayılır"),
    ("Bakuchiol", "bitkisel kaynaklı bakım bileşeni"),
]

ICERIK = {
    "hydravie": dict(
        foto="hydravie-707e5d0af2.png",
        ad="HYDRAVIE", alt_ad="Yoğun Nemlendirici Yüz Kremi",
        ust_etiket="", manset="",
        govde="Kuru ve hassas ciltlerin günlük bakımına yönelik "
              "geliştirilmiş yoğun nemlendirici yüz kremidir.",
        hacim="50 ml", inci="", uyari="", mikro=""),
    "kinesis": dict(
        foto="kinesis-b56d0560c0.png",
        ad="KINESIS +", alt_ad="Sporcu Bakım Kremi",
        ust_etiket="", manset="",
        govde="", hacim="150 ml", inci="", uyari="",
        mikro="Susam, avokado, hodan, tamanu ve kantaron yağları içeren "
              "formül; masajla birlikte uygulanır."),
    "femisia": dict(
        foto="femisia-for-women-c35cd72cf2.png",
        ad="FEMISIA for WOMEN", alt_ad="Bitkisel İntim Bakım Kremi",
        ust_etiket="",
        manset="Bakım, gösterilmesi gereken bir şey değildir.",
        govde="Hindistan cevizi yağı ve aloe vera tabanlı kozmetik bakım "
              "kremidir. Hassas bölgede nem ve yumuşaklık hissi bırakır; "
              "hafif yapılıdır, hızla emilir.",
        hacim="50 ml",
        inci="INCI – Aqua – Cocos Nucifera Oil – Aloe Barbadensis Leaf "
             "Juice – Butyrospermum Parkii Butter – Borago Officinalis "
             "Seed Oil – L-Arginine",
        uyari="", mikro=""),
    "babysol": dict(
        foto="babysol-396011a519.png",
        ad="BABYSOL", alt_ad="Bebek Güneş Bakım Kremi · non-nano çinko oksit",
        ust_etiket="", manset="", govde="", hacim="150 ml", inci="",
        uyari="Güneşe uzun süre maruz kalmak ciddi risk oluşturur. "
              "6 aydan küçük bebeklerde doktor önerisi ile kullanınız.",
        mikro=""),
}


def _icerik(slug: str) -> kk.Icerik:
    d = ICERIK[slug]
    foto = GORSEL / d["foto"]
    a = fa.analiz(foto).sozluk()
    return kk.Icerik(
        slug=slug, ad=d["ad"], alt_ad=d["alt_ad"],
        ust_etiket=d["ust_etiket"], manset=d["manset"], govde=d["govde"],
        hacim=d["hacim"], inci=d["inci"], uyari=d["uyari"],
        mikro=d.get("mikro", ""), kaynak_foto=str(foto), analiz=a), a


def _kapilar(plan, g, pdf_yolu, onceki_imzalar):
    qa = tqa.kapi(pdf_yolu, tasma_mm=ts.TASMA_MM, guvenli_mm=ts.GUVENLI_MM)
    kontrast = rd.metin_kontrast_denetimi(plan, g)
    olc = so.sayfa_olcumleri(pdf_yolu)[0]
    itiraz = []
    if olc.bosluk_orani > 0.66 and olc.ogeler < 9:
        itiraz.append({"kusur_tipi": "olu_bosluk", "agirlik": "YUKSEK",
                       "neden": "bosluk %.2f, oge %d"
                                % (olc.bosluk_orani, olc.ogeler)})
    if olc.duzen_imzasi in onceki_imzalar:
        itiraz.append({"kusur_tipi": "tekrar", "agirlik": "YUKSEK",
                       "neden": "duzen imzasi katalogda zaten var"})
    if kontrast:
        itiraz.append({"kusur_tipi": "zayif_hiyerarsi", "agirlik": "YUKSEK",
                       "neden": "%d metin blogu okunmuyor" % len(kontrast),
                       "kontrast_ihlalleri": kontrast})
    return qa, itiraz, olc


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    sonuc = []
    imzalar: list[str] = []

    isler = []

    # 1 · KAPAK
    bantlar = []
    for dosya, etiket in KAPAK_BANTLARI:
        p = GORSEL / dosya
        bantlar.append((str(p), fa.analiz(p).sozluk(), etiket))
    kapak_ic, kapak_a = _icerik("kinesis")   # icerik kullanilmiyor, analiz zemin icin
    isler.append(("cover", "kinesis",
                  lambda ic, pal: k2.kapak_malzeme_indeksi(ic, pal, bantlar),
                  bantlar[0][1]))

    # 2-5
    isler.append(("hydravie", "hydravie",
                  lambda ic, pal: k2.hydravie_numune_foyu(ic, pal,
                                                          HYDRAVIE_TABLO), None))
    isler.append(("kinesis", "kinesis", k2.kinesis_fotograf_grid, None))
    isler.append(("private-care", "femisia", k2.femisia_surekli_yuzey, None))
    isler.append(("daily-care", "babysol", k2.babysol_isik_alani, None))

    for klasor, slug, uretici, zemin_analiz in isler:
        ic, a = _icerik(slug)
        sinif = vr.siniflandir(pathlib.Path(ic.kaynak_foto))
        palet = ts.sayfa_paleti(a)
        plan = uretici(ic, palet)
        zemin = zemin_analiz or a

        hedef = CIKTI / klasor
        hedef.mkdir(parents=True, exist_ok=True)
        g = rd.goruntu_katmani(plan, zemin)
        pdf_yolu = hedef / ("%s.pdf" % klasor)
        rd.pdf_uret(plan, g, pdf_yolu)

        qa, itiraz, olc = _kapilar(plan, g, pdf_yolu, imzalar)
        imzalar.append(olc.duzen_imzasi)
        yuksek = [i for i in itiraz if i["agirlik"] == "YUKSEK"]

        import pymupdf
        d = pymupdf.open(str(pdf_yolu))
        d[0].get_pixmap(dpi=300).save(str(hedef / ("%s.png" % klasor)))
        d.close()

        koken = bt.Koken(varlik=slug,
                         kaynak_ozeti=bt.dosya_ozeti(ic.kaynak_foto))
        koken.ekle("native_crop", "katalog_render.kirp_native", "2026-09-26",
                   bt.dosya_ozeti(ic.kaynak_foto), "-", "yukari ornekleme yok")
        koken.ekle("page_placement", "katalog_render.goruntu_katmani",
                   "2026-09-26", "-", "-",
                   "urun pikseli uretken modelden GECMEDI")
        bt.koken_yaz(koken, hedef / "koken.json")

        kayit = {
            "klasor": klasor, "slug": slug, "konsept": plan.konsept,
            "varlik_sinifi": sinif.asset_type,
            "olcumler": plan.olcumler,
            "tipografi_qa": {"gecti": qa["gecti"],
                             "durduran": qa["durduran_ihlal"],
                             "uyari": qa["uyari"],
                             "tip_dagilimi": qa["tip_dagilimi"]},
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
        print("%-13s %-20s QA=%s kontrast=%d punto=%.0f bosluk=%.2f -> %s"
              % (klasor, plan.konsept, qa["gecti"], kayit["kontrast_ihlali"],
                 olc.en_buyuk_punto, olc.bosluk_orani, kayit["sonuc"]))
        for i in itiraz:
            print("     ITIRAZ %s %s: %s" % (i["agirlik"], i["kusur_tipi"],
                                             i["neden"][:70]))

    (CIKTI / "pilot2-kayit.json").write_text(
        json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
