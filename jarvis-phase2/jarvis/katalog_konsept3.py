"""TUR 3 -- katalog dizisi olarak tasarlanmis bes sayfa.

Altyapi degismedi: ayni render motoru, ayni kapilar, ayni tasarim
sistemi. Degisen iki sey:

1) ASET HAVUZU. Sayfalar artik Wix urun sayfalarinin parlak krem
   e-ticaret gorselleriyle degil, Creative Asset Library'deki GERCEK
   studyo cekimiyle kuruluyor (mavi-gri sonsuz fon, gercek golge).

2) DIZI. Sayfalar tek tek degil, bir koreografi olarak tasarlandi:
   renk / isik / yogunluk / urun olcegi / tipografik olcek ritmi
   sayfadan sayfaya bilincli olarak degisiyor.

FIZIKSEL KISIT -- tasarimi bu belirledi:
   Studyo arsivi 1800x1200 px. Yukari ornekleme yasak oldugu icin
   150 DPI tabani su siniri koyuyor:
       en  <= 1800*25.4/150 = 305 mm
       boy <= 1200*25.4/150 = 203 mm
   Yani TAM TASMA KARE (216x216) bu arsivden IMKANSIZ (141 DPI).
   Cozum tavizle degil malzemeyle verildi: fotograf kendi 3:2
   cercevesini koruyan tam genislik bandi (216x144 -> 212 DPI) ya da
   yuksekligi 200 mm'yi asmayan kolon olarak kullaniliyor.
"""
from __future__ import annotations

from jarvis import katalog_render as rd
from jarvis import katalog_tasarim_sistemi as ts
from jarvis.katalog_konsept import Icerik

SAYFA = ts.SAYFA_MM          # 216
GUVENLI = 11.0               # kesimden 8 mm ice
BANT = 144.0                 # 216 mm genislikte 3:2 bandin yuksekligi

# Dizi rolleri -- CATALOG SEQUENCE DIRECTOR (ECD capability) kaydi
DIZI = {
    "cover":        dict(sira=1, rol="visual_opening", isik="acik",
                         yogunluk="orta", urun_olcegi="orta", insan=False),
    "hydravie":     dict(sira=2, rol="technical_quiet", isik="acik",
                         yogunluk="yuksek", urun_olcegi="kucuk", insan=False),
    "kinesis":      dict(sira=3, rol="hero_interruption", isik="KOYU",
                         yogunluk="dusuk", urun_olcegi="buyuk", insan=True),
    "private-care": dict(sira=4, rol="material_pair", isik="acik",
                         yogunluk="orta", urun_olcegi="orta", insan=False),
    "daily-care":   dict(sira=5, rol="bright_close", isik="karma",
                         yogunluk="orta", urun_olcegi="orta", insan=False),
}


# --- yardimcilar ---------------------------------------------------------

def _olcu(yol: str) -> tuple[int, int]:
    from PIL import Image
    with Image.open(yol) as im:
        return im.size


def azami_dpi(yol: str, en_mm: float, boy_mm: float) -> float:
    """Yukari ornekleme yapmadan ulasilabilen azami yerlesim DPI'i."""
    w, h = _olcu(yol)
    return min(w * 25.4 / en_mm, h * 25.4 / boy_mm)


def kadraj(yol: str, en_mm: float, boy_mm: float,
           odak_x: float = 0.5, odak_y: float = 0.5,
           sik: float = 1.0) -> dict:
    """Yerlesim oranina BIREBIR esit kadraj kutusu uretir.

    Kadraj orani yerlesim oranindan saparsa render motoru dogru
    olarak reddediyor; bu yuzden oran burada zorlanir.

    sik < 1.0 kadraji daraltir (yakinlastirir) ve odaga yeniden
    ortalar -- fotografin bos zemin tarafini disarida birakmak icin.
    Daraltma DPI'i dusurur; cagiran taraf _dpi_kur ile dogrular.
    """
    w, h = _olcu(yol)
    hedef = en_mm / boy_mm
    kw, kh = w, h
    if w / h > hedef:
        kw = h * hedef
    else:
        kh = w / hedef
    kw *= sik
    kh *= sik
    fx, fy = kw / w, kh / h
    x0 = min(max(odak_x - fx / 2, 0.0), 1.0 - fx)
    y0 = min(max(odak_y - fy / 2, 0.0), 1.0 - fy)
    return {"ad": "dizi_kadraji", "x": round(x0, 4), "y": round(y0, 4),
            "en": round(fx, 4), "boy": round(fy, 4),
            "piksel": [int(round(kw)), int(round(kh))]}


