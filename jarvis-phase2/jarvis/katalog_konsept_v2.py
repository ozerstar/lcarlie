"""25 CREATIVE CONCEPT V2 -- gercek sayfa planlari, gercek kutu metni.

Her konsept:
  - bir CONCEPT KERNEL'e baglidir (katalog_dna.KERNEL)
  - kendi BILGI KOREOGRAFISINI bildirir (FIRST/SECOND/THIRD/TECHNICAL/UTILITY)
  - sayfa-urun ILISKISINI bildirir (katalog_dna.ILISKILER) -- mekanik
    renk eslesmesi yasak
  - hangi GERCEK icerik alanlarina ihtiyac duydugunu bildirir; alan
    kutu gercegin de yoksa konsept REAL_CONTENT_FAIL alir
  - tipografik REPERTUAR kipini bildirir (U maddesi)

Tur 3 duzenleri KOPYALANMADI; tur 3 yalnizca degerlendirme asamasinda
BASELINE_CHALLENGER olarak kullanilir.
"""
from __future__ import annotations

from jarvis import katalog_icerik_v2 as ic2
from jarvis import katalog_render as rd
from jarvis import katalog_tasarim_sistemi as ts
from jarvis.katalog_konsept3 import _dpi_kur, kadraj

SAYFA = ts.SAYFA_MM            # 216
GUVENLI = 11.0                 # kesimden 8 mm ice
IC = SAYFA - 2 * GUVENLI       # 194

# tipografik repertuar kipleri (U)
REPERTUAR = ("MONUMENTAL_DISPLAY", "QUIET_EDITORIAL", "PRODUCT_NAME_DOMINANCE",
             "IMAGE_INTEGRATED_TYPE", "SCIENTIFIC_MICROTYPE",
             "INGREDIENT_NOMENCLATURE", "TECHNICAL_TYPOGRAPHY",
             "NUMBER_DRIVEN")

MUR = (0.10, 0.10, 0.12)
SOLUK = (0.40, 0.40, 0.44)
BEYAZ = (1.0, 1.0, 1.0)
ACIK = (0.86, 0.87, 0.89)


def _meta(plan, *, kernel, koreografi, iliski, repertuar, bosluk,
          gerekli_icerik, urun_olcegi, enerji, fikir, tur3_farki):
    plan.olcumler.update({
        "v2": True,
        "kernel": kernel,
        "koreografi": koreografi,
        "iliski": iliski,
        "repertuar": repertuar,
        "bosluk_sinifi": bosluk,
        "gerekli_icerik": list(gerekli_icerik),
        "urun_olcegi": urun_olcegi,
        "enerji": enerji,
        "fikir": fikir,
        "tur3_farki": tur3_farki,
    })
    return plan


def _zemin(plan, rgb):
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=rgb)


def _foto(plan, yol, x, y, en, boy, odak_x=0.5, odak_y=0.5, sik=1.0):
    plan.ekle("foto", kaynak=yol, kadraj=kadraj(yol, en, boy, odak_x, odak_y, sik),
              x=x, y=y, en=en, boy=boy, tuy_px=0)


def _kunye_satiri(plan, d, y, renk=SOLUK, punto=5.8):
    """Net miktar CELISKI ise BASILMAZ."""
    if d["net_miktar_durum"] == "OKUNDU":
        plan.ekle("metin", stil="not_etiketi", metin=d["net_miktar"],
                  x=SAYFA - GUVENLI - 30.0, y=y, en=30.0, renk=renk,
                  punto=punto, azami_satir=1, hiza="sag")


def _not_alani(plan, x, y, en, renk=SOLUK, satir=3, etiket="SANA NOT"):
    """R: gercek yazilabilir alan -- dekoratif ciz degil."""
    plan.ekle("not_alani", x=x, y=y, en=en, etiket=etiket, renk=renk,
              satir=satir, aralik=7.0)


# =======================================================================
# KAPAK -- kernel: "Bir marka, ayni anda kac ayri dunyaya bakabildigidir."
# =======================================================================

def c1_dokuz_aile(a: dict) -> rd.SayfaPlani:
    """DOKUZ AILE -- markanin gercek yapisi: 9 bakim ailesi, indeks olarak."""
    plan = rd.SayfaPlani("cover", "v2_dokuz_aile", 300.0)
    _zemin(plan, (247, 246, 243))
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI, y=34.0,
              en=IC, renk=MUR, punto=26.0, satir_pt=27.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=40.0, en=IC, renk=MUR, kalinlik=0.6)
    aileler = ["YÜZ VE EL", "HASSAS BÖLGE", "BEBEK VE ÇOCUK", "SPOR VE MASAJ",
               "VÜCUT VE BACAK", "AYAK VE TIRNAK", "AĞIZ VE DİŞ",
               "KULAK", "SAÇ"]
    y = 58.0
    for i, ad in enumerate(aileler):
        plan.ekle("metin", stil="urun_ad_kucuk", metin=ad, x=GUVENLI, y=y,
                  en=120.0, renk=MUR, punto=11.0, azami_satir=1)
        plan.ekle("metin", stil="not_etiketi", metin="%02d" % (i + 1),
                  x=SAYFA - GUVENLI - 16.0, y=y, en=16.0, renk=SOLUK,
                  punto=6.0, azami_satir=1, hiza="sag")
        plan.ekle("cizgi", x=GUVENLI, y=y + 3.0, en=IC,
                  renk=(0.78, 0.78, 0.80), kalinlik=0.25)
        y += 14.0
    plan.ekle("metin", stil="not_etiketi",
              metin="DERMOKOZMETİK ÜRÜN KATALOĞU · 36 ÜRÜN · 2026",
              x=GUVENLI, y=SAYFA - GUVENLI - 2.0, en=IC, renk=SOLUK,
              punto=6.2, azami_satir=1)
    return _meta(plan, kernel="cover",
                 koreografi="FIRST=marka · SECOND=aile indeksi · "
                            "THIRD=yil · TECHNICAL=yok · UTILITY=yok",
                 iliski="NEUTRAL_ISOLATION", repertuar="TECHNICAL_TYPOGRAPHY",
                 bosluk="ACTIVE -- satir araliklari indeksi okunur kiliyor",
                 gerekli_icerik=[], urun_olcegi="YOK", enerji="sistematik",
                 fikir="Marka bir indeks olarak kendini tanitir; hicbir urun "
                       "digerinin onune gecmez.",
                 tur3_farki="Tur 3 uc urun panosu kullandi; burada FOTOGRAF "
                            "HIC YOK, kapak saf tipografik yapi.")


def c2_tek_malzeme(a: dict, foto: str) -> rd.SayfaPlani:
    """TEK MALZEME -- tam sayfa makro; marka sakin bolgede."""
    dpi = _dpi_kur(foto, SAYFA, 198.0)
    plan = rd.SayfaPlani("cover", "v2_tek_malzeme", dpi)
    _zemin(plan, (22, 24, 27))
    _foto(plan, foto, 0.0, 0.0, SAYFA, 198.0, 0.42, 0.50)
    # OLCULDU: y=SAYFA-7 (209 mm) guvenli alan tavanini (205 mm) asiyordu;
    # tipografi QA 4 durduran ihlal verdi. Marka satiri iceri alindi.
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI,
              y=SAYFA - GUVENLI - 3.0, en=IC, renk=BEYAZ, punto=17.0,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="ÜRÜN KATALOĞU · 2026",
              x=SAYFA - GUVENLI - 60.0, y=SAYFA - GUVENLI - 3.0, en=60.0,
              renk=(0.72, 0.74, 0.76), punto=6.0, azami_satir=1, hiza="sag")
    return _meta(plan, kernel="cover",
                 koreografi="FIRST=malzeme · SECOND=marka · THIRD=yil",
                 iliski="MATERIAL_DERIVATION", repertuar="IMAGE_INTEGRATED_TYPE",
                 bosluk="ACTIVE -- alt koyu bant markayi tasiyor",
                 gerekli_icerik=[], urun_olcegi="YOK -- urun gorunmez",
                 enerji="duyusal",
                 fikir="Marka once bir MALZEME olarak karsilar; urun sonra gelir.",
                 tur3_farki="Tur 3 uc ayri urun gosterdi; burada tek makro "
                            "kadraj ve urun hic yok.")


