#!/usr/bin/env python3
"""Creative Department orkestrasyonu -- 5 pilot sayfa uretir.

AKIS:
    1. Product Asset Classifier  -> sinif ve izin matrisi (ZORUNLU ILK KAPI)
    2. Foto analizi              -> palet, isik, kadraj, metin guvenli alan
    3. Art Director              -> 3 konsept
    4. Kanit olcumu              -> her konsept icin baskinlik/olu bosluk/...
    5. ECD secimi                -> kanitla, skorla degil
    6. Render + QA               -> tipografi, butunluk, prepress
    7. Independent Critic        -> YALNIZ render'a bakar, brief'i gormez
    8. Revizyon                  -> en fazla 3 tur
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

KOK = pathlib.Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import katalog_butunluk as bt          # noqa: E402
from jarvis import katalog_foto_analiz as fa       # noqa: E402
from jarvis import katalog_kanit as kn             # noqa: E402
from jarvis import katalog_konsept as kk           # noqa: E402
from jarvis import katalog_render as rd            # noqa: E402
from jarvis import katalog_sayfa_olcum as so       # noqa: E402
from jarvis import katalog_tasarim_sistemi as ts   # noqa: E402
from jarvis import katalog_tipografi_qa as tqa     # noqa: E402
from jarvis import katalog_varlik as vr            # noqa: E402

GORSEL = pathlib.Path("/opt/lcarlie/pilot-assets")
CIKTI = pathlib.Path("/opt/lcarlie/output/catalog-pilot")
AZAMI_TUR = 3


# --- icerik (gercek urun metninden) --------------------------------------

PILOTLAR = [
    dict(
        klasor="cover", tercih="kapak_tam_bleed", slug="cover", tur="KAPAK",
        # TYPE A editoryal: spor salonu sahnesi -- marka dunyasi
        foto="kinesis-4f9e28543c.png",
        ad="L'CARLIÉ", alt_ad="Dermokozmetik Ürün Kataloğu",
        ust_etiket="2026 · ECZANE VE KLİNİK",
        manset="Bitkisel formülasyon,\nölçülebilir bakım.",
        govde="Bu katalog saha görüşmesinde kullanılmak üzere hazırlandı. "
              "Her sayfada ürünün doğrulanmış bilgisi ve not alabileceğiniz "
              "bir alan bulunur.",
        hacim="", inci="",
        not_etiketi="GÖRÜŞME NOTU",
    ),
    dict(
        klasor="hydravie", tercih="ust_blok", slug="hydravie", tur="URUN",
        # TYPE A editoryal: laboratuvar naturmortu -- bilimsel guven
        foto="hydravie-707e5d0af2.png",
        ad="HYDRAVIE", alt_ad="Yoğun Nemlendirici Yüz Kremi",
        ust_etiket="YÜZ BAKIMI · KURU VE HASSAS CİLT",
        manset="Nem, cildin\nkonforuyla ölçülür.",
        govde="Kuru ve hassas ciltlerin günlük bakımına yönelik geliştirilmiş "
              "yoğun nemlendirici yüz kremidir. Niacinamide, Panthenol, Sodium "
              "Hyaluronate ve Squalane içeren formülü cildin nem dengesinin "
              "korunmasına yardımcı olur.",
        inci="INCI · Aqua · Niacinamide · Panthenol · Sodium Hyaluronate · "
             "Squalane · Bakuchiol",
        hacim="50 ml", not_etiketi="SAHA NOTU",
    ),
    dict(
        klasor="kinesis", tercih="kare_blok", slug="kinesis", tur="URUN",
        # TYPE A editoryal: jel dokusu -- malzeme dili
        foto="kinesis-b56d0560c0.png",
        ad="KINESIS +", alt_ad="Sporcu Bakım Kremi",
        ust_etiket="VÜCUT VE MASAJ · AKTİF YAŞAM",
        manset="Hareketten sonra\ngelen bakım.",
        govde="Spor yapanlar ve aktif yaşam süren bireylerin günlük bakım "
              "rutinine eşlik etmek üzere geliştirildi. Susam, avokado, hodan, "
              "tamanu ve kantaron yağları içeren formülü cildin daha esnek ve "
              "bakımlı görünmesine destek olur.",
        inci="INCI · Sesamum Indicum Seed Oil · Persea Gratissima Oil · Borago "
             "Officinalis Seed Oil · Calophyllum Inophyllum Seed Oil · "
             "Hypericum Perforatum Extract",
        hacim="150 ml", not_etiketi="SAHA NOTU",
    ),
    dict(
        klasor="private-care", tercih="fotografik_hakimiyet", slug="femisia", tur="URUN",
        # TYPE B packshot: siki kadraj + doygun blok. Katalog
        # editoryal sahne ile temiz packshot arasinda RITIM kurar;
        # bes sayfa bes farkli iskelet kullanir.
        foto="femisia-for-women-d22bb439da.png",
        ad="FEMISIA", alt_ad="for WOMEN · Bitkisel İntim Bakım Kremi",
        ust_etiket="HASSAS BÖLGE BAKIMI",
        manset="Hassas bölge bakımı,\nsessiz bir özen ister.",
        govde="Hindistan cevizi yağı ve aloe vera tabanlı kozmetik bakım "
              "kremidir. Hassas bölgede nem ve yumuşaklık hissi bırakır; "
              "hafif yapılıdır, hızla emilir.",
        inci="INCI · Aqua · Cocos Nucifera Oil · Aloe Barbadensis Leaf Juice · "
             "Butyrospermum Parkii Butter · Borago Officinalis Seed Oil · "
             "L-Arginine",
        hacim="50 ml", not_etiketi="SAHA NOTU",
    ),
    dict(
        klasor="daily-care", tercih="kontrollu_asimetri", slug="babysol", tur="URUN",
        # TYPE B packshot: alttan tasma iskeleti
        foto="babysol-de9823b849.png",
        ad="BABYSOL", alt_ad="Bebek Güneş Bakım Kremi · SPF 50+",
        ust_etiket="BEBEK VE ÇOCUK · GÜNLÜK BAKIM",
        manset="Fiziksel filtre,\nnazik bakım.",
        govde="Bebeklerin hassas cilt yapısı dikkate alınarak geliştirilmiş, "
              "fiziksel filtre içeren bir güneş bakım ürünüdür. Non-nano çinko "
              "oksit içeriğiyle güneş bakım rutinine eşlik eder.",
        inci="INCI · Zinc Oxide (non-nano) · Calophyllum Inophyllum Seed Oil · "
             "Butyrospermum Parkii Butter · Aloe Barbadensis Leaf Juice · "
             "Bisabolol · Ceramide NP",
        hacim="150 ml", not_etiketi="SAHA NOTU",
        uyari="Güneşe uzun süre maruz kalmak ciddi risk oluşturur. "
              "6 aydan küçük bebeklerde doktor önerisi ile kullanınız.",
    ),
]


# --- kanit olcumu (Art Director girdisi) ---------------------------------

def konsept_kaniti(plan, analiz: dict, pdf_yolu) -> dict:
    """Her konsept icin olculen kanit. SKOR URETMEZ."""
    olc = so.sayfa_olcumleri(pdf_yolu)[0]
    o = plan.olcumler
    sayfa_alan = ts.SAYFA_MM ** 2
    urun_alan = o.get("urun_en_mm", 0) * o.get("urun_boy_mm", 0)
    # sayfada gorunen kismi (tasan kisimlar sayilmaz)
    gorunur = min(1.0, urun_alan / sayfa_alan)

    return {
        "urun_yukseklik_orani": round(o.get("urun_boy_mm", 0) / ts.SAYFA_MM, 3),
        "urun_alan_orani": round(gorunur, 3),
        "urun_dpi": o.get("urun_dpi"),
        "kadraj": o.get("kadraj"),
        "bosluk_orani": olc.bosluk_orani,
        "metin_alan_orani": olc.metin_alan_orani,
        "gorsel_alan_orani": round(olc.gorsel_alan_orani + olc.cizim_alan_orani, 4),
        "oge_sayisi": olc.ogeler,
        "yogunluk": olc.yogunluk,
        "duzen_imzasi": olc.duzen_imzasi,
        "en_buyuk_punto": olc.en_buyuk_punto,
        "olcek_kontrasti": round(olc.en_buyuk_punto / 9.5, 2),
    }


def ecd_secimi(kanitlar: dict, kullanilan_iskeletler: set,
               tercih: str | None = None) -> tuple[str, str]:
    """ECD kanitla secer.

    TERCIH: Sanat yonetmeni bir iskeleti one surebilir. Bu bir atlama
    DEGILDIR -- tercih edilen iskelet de olu bosluk elemesinden ve
    tekrar kuralindan gecmek zorundadir; gecemezse kanit temelli
    secim devreye girer ve bu KAYDA GECER."""
    adaylar = list(kanitlar.items())

    # 1. Olu bosluk elemesi: bosluk yuksek + oge sayisi dusuk
    elenen = {k: "olu bosluk suphesi (bosluk %.2f, oge %d)"
                 % (v["bosluk_orani"], v["oge_sayisi"])
              for k, v in adaylar if v["bosluk_orani"] > 0.62 and v["oge_sayisi"] < 8}
    kalan = [(k, v) for k, v in adaylar if k not in elenen]
    if not kalan:
        kalan = adaylar

    # 2. TUTARLI VARYASYON SERT KURAL: bu katalogda kullanilmis iskelet
    # baska bir sayfada tekrar KULLANILAMAZ. Ancak hicbir taze iskelet
    # kalmadiysa tekrar kacinilmazdir ve bu ACIKCA kayda gecer.
    taze = [(k, v) for k, v in kalan if k not in kullanilan_iskeletler]
    havuz = taze or kalan
    tekrar_zorunlu = not taze

    # 3. Sanat yonetmeni tercihi -- havuzda ise ve kural ihlali yoksa
    if tercih and any(k == tercih for k, _ in havuz):
        kazanan = next(kv for kv in havuz if kv[0] == tercih)
        return (tercih,
                "sanat yonetmeni tercihi; urun yukseklik orani %.2f, "
                "olcek kontrasti %.1fx; olu bosluk ve tekrar kurallarindan gecti"
                % (kazanan[1]["urun_yukseklik_orani"],
                   kazanan[1]["olcek_kontrasti"]))

    # 4. Tercih yoksa/gecmediyse: urun hakimiyeti en yuksek olan
    kazanan = max(havuz, key=lambda kv: (kv[1]["urun_yukseklik_orani"],
                                         kv[1]["olcek_kontrasti"]))
    ad = kazanan[0]
    gerekce = ("urun yukseklik orani %.2f (en yuksek), olcek kontrasti %.1fx"
               % (kazanan[1]["urun_yukseklik_orani"],
                  kazanan[1]["olcek_kontrasti"]))
    if tekrar_zorunlu:
        gerekce += ("; UYARI: taze iskelet kalmadi, tekrar KACINILMAZ -- "
                    "iskelet havuzu genisletilmeli")
    elif ad in [k for k, _ in taze]:
        gerekce += "; bu iskelet katalogda henuz kullanilmadi (tutarli varyasyon)"
    if elenen:
        gerekce += "; elenen: " + ", ".join("%s (%s)" % (k, s)
                                            for k, s in elenen.items())
    return ad, gerekce


# --- Independent Critic --------------------------------------------------

KUSUR_TAKSONOMISI = ("tekrar", "klise", "kucuk_urun", "olu_bosluk",
                     "zayif_hiyerarsi", "yapay_zeka_gorunumu", "kadraj_kazasi",
                     "ton_dengesizligi", "acilim_dengesizligi")


def elestirmen(pdf_yolu, onceki_imzalar: list[str]) -> list[dict]:
    """YALNIZ render'a bakar. Brief'i, gerekceleri, konsept adini gormez.

    Deterministik sinyallere dayanir; her itiraz taksonomiden adlandirilir."""
    olc = so.sayfa_olcumleri(pdf_yolu)[0]
    itirazlar: list[dict] = []

    if olc.bosluk_orani > 0.66 and olc.ogeler < 9:
        itirazlar.append({
            "kusur_tipi": "olu_bosluk", "agirlik": "YUKSEK",
            "bolge": "sayfa geneli",
            "neden": "bosluk orani %.2f ve yalnizca %d oge var; boslugun bir "
                     "isi oldugu gorunmuyor" % (olc.bosluk_orani, olc.ogeler)})
    if olc.en_buyuk_punto < 20:
        itirazlar.append({
            "kusur_tipi": "zayif_hiyerarsi", "agirlik": "ORTA",
            "bolge": "tipografi",
            "neden": "en buyuk punto %.1f; olcek kontrasti %.1fx -- sayfa "
                     "hiyerarsi kurmuyor" % (olc.en_buyuk_punto,
                                             olc.en_buyuk_punto / 9.5)})
    if olc.duzen_imzasi in onceki_imzalar:
        itirazlar.append({
            "kusur_tipi": "tekrar", "agirlik": "YUKSEK",
            "bolge": "duzen", "neden": "duzen imzasi katalogda zaten kullanilmis"})
    if olc.metin_alan_orani < 0.012:
        itirazlar.append({
            "kusur_tipi": "zayif_hiyerarsi", "agirlik": "DUSUK",
            "bolge": "metin", "neden": "metin alani %.3f -- sayfa bilgi tasimiyor"
                                       % olc.metin_alan_orani})
    return itirazlar


# --- tek pilot -----------------------------------------------------------

def pilot_uret(p: dict, kullanilan_iskeletler: set) -> dict:
    foto = GORSEL / p["foto"]
    hedef = CIKTI / p["klasor"]
    hedef.mkdir(parents=True, exist_ok=True)

    # 1. ZORUNLU ILK KAPI: varlik siniflandirmasi
    sinif = vr.siniflandir(foto)
    if sinif.asset_type == "D":
        return {"slug": p["slug"], "durum": "DURDURULDU",
                "sebep": "TYPE D varlik", "kanit": list(sinif.evidence)}

    # 2. analiz
    a = fa.analiz(foto).sozluk()
    palet = ts.sayfa_paleti(a)

    ic = kk.Icerik(
        slug=p["slug"], ad=p["ad"], alt_ad=p["alt_ad"],
        ust_etiket=p["ust_etiket"], manset=p["manset"], govde=p["govde"],
        hacim=p.get("hacim", ""), inci=p.get("inci", ""),
        uyari=p.get("uyari", ""),
        not_etiketi=p.get("not_etiketi", "SAHA NOTU"),
        kaynak_foto=str(foto), analiz=a)

    kayit: dict = {
        "slug": p["slug"], "klasor": p["klasor"], "tur": p["tur"],
        "kaynak_foto": str(foto),
        "varlik_sinifi": {
            "asset_type": sinif.asset_type, "confidence": sinif.confidence,
            "izinli": list(sinif.allowed_operations),
            "yasak": list(sinif.forbidden_operations),
            "kanit": list(sinif.evidence)[:4],
            "azami_guvenli_mm": list(sinif.max_safe_placement_mm)},
        "palet": {k: v for k, v in palet.items() if k != "baskin"},
        "konseptler": {}, "turlar": [],
    }

    gecici = hedef / "_konseptler"
    gecici.mkdir(exist_ok=True)
    kanitlar: dict = {}
    planlar: dict = {}
    for plan in kk.uret_sinifa_gore(ic, palet, sinif.asset_type, p["tur"]):
        g = rd.goruntu_katmani(plan, a)
        yol = gecici / ("%s.pdf" % plan.kimlik)
        rd.pdf_uret(plan, g, yol)
        kanitlar[plan.konsept] = konsept_kaniti(plan, a, yol)
        planlar[plan.konsept] = plan
        import pymupdf
        d = pymupdf.open(str(yol))
        d[0].get_pixmap(dpi=90).save(str(gecici / ("%s.png" % plan.kimlik)))
        d.close()
    kayit["konseptler"] = kanitlar

    secilen, gerekce = ecd_secimi(kanitlar, kullanilan_iskeletler,
                                  p.get("tercih"))
    kayit["secilen_konsept"] = secilen
    kayit["secim_gerekcesi"] = gerekce

    # 6-8. render, QA, elestiri, revizyon
    plan = planlar[secilen]
    onceki_imzalar: list[str] = list(kullanilan_iskeletler)
    for tur in range(1, AZAMI_TUR + 1):
        g = rd.goruntu_katmani(plan, a)
        pdf_yolu = hedef / ("%s.pdf" % p["klasor"])
        rd.pdf_uret(plan, g, pdf_yolu)

        qa_tip = tqa.kapi(pdf_yolu, tasma_mm=ts.TASMA_MM,
                          guvenli_mm=ts.GUVENLI_MM)
        # Anayasa md.25: tipografi gorselin uzerine atilmaz.
        kontrast = rd.metin_kontrast_denetimi(plan, g)
        itiraz = elestirmen(pdf_yolu, onceki_imzalar)
        if kontrast:
            itiraz.append({
                "kusur_tipi": "zayif_hiyerarsi", "agirlik": "YUKSEK",
                "bolge": "metin/goruntu", "kontrast_ihlalleri": kontrast,
                "neden": "%d metin blogu goruntu uzerinde okunmuyor" % len(kontrast)})
        yuksek = [i for i in itiraz if i["agirlik"] == "YUKSEK"]

        tur_kaydi = {
            "tur": tur, "konsept": plan.konsept,
            "tipografi_qa": {"gecti": qa_tip["gecti"],
                             "durduran": qa_tip["durduran_ihlal"],
                             "uyari": qa_tip["uyari"],
                             "tip_dagilimi": qa_tip["tip_dagilimi"]},
            "elestirmen_itirazlari": itiraz,
            "metin_kontrast_ihlali": len(kontrast),
            "olcumler": plan.olcumler,
        }
        kayit["turlar"].append(tur_kaydi)

        if qa_tip["gecti"] and not yuksek:
            tur_kaydi["sonuc"] = "KABUL"
            break
        tur_kaydi["sonuc"] = "REVISE"
        # revizyon: bir sonraki en guclu konsepte gec
        kalan = [k for k in kanitlar if k != plan.konsept]
        if not kalan:
            break
        yeni, _ = ecd_secimi({k: kanitlar[k] for k in kalan},
                             kullanilan_iskeletler, None)
        tur_kaydi["revizyon"] = "konsept %s -> %s" % (plan.konsept, yeni)
        plan = planlar[yeni]
        kayit["secilen_konsept"] = yeni

    # PNG teslimati PDF'ten -- PNG ile PDF birebir ayni
    import pymupdf
    d = pymupdf.open(str(pdf_yolu))
    d[0].get_pixmap(dpi=300).save(str(hedef / ("%s.png" % p["klasor"])))
    d.close()

    # butunluk: urun pikseline dokunulmadi -- koken zinciri
    koken = bt.Koken(varlik=p["slug"], kaynak_ozeti=bt.dosya_ozeti(foto))
    koken.ekle("native_crop", "katalog_render.kirp_native", "2026-09-26",
               bt.dosya_ozeti(foto), "-", "yukari ornekleme yok")
    koken.ekle("page_placement", "katalog_render.goruntu_katmani",
               "2026-09-26", "-", "-",
               "urun pikseli uretken modelden GECMEDI")
    bt.koken_yaz(koken, hedef / "koken.json")
    kayit["koken"] = koken.sozluk()

    # kanit paketi
    paket = kn.paket_uret(pdf_yolu, sayfa_no=1,
                          sayfa_rolu="HERO" if p["tur"] == "KAPAK" else "KATALOG")
    paket.varlik_siniflandirmasi = kayit["varlik_sinifi"]
    paket.renk = kayit["palet"]
    kn.paket_yaz(paket, hedef / "kanit-paketi.json")

    kayit["pdf"] = str(pdf_yolu)
    kayit["png"] = str(hedef / ("%s.png" % p["klasor"]))
    kayit["kullanilan_iskelet"] = plan.konsept
    shutil.rmtree(gecici, ignore_errors=True)
    return kayit


def main() -> int:
    CIKTI.mkdir(parents=True, exist_ok=True)
    kullanilan: set = set()
    sonuclar = []
    for p in PILOTLAR:
        k = pilot_uret(p, kullanilan)
        if k.get("kullanilan_iskelet"):
            kullanilan.add(k["kullanilan_iskelet"])
        sonuclar.append(k)
        print("%-13s %-22s tur=%d  %s" % (
            k["klasor"], k.get("kullanilan_iskelet", "-"),
            len(k.get("turlar", [])),
            k["turlar"][-1]["sonuc"] if k.get("turlar") else k.get("durum", "?")))

    (CIKTI / "pilot-kayit.json").write_text(
        json.dumps(sonuclar, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nkayit: %s" % (CIKTI / "pilot-kayit.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