def _dpi_kur(yol: str, en_mm: float, boy_mm: float,
             sik: float = 1.0) -> float:
    d = azami_dpi(yol, en_mm, boy_mm) * sik
    if d < ts.SAHNE_TABAN_DPI:
        raise ValueError(
            "%s: %.0fx%.0f mm yerlesim %.0f DPI verir, taban %.0f"
            % (yol, en_mm, boy_mm, d, ts.SAHNE_TABAN_DPI))
    return min(d, ts.HEDEF_DPI)


# =========================================================================
# 1 · KAPAK -- UC URUN BANDI
#     Uc gercek urun rengi yan yana. Tur 2'nin kusuru: uc "malzeme"
#     seridinin ucu de kremdi, tek serit gibi okunuyordu. Burada uc
#     bant uc AYRI urun renginden geliyor: sari / kirmizi-mavi / lime.
# =========================================================================

def kapak_uc_urun(ic: Icerik, palet: dict,
                  panolar: list[tuple[str, str]]) -> rd.SayfaPlani:
    """panolar: [(foto_yolu, kategori_etiketi, odak_x)] -- uc urun ailesi."""
    # OLCULDU: pano 70x144 iken kadraj genisligi kaynagin yalnizca
    # %32.4'unu aliyordu; urun kutulari %46-56 genisliginde oldugu icin
    # logotype kelime ortasindan kesiliyordu ("ARLIE", "FEMISI").
    # Pano orani urunu TAM icine alacak sekilde yeniden hesaplandi:
    # kadraj genisligi = 1200*(70/83)/1800 = %56.2 > en genis urun.
    bosluk = 3.0
    pano_en = (SAYFA - 2 * bosluk) / 3.0        # 70 mm
    pano_boy = 83.0
    ust = 64.0

    dpi = min(_dpi_kur(p[0], pano_en, pano_boy) for p in panolar[:3])
    dpi = min(dpi, ts.HEDEF_DPI)
    plan = rd.SayfaPlani("cover", "uc_urun_bandi", dpi)

    zemin = (250, 249, 247)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=zemin)

    for i, (yol, etiket, odak) in enumerate(panolar[:3]):
        x = i * (pano_en + bosluk)
        plan.ekle("foto", kaynak=yol,
                  kadraj=kadraj(yol, pano_en, pano_boy, odak, 0.5),
                  x=x, y=ust, en=pano_en, boy=pano_boy, tuy_px=0)
        plan.ekle("metin", stil="not_etiketi", metin=etiket,
                  x=x + (GUVENLI if i == 0 else 1.0), y=ust + pano_boy + 7.0,
                  en=pano_en - 2.0, renk=(0.12, 0.12, 0.14), punto=5.8,
                  azami_satir=1)

    m = (0.09, 0.09, 0.11)
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ",
              x=GUVENLI, y=24.0, en=SAYFA - 2 * GUVENLI, renk=m,
              punto=30.0, satir_pt=31.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="DERMOKOZMETİK ÜRÜN KATALOĞU",
              x=GUVENLI, y=33.0, en=140.0, renk=(0.34, 0.34, 0.37), punto=6.2,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="36 ÜRÜN · 9 BAKIM AİLESİ · 2026",
              x=GUVENLI, y=SAYFA - GUVENLI - 2.0, en=140.0,
              renk=(0.34, 0.34, 0.37), punto=6.2, azami_satir=1)

    plan.olcumler = {"tip": "KAPAK_uc_urun_bandi", "pano_sayisi": 3,
                     "urun_en_mm": round(pano_en, 1), "urun_boy_mm": pano_boy,
                     "urun_dpi": round(dpi, 1), "kadraj": "dizi_kadraji",
                     "mansert": False, "baskin_oge": "uc_urun_panosu",
                     "dizi": DIZI["cover"]}
    return plan


# =========================================================================
# 2 · HYDRAVIE -- NUMUNE FOYU
#     Tur 2'de calisan tek sayfa. Fikir korundu, aset degisti:
#     krem e-ticaret karesi -> soguk mavi-gri studyo cekimi.
# =========================================================================