def c3_otuzalti(a: dict, foto: str) -> rd.SayfaPlani:
    """36 -- markanin gercek ayirt edici sayisi, number-driven."""
    dpi = _dpi_kur(foto, 96.0, 128.0)
    plan = rd.SayfaPlani("cover", "v2_otuzalti", dpi)
    _zemin(plan, (250, 249, 247))
    plan.ekle("metin", stil="devasa", metin="36", x=GUVENLI, y=104.0,
              en=120.0, renk=MUR, punto=96.0, satir_pt=98.0, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="ÜRÜN", x=GUVENLI + 2.0,
              y=120.0, en=80.0, renk=MUR, punto=13.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="DOKUZ BAKIM AİLESİ",
              x=GUVENLI + 2.0, y=129.0, en=90.0, renk=SOLUK, punto=6.2,
              azami_satir=1)
    _foto(plan, foto, SAYFA - 96.0, 44.0, 96.0, 128.0, 0.36, 0.48)
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI, y=34.0,
              en=IC, renk=MUR, punto=20.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="DERMOKOZMETİK · 2026",
              x=GUVENLI, y=SAYFA - GUVENLI - 2.0, en=IC, renk=SOLUK,
              punto=6.2, azami_satir=1)
    return _meta(plan, kernel="cover",
                 koreografi="FIRST=sayi · SECOND=marka · THIRD=urun karesi",
                 iliski="CONTROLLED_ACCENT", repertuar="NUMBER_DRIVEN",
                 bosluk="ACTIVE -- sayinin etrafindaki bosluk olcegi kuruyor",
                 gerekli_icerik=[], urun_olcegi="ORTA",
                 enerji="beyan",
                 fikir="Markanin farki bir sayidir: 36. Rakipler 3-8 urunde "
                       "uzmanlasiyor.",
                 tur3_farki="Tur 3'te sayi hic kullanilmadi; burada sayi "
                            "sayfanin baskin ogesi.")


def c4_kunye(a: dict, foto: str) -> rd.SayfaPlani:
    """KÜNYE -- kapak bir masthead; yogun kucuk tipografi."""
    dpi = _dpi_kur(foto, 78.0, 78.0)
    plan = rd.SayfaPlani("cover", "v2_kunye", dpi)
    _zemin(plan, (232, 230, 225))
    plan.ekle("metin", stil="urun_ad", metin="L'CARLIÉ", x=GUVENLI, y=30.0,
              en=IC, renk=MUR, punto=15.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=34.0, en=IC, renk=MUR, kalinlik=0.4)
    satirlar = [
        ("KATALOG", "2026 · Birinci baskı"),
        ("KAPSAM", "36 ürün · 9 bakım ailesi"),
        ("FORMAT", "210 × 210 mm · 3 mm taşma"),
        ("FOTOĞRAF", "Stüdyo çekimi · mavi-gri sonsuz fon"),
        ("METİN", "Onaylı kutu metni kaynaklı"),
        ("BASKI", "Kâğıt ve ICC profili seçilmedi"),
    ]
    y = 46.0
    for et, dg in satirlar:
        plan.ekle("metin", stil="not_etiketi", metin=et, x=GUVENLI, y=y,
                  en=34.0, renk=SOLUK, punto=5.8, azami_satir=1)
        plan.ekle("metin", stil="govde_hafif", metin=dg, x=GUVENLI + 36.0,
                  y=y, en=84.0, renk=MUR, punto=7.0, azami_satir=1)
        y += 10.0
    _foto(plan, foto, SAYFA - 78.0, SAYFA - 78.0, 78.0, 78.0, 0.36, 0.42)
    return _meta(plan, kernel="cover",
                 koreografi="FIRST=marka · SECOND=kunye tablosu · "
                            "THIRD=urun detayi",
                 iliski="NEUTRAL_ISOLATION", repertuar="SCIENTIFIC_MICROTYPE",
                 bosluk="ACTIVE -- sag ust bosluk kunyeyi sola cekiyor",
                 gerekli_icerik=[], urun_olcegi="KUCUK", enerji="edebi",
                 fikir="Kapak bir kunye sayfasidir: katalog kendini once "
                       "kaydeder, sonra gosterir.",
                 tur3_farki="Tur 3 kapak gorselle acti; burada acilis metin "
                            "ve kayit.")


def c5_uc_isik(a: dict, fotolar: list[str]) -> rd.SayfaPlani:
    """ÜÇ IŞIK -- ayni malzeme, olculen uc farkli isik acisi."""
    en = 62.0
    boy = 83.0
    dpi = min(_dpi_kur(f, en, boy) for f in fotolar[:3])
    plan = rd.SayfaPlani("cover", "v2_uc_isik", min(dpi, 300.0))
    _zemin(plan, (250, 249, 247))
    x0 = (SAYFA - 3 * en - 2 * 5.0) / 2.0
    for i, f in enumerate(fotolar[:3]):
        x = x0 + i * (en + 5.0)
        _foto(plan, f, x, 66.0, en, boy, 0.36, 0.48)
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI, y=42.0,
              en=IC, renk=MUR, punto=22.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi",
              metin="AYNI IŞIK DİSİPLİNİ · ÜÇ BAKIM AİLESİ",
              x=GUVENLI, y=50.0, en=IC, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="2026",
              x=GUVENLI, y=SAYFA - GUVENLI - 2.0, en=40.0, renk=SOLUK,
              punto=6.2, azami_satir=1)
    return _meta(plan, kernel="cover",
                 koreografi="FIRST=uc kare · SECOND=marka · THIRD=yil",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- alt ucte bir sessizlik kapagi bitiriyor",
                 gerekli_icerik=[], urun_olcegi="KUCUK", enerji="teknik",
                 fikir="Marka tutarliligi urunde degil ISIKTA: uc ayri aile, "
                       "tek isik disiplini.",
                 tur3_farki="Tur 3 panolari kategori RENKLERINI gosteriyordu; "
                            "burada gosterilen sey ISIK.")


# =======================================================================
# HYDRAVIE -- kernel: "Nem, tutulan bir seydir -- tutuldugu yer gorunur
# olmali."  Gercek icerik: tanim VAR, kullanim VAR, uyari VAR, INCI YOK.
# =======================================================================

def h1_aski(d: dict, foto: str) -> rd.SayfaPlani:
    """ASKI -- fotograf sayfanin optik merkezinde askida; metin cevresinde."""
    en, boy = 104.0, 138.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("hydravie", "v2_aski", dpi)
    _zemin(plan, (228, 234, 240))
    x = (SAYFA - en) / 2.0
    _foto(plan, foto, x, 46.0, en, boy, 0.34, 0.44)
    plan.ekle("metin", stil="urun_ad", metin="HYDRAVIE", x=GUVENLI, y=28.0,
              en=IC, renk=MUR, punto=18.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"],
              x=GUVENLI, y=36.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM", x=GUVENLI, y=52.0,
              en=28.0, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 90),
              x=GUVENLI, y=59.0, en=40.0, renk=MUR, punto=6.6, satir_pt=8.6,
              azami_satir=4)
    plan.ekle("metin", stil="alt_yazi", metin="UYARI",
              x=SAYFA - GUVENLI - 40.0, y=52.0, en=40.0, renk=SOLUK,
              punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["uyari"], 110),
              x=SAYFA - GUVENLI - 40.0, y=59.0, en=40.0, renk=MUR, punto=6.6,
              satir_pt=8.6, azami_satir=5)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 200),
              x=GUVENLI, y=196.0, en=IC, renk=(0.20, 0.24, 0.30), punto=7.2,
              satir_pt=9.6, azami_satir=2)
    _not_alani(plan, GUVENLI, 176.0, 120.0, satir=2)
    _kunye_satiri(plan, d, 188.0)
    return _meta(plan, kernel="hydravie",
                 koreografi="FIRST=urun adi · SECOND=askidaki kare · "
                            "THIRD=kullanim/uyari kanatlari · "
                            "TECHNICAL=yok (INCI kaynakta YOK) · "
                            "UTILITY=not alani",
                 iliski="TONAL_CONTINUITY", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- fotografin etrafindaki bosluk askida "
                        "tutma fikrinin kendisi",
                 gerekli_icerik=["tanim", "kullanim", "uyari"],
                 urun_olcegi="ORTA", enerji="sakin",
                 fikir="Kare sayfanin ortasinda asili durur; metin ona "
                       "dokunmaz, cevresinde durur.",
                 tur3_farki="Tur 3 fotografi sag ust kare bloga koyup tabloyu "
                            "tam genislige acti; burada foto MERKEZDE ve "
                            "tablo YOK.")


