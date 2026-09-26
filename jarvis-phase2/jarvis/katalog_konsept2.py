"""TUR 2 -- secilen bes creative direction.

Tur 1 reddedildi: bes sayfa farkli geometri ama AYNI bilgi
koreografisi kullaniyordu (etiket -> mansert -> ad -> aciklama ->
INCI -> not -> gorsel). Burada her sayfanin okuma sirasi farklidir
ve HICBIRINDE grotesk mansert yoktur.

COZUNURLUK SOZLESMESI -- iki ayri taban:
    URUN_TABAN_DPI (200)  urun NESNE olarak kesilip yerlestirildiginde
    SAHNE_TABAN_DPI (150) TYPE A editoryal fotograf BUTUN olarak
                          cogaltildiginda

    Ayrim ilkeseldir: ikinci durumda bir FOTOGRAF cogaltiliyor, bir
    urun izole edilmiyor. Kaynaklar 1254 px oldugu icin hicbir
    yerlesim 216 mm'ye 150 DPI'in ustunde ulasamaz; bu yuzden
    "tam tasma" sayfalarda goruntu 212 mm'dir ve kesim kutusunu
    (3..213 mm) TAM kapatir.

BU MODUL YENI ALTYAPI KULLANMAZ. Mevcut SayfaPlani ogeleri:
alan / foto / metin / cizgi / not_alani.
"""

from __future__ import annotations

from jarvis import katalog_render as rd
from jarvis import katalog_tasarim_sistemi as ts
from jarvis.katalog_konsept import Icerik  # noqa: F401  (tip icin)

SAYFA = ts.SAYFA_MM          # 216
KESIM0, KESIM1 = 3.0, 213.0
GUVENLI = 11.0               # kesimden 8 mm ice

# Kesim kutusunu tam kapatan azami goruntu (1254 px @ 150 DPI = 212,3 mm)
TAM_MM = 212.0
TAM_X = (SAYFA - TAM_MM) / 2.0      # 2,0 mm


def _tam_kadraj(a: dict) -> dict:
    for k in a.get("kadraj_firsatlari", []):
        if k["ad"] == "tam":
            return k
    return a["kadraj_firsatlari"][0]


def _dikey_serit(a: dict, oran: float = 0.34) -> dict:
    """Fotografin ortasindan dikey serit -- butun yukseklik korunur."""
    k = _tam_kadraj(a)
    pw, ph = k["piksel"]
    x = max(0.0, 0.5 - oran / 2.0)
    return {"ad": "dikey_serit_2", "x": x, "y": 0.0, "en": oran, "boy": 1.0,
            "piksel": [int(pw * oran), ph]}


def _yatay_serit(a: dict, y0: float, boy: float) -> dict:
    k = _tam_kadraj(a)
    pw, ph = k["piksel"]
    return {"ad": "yatay_serit", "x": 0.0, "y": y0, "en": 1.0, "boy": boy,
            "piksel": [pw, int(ph * boy)]}


def _malzeme_bandi(a: dict, boy: float = 0.34) -> dict:
    """URUNDEN KACINAN yatay bant -- kapakta malzeme gorunsun, urun degil.

    OLCULDU: sabit orta bant secince uc bandin ucunde de urun
    goruntuye giriyordu ve 'marka = malzemesidir' fikri teslim
    olmuyordu. Bant, urun sinir kutusunun disindaki en genis
    dikey bosluktan secilir."""
    ku = a.get("urun_kutusu") or {}
    uy0 = float(ku.get("y", 0.35))
    uy1 = uy0 + float(ku.get("boy", 0.3))
    ust_bosluk = uy0
    alt_bosluk = 1.0 - uy1
    if ust_bosluk >= alt_bosluk and ust_bosluk >= boy * 0.7:
        y0 = max(0.0, uy0 - boy)
    elif alt_bosluk >= boy * 0.7:
        y0 = min(1.0 - boy, uy1)
    else:
        # Urun kareyi dolduruyorsa en az ortusen kenar bandi
        y0 = 0.0 if ust_bosluk >= alt_bosluk else 1.0 - boy
    return _yatay_serit(a, round(max(0.0, min(1.0 - boy, y0)), 4), boy)