def hydravie_numune_foyu(ic: Icerik, palet: dict,
                         tablo: list[tuple[str, str]]) -> rd.SayfaPlani:
    # OLCULDU: 73x200 mm dar dikey kolon, YATAY duran kutunun yazisini
    # ortasindan kesiyordu ("L'CARL", "YDRAVIE"). Kaynak 1800x1200 ve
    # kutu karenin %46'si genisliginde; 73:200 oranindaki bir kadraj
    # kaynagin yalnizca %36.5'ini alabiliyor -- kutu ASLA sigmaz.
    # Cozum: fotograf kare bloga alindi (kadraj kaynagin %66.7'si),
    # tablo da tam genislige acilarak daha da baskin hale geldi.
    blok = 88.0
    blok_x = SAYFA - blok
    dpi = _dpi_kur(ic.kaynak_foto, blok, blok)
    plan = rd.SayfaPlani("hydravie", "numune_foyu", dpi)

    zemin = (222, 230, 238)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=zemin)
    plan.ekle("foto", kaynak=ic.kaynak_foto,
              kadraj=kadraj(ic.kaynak_foto, blok, blok, 0.36, 0.34),
              x=blok_x, y=0.0, en=blok, boy=blok, tuy_px=0)

    mur = (0.10, 0.12, 0.16)
    sol = GUVENLI
    bas_en = blok_x - GUVENLI - 10.0

    plan.ekle("metin", stil="not_etiketi", metin="NUMUNE FÖYÜ · 01",
              x=sol, y=22.0, en=bas_en, renk=(0.38, 0.42, 0.48), punto=6.0,
              azami_satir=1)
    plan.ekle("metin", stil="urun_ad", metin=ic.ad,
              x=sol, y=36.0, en=bas_en, renk=mur, punto=19.0, satir_pt=20.0,
              azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin=ic.alt_ad,
              x=sol, y=45.0, en=bas_en, renk=(0.30, 0.34, 0.40), punto=8.0,
              azami_satir=2)

    # Tablo TAM GENISLIK -- sayfanin baskin ogesi
    en = SAYFA - 2 * GUVENLI
    y = 104.0
    plan.ekle("cizgi", x=sol, y=y - 4.0, en=en, renk=mur, kalinlik=0.5)
    plan.ekle("metin", stil="not_etiketi", metin="İÇERİK",
              x=sol, y=y, en=52.0, renk=(0.38, 0.42, 0.48), punto=5.8,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="İŞLEVİ",
              x=sol + 56.0, y=y, en=en - 56.0, renk=(0.38, 0.42, 0.48),
              punto=5.8, azami_satir=1)
    y += 7.5
    for ad, islev in tablo:
        plan.ekle("cizgi", x=sol, y=y - 2.0, en=en, renk=(0.62, 0.66, 0.72),
                  kalinlik=0.3)
        plan.ekle("metin", stil="alt_yazi", metin=ad,
                  x=sol, y=y + 4.5, en=52.0, renk=mur, punto=7.2,
                  azami_satir=1)
        plan.ekle("metin", stil="govde_hafif", metin=islev,
                  x=sol + 56.0, y=y + 4.5, en=en - 56.0,
                  renk=(0.22, 0.26, 0.32), punto=7.0, satir_pt=8.8,
                  azami_satir=1)
        y += 12.0

    plan.ekle("cizgi", x=sol, y=y - 2.0, en=en, renk=mur, kalinlik=0.5)
    plan.ekle("metin", stil="govde_hafif", metin=ic.govde,
              x=sol, y=y + 9.0, en=126.0, renk=(0.20, 0.24, 0.30), punto=7.4,
              satir_pt=10.4, azami_satir=3)

    plan.ekle("not_alani", x=sol, y=SAYFA - GUVENLI - 15.0, en=118.0,
              etiket="SAHA NOTU", renk=(0.42, 0.46, 0.52))
    plan.ekle("metin", stil="not_etiketi", metin=ic.hacim,
              x=SAYFA - GUVENLI - 24.0, y=SAYFA - GUVENLI - 2.0, en=24.0,
              renk=(0.38, 0.42, 0.48), punto=6.0, azami_satir=1, hiza="sag")

    plan.olcumler = {"tip": "veri_foyu", "urun_en_mm": blok,
                     "urun_boy_mm": blok, "urun_dpi": round(dpi, 1),
                     "kadraj": "kare_blok", "mansert": False,
                     "baskin_oge": "icerik_tablosu", "dizi": DIZI["hydravie"]}
    return plan