def h2_iki_zaman(d: dict, foto: str, foto2: str) -> rd.SayfaPlani:
    """IKI ZAMAN -- kutu metnindeki sabah/aksam ritmi sayfa yapisi olur."""
    en, boy = 108.0, 92.0
    dpi = min(_dpi_kur(foto, en, boy), _dpi_kur(foto2, en, boy))
    plan = rd.SayfaPlani("hydravie", "v2_iki_zaman", dpi)
    _zemin(plan, (243, 244, 246))
    _foto(plan, foto, 0.0, 30.0, en, boy, 0.34, 0.42)
    _foto(plan, foto2, SAYFA - en, 30.0, en, boy, 0.34, 0.52)
    plan.ekle("metin", stil="not_etiketi", metin="SABAH", x=GUVENLI, y=26.0,
              en=60.0, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="AKŞAM",
              x=SAYFA - GUVENLI - 60.0, y=26.0, en=60.0, renk=SOLUK,
              punto=6.0, azami_satir=1, hiza="sag")
    plan.ekle("metin", stil="urun_ad", metin="HYDRAVIE", x=GUVENLI, y=140.0,
              en=IC, renk=MUR, punto=20.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin="Yoğun Nemlendirici Yüz Kremi",
              x=GUVENLI, y=149.0, en=IC, renk=SOLUK, punto=8.5, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=155.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 120),
              x=GUVENLI, y=164.0, en=88.0, renk=MUR, punto=7.0, satir_pt=9.4,
              azami_satir=3)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 190),
              x=GUVENLI + 96.0, y=164.0, en=IC - 96.0, renk=(0.24, 0.26, 0.30),
              punto=7.0, satir_pt=9.4, azami_satir=4)
    _not_alani(plan, GUVENLI, 194.0, 110.0, satir=2)
    _kunye_satiri(plan, d, 198.0)
    return _meta(plan, kernel="hydravie",
                 koreografi="FIRST=iki kare · SECOND=zaman etiketleri · "
                            "THIRD=urun adi · TECHNICAL=kullanim · "
                            "UTILITY=not alani",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- iki kare arasindaki bosluk gunun iki "
                        "ucunu ayiriyor",
                 gerekli_icerik=["tanim", "kullanim"],
                 urun_olcegi="ORTA", enerji="ritmik",
                 fikir="Urunun ritmi gunde iki kez. Sayfa da iki zamana "
                       "bolunur.",
                 tur3_farki="Tur 3 tek fotograf blogu kullandi; burada ayni "
                            "urunun IKI ayri karesi zamani kuruyor.")


def h3_bilesen_merdiveni(d: dict, foto: str) -> rd.SayfaPlani:
    """BILESEN MERDIVENI -- TR adi / INCI adi basamak basamak, hiyerarsik."""
    en, boy = 84.0, 84.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("hydravie", "v2_bilesen_merdiveni", dpi)
    # J · TONAL_CONTINUITY: zemin fotografin OLCULEN fonundan turetildi
    # (kaynak zemin rgb(207,218,230)); notr bir beyaz secmek iliskiyi
    # kurmamak olurdu.
    _zemin(plan, (212, 223, 234))
    plan.ekle("metin", stil="urun_ad", metin="HYDRAVIE", x=GUVENLI, y=30.0,
              en=IC, renk=MUR, punto=17.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="ÖNE ÇIKAN İÇERİKLER",
              x=GUVENLI, y=44.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    y = 56.0
    for i, (tr, inci, _oran) in enumerate(d["one_cikan"]):
        x = GUVENLI + i * 6.0
        plan.ekle("metin", stil="urun_ad_kucuk", metin=tr, x=x, y=y,
                  en=110.0, renk=MUR, punto=10.5 - i * 0.5, azami_satir=1)
        plan.ekle("metin", stil="inci", metin=inci, x=x, y=y + 6.0,
                  en=110.0, renk=SOLUK, punto=6.0, azami_satir=1)
        plan.ekle("cizgi", x=x, y=y + 9.5, en=112.0 - i * 6.0,
                  renk=(0.74, 0.76, 0.78), kalinlik=0.25)
        y += 19.0
    _foto(plan, foto, SAYFA - en, SAYFA - en, en, en, 0.36, 0.40)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 150),
              x=GUVENLI, y=160.0, en=112.0, renk=(0.22, 0.26, 0.30),
              punto=7.0, satir_pt=9.4, azami_satir=4)
    _not_alani(plan, GUVENLI, 196.0, 108.0, satir=2)
    return _meta(plan, kernel="hydravie",
                 koreografi="FIRST=urun adi · SECOND=bilesen merdiveni · "
                            "THIRD=tanim · TECHNICAL=INCI adlari · "
                            "UTILITY=not alani",
                 iliski="TONAL_CONTINUITY",
                 repertuar="INGREDIENT_NOMENCLATURE",
                 bosluk="ACTIVE -- merdivenin sag tarafindaki artan bosluk "
                        "hiyerarsiyi gosteriyor",
                 gerekli_icerik=["tanim", "one_cikan"],
                 urun_olcegi="KUCUK", enerji="bilimsel",
                 fikir="Bilesenler esit kart degil hiyerarsik bir merdiven. "
                       "Kahraman bilesen en ustte ve en buyuk.",
                 tur3_farki="Tur 3 tablosu tum satirlari ESIT gosteriyordu; "
                            "burada bilesenler arasinda hiyerarsi var.")


def h4_golge_olcusu(d: dict, foto: str) -> rd.SayfaPlani:
    """GOLGE OLCUSU -- fotografin capraz golgesi tipografiyi hizalar."""
    dpi = _dpi_kur(foto, SAYFA, 132.0)
    plan = rd.SayfaPlani("hydravie", "v2_golge_olcusu", dpi)
    _zemin(plan, (218, 227, 236))
    _foto(plan, foto, 0.0, 0.0, SAYFA, 132.0, 0.40, 0.46)
    plan.ekle("metin", stil="urun_ad", metin="HYDRAVIE", x=GUVENLI, y=150.0,
              en=IC, renk=MUR, punto=19.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin=d["kategori"], x=GUVENLI,
              y=159.0, en=IC, renk=SOLUK, punto=8.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=165.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 190),
              x=GUVENLI, y=174.0, en=104.0, renk=(0.20, 0.24, 0.30),
              punto=7.2, satir_pt=9.6, azami_satir=4)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM",
              x=GUVENLI + 112.0, y=174.0, en=82.0, renk=SOLUK, punto=5.8,
              azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 95),
              x=GUVENLI + 112.0, y=181.0, en=82.0, renk=MUR, punto=6.8,
              satir_pt=8.8, azami_satir=3)
    _not_alani(plan, GUVENLI, 198.0, 104.0, satir=1)
    _kunye_satiri(plan, d, 202.0)
    return _meta(plan, kernel="hydravie",
                 koreografi="FIRST=golge · SECOND=urun adi · THIRD=tanim · "
                            "TECHNICAL=kullanim · UTILITY=not alani",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="PRODUCT_NAME_DOMINANCE",
                 bosluk="ACTIVE -- fotograf altindaki serit metni tasiyor",
                 gerekli_icerik=["tanim", "kullanim"],
                 urun_olcegi="BUYUK", enerji="sakin",
                 fikir="Karenin olculen capraz golgesi sayfanin hizalama "
                       "cizgisi olur.",
                 tur3_farki="Tur 3 fotografi kare bloga sikistirdi; burada "
                            "tam genislik ve golge yapiyi kuruyor.")