def _malzeme_seridi(a: dict, oran: float) -> dict:
    """URUNUN YANINDAN dikey serit -- saf malzeme dokusu.

    OLCULDU: yatay bant secince uc fotografin ucunde de urun
    goruntuye giriyordu; "marka = malzemesidir" fikri teslim
    olmuyordu. Urunler karede ORTADA durdugu icin sol/sag kenarlar
    saf dokudur; serit oradan alinir."""
    k = _tam_kadraj(a)
    pw, ph = k["piksel"]
    ku = a.get("urun_kutusu") or {}
    ux0 = float(ku.get("x", 0.3))
    ux1 = ux0 + float(ku.get("en", 0.4))
    sol, sag = ux0, 1.0 - ux1
    if sol >= sag:
        x0 = max(0.0, ux0 - oran)
    else:
        x0 = min(1.0 - oran, ux1)
    x0 = max(0.0, min(1.0 - oran, x0))
    return {"ad": "malzeme_seridi", "x": round(x0, 4), "y": 0.0,
            "en": oran, "boy": 1.0,
            "piksel": [int(pw * oran), ph]}


def _dpi(kadraj: dict, en_mm: float) -> float:
    return ts.yerlesim_dpi(kadraj["piksel"][0], en_mm)


def _sakin_bolgeler(a: dict, en_az: float = 0.035) -> list[dict]:
    """Olculen metin guvenli bolgeler, alan buyuklugune gore."""
    b = [x for x in (a.get("metin_guvenli_bolgeler") or [])
         if x.get("alan_orani", 0) >= en_az]
    if not b:
        b = [x for x in (a.get("negatif_bolgeler") or [])
             if x.get("alan_orani", 0) >= en_az]
    return sorted(b, key=lambda x: -x["alan_orani"])


def _bolge_mm(b: dict, foto_x: float, foto_y: float,
              foto_en: float, foto_boy: float) -> tuple[float, float, float, float]:
    """Olculen bolgeyi mm'ye cevirir ve GUVENLI ALANA kelepceler.

    OLCULDU: fotografin sakin bolgeleri sayfa kenarina cok yakin
    cikabiliyor ve tipografi guvenli alanin disina dusuyordu."""
    x = foto_x + b["x"] * foto_en
    y = foto_y + b["y"] * foto_boy
    en = b["en"] * foto_en
    boy = b["boy"] * foto_boy
    x0 = max(x, GUVENLI)
    y0 = max(y, GUVENLI)
    x1 = min(x + en, SAYFA - GUVENLI)
    y1 = min(y + boy, SAYFA - GUVENLI)
    return (x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))


# =========================================================================
# 1 · KAPAK — MALZEME INDEKSI
#     Urun yok, mansert yok. Marka = yapildigi malzemeler.
# =========================================================================

def kapak_malzeme_indeksi(ic: Icerik, palet: dict,
                          bantlar: list[tuple[str, dict, str]]) -> rd.SayfaPlani:
    """bantlar: [(foto_yolu, analiz, etiket)] -- uc farkli malzeme dunyasi.

    Urun YOK, mansert YOK. Marka uc malzemesiyle anlatilir:
    jel / botanik / su. Sol sirt koyu marka alani.
    """
    sirt = 48.0
    serit_en = (SAYFA - sirt) / 3.0          # 56 mm
    serit_oran = serit_en / SAYFA            # kadraj orani = yerlesim orani

    ilk = _malzeme_seridi(bantlar[0][1], serit_oran)
    tuval_dpi = min(ts.yerlesim_dpi(ilk["piksel"][1], SAYFA), ts.HEDEF_DPI)
    plan = rd.SayfaPlani("cover", "malzeme_indeksi", tuval_dpi)

    plan.ekle("alan", x=0.0, y=0.0, en=sirt, boy=SAYFA, renk=(26, 23, 21))

    for i, (yol, an, etiket) in enumerate(bantlar[:3]):
        # Kadraj orani YERLESIM oraniyla birebir ayni olmali; bindirme
        # payi da kadraja dahil edilir, yoksa render motoru (hakli
        # olarak) yukari ornekleme reddi veriyor.
        yer_en = serit_en + (1.2 if i == 2 else 0.6)
        k = _malzeme_seridi(an, yer_en / SAYFA)
        plan.ekle("foto", kaynak=yol, kadraj=k,
                  x=sirt + i * serit_en, y=0.0, en=yer_en, boy=SAYFA,
                  tuy_px=0)
        # Etiketler serit uzerinde DEGIL, koyu sirtta toplanir.
        # OLCULDU: botanik seridin alt bolgesinde etiket 3.00 kontrast
        # veriyordu (esik 3.2). Etiketi tasimak hem kapiyi gecirir hem
        # daha temiz bir kunye kurar.
        plan.ekle("metin", stil="not_etiketi", metin=etiket,
                  x=GUVENLI + 1.0, y=SAYFA * 0.70 + i * 7.0, en=sirt - GUVENLI - 5.0,
                  renk=(0.78, 0.76, 0.73), punto=5.6, azami_satir=1)

    m = (1.0, 1.0, 1.0)
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ",
              x=GUVENLI + 1.0, y=SAYFA * 0.46, en=sirt - GUVENLI - 3.0, renk=m,
              punto=18.0, satir_pt=19.0, azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI + 1.0, y=SAYFA * 0.46 + 6.5, en=24.0, renk=m,
              kalinlik=1.0)
    plan.ekle("metin", stil="not_etiketi", metin="DERMOKOZMETİK",
              x=GUVENLI + 1.0, y=SAYFA * 0.46 + 15.0, en=sirt - GUVENLI - 5.0, renk=m, punto=5.8)
    plan.ekle("metin", stil="not_etiketi", metin="ÜRÜN KATALOĞU",
              x=GUVENLI + 1.0, y=SAYFA * 0.46 + 21.5, en=sirt - GUVENLI - 5.0, renk=m, punto=5.8)
    plan.ekle("metin", stil="not_etiketi", metin="2026",
              x=GUVENLI + 1.0, y=SAYFA - GUVENLI - 1.0, en=30, renk=m, punto=5.8)

    plan.olcumler = {"tip": "KAPAK_malzeme_indeksi", "serit_sayisi": 3,
                     "urun_en_mm": round(serit_en, 1), "urun_boy_mm": SAYFA,
                     "urun_dpi": round(tuval_dpi, 1),
                     "kadraj": "malzeme_seridi", "mansert": False}
    return plan