# =========================================================================
# 3 · KINESIS+ -- SALON
#     Dizinin omurgasi: tek KOYU sayfa, tek insan karesi.
#     OLCULDU: karenin sol-alt cegregi L=7..54 -- ters tipografi oraya.
#     (Tur 2 tasarisi metni sol-UST'e koyuyordu; orasi pencere, L=212+.)
# =========================================================================

def kinesis_salon(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    yan = 212.0
    kenar = (SAYFA - yan) / 2.0
    dpi = _dpi_kur(ic.kaynak_foto, yan, yan)
    plan = rd.SayfaPlani("kinesis", "salon", dpi)

    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=(22, 24, 27))
    plan.ekle("foto", kaynak=ic.kaynak_foto,
              kadraj=kadraj(ic.kaynak_foto, yan, yan, 0.5, 0.5),
              x=kenar, y=kenar, en=yan, boy=yan, tuy_px=0)

    b = (1.0, 1.0, 1.0)
    taban = SAYFA - GUVENLI
    plan.ekle("metin", stil="urun_ad", metin=ic.ad,
              x=GUVENLI, y=taban - 34.0, en=110.0, renk=b,
              punto=20.0, satir_pt=21.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=taban - 29.0, en=28.0, renk=b, kalinlik=0.8)
    plan.ekle("metin", stil="not_etiketi", metin=ic.alt_ad,
              x=GUVENLI, y=taban - 20.0, en=104.0, renk=(0.86, 0.87, 0.88),
              punto=6.4, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif", metin=ic.mikro,
              x=GUVENLI, y=taban - 11.0, en=104.0, renk=(0.80, 0.82, 0.84),
              punto=6.6, satir_pt=8.8, azami_satir=2)
    plan.ekle("metin", stil="not_etiketi", metin=ic.hacim,
              x=SAYFA - GUVENLI - 24.0, y=taban - 2.0, en=24.0, renk=b,
              punto=6.2, azami_satir=1)

    plan.olcumler = {"tip": "salon", "urun_en_mm": yan, "urun_boy_mm": yan,
                     "urun_dpi": round(dpi, 1), "kadraj": "tam",
                     "mansert": False, "baskin_oge": "fotograf",
                     "ters_tipografi": True, "dizi": DIZI["kinesis"]}
    return plan


# =========================================================================
# 4 · FEMISIA / VIREON -- CIFT
#     Tek fotografta iki urun: kadinlara ve erkeklere. Katalogda
#     baska hicbir sayfanin yapamadigi sey -- ikili anlati tek karede.
#     Bant SAYFANIN ORTASINDA yuzer: ustunde ve altinda zemin var.
# =========================================================================