def h5_temiz_yuzey(d: dict, foto: str) -> rd.SayfaPlani:
    """TEMIZ YUZEY -- azami kisitlama: kucuk urun, tek cumle."""
    en, boy = 66.0, 88.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("hydravie", "v2_temiz_yuzey", dpi)
    _zemin(plan, (234, 239, 243))
    _foto(plan, foto, SAYFA - GUVENLI - en, 44.0, en, boy, 0.34, 0.44)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="HYDRAVIE", x=GUVENLI,
              y=46.0, en=100.0, renk=MUR, punto=12.0, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 120),
              x=GUVENLI, y=62.0, en=92.0, renk=(0.22, 0.26, 0.30), punto=7.6,
              satir_pt=11.0, azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="KULLANIM — " + ic2.kisalt(d["kullanim"], 80),
              x=GUVENLI, y=178.0, en=IC, renk=SOLUK, punto=6.0, satir_pt=7.8,
              azami_satir=2)
    _not_alani(plan, GUVENLI, 194.0, 96.0, satir=2)
    _kunye_satiri(plan, d, 198.0)
    return _meta(plan, kernel="hydravie",
                 koreografi="FIRST=tek cumle · SECOND=urun · "
                            "THIRD=kullanim mikro · UTILITY=not alani",
                 iliski="NO_REPETITION", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- sayfanin alt yarisi kasitli sessizlik",
                 gerekli_icerik=["tanim", "kullanim"],
                 urun_olcegi="KUCUK", enerji="cok sakin",
                 fikir="Azami kisitlama: sayfada yalnizca kalmasi zorunlu "
                       "olanlar var.",
                 tur3_farki="Tur 3 HYDRAVIE sayfasi besin EN YOGUNUYDU; "
                            "bu en seyregi.")


# =======================================================================
# KINESIS+ -- kernel: "Bakim, dinlenme aninda degil caba aninda baslar."
# GERCEK KISIT: onayli kutu metninde YALNIZCA kullanim var.
# tanim YOK, uyari YOK, INCI YOK, bilesen tablosu YOK.
# Bu yuzden KINESIS konseptleri metinle degil ANLAMLA tasinmak zorunda.
# =======================================================================

def k1_tek_talimat(d: dict, foto: str) -> rd.SayfaPlani:
    """TEK TALIMAT -- elimizdeki TEK onayli metin sayfanin kahramani olur."""
    en, boy = 96.0, 128.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("kinesis", "v2_tek_talimat", dpi)
    _zemin(plan, (236, 233, 226))
    _foto(plan, foto, SAYFA - en, SAYFA - boy - 20.0, en, boy, 0.34, 0.46)
    plan.ekle("metin", stil="not_etiketi", metin="KULLANIM", x=GUVENLI,
              y=40.0, en=IC, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin=d["kullanim"], x=GUVENLI,
              y=56.0, en=104.0, renk=MUR, punto=13.0, satir_pt=18.0,
              azami_satir=7)
    plan.ekle("cizgi", x=GUVENLI, y=140.0, en=104.0, renk=MUR, kalinlik=0.5)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="KINESIS +", x=GUVENLI,
              y=152.0, en=104.0, renk=MUR, punto=12.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"], x=GUVENLI,
              y=159.0, en=104.0, renk=SOLUK, punto=5.8, azami_satir=1)
    _not_alani(plan, GUVENLI, 186.0, 100.0, satir=2)
    _kunye_satiri(plan, d, 200.0)
    return _meta(plan, kernel="kinesis+",
                 koreografi="FIRST=talimat · SECOND=urun karesi · "
                            "THIRD=urun adi · TECHNICAL=yok · "
                            "UTILITY=not alani",
                 iliski="TONAL_CONTINUITY", repertuar="MONUMENTAL_DISPLAY",
                 bosluk="ACTIVE -- talimatin genis satir araligi sayfayi "
                        "yavaslatiyor",
                 gerekli_icerik=["kullanim"],
                 urun_olcegi="ORTA", enerji="direktif",
                 fikir="Bu urunun onayli tek metni kullanim talimatidir. "
                       "Sayfa bunu gizlemek yerine kahraman yapar.",
                 tur3_farki="Tur 3 KINESIS sayfasi bir ETIKET cumlesini "
                            "govde sanmisti; burada gercek tek metin one "
                            "cikiyor.")


def k2_caba(d: dict, foto: str) -> rd.SayfaPlani:
    """CABA -- insan karesine SIKI kadraj; tur 3 genis salon planinin tersi."""
    # OLCULDU: kaynak 1254x1254. sik=0.62 kadrajda 777 px kalir;
    # 200 mm yerlesim 99 PPI verir -- taban delinir. Siki kadraj FIKRIN
    # kendisi oldugu icin kadraj korundu, YERLESIM kucultuldu: koyu
    # alanda yuzen 128 mm kare (154 PPI).
    yan = 128.0
    dpi = _dpi_kur(foto, yan, yan, 0.62)
    plan = rd.SayfaPlani("kinesis", "v2_caba", dpi)
    _zemin(plan, (20, 21, 23))
    plan.ekle("foto", kaynak=foto,
              kadraj=kadraj(foto, yan, yan, 0.40, 0.34, 0.62),
              x=(SAYFA - yan) / 2.0, y=36.0, en=yan, boy=yan, tuy_px=0)
    plan.ekle("metin", stil="urun_ad", metin="KINESIS +",
              x=GUVENLI, y=SAYFA - GUVENLI - 14.0, en=120.0, renk=BEYAZ,
              punto=17.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"],
              x=GUVENLI, y=SAYFA - GUVENLI - 6.0, en=120.0,
              renk=(0.72, 0.73, 0.75), punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="BÖLÜM AÇILIŞI",
              x=SAYFA - GUVENLI - 70.0, y=26.0, en=70.0,
              renk=(0.60, 0.61, 0.63), punto=5.8, azami_satir=1, hiza="sag")
    return _meta(plan, kernel="kinesis+",
                 koreografi="FIRST=caba · SECOND=urun adi · THIRD=kategori · "
                            "TECHNICAL=yok · UTILITY=yok (bolum acilisi)",
                 iliski="NO_REPETITION", repertuar="IMAGE_INTEGRATED_TYPE",
                 bosluk="ACTIVE -- alt koyu serit tek nefes",
                 gerekli_icerik=[],
                 urun_olcegi="KUCUK -- urun kadrajin icinde kaliyor",
                 enerji="cok yuksek",
                 fikir="Bakim caba aninda baslar; sayfa o ani sikistirir.",
                 tur3_farki="Tur 3 ayni kareyi GENIS kullandi ve urunu one "
                            "cikardi; burada kadraj sikilastirildi ve sayfa "
                            "bir BOLUM ACILISI olarak davraniyor.")