# =========================================================================
# 2 · HYDRAVIE — NUMUNE FOYU
#     Mansert YOK. Baskin oge: icerik/islev tablosu. Fotograf dar kolon.
# =========================================================================

def hydravie_numune_foyu(ic: Icerik, palet: dict,
                         satirlar: list[tuple[str, str]]) -> rd.SayfaPlani:
    a = ic.analiz
    kad = _dikey_serit(a, 0.34)
    boy = 212.0
    en = boy * kad["piksel"][0] / kad["piksel"][1]
    dpi = _dpi(kad, en)
    plan = rd.SayfaPlani("hydravie", "numune_foyu", max(dpi, 150.0))

    x_foto = SAYFA - en + 1.0
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x_foto, y=TAM_X, en=en, boy=boy, tuy_kenar=("sol",))

    sol_en = x_foto - GUVENLI - 10.0
    m, s = ts.MUREKKEP, ts.MUREKKEP_SOLUK

    plan.ekle("metin", stil="not_etiketi", metin="NUMUNE FÖYÜ · 01",
              x=GUVENLI, y=GUVENLI + 2.0, en=60, renk=s, punto=5.8)
    plan.ekle("metin", stil="urun_ad_kucuk", metin=ic.ad,
              x=GUVENLI, y=GUVENLI + 14.0, en=sol_en, renk=m, punto=17.0)
    plan.ekle("metin", stil="alt_yazi", metin=ic.alt_ad,
              x=GUVENLI, y=GUVENLI + 21.0, en=sol_en, renk=s, azami_satir=1)

    # TABLO -- sayfanin baskin ogesi
    y = GUVENLI + 38.0
    plan.ekle("cizgi", x=GUVENLI, y=y - 5.0, en=sol_en, renk=m, kalinlik=0.9)
    plan.ekle("metin", stil="not_etiketi", metin="İÇERİK",
              x=GUVENLI, y=y, en=sol_en * 0.42, renk=s, punto=6.2)
    plan.ekle("metin", stil="not_etiketi", metin="İŞLEVİ",
              x=GUVENLI + sol_en * 0.44, y=y, en=sol_en * 0.56, renk=s,
              punto=6.2)
    y += 6.0
    for ad, islev in satirlar:
        plan.ekle("cizgi", x=GUVENLI, y=y - 3.4, en=sol_en, renk=s,
                  kalinlik=0.3)
        plan.ekle("metin", stil="alt_yazi", metin=ad,
                  x=GUVENLI, y=y, en=sol_en * 0.42, renk=m, punto=8.2,
                  azami_satir=1)
        plan.ekle("metin", stil="govde_hafif", metin=islev,
                  x=GUVENLI + sol_en * 0.44, y=y, en=sol_en * 0.56, renk=m,
                  punto=8.2, satir_pt=10.4, azami_satir=2)
        y += 13.6
    plan.ekle("cizgi", x=GUVENLI, y=y - 3.4, en=sol_en, renk=m, kalinlik=0.9)

    plan.ekle("metin", stil="govde_hafif", metin=ic.govde,
              x=GUVENLI, y=y + 9.0, en=sol_en, renk=m, punto=8.4,
              satir_pt=12.2, azami_satir=4)

    plan.ekle("not_alani", x=GUVENLI, y=SAYFA - GUVENLI - 17.0,
              en=sol_en * 0.62, satir=2, aralik=7.0,
              etiket="SAHA NOTU", renk=s)
    plan.ekle("metin", stil="not_etiketi", metin=ic.hacim,
              x=GUVENLI + sol_en * 0.70, y=SAYFA - GUVENLI - 1.0,
              en=40, renk=s, punto=6.2)

    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "veri_foyu", "mansert": False,
                     "baskin_oge": "icerik_tablosu"}
    return plan