def femisia_cift(ic: Icerik, palet: dict, sag: dict) -> rd.SayfaPlani:
    # OLCULDU: bant y=36'da iken alttaki iki kolon govde metni guvenli
    # alani 5 pt asiyordu (4 durduran ihlal) ve INCI 5.4 pt ile 5.5
    # tabanin altina dusuyordu. Bant yukari alindi, govde iki satira
    # sabitlendi, INCI 5.6 pt'ye cikarildi.
    bant_y = 22.0
    # OLCULDU: tam kare (sik=1.0) kaynagin bos zemin tarafini da
    # sayfaya tasiyordu; bandin sag ucte biri olu mavi alandi.
    sik = 0.82
    dpi = _dpi_kur(ic.kaynak_foto, SAYFA, BANT, sik)
    plan = rd.SayfaPlani("private-care", "cift", dpi)

    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=(250, 249, 247))
    plan.ekle("foto", kaynak=ic.kaynak_foto,
              kadraj=kadraj(ic.kaynak_foto, SAYFA, BANT, 0.38, 0.48, sik),
              x=0.0, y=bant_y, en=SAYFA, boy=BANT, tuy_px=0)

    mur = (0.10, 0.10, 0.12)
    sol_renk = (0.38, 0.38, 0.41)
    plan.ekle("metin", stil="not_etiketi", metin="HASSAS BÖLGE BAKIMI · İKİ FORMÜL",
              x=GUVENLI, y=16.0, en=SAYFA - 2 * GUVENLI, renk=sol_renk,
              punto=6.2, azami_satir=1)

    orta = SAYFA / 2.0
    ty = bant_y + BANT + 12.0
    kol = orta - GUVENLI - 6.0
    plan.ekle("cizgi", x=orta, y=ty - 6.0, en=0.0, boy=34.0,
              renk=(0.72, 0.72, 0.75), kalinlik=0.4)

    for x0, ad, alt, govde in (
            (GUVENLI, ic.ad, ic.alt_ad, ic.govde),
            (orta + 6.0, sag["ad"], sag["alt_ad"], sag["govde"])):
        plan.ekle("metin", stil="urun_ad_kucuk", metin=ad,
                  x=x0, y=ty, en=kol, renk=mur, punto=12.5, satir_pt=13.5,
                  azami_satir=1)
        plan.ekle("metin", stil="not_etiketi", metin=alt,
                  x=x0, y=ty + 7.0, en=kol, renk=sol_renk, punto=5.8,
                  azami_satir=1)
        plan.ekle("metin", stil="govde_hafif", metin=govde,
                  x=x0, y=ty + 14.0, en=kol, renk=(0.22, 0.22, 0.26),
                  punto=7.0, satir_pt=9.6, azami_satir=2)

    plan.ekle("metin", stil="inci", metin=ic.inci,
              x=GUVENLI, y=SAYFA - GUVENLI - 3.0, en=SAYFA - 2 * GUVENLI,
              renk=(0.46, 0.46, 0.50), punto=5.6, satir_pt=7.2, azami_satir=1)

    plan.olcumler = {"tip": "cift", "urun_en_mm": SAYFA, "urun_boy_mm": BANT,
                     "urun_dpi": round(dpi, 1), "kadraj": "tam_genislik_bandi",
                     "mansert": False, "baskin_oge": "ikili_fotograf",
                     "dizi": DIZI["private-care"]}
    return plan


# =========================================================================
# 5 · BABYSOL -- ALT BANT
#     Dizinin kapanisi. Fotograf ust bant, altta KOYU alan: zorunlu
#     gunes uyarisi artik sayfaya sonradan yapistirilmis soluk bir
#     kutu degil, kapanisin kendisi.
# =========================================================================

def babysol_alt_bant(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    sik = 0.80          # olu mavi alani disarida birak, kutuya yaklas
    dpi = _dpi_kur(ic.kaynak_foto, SAYFA, BANT, sik)
    plan = rd.SayfaPlani("daily-care", "alt_bant", dpi)

    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=(24, 27, 32))
    plan.ekle("foto", kaynak=ic.kaynak_foto,
              kadraj=kadraj(ic.kaynak_foto, SAYFA, BANT, 0.39, 0.46, sik),
              x=0.0, y=0.0, en=SAYFA, boy=BANT, tuy_px=0)

    b = (1.0, 1.0, 1.0)
    soluk = (0.78, 0.80, 0.82)
    y = BANT + 18.0
    plan.ekle("metin", stil="urun_ad", metin=ic.ad,
              x=GUVENLI, y=y, en=120.0, renk=b, punto=24.0, satir_pt=25.0,
              azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin="SPF 50+",
              x=GUVENLI + 92.0, y=y, en=44.0, renk=b, punto=13.0,
              azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=ic.alt_ad,
              x=GUVENLI, y=y + 9.0, en=SAYFA - 2 * GUVENLI, renk=soluk,
              punto=6.2, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=y + 15.0, en=SAYFA - 2 * GUVENLI,
              renk=(0.42, 0.45, 0.50), kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif", metin=ic.uyari,
              x=GUVENLI, y=y + 22.0, en=118.0, renk=soluk, punto=6.4,
              satir_pt=8.6, azami_satir=3)
    plan.ekle("not_alani", x=GUVENLI + 128.0, y=y + 22.0, en=58.0,
              etiket="SAHA NOTU", renk=(0.62, 0.65, 0.70))
    plan.ekle("metin", stil="not_etiketi", metin=ic.hacim,
              x=SAYFA - GUVENLI - 24.0, y=y + 9.0, en=24.0, renk=soluk,
              punto=6.2, azami_satir=1)

    plan.olcumler = {"tip": "alt_bant", "urun_en_mm": SAYFA,
                     "urun_boy_mm": BANT, "urun_dpi": round(dpi, 1),
                     "kadraj": "tam_genislik_bandi", "mansert": False,
                     "baskin_oge": "ad_ve_spf", "zorunlu_uyari": True,
                     "dizi": DIZI["daily-care"]}
    return plan