def k3_bes_on_pompa(d: dict, foto: str) -> rd.SayfaPlani:
    """5-10 POMPA -- kutu metnindeki gercek doz, number-driven kompozisyon."""
    en, boy = 104.0, 139.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("kinesis", "v2_bes_on_pompa", dpi)
    _zemin(plan, (245, 243, 238))
    _foto(plan, foto, 0.0, 44.0, en, boy, 0.36, 0.46)
    plan.ekle("metin", stil="devasa", metin="5–10", x=GUVENLI + 112.0,
              y=94.0, en=88.0, renk=MUR, punto=52.0, satir_pt=54.0,
              azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="POMPA",
              x=GUVENLI + 114.0, y=106.0, en=80.0, renk=MUR, punto=12.0,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="GÜNDE İKİ KEZ",
              x=GUVENLI + 114.0, y=114.0, en=80.0, renk=SOLUK, punto=6.0,
              azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="KINESIS +",
              x=GUVENLI + 112.0, y=52.0, en=84.0, renk=MUR, punto=13.0,
              azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 130),
              x=GUVENLI + 112.0, y=134.0, en=84.0, renk=(0.24, 0.24, 0.28),
              punto=6.8, satir_pt=8.8, azami_satir=5)
    _not_alani(plan, GUVENLI + 112.0, 186.0, 82.0, satir=2)
    _kunye_satiri(plan, d, 200.0)
    return _meta(plan, kernel="kinesis+",
                 koreografi="FIRST=doz sayisi · SECOND=urun karesi · "
                            "THIRD=urun adi · TECHNICAL=kullanim · "
                            "UTILITY=not alani",
                 iliski="COMPLEMENTARY_CONTRAST", repertuar="NUMBER_DRIVEN",
                 bosluk="ACTIVE -- sayinin etrafi bos kalmali",
                 gerekli_icerik=["kullanim"],
                 urun_olcegi="ORTA", enerji="kesin",
                 fikir="Elimizdeki tek dogrulanmis veri dozdur. Doz sayfanin "
                       "olcegi olur.",
                 tur3_farki="Tur 3'te sayi hic kullanilmadi.")


def k4_iki_kez(d: dict, foto: str, foto2: str) -> rd.SayfaPlani:
    """IKI KEZ -- gunde iki kez ritmi sayfanin iki ozdes bolgesi olur."""
    en, boy = 88.0, 88.0
    dpi = min(_dpi_kur(foto, en, boy), _dpi_kur(foto2, en, boy))
    plan = rd.SayfaPlani("kinesis", "v2_iki_kez", dpi)
    _zemin(plan, (240, 238, 232))
    _foto(plan, foto, GUVENLI, 44.0, en, boy, 0.34, 0.44)
    _foto(plan, foto2, SAYFA - GUVENLI - en, 44.0, en, boy, 0.36, 0.50)
    plan.ekle("metin", stil="urun_ad", metin="KINESIS +", x=GUVENLI, y=32.0,
              en=IC, renk=MUR, punto=18.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="01", x=GUVENLI, y=142.0,
              en=30.0, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="02",
              x=SAYFA - GUVENLI - en, y=142.0, en=30.0, renk=SOLUK,
              punto=6.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=148.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 150),
              x=GUVENLI, y=158.0, en=120.0, renk=MUR, punto=7.2, satir_pt=9.6,
              azami_satir=4)
    _not_alani(plan, GUVENLI, 194.0, 118.0, satir=2)
    _kunye_satiri(plan, d, 198.0)
    return _meta(plan, kernel="kinesis+",
                 koreografi="FIRST=iki ozdes bolge · SECOND=urun adi · "
                            "THIRD=kullanim · UTILITY=not alani",
                 iliski="TONAL_CONTINUITY", repertuar="TECHNICAL_TYPOGRAPHY",
                 bosluk="ACTIVE -- iki bolge arasindaki bosluk tekrar "
                        "fikrini tasiyor",
                 gerekli_icerik=["kullanim"],
                 urun_olcegi="ORTA", enerji="olculu",
                 fikir="Gunde iki kez. Sayfa da iki kez.",
                 tur3_farki="Tur 3 tek tam tasma kare kullandi; burada ayni "
                            "urunun iki karesi ritmi kuruyor.")


def k5_eksik_veri(d: dict, foto: str) -> rd.SayfaPlani:
    """EKSIK VERI -- onayli metin yoksa sayfa bunu gizlemez, kisitlanir."""
    dpi = _dpi_kur(foto, SAYFA, 152.0)
    plan = rd.SayfaPlani("kinesis", "v2_eksik_veri", dpi)
    _zemin(plan, (28, 27, 24))
    _foto(plan, foto, 0.0, 0.0, SAYFA, 152.0, 0.38, 0.48)
    plan.ekle("metin", stil="urun_ad", metin="KINESIS +", x=GUVENLI, y=176.0,
              en=IC, renk=BEYAZ, punto=20.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"], x=GUVENLI,
              y=185.0, en=IC, renk=(0.74, 0.74, 0.72), punto=6.0,
              azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 120),
              x=GUVENLI, y=196.0, en=120.0, renk=(0.80, 0.80, 0.78),
              punto=6.8, satir_pt=8.8, azami_satir=2)
    _not_alani(plan, SAYFA - GUVENLI - 60.0, 196.0, 60.0,
               renk=(0.62, 0.62, 0.60), satir=2)
    return _meta(plan, kernel="kinesis+",
                 koreografi="FIRST=malzeme · SECOND=urun adi · "
                            "THIRD=kullanim · TECHNICAL=yok · "
                            "UTILITY=not alani",
                 iliski="MATERIAL_DERIVATION", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- koyu alt alan metni tasiyor",
                 gerekli_icerik=["kullanim"],
                 urun_olcegi="BUYUK", enerji="agir",
                 fikir="Onayli metin yoksa sayfa metin uydurmaz; malzemeye "
                       "ve olcege guvenir.",
                 tur3_farki="Tur 3 bu urune bir ETIKET cumlesi eklemisti; "
                            "burada eksiklik kabul ediliyor.")


# =======================================================================
# FEMISIA / VIREON -- kernel: "Iki beden, tek formul dili."
# Gercek icerik: her ikisinde de tanim, kullanim, uyari, TAM INCI var.
# OLCULEN GERCEK: epimedium ve L-arginin HER IKI formulde de bulunuyor.
# =======================================================================

ORTAK_BILESEN = [
    ("Epimedium", "Epimedium Grandiflorum Leaf Extract"),
    ("L-Arginin", "L-Arginine"),
]


def f1_ortak_inci(d: dict, dv: dict, foto: str) -> rd.SayfaPlani:
    """ORTAK INCI -- iki formulun PAYLASTIGI bilesenler sayfanin omurgasi."""
    en, boy = 90.0, 120.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("private-care", "v2_ortak_inci", dpi)
    _zemin(plan, (246, 245, 243))
    _foto(plan, foto, SAYFA - en, 40.0, en, boy, 0.34, 0.46)
    plan.ekle("metin", stil="not_etiketi", metin="İKİ FORMÜL · ORTAK ÇEKİRDEK",
              x=GUVENLI, y=32.0, en=IC, renk=SOLUK, punto=6.0, azami_satir=1)
    y = 52.0
    for tr, inci in ORTAK_BILESEN:
        plan.ekle("metin", stil="urun_ad_kucuk", metin=tr, x=GUVENLI, y=y,
                  en=104.0, renk=MUR, punto=14.0, azami_satir=1)
        plan.ekle("metin", stil="inci", metin=inci, x=GUVENLI, y=y + 7.0,
                  en=104.0, renk=SOLUK, punto=6.2, azami_satir=1)
        plan.ekle("cizgi", x=GUVENLI, y=y + 11.0, en=104.0,
                  renk=(0.76, 0.75, 0.73), kalinlik=0.3)
        y += 26.0
    plan.ekle("metin", stil="urun_ad_kucuk", metin="FEMISIA", x=GUVENLI,
              y=124.0, en=50.0, renk=MUR, punto=11.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="for WOMEN", x=GUVENLI,
              y=130.0, en=50.0, renk=SOLUK, punto=5.6, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="VIREON", x=GUVENLI + 58.0,
              y=124.0, en=50.0, renk=MUR, punto=11.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="for MEN", x=GUVENLI + 58.0,
              y=130.0, en=50.0, renk=SOLUK, punto=5.6, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 130),
              x=GUVENLI, y=144.0, en=50.0, renk=(0.24, 0.24, 0.28), punto=6.4,
              satir_pt=8.2, azami_satir=5)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(dv["tanim"], 130),
              x=GUVENLI + 58.0, y=144.0, en=50.0, renk=(0.24, 0.24, 0.28),
              punto=6.4, satir_pt=8.2, azami_satir=5)
    plan.ekle("metin", stil="inci", metin=ic2.kisalt(d["inci"], 300),
              x=GUVENLI, y=190.0, en=IC, renk=(0.46, 0.46, 0.48), punto=5.6,
              satir_pt=7.2, azami_satir=3)
    _not_alani(plan, SAYFA - GUVENLI - 84.0, 168.0, 84.0, satir=2)
    return _meta(plan, kernel="femisia",
                 koreografi="FIRST=ortak bilesenler · SECOND=iki urun adi · "
                            "THIRD=iki tanim · TECHNICAL=tam INCI · "
                            "UTILITY=not alani",
                 iliski="NEUTRAL_ISOLATION",
                 repertuar="INGREDIENT_NOMENCLATURE",
                 bosluk="ACTIVE -- ortak bilesenlerin altindaki bosluk "
                        "ayrimi gorsellestiriyor",
                 gerekli_icerik=["tanim", "inci"],
                 urun_olcegi="ORTA", enerji="sessiz",
                 fikir="Iki urunun ortak cekirdegi sayfanin omurgasi olur; "
                       "ayrim ancak ondan sonra gelir.",
                 tur3_farki="Tur 3 iki urunu yan yana GOSTERDI; burada "
                            "gosterilen sey ORTAKLIK -- olculen gercek.")