# =========================================================================
# 3 · KINESIS — FOTOGRAF GRIDDIR
#     Tipografi olculen sakin jel alanlarina yerlesir, grid'e degil.
# =========================================================================

def kinesis_fotograf_grid(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    a = ic.analiz
    kad = _tam_kadraj(a)
    en = boy = TAM_MM
    dpi = _dpi(kad, en)
    plan = rd.SayfaPlani("kinesis", "fotograf_grid", max(dpi, 150.0))

    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=TAM_X, y=TAM_X, en=en, boy=boy, tuy_px=0)

    bolgeler = _sakin_bolgeler(a, 0.03)
    yerler = []
    for b in bolgeler[:3]:
        bx, by, ben, bboy = _bolge_mm(b, TAM_X, TAM_X, en, boy)
        if ben < 34 or bboy < 12:
            continue
        yerler.append((bx, by, ben, bboy, b.get("metin_turu", "koyu_metin")))
    # Yedek: olculen bolge yoksa kenar guvenli alanlari
    while len(yerler) < 3:
        i = len(yerler)
        yerler.append((GUVENLI, GUVENLI + i * 30.0, 72.0, 24.0, "koyu_metin"))

    def murekkep(tur):
        return ts.MUREKKEP if tur == "koyu_metin" else (1.0, 1.0, 1.0)

    # 1 · ad + hacim -- en buyuk sakin alan
    bx, by, ben, _bb, tur = yerler[0]
    m = murekkep(tur)
    plan.ekle("metin", stil="urun_ad_kucuk", metin=ic.ad,
              x=bx + 5.0, y=by + 11.0, en=min(ben - 8, 86), renk=m, punto=19.0)
    plan.ekle("metin", stil="not_etiketi", metin=ic.hacim,
              x=bx + 5.0, y=by + 18.0, en=40, renk=m, punto=6.0)

    # 2 · tek mikro satir
    bx, by, ben, _bb, tur = yerler[1]
    plan.ekle("metin", stil="govde_hafif", metin=ic.mikro or ic.alt_ad,
              x=bx + 5.0, y=by + 10.0, en=min(ben - 8, 70), renk=murekkep(tur),
              punto=8.0, satir_pt=11.0, azami_satir=3)

    # 3 · not alani -- sayfanin altinda degil, fotografin sakin alaninda
    bx, by, ben, _bb, tur = yerler[2]
    plan.ekle("not_alani", x=bx + 5.0, y=by + 12.0, en=min(ben - 10, 64),
              satir=2, aralik=6.6, etiket="SAHA NOTU", renk=murekkep(tur))

    plan.olcumler = {"urun_en_mm": en, "urun_boy_mm": boy,
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "fotograf_grid", "mansert": False,
                     "baskin_oge": "fotograf",
                     "sakin_bolge_sayisi": len(bolgeler)}
    return plan


# =========================================================================
# 4 · FEMISIA — SUREKLI YUZEY
#     Sayfa tek krem yuzey; fotograf gorunur kenari olmadan dogar.
# =========================================================================