# =========================================================================
# 6 · TICARI SKU KATMANI -- EDITORYAL SAYFADAN AYRI
#     Fiyat ve barkod editoryal kompozisyona GIRMEZ. Boylece fiyat
#     degistiginde premium katalogun tamami eskimez; yalnizca bu
#     katman yeniden basilir.
# =========================================================================

def sku_indeksi(satirlar: list[dict], baslik: str = "ÜRÜN İNDEKSİ") -> rd.SayfaPlani:
    plan = rd.SayfaPlani("sku-index", "ticari_katman", 300.0)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=(247, 246, 243))
    mur = (0.10, 0.10, 0.12)
    soluk = (0.42, 0.42, 0.46)

    plan.ekle("metin", stil="not_etiketi", metin="TİCARİ KATMAN · B",
              x=GUVENLI, y=22.0, en=120.0, renk=soluk, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin=baslik,
              x=GUVENLI, y=32.0, en=160.0, renk=mur, punto=13.0, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin="Bu sayfa editoryal ürün sayfalarından ayrıdır. Fiyat "
                    "güncellendiğinde yalnızca bu form yeniden basılır; "
                    "katalogun tamamı geçerliliğini korur.",
              x=GUVENLI, y=41.0, en=SAYFA - 2 * GUVENLI, renk=soluk,
              punto=7.0, satir_pt=9.4, azami_satir=3)

    en = SAYFA - 2 * GUVENLI
    kol = [GUVENLI, GUVENLI + 58.0, GUVENLI + 106.0,
           GUVENLI + 132.0, GUVENLI + 158.0]
    y = 62.0
    plan.ekle("cizgi", x=GUVENLI, y=y - 4.0, en=en, renk=mur, kalinlik=0.5)
    basliklar = ("ÜRÜN", "BARKOD / SKU", "HACİM", "SİPARİŞ KODU",
                 "BAYİ FİYATI")
    for x0, b in zip(kol, basliklar, strict=True):
        plan.ekle("metin", stil="not_etiketi", metin=b, x=x0, y=y,
                  en=56.0, renk=soluk, punto=5.6, azami_satir=1)
    y += 8.0
    for s in satirlar:
        plan.ekle("cizgi", x=GUVENLI, y=y - 2.5, en=en,
                  renk=(0.70, 0.70, 0.74), kalinlik=0.3)
        for x0, v, stil, pt in (
                (kol[0], s["ad"], "alt_yazi", 7.0),
                (kol[1], s["sku"], "govde_hafif", 6.8),
                (kol[2], s["hacim"], "govde_hafif", 6.8),
                (kol[3], s["kod"], "govde_hafif", 6.8),
                (kol[4], s["fiyat"], "govde_hafif", 6.8)):
            plan.ekle("metin", stil=stil, metin=v, x=x0, y=y + 3.5,
                      en=56.0, renk=mur if stil == "alt_yazi" else (0.24, 0.24, 0.28),
                      punto=pt, azami_satir=1)
        y += 11.0

    plan.ekle("cizgi", x=GUVENLI, y=y - 2.5, en=en, renk=mur, kalinlik=0.5)
    plan.ekle("metin", stil="inci",
              metin="Barkod/SKU kaynağı: ürün künyesi (kunye.json). "
                    "Bayi fiyatı bu turda DOLDURULMADI -- fiyat otoritesi "
                    "Wix PSF'i olup kademe hesabı ayrı karardır.",
              x=GUVENLI, y=y + 10.0, en=en, renk=soluk, punto=5.6,
              satir_pt=7.4, azami_satir=3)
    plan.ekle("not_alani", x=GUVENLI, y=SAYFA - GUVENLI - 14.0, en=en - 40.0,
              etiket="SİPARİŞ NOTU", renk=soluk)

    plan.olcumler = {"tip": "ticari_katman", "satir": len(satirlar),
                     "urun_en_mm": 0.0, "urun_boy_mm": 0.0, "urun_dpi": 300.0,
                     "kadraj": "yok", "mansert": False,
                     "baskin_oge": "sku_tablosu"}
    return plan