def f2_tam_inci(d: dict, foto: str) -> rd.SayfaPlani:
    """TAM INCI -- teknik luks: INCI ne dipnot ne hero, tasarlanmis blok."""
    en, boy = 70.0, 94.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("private-care", "v2_tam_inci", dpi)
    # J · MATERIAL_DERIVATION: FEMISIA kutusu mat siyah-kirmizi karton,
    # sise amber cam. Zemin bu sicak malzemeden turetildi -- urun rengi
    # kopyalanmadi, malzemenin tonu alindi.
    _zemin(plan, (228, 216, 206))
    plan.ekle("metin", stil="urun_ad", metin="FEMISIA", x=GUVENLI, y=32.0,
              en=IC, renk=MUR, punto=18.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"], x=GUVENLI,
              y=40.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=48.0, en=IC, renk=MUR, kalinlik=0.5)
    plan.ekle("metin", stil="not_etiketi", metin="INCI", x=GUVENLI, y=58.0,
              en=30.0, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="inci", metin=d["inci"], x=GUVENLI, y=68.0,
              en=118.0, renk=(0.20, 0.20, 0.24), punto=7.0, satir_pt=10.2,
              azami_satir=13)
    _foto(plan, foto, SAYFA - en, 58.0, en, boy, 0.34, 0.44)
    # CRITIC (CRAFT REVISE): sag alt kose gorece bostu. Kullanim metni
    # oraya alindi ve not alani yukari cekildi; INCI blogu solda kaldi.
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 140),
              x=SAYFA - GUVENLI - 70.0, y=162.0, en=70.0,
              renk=(0.26, 0.24, 0.22), punto=6.6, satir_pt=8.6, azami_satir=5)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM",
              x=SAYFA - GUVENLI - 70.0, y=186.0, en=70.0, renk=SOLUK,
              punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 100),
              x=SAYFA - GUVENLI - 70.0, y=193.0, en=70.0,
              renk=(0.26, 0.24, 0.22), punto=6.4, satir_pt=8.2, azami_satir=4)
    plan.ekle("metin", stil="inci", metin=ic2.kisalt(d["uyari"], 170),
              x=GUVENLI, y=194.0, en=112.0, renk=SOLUK, punto=5.6,
              satir_pt=7.2, azami_satir=3)
    _not_alani(plan, GUVENLI, 176.0, 112.0, satir=1)
    _kunye_satiri(plan, d, 52.0)
    return _meta(plan, kernel="femisia",
                 koreografi="FIRST=urun adi · SECOND=tam INCI blogu · "
                            "THIRD=urun karesi · TECHNICAL=INCI · "
                            "UTILITY=not alani",
                 iliski="NEUTRAL_ISOLATION", repertuar="TECHNICAL_TYPOGRAPHY",
                 bosluk="ACTIVE -- INCI blogunun satir araligi okunurlugu "
                        "kuruyor",
                 gerekli_icerik=["inci", "tanim", "uyari"],
                 urun_olcegi="KUCUK", enerji="teknik",
                 fikir="INCI gri dipnot degil; 7 punto ve 10.2 pt satir "
                       "araligiyla tasarlanmis bir bilgi bolgesi.",
                 tur3_farki="Tur 3'te INCI tek satir 5.6 punto dipnottu; "
                            "burada sayfanin ikinci baskin ogesi.")


def f3_gecis(d: dict, dv: dict, foto: str) -> rd.SayfaPlani:
    """GECIS -- fotograf oluktan gecer, iki sutun onu takip eder."""
    dpi = _dpi_kur(foto, SAYFA, 118.0, 0.86)
    plan = rd.SayfaPlani("private-care", "v2_gecis", dpi)
    _zemin(plan, (244, 242, 240))
    plan.ekle("foto", kaynak=foto,
              kadraj=kadraj(foto, SAYFA, 118.0, 0.40, 0.46, 0.86),
              x=0.0, y=54.0, en=SAYFA, boy=118.0, tuy_px=0)
    plan.ekle("metin", stil="urun_ad", metin="FEMISIA  ·  VIREON",
              x=GUVENLI, y=34.0, en=IC, renk=MUR, punto=17.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi",
              metin="KADIN VE ERKEK İÇİN İKİ AYRI FORMÜL", x=GUVENLI,
              y=42.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    orta = SAYFA / 2.0
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 150),
              x=GUVENLI, y=184.0, en=orta - GUVENLI - 6.0,
              renk=(0.24, 0.24, 0.28), punto=6.8, satir_pt=8.8, azami_satir=4)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(dv["tanim"], 150),
              x=orta + 6.0, y=184.0, en=orta - GUVENLI - 6.0,
              renk=(0.24, 0.24, 0.28), punto=6.8, satir_pt=8.8, azami_satir=4)
    plan.ekle("cizgi", x=orta, y=180.0, en=0.0, boy=30.0,
              renk=(0.74, 0.73, 0.72), kalinlik=0.3)
    return _meta(plan, kernel="femisia",
                 koreografi="FIRST=gecis bandi · SECOND=iki ad · "
                            "THIRD=iki tanim · UTILITY=yok",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="PRODUCT_NAME_DOMINANCE",
                 bosluk="ACTIVE -- bandin ustundeki ve altindaki bosluk "
                        "esit degil, sayfa asagiya akiyor",
                 gerekli_icerik=["tanim"],
                 urun_olcegi="BUYUK", enerji="dengeli",
                 fikir="Iki urun tek fotografta; sayfa onlari ayirmak yerine "
                       "bir gecis olarak kurar.",
                 tur3_farki="Tur 3 bandi ORTADA yuzuyordu ve metin altta iki "
                            "simetrik kolondaydi; burada bant asagi kayiyor "
                            "ve simetri kiriliyor.")