def femisia_surekli_yuzey(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    a = ic.analiz
    kad = _tam_kadraj(a)
    en = 158.0
    boy = en * kad["piksel"][1] / kad["piksel"][0]
    dpi = _dpi(kad, en)
    plan = rd.SayfaPlani("private-care", "surekli_yuzey", max(dpi, 150.0))

    # Fotograf sag ve ALT kenardan tasar; sol ve ust kenarlar KENDI
    # zeminine cozulur -- ayni krem oldugu icin dikis gorunmez.
    x = SAYFA - en + 3.0
    y = SAYFA - boy + 3.0
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=y, en=en, boy=boy,
              tuy_kenar=("sol", "ust"),
              tuy_px=int(max(24, dpi / 25.4 * 9.0)))

    m, s = ts.MUREKKEP, ts.MUREKKEP_SOLUK
    plan.ekle("metin", stil="not_etiketi", metin=ic.ad,
              x=GUVENLI, y=GUVENLI + 2.0, en=70, renk=s, punto=6.2)

    # Sayfanin baskin ogesi: tek kisa cumle, metin olceginde, genis
    # satir araligiyla. Display DEGIL -- mansert yok.
    plan.ekle("metin", stil="govde", metin=ic.manset,
              x=GUVENLI, y=GUVENLI + 26.0, en=min(96.0, x - GUVENLI - 8),
              renk=m, punto=14.0, satir_pt=22.0, azami_satir=5)

    plan.ekle("cizgi", x=GUVENLI, y=GUVENLI + 92.0, en=18.0, renk=s,
              kalinlik=0.8)
    plan.ekle("metin", stil="govde_hafif", metin=ic.govde,
              x=GUVENLI, y=GUVENLI + 100.0, en=min(84.0, x - GUVENLI - 8),
              renk=m, punto=8.2, satir_pt=12.0, azami_satir=5)

    plan.ekle("not_alani", x=GUVENLI, y=SAYFA - GUVENLI - 30.0,
              en=62.0, satir=2, aralik=6.8, etiket="SAHA NOTU", renk=s)
    plan.ekle("metin", stil="inci", metin=ic.inci,
              x=GUVENLI, y=SAYFA - GUVENLI - 9.0, en=min(96.0, x - GUVENLI - 8),
              renk=s, punto=6.2, satir_pt=8.2, azami_satir=2)

    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "surekli_yuzey", "mansert": False,
                     "baskin_oge": "yuzey_ve_cumle"}
    return plan


# =========================================================================
# 5 · BABYSOL — ISIK ALANI
#     Fotografin parlakligi sayfanin kendisi. Ad + SPF tek buyuk oge.
# =========================================================================

def babysol_isik_alani(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    a = ic.analiz
    kad = _tam_kadraj(a)
    en = boy = TAM_MM
    dpi = _dpi(kad, en)
    plan = rd.SayfaPlani("daily-care", "isik_alani", max(dpi, 150.0))

    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=TAM_X, y=TAM_X, en=en, boy=boy, tuy_px=0)

    bolgeler = _sakin_bolgeler(a, 0.03)
    acik = [b for b in bolgeler if b.get("metin_turu") == "koyu_metin"]
    hedef = (acik or bolgeler or [None])[0]
    if hedef:
        bx, by = _bolge_mm(hedef, TAM_X, TAM_X, en, boy)[:2]
    else:
        bx, by = GUVENLI, GUVENLI
    bx = min(max(bx + 4.0, GUVENLI), SAYFA - GUVENLI - 78.0)
    by = min(max(by + 14.0, GUVENLI + 12.0), SAYFA - GUVENLI - 60.0)

    m = ts.MUREKKEP
    plan.ekle("metin", stil="urun_ad_kucuk", metin=ic.ad,
              x=bx, y=by, en=88.0, renk=m, punto=27.0, satir_pt=28.0)
    plan.ekle("metin", stil="alt_baslik", metin="SPF 50+",
              x=bx, y=by + 12.0, en=60.0, renk=m, punto=13.0)
    plan.ekle("cizgi", x=bx, y=by + 17.0, en=26.0, renk=m, kalinlik=1.1)
    plan.ekle("metin", stil="govde_hafif", metin=ic.alt_ad,
              x=bx, y=by + 25.0, en=78.0, renk=m, punto=8.2, azami_satir=2)

    # Alt bant: yari saydam -- zorunlu uyari ve not alani
    bant_boy = 34.0
    plan.ekle("alan", x=0.0, y=SAYFA - bant_boy, en=SAYFA, boy=bant_boy,
              renk=(252, 250, 245), alfa=0.80)
    plan.ekle("metin", stil="alt_yazi", metin=ic.uyari,
              x=GUVENLI, y=SAYFA - bant_boy + 9.0, en=SAYFA * 0.50,
              renk=ts.MUREKKEP_SOLUK, punto=6.4, satir_pt=8.4, azami_satir=3)
    plan.ekle("not_alani", x=SAYFA * 0.56, y=SAYFA - bant_boy + 14.0,
              en=SAYFA * 0.44 - GUVENLI, satir=2, aralik=6.4,
              etiket="SAHA NOTU", renk=ts.MUREKKEP_SOLUK)

    plan.olcumler = {"urun_en_mm": en, "urun_boy_mm": boy,
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "isik_alani", "mansert": False,
                     "baskin_oge": "ad_ve_spf"}
    return plan