def f4_ketum(d: dict, foto: str) -> rd.SayfaPlani:
    """KETUM -- kategori ketumluğu: urun cok kucuk, alan cok genis."""
    en, boy = 46.0, 62.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("private-care", "v2_ketum", dpi)
    _zemin(plan, (231, 227, 224))
    _foto(plan, foto, SAYFA - GUVENLI - en, SAYFA - GUVENLI - boy, en, boy,
          0.34, 0.44)
    plan.ekle("metin", stil="alt_baslik", metin=ic2.kisalt(d["tanim"], 96),
              x=GUVENLI, y=62.0, en=118.0, renk=MUR, punto=11.5,
              satir_pt=16.5, azami_satir=4)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="FEMISIA", x=GUVENLI,
              y=SAYFA - GUVENLI - 14.0, en=90.0, renk=MUR, punto=10.5,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="for WOMEN · " + d["kategori"],
              x=GUVENLI, y=SAYFA - GUVENLI - 7.0, en=110.0, renk=SOLUK,
              punto=5.6, azami_satir=1)
    # OLCULDU: (0.52,0.50,0.49) murekkep bu zeminde 3.2 kontrast esigini
    # gecemiyordu (1 metin blogu okunmuyor). Koyulastirildi.
    plan.ekle("metin", stil="inci", metin=ic2.kisalt(d["inci"], 150),
              x=GUVENLI, y=160.0, en=110.0, renk=(0.34, 0.32, 0.31),
              punto=5.6, satir_pt=7.0, azami_satir=2)
    return _meta(plan, kernel="femisia",
                 koreografi="FIRST=tek cumle · SECOND=INCI mikro · "
                            "THIRD=urun adi · UTILITY=yok",
                 iliski="MATERIAL_DERIVATION", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- genis bos alan kategorinin ketumlugunu "
                        "tasiyor; DEAD degil cunku urun kosede ve okuma "
                        "yonunu o belirliyor",
                 gerekli_icerik=["tanim", "inci"],
                 urun_olcegi="COK KUCUK", enerji="cok sessiz",
                 fikir="Hassas bolge kategorisi gosterilmez; sayfa da "
                       "gostermez.",
                 tur3_farki="Tur 3 bu kategoriyi tam genislik bandiyla "
                            "GOSTERIYORDU; bu onun tam tersi.")


def f5_bilesen_portresi(d: dict, foto: str) -> rd.SayfaPlani:
    """BILESEN PORTRESI -- kahraman bilesen; urun dipnot olur."""
    en, boy = 60.0, 80.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("private-care", "v2_bilesen_portresi", dpi)
    _zemin(plan, (240, 236, 233))
    tr, inci, _ = d["one_cikan"][0]
    plan.ekle("metin", stil="devasa", metin=tr, x=GUVENLI, y=76.0,
              en=IC, renk=MUR, punto=38.0, satir_pt=40.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin=inci, x=GUVENLI, y=90.0,
              en=IC, renk=SOLUK, punto=10.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=98.0, en=IC, renk=MUR, kalinlik=0.4)
    ikincil = d["one_cikan"][1:4]
    y = 110.0
    for t2, i2, _o in ikincil:
        plan.ekle("metin", stil="alt_yazi", metin=t2, x=GUVENLI, y=y,
                  en=56.0, renk=MUR, punto=7.2, azami_satir=1)
        plan.ekle("metin", stil="inci", metin=i2, x=GUVENLI + 58.0, y=y,
                  en=76.0, renk=SOLUK, punto=6.0, azami_satir=1)
        y += 10.0
    _foto(plan, foto, SAYFA - GUVENLI - en, 108.0, en, boy, 0.34, 0.44)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="FEMISIA", x=GUVENLI,
              y=172.0, en=100.0, renk=MUR, punto=11.0, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["tanim"], 120),
              x=GUVENLI, y=182.0, en=118.0, renk=(0.26, 0.26, 0.28),
              punto=6.6, satir_pt=8.6, azami_satir=3)
    _not_alani(plan, GUVENLI, 204.0, 100.0, satir=1)
    return _meta(plan, kernel="femisia",
                 koreografi="FIRST=kahraman bilesen · SECOND=ikincil "
                            "bilesen rayi · THIRD=urun · TECHNICAL=INCI "
                            "adlari · UTILITY=not alani",
                 iliski="NEUTRAL_ISOLATION",
                 repertuar="INGREDIENT_NOMENCLATURE",
                 bosluk="ACTIVE -- kahraman bilesenin ustundeki bosluk "
                        "olcegi kuruyor",
                 gerekli_icerik=["one_cikan", "tanim"],
                 urun_olcegi="KUCUK", enerji="botanik",
                 fikir="Formulun kahramani urunden once gelir; urun onun "
                       "tasiyicisidir.",
                 tur3_farki="Tur 3'te bilesen adlari hic gorunmuyordu.")


# =======================================================================
# BABYSOL -- kernel: "Koruma gorunmez; gorunen tek sey ondan sonraki gun."
# Gercek icerik: tanim, kullanim, ZORUNLU uyari, INCI TR+EN,
# bilesen tablosu ORANLARIYLA (cinko oksit %30).
# Net miktar CELISKILI -- basilmaz.
# =======================================================================

def b1_otuz(d: dict, foto: str) -> rd.SayfaPlani:
    """%30 -- gercek cinko oksit orani number-driven kompozisyon olur."""
    en, boy = 100.0, 133.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("daily-care", "v2_otuz", dpi)
    _zemin(plan, (236, 240, 244))
    _foto(plan, foto, SAYFA - en, 52.0, en, boy, 0.36, 0.46)
    plan.ekle("metin", stil="devasa", metin="%30", x=GUVENLI, y=104.0,
              en=104.0, renk=MUR, punto=56.0, satir_pt=58.0, azami_satir=1)
    tr, inci, oran = d["one_cikan"][0]
    plan.ekle("metin", stil="urun_ad_kucuk", metin=tr, x=GUVENLI + 2.0,
              y=116.0, en=100.0, renk=MUR, punto=11.0, azami_satir=1)
    plan.ekle("metin", stil="inci", metin=inci, x=GUVENLI + 2.0, y=123.0,
              en=100.0, renk=SOLUK, punto=6.2, azami_satir=1)
    plan.ekle("metin", stil="urun_ad", metin="BABYSOL", x=GUVENLI, y=36.0,
              en=IC, renk=MUR, punto=19.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"], x=GUVENLI,
              y=44.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="inci", metin=d["uyari"], x=GUVENLI, y=170.0,
              en=104.0, renk=(0.30, 0.32, 0.36), punto=5.8, satir_pt=7.4,
              azami_satir=6)
    _not_alani(plan, SAYFA - GUVENLI - 92.0, 196.0, 92.0, satir=2)
    return _meta(plan, kernel="babysol",
                 koreografi="FIRST=oran · SECOND=urun adi · "
                            "THIRD=urun karesi · TECHNICAL=zorunlu uyari · "
                            "UTILITY=not alani",
                 iliski="COMPLEMENTARY_CONTRAST", repertuar="NUMBER_DRIVEN",
                 bosluk="ACTIVE -- oranin etrafi bos",
                 gerekli_icerik=["uyari", "one_cikan"],
                 urun_olcegi="ORTA", enerji="kesin",
                 fikir="Fiziksel filtre bir orandir: %30 non-nano cinko "
                       "oksit. Sayfa iddiayi degil orani gosterir.",
                 tur3_farki="Tur 3 SPF 50+ yaziyordu; burada gosterilen sey "
                            "formulun kendisi.")


def b2_zorunlu_metin(d: dict, foto: str) -> rd.SayfaPlani:
    """ZORUNLU METIN -- mevzuat metni sayfanin baskin tipografik ogesi."""
    en, boy = 84.0, 112.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("daily-care", "v2_zorunlu_metin", dpi)
    # J · PHOTOGRAPHIC_CONTINUATION: karenin mavi-gri fonu sayfaya
    # tasindi; sari urun boylece tek renk kaynagi olarak kaliyor.
    _zemin(plan, (218, 228, 236))
    _foto(plan, foto, SAYFA - GUVENLI - en, 34.0, en, boy, 0.36, 0.46)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="BABYSOL", x=GUVENLI,
              y=40.0, en=96.0, renk=MUR, punto=12.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"], x=GUVENLI,
              y=47.0, en=96.0, renk=SOLUK, punto=5.6, azami_satir=1)
    # CRITIC (CRAFT REVISE): 11 satirlik uyari duvari nefes birakmiyordu.
    # Punto korundu, satir araligi 13 -> 14.5 acildi, satir sayisi 8'e
    # indirildi ve metin cumle sinirinda kesildi.
    plan.ekle("metin", stil="alt_baslik", metin=ic2.kisalt(d["uyari"], 300),
              x=GUVENLI, y=66.0, en=96.0, renk=MUR, punto=9.0, satir_pt=14.5,
              azami_satir=8)
    plan.ekle("cizgi", x=GUVENLI, y=166.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif", metin=ic2.kisalt(d["kullanim"], 140),
              x=GUVENLI, y=176.0, en=118.0, renk=(0.26, 0.26, 0.28),
              punto=6.8, satir_pt=8.8, azami_satir=3)
    _not_alani(plan, SAYFA - GUVENLI - 66.0, 176.0, 66.0, satir=2)
    return _meta(plan, kernel="babysol",
                 koreografi="FIRST=zorunlu uyari · SECOND=urun adi · "
                            "THIRD=kullanim · UTILITY=not alani",
                 iliski="NO_REPETITION", repertuar="MONUMENTAL_DISPLAY",
                 bosluk="ACTIVE -- uyari blogunun genis satir araligi",
                 gerekli_icerik=["uyari", "kullanim"],
                 urun_olcegi="ORTA", enerji="ciddi",
                 fikir="Mevzuat metni yuk degil; gunes urununde soylenecek "
                       "en dogru sey zaten odur.",
                 tur3_farki="Tur 3 uyariyi koyu bandin icinde 6.4 punto "
                            "mikro metin yapmisti; burada 9 punto ve "
                            "sayfanin baskin ogesi.")


def b3_onbes_dakika(d: dict, foto: str) -> rd.SayfaPlani:
    """15 DAKIKA -- kullanim metnindeki gercek sure sayfanin fikri olur."""
    dpi = _dpi_kur(foto, SAYFA, 128.0, 0.84)
    plan = rd.SayfaPlani("daily-care", "v2_onbes_dakika", dpi)
    _zemin(plan, (252, 250, 245))
    plan.ekle("foto", kaynak=foto,
              kadraj=kadraj(foto, SAYFA, 128.0, 0.38, 0.46, 0.84),
              x=0.0, y=60.0, en=SAYFA, boy=128.0, tuy_px=0)
    plan.ekle("metin", stil="devasa", metin="15", x=GUVENLI, y=44.0,
              en=60.0, renk=MUR, punto=40.0, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="DAKİKA ÖNCE",
              x=GUVENLI + 34.0, y=44.0, en=90.0, renk=MUR, punto=11.0,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="GÜNEŞE ÇIKMADAN",
              x=GUVENLI + 34.0, y=36.0, en=90.0, renk=SOLUK, punto=5.8,
              azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="BABYSOL",
              x=SAYFA - GUVENLI - 70.0, y=44.0, en=70.0, renk=MUR,
              punto=12.0, azami_satir=1, hiza="sag")
    plan.ekle("metin", stil="inci", metin=d["uyari"], x=GUVENLI, y=196.0,
              en=130.0, renk=SOLUK, punto=5.6, satir_pt=7.0, azami_satir=3)
    _not_alani(plan, SAYFA - GUVENLI - 58.0, 196.0, 58.0, satir=2)
    return _meta(plan, kernel="babysol",
                 koreografi="FIRST=sure · SECOND=fotograf · "
                            "THIRD=urun adi · TECHNICAL=zorunlu uyari · "
                            "UTILITY=not alani",
                 iliski="PHOTOGRAPHIC_CONTINUATION", repertuar="NUMBER_DRIVEN",
                 bosluk="ACTIVE -- ust seritteki bosluk sureyi yalniz "
                        "birakiyor",
                 gerekli_icerik=["kullanim", "uyari"],
                 urun_olcegi="BUYUK", enerji="zamansal",
                 fikir="Koruma bir andan once baslar: 15 dakika. Sayfanin "
                       "konusu urun degil o araliktir.",
                 tur3_farki="Tur 3 ad+SPF ikilisini kullandi; burada sayfayi "
                            "bir SURE kuruyor.")


def b4_filtre(d: dict, foto: str, foto2: str) -> rd.SayfaPlani:
    """FILTRE -- fiziksel filtre katmanli kompozisyonla anlatilir."""
    dpi = min(_dpi_kur(foto, SAYFA, 76.0), _dpi_kur(foto2, SAYFA, 76.0))
    plan = rd.SayfaPlani("daily-care", "v2_filtre", dpi)
    _zemin(plan, (245, 243, 238))
    plan.ekle("foto", kaynak=foto, kadraj=kadraj(foto, SAYFA, 76.0, 0.38, 0.40),
              x=0.0, y=30.0, en=SAYFA, boy=76.0, tuy_px=0)
    plan.ekle("foto", kaynak=foto2, kadraj=kadraj(foto2, SAYFA, 76.0, 0.40, 0.56),
              x=0.0, y=112.0, en=SAYFA, boy=76.0, tuy_px=0)
    plan.ekle("metin", stil="not_etiketi", metin="YÜZEYDE KALAN KATMAN",
              x=GUVENLI, y=24.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="BABYSOL", x=GUVENLI,
              y=200.0, en=90.0, renk=MUR, punto=12.0, azami_satir=1)
    plan.ekle("metin", stil="inci", metin=ic2.kisalt(d["uyari"], 190),
              x=GUVENLI + 96.0, y=196.0, en=IC - 96.0, renk=SOLUK, punto=5.6,
              satir_pt=7.0, azami_satir=3)
    return _meta(plan, kernel="babysol",
                 koreografi="FIRST=iki katman · SECOND=urun adi · "
                            "TECHNICAL=zorunlu uyari · UTILITY=yok",
                 iliski="MATERIAL_DERIVATION", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- iki katman arasindaki serit filtreyi "
                        "gorsellestiriyor",
                 gerekli_icerik=["uyari"],
                 urun_olcegi="ORTA", enerji="katmanli",
                 fikir="Fiziksel filtre yuzeyde kalir. Sayfa iki katmana "
                       "bolunur ve aradaki bosluk filtredir.",
                 tur3_farki="Tur 3 tek ust bant + koyu alan kullandi; burada "
                            "iki esit katman ve aralarinda bosluk var.")


def b5_gunden_sonra(d: dict, foto: str) -> rd.SayfaPlani:
    """GUNDEN SONRA -- urun kucuk, isik alani genis."""
    en, boy = 56.0, 75.0
    dpi = _dpi_kur(foto, en, boy)
    plan = rd.SayfaPlani("daily-care", "v2_gunden_sonra", dpi)
    _zemin(plan, (247, 243, 232))
    _foto(plan, foto, GUVENLI, SAYFA - GUVENLI - boy, en, boy, 0.36, 0.46)
    plan.ekle("metin", stil="alt_baslik", metin=ic2.kisalt(d["tanim"], 130),
              x=GUVENLI, y=58.0, en=126.0, renk=MUR, punto=11.0,
              satir_pt=16.0, azami_satir=5)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="BABYSOL",
              x=SAYFA - GUVENLI - 80.0, y=SAYFA - GUVENLI - 60.0, en=80.0,
              renk=MUR, punto=12.0, azami_satir=1, hiza="sag")
    plan.ekle("metin", stil="not_etiketi", metin=d["kategori"],
              x=SAYFA - GUVENLI - 80.0, y=SAYFA - GUVENLI - 53.0, en=80.0,
              renk=SOLUK, punto=5.6, azami_satir=1, hiza="sag")
    plan.ekle("metin", stil="inci", metin=ic2.kisalt(d["uyari"], 200),
              x=SAYFA - GUVENLI - 80.0, y=SAYFA - GUVENLI - 40.0, en=80.0,
              renk=SOLUK, punto=5.6, satir_pt=7.0, azami_satir=5)
    return _meta(plan, kernel="babysol",
                 koreografi="FIRST=tek cumle · SECOND=urun · "
                            "THIRD=zorunlu uyari · UTILITY=yok",
                 iliski="TONAL_CONTINUITY", repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- ust alan isigin kendisi",
                 gerekli_icerik=["tanim", "uyari"],
                 urun_olcegi="KUCUK", enerji="sakin",
                 fikir="Koruma gorunmez; sayfanin cogu bos isik alani, urun "
                       "kosede.",
                 tur3_farki="Tur 3 urunu tam genislik bandinda BUYUK "
                            "gosteriyordu; bu onun tersi.")
