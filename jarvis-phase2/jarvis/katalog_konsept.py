"""Konsept uretimi -- uc CIDDI iskelet, kanit temelli secim.

ILK BULDUGUN DUZENI KULLANMA: her sayfa icin uc farkli iskelet.
Ayni duzenin uc rengi konsept degildir.

RENDER TURLARINDA OLCULEN VE DUZELTILEN KUSURLAR:
  tur 1  Renk alanlari soluktu -> "pastel kutuya konmus packshot".
         Alanlar artik urunun KENDI doygun renginden kuruluyor.
  tur 1  Baslik ve govde tasiyordu -> yerlesim yeniden hesaplandi.
  tur 2  Fotograf renk alaninin uzerinde YAPISTIRILMIS dikdortgen gibi
         duruyordu. Cozum: fotograf sayfa kenarlarindan tasar, yalniz
         ic kenarlari tuylenir; gorunen tek kenar bilincli cizgidir.
  tur 3  C'de blok ile fotograf arasinda CENTIK olusuyordu ve sag alt
         %40 OLU BOSLUKTU -- brief'in acikca yasakladigi hata.
         Fotograf ust kenari blok tabanina hizalandi; bos kolon
         INCI mikro metni ve not alaniyla dolduruldu.
  tur 3  Not alani kaybolmustu. Fiziksel satis katalogunun geregi:
         her urun sayfasinda yazilabilir alan ZORUNLU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis import katalog_render as rd
from jarvis import katalog_tasarim_sistemi as ts

SAYFA = ts.SAYFA_MM
GUVENLI = ts.TASMA_MM + ts.GUVENLI_MM
KENAR = ts.TASMA_MM + ts.KENAR_MM


@dataclass
class Icerik:
    slug: str
    ad: str
    alt_ad: str
    ust_etiket: str
    manset: str
    govde: str
    hacim: str
    inci: str = ""
    mikro: str = ""
    uyari: str = ""          # mevzuat geregi zorunlu ibare
    not_etiketi: str = "SAHA NOTU"
    kaynak_foto: str = ""
    analiz: dict = field(default_factory=dict)


def _kadraj(analiz: dict, ad: str) -> dict:
    for k in analiz.get("kadraj_firsatlari", []):
        if k["ad"] == ad:
            return k
    return analiz["kadraj_firsatlari"][0]


def _olcekle(kadraj: dict, hedef_boy_mm: float) -> tuple[float, float, float]:
    """YUKARI ORNEKLEME YOK: taban DPI altina duserse hedef kucultulur."""
    pw, ph = kadraj["piksel"]
    oran = pw / ph
    boy = hedef_boy_mm
    dpi = ts.yerlesim_dpi(ph, boy)
    if dpi < ts.URUN_TABAN_DPI:
        boy = ts.azami_mm(ph, ts.URUN_TABAN_DPI)
        dpi = ts.URUN_TABAN_DPI
    return boy * oran, boy, dpi


def _koyu(renk, oran=0.55):
    return tuple(int(round(v * oran)) for v in renk)


def _kunye(plan, ic, x, y, en, renk_ad, renk_govde, not_renk, genis=False):
    """Urun kunyesi. GOVDENIN ALT SINIRINI dondurur.

    OLCULDU: sabit ofsetle hesaplanan INCI/uyari, govde beklenenden
    uzun sardiginda uzerine biniyordu (7 carpisma, BABYSOL). Akis
    artik gercek satir sayisindan hesaplanir."""
    plan.ekle("metin", stil="urun_ad_kucuk", metin=ic.ad, x=x, y=y, en=en,
              renk=renk_ad)
    alt_n = min(2, rd.satir_sayisi(ic.alt_ad, "alt_yazi", en))
    plan.ekle("metin", stil="alt_yazi", metin=ic.alt_ad, x=x, y=y + 7.6,
              en=en, renk=renk_govde, azami_satir=2)
    gy = y + 7.6 + alt_n * 10.5 / ts.MM + 5.0
    azami = 8 if genis else 7
    plan.ekle("metin", stil="govde", metin=ic.govde, x=x, y=gy, en=en,
              renk=renk_ad, azami_satir=azami)
    return gy + rd.blok_yuksekligi_mm(ic.govde, "govde", en,
                                      azami_satir=azami)


def _not_bloku(plan, ic, x, y, en, renk, inci_ustte=True, akis_alt=None):
    """Not alani + (varsa) zorunlu uyari ve INCI, CAKISMADAN.

    OLCULDU: INCI metni sabit bir y'ye konunca not alani cizgileriyle
    cakisiyordu (BABYSOL). Artik hepsi not alanindan geriye dogru
    hesaplaniyor."""
    # Akis alt siniri verilmisse not blogu ondan asagi baslar
    if akis_alt is not None:
        gereken = 6.0 + (13.0 if (inci_ustte and ic.inci) else 0.0)                   + (11.0 if ic.uyari else 0.0)
        y = max(y, akis_alt + gereken)
        y = min(y, SAYFA - GUVENLI - 24.0)
    imza = y
    if ic.uyari:
        # MEVZUAT: zorunlu ibare atlanmaz. Not alaninin ustune yazilir.
        imza -= 11.0
        plan.ekle("metin", stil="alt_yazi", metin=ic.uyari, x=x, y=imza,
                  en=en, renk=renk, azami_satir=2, punto=6.6, satir_pt=8.6)
    if inci_ustte and ic.inci:
        imza -= 13.0
        plan.ekle("metin", stil="inci", metin=ic.inci, x=x, y=imza,
                  en=en, renk=renk, azami_satir=3)
    plan.ekle("cizgi", x=x, y=y - 6.0, en=en * 0.34, renk=renk, kalinlik=0.7)
    plan.ekle("not_alani", x=x, y=y + 6.0, en=en, satir=3, aralik=7.4,
              etiket=ic.not_etiketi, renk=renk)


# --- KONSEPT A: fotografik hakimiyet -------------------------------------
# Urun sagdan tasar, tam boy. Solda urunun kendi doygun renginden dikey
# blok. Tek gorunen kenar: fotografin sol kenari.

def konsept_a(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    a = ic.analiz
    kad = _kadraj(a, "dikey_serit")
    en, boy, dpi = _olcekle(kad, SAYFA + 14.0)
    plan = rd.SayfaPlani("%s-A" % ic.slug, "fotografik_hakimiyet", dpi)

    blok_en = SAYFA * 0.46
    blok_renk = palet["vurgu"]
    plan.ekle("alan", x=0.0, y=0.0, en=blok_en, boy=SAYFA, renk=blok_renk)

    x = max(blok_en - 2.0, SAYFA - en)
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=-7.0, en=en, boy=boy, tuy_kenar=("sol",))

    m = ts.metin_rengi_sec(blok_renk)
    soluk = tuple(min(1.0, v * 0.72 + 0.20) for v in m)
    ic_en = blok_en - KENAR - 11

    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 3, en=ic_en, renk=m)
    plan.ekle("cizgi", x=KENAR, y=KENAR + 8.0, en=22, renk=m, kalinlik=1.4)
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 26, en=ic_en, renk=m, azami_satir=6,
              punto=23.0, satir_pt=24.5)

    ky = SAYFA * 0.50
    alt = _kunye(plan, ic, KENAR, ky, ic_en, m, soluk, soluk)
    _not_bloku(plan, ic, KENAR, SAYFA - GUVENLI - 34.0, ic_en, soluk,
               akis_alt=alt)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=blok_en + 6, y=SAYFA - GUVENLI - 1, en=40,
              renk=ts.MUREKKEP_SOLUK)
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "blok_orani": round(blok_en / SAYFA, 3)}
    return plan


# --- KONSEPT B: yatay ufuk -----------------------------------------------
# Fotografin kendi zemini tum sayfa. Urun sag alttan tasar. Ust yari
# sessiz, dev manset. Renk bloku YOK -- kutu hissi yaratmamak icin
# yalniz ince bir vurgu cizgisi.

def konsept_b(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    zm, zs = ts.zemin_murekkebi(palet)
    a = ic.analiz
    kad = _kadraj(a, "siki")
    en, boy, dpi = _olcekle(kad, SAYFA * 0.76)
    plan = rd.SayfaPlani("%s-B" % ic.slug, "yatay_ufuk", dpi)

    x = SAYFA - en + 4.0
    y = SAYFA - boy + 8.0
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=y, en=en, boy=boy, tuy_kenar=("sol", "ust"))

    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 3, en=SAYFA * 0.5, renk=palet["alan_koyu"])
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 26, en=SAYFA - 2 * KENAR, renk=zm,
              azami_satir=3, punto=30.0, satir_pt=31.0)
    plan.ekle("cizgi", x=KENAR, y=SAYFA * 0.44, en=SAYFA * 0.30,
              renk=palet["vurgu"], kalinlik=1.6)

    sol_en = x - KENAR - 10
    ky = SAYFA * 0.50
    alt = _kunye(plan, ic, KENAR, ky, sol_en, zm, zs, zs)
    _not_bloku(plan, ic, KENAR, SAYFA - GUVENLI - 34.0, sol_en, zs,
               akis_alt=alt)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=SAYFA - KENAR - 40, y=KENAR + 3, en=40, hiza="sag",
              renk=palet["alan_koyu"])
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"]}
    return plan


# --- KONSEPT C: kontrollu asimetri ---------------------------------------
# Ust yari doygun blok + dev manset. Urun sol alttan tasar ve ust kenari
# blok tabanina TAM hizalanir -- centik olusmaz. Sag kolon kunye + INCI
# + not alani ile doldurulur; olu bosluk birakilmaz.

def konsept_c(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    zm, zs = ts.zemin_murekkebi(palet)
    a = ic.analiz
    kad = _kadraj(a, "siki")
    en, boy, dpi = _olcekle(kad, SAYFA * 0.66)
    plan = rd.SayfaPlani("%s-C" % ic.slug, "kontrollu_asimetri", dpi)

    blok_boy = SAYFA - boy + 6.0          # fotograf ustu ile TAM hizali
    blok_renk = _koyu(palet["vurgu"], 0.80)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=blok_boy, renk=blok_renk)

    x = -5.0
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=blok_boy - 6.0, en=en, boy=boy, tuy_kenar=("sag",))

    m = ts.metin_rengi_sec(blok_renk)
    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 2, en=SAYFA * 0.6, renk=m)
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 24, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=3, punto=31.0, satir_pt=32.0)
    plan.ekle("cizgi", x=SAYFA - KENAR - 34, y=blok_boy - 13, en=34,
              renk=m, kalinlik=1.4)

    sag_x = x + en + 12
    sag_en = SAYFA - KENAR - sag_x
    ky = blok_boy + 14.0
    _kunye(plan, ic, sag_x, ky, sag_en, zm, zs, zs, genis=True)

    _not_bloku(plan, ic, sag_x, SAYFA - GUVENLI - 34.0, sag_en, zs)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=sag_x, y=ky - 6.0, en=40, renk=palet["alan_koyu"])
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "blok_orani": round(blok_boy / SAYFA, 3)}
    return plan


KONSEPTLER = {
    "fotografik_hakimiyet": konsept_a,
    "yatay_ufuk": konsept_b,
    "kontrollu_asimetri": konsept_c,
}


def uret(ic: Icerik, palet: dict) -> list[rd.SayfaPlani]:
    return [f(ic, palet) for f in (konsept_a, konsept_b, konsept_c)]

# =========================================================================
# TYPE A ISKELETLERI -- editoryal fotograf icin.
# TYPE A'da urune KIRPMA YASAK. Yalniz "careful_whole_image_crop_where_
# justified" izinlidir. Bu iki iskelet fotografi BUTUN olarak yerlestirir;
# duzen fotograftan turetilir.
# =========================================================================

def konsept_d(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    """TAM KARE -- fotograf tam genislikte bant, sol/sagdan tasar.

    Sayfanin ust ve alt bantlari tipografiye birakilir. Kare formatta
    en guclu editoryal hamle: goruntu sayfayi yatay olarak keser."""
    zm, zs = ts.zemin_murekkebi(palet)
    a = ic.analiz
    kad = _kadraj(a, "tam")
    pw, ph = kad["piksel"]
    # OLCULDU: kare fotografi tam genislikte koymak sayfanin TAMAMINI
    # kapatiyor ve baslik fotografin uzerine dusuyordu (kapak sayfasi).
    # Goruntu yuksekligi sinirlanir; ust ve alt bantlar TIPOGRAFIYE kalir.
    boy = SAYFA * 0.54
    en = boy * pw / ph
    if en > SAYFA + 8.0:
        en = SAYFA + 8.0
        boy = en * ph / pw
    dpi = ts.yerlesim_dpi(pw, en)
    if dpi < ts.URUN_TABAN_DPI:
        en = ts.azami_mm(pw, ts.URUN_TABAN_DPI)
        boy = en * ph / pw
        dpi = ts.URUN_TABAN_DPI
    plan = rd.SayfaPlani("%s-D" % ic.slug, "tam_kare", dpi)

    y = SAYFA * 0.30
    x = (SAYFA - en) / 2.0
    kenarlar = ["ust", "alt"] + ([] if en >= SAYFA else ["sol", "sag"])
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=y, en=en, boy=boy, tuy_kenar=tuple(kenarlar))

    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 2, en=SAYFA * 0.7, renk=palet["alan_koyu"])
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 22, en=SAYFA - 2 * KENAR, renk=zm,
              azami_satir=3, punto=27.0, satir_pt=28.0)

    alt_y = y + boy + 12.0
    if alt_y > SAYFA - GUVENLI - 34:
        alt_y = SAYFA - GUVENLI - 34
    plan.ekle("metin", stil="urun_ad_kucuk", metin=ic.ad,
              x=KENAR, y=alt_y, en=SAYFA * 0.42, renk=zm)
    plan.ekle("metin", stil="alt_yazi", metin=ic.alt_ad,
              x=KENAR, y=alt_y + 7.6, en=SAYFA * 0.42,
              renk=zs, azami_satir=2)
    plan.ekle("metin", stil="govde", metin=ic.govde,
              x=SAYFA * 0.50, y=alt_y, en=SAYFA * 0.50 - KENAR,
              renk=zm, azami_satir=5)
    plan.ekle("cizgi", x=KENAR, y=alt_y - 7.0, en=SAYFA - 2 * KENAR,
              renk=palet["vurgu"], kalinlik=1.2)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=SAYFA - KENAR - 40, y=KENAR + 2, en=40, hiza="sag",
              renk=palet["alan_koyu"])
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "TYPE_A_butun_goruntu"}
    return plan


def konsept_e(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    """KARE BLOK -- fotograf sag alttan tasan kare; solda renk alani.

    Fotograf butun olarak durur; kirpilmaz. Tip sol kolonda dikey
    yigilir. Kosegen agirlik: goruntu sag alt, tipografi sol ust."""
    zm, zs = ts.zemin_murekkebi(palet)
    a = ic.analiz
    kad = _kadraj(a, "tam")
    pw, ph = kad["piksel"]
    en = SAYFA * 0.62
    boy = en * ph / pw
    dpi = ts.yerlesim_dpi(pw, en)
    if dpi < ts.URUN_TABAN_DPI:
        en = ts.azami_mm(pw, ts.URUN_TABAN_DPI)
        boy = en * ph / pw
        dpi = ts.URUN_TABAN_DPI
    plan = rd.SayfaPlani("%s-E" % ic.slug, "kare_blok", dpi)

    blok_renk = palet["alan_orta"]
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA - boy + 10,
              renk=blok_renk)

    x = SAYFA - en + 6.0
    y = SAYFA - boy + 4.0
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=x, y=y, en=en, boy=boy, tuy_kenar=("sol", "ust"))

    m = ts.metin_rengi_sec(blok_renk)
    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 2, en=SAYFA * 0.6, renk=m)
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 22, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=3, punto=28.0, satir_pt=29.0)

    sol_en = x - KENAR - 8
    ky = y + 8.0
    alt = _kunye(plan, ic, KENAR, ky, sol_en, zm, zs, zs)
    _not_bloku(plan, ic, KENAR, SAYFA - GUVENLI - 34.0, sol_en, zs,
               akis_alt=alt)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=SAYFA - KENAR - 40, y=KENAR + 2, en=40, hiza="sag", renk=m)
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "TYPE_A_butun_goruntu"}
    return plan


def konsept_f(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    """UST BLOK -- doygun renk bandi ustte, butun fotograf sol alttan tasar.

    konsept_c ile ayni kosegen mantik, ama fotograf KIRPILMAZ: TYPE A
    icin gecerli surum."""
    zm, zs = ts.zemin_murekkebi(palet)
    a = ic.analiz
    kad = _kadraj(a, "tam")
    pw, ph = kad["piksel"]
    en = SAYFA * 0.70
    boy = en * ph / pw
    dpi = ts.yerlesim_dpi(pw, en)
    if dpi < ts.URUN_TABAN_DPI:
        en = ts.azami_mm(pw, ts.URUN_TABAN_DPI)
        boy = en * ph / pw
        dpi = ts.URUN_TABAN_DPI
    plan = rd.SayfaPlani("%s-F" % ic.slug, "ust_blok", dpi)

    blok_boy = SAYFA - boy + 6.0
    blok_renk = _koyu(palet["vurgu"], 0.80)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=blok_boy, renk=blok_renk)

    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=-5.0, y=blok_boy - 6.0, en=en, boy=boy, tuy_kenar=("sag",))

    m = ts.metin_rengi_sec(blok_renk)
    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 2, en=SAYFA * 0.6, renk=m)
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 24, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=3, punto=29.0, satir_pt=30.0)

    sag_x = en - 5.0 + 12
    sag_en = SAYFA - KENAR - sag_x
    if sag_en < 46:
        sag_x = SAYFA - KENAR - 52
        sag_en = 52
    ky = blok_boy + 14.0
    alt = _kunye(plan, ic, sag_x, ky, sag_en, zm, zs, zs, genis=True)
    _not_bloku(plan, ic, sag_x, SAYFA - GUVENLI - 34.0, sag_en, zs,
               akis_alt=alt)
    plan.ekle("metin", stil="alt_yazi", metin=ic.hacim,
              x=sag_x, y=ky - 6.0, en=40, renk=palet["alan_koyu"])
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "TYPE_A_butun_goruntu"}
    return plan


TIP_A_KONSEPTLERI = (konsept_d, konsept_e, konsept_f)
TIP_B_KONSEPTLERI = (konsept_a, konsept_b, konsept_c)


def uret_sinifa_gore(ic: Icerik, palet: dict, asset_type: str,
                     sayfa_turu: str = "URUN") -> list[rd.SayfaPlani]:
    """TYPE A'da urune kirpma YASAK -- yalniz butun-goruntu iskeletleri.
    Kapak kendi iskelet havuzunu kullanir."""
    if sayfa_turu == "KAPAK":
        return [f(ic, palet) for f in KAPAK_KONSEPTLERI]
    havuz = TIP_A_KONSEPTLERI if asset_type == "A" else TIP_B_KONSEPTLERI
    return [f(ic, palet) for f in havuz]

# =========================================================================
# KAPAK ISKELETLERI -- urun sayfasi degildir: kunye ve INCI tasimaz.
# OLCULDU: urun sayfasi iskeletini kapakta kullanmak, koyu editoryal
# fotograf uzerine kunye metni dusurup uc turda da kontrast kapisindan
# geciremedi. Kapak kendi iskeletini ister.
# =========================================================================

def kapak_tam_bleed(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    """Fotograf tum sayfayi kaplar; altta doygun marka bandi.

    Tip yalnizca bandin uzerinde durur -- fotografin uzerinde METIN YOK.
    Bu, kontrast sorununu tasarim kararina cevirir, sonradan yamaya degil."""
    a = ic.analiz
    kad = _kadraj(a, "tam")
    pw, ph = kad["piksel"]
    en = SAYFA + 8.0
    boy = en * ph / pw
    dpi = ts.yerlesim_dpi(pw, en)
    if dpi < ts.SAHNE_TABAN_DPI:
        en = ts.azami_mm(pw, ts.SAHNE_TABAN_DPI)
        boy = en * ph / pw
        dpi = ts.SAHNE_TABAN_DPI
    plan = rd.SayfaPlani("%s-K1" % ic.slug, "kapak_tam_bleed", dpi)

    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=(SAYFA - en) / 2.0, y=(SAYFA - boy) * 0.42,
              en=en, boy=boy, tuy_px=0)

    bant_boy = SAYFA * 0.30
    bant_y = SAYFA - bant_boy
    bant_renk = _koyu(palet["vurgu"], 0.82)
    plan.ekle("alan", x=0.0, y=bant_y, en=SAYFA, boy=bant_boy, renk=bant_renk)

    m = ts.metin_rengi_sec(bant_renk)
    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=bant_y + 14, en=SAYFA * 0.7, renk=m)
    plan.ekle("metin", stil="devasa", metin=ic.ad,
              x=KENAR, y=bant_y + 36, en=SAYFA - 2 * KENAR, renk=m,
              punto=42.0, satir_pt=42.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik", metin=ic.alt_ad,
              x=KENAR, y=bant_y + 48, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=1)
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "KAPAK_tam_bleed"}
    return plan


def kapak_bolunmus(ic: Icerik, palet: dict) -> rd.SayfaPlani:
    """Ust yari doygun marka alani + dev tipografi; alt yari fotograf."""
    a = ic.analiz
    kad = _kadraj(a, "tam")
    pw, ph = kad["piksel"]
    boy = SAYFA * 0.54
    en = boy * pw / ph
    if en < SAYFA + 8.0:
        en = SAYFA + 8.0
        boy = en * ph / pw
    dpi = ts.yerlesim_dpi(pw, en)
    if dpi < ts.SAHNE_TABAN_DPI:
        en = ts.azami_mm(pw, ts.SAHNE_TABAN_DPI)
        boy = en * ph / pw
        dpi = ts.SAHNE_TABAN_DPI
    plan = rd.SayfaPlani("%s-K2" % ic.slug, "kapak_bolunmus", dpi)

    alan_boy = SAYFA - boy + 4.0
    alan_renk = _koyu(palet["vurgu"], 0.86)
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=alan_boy, renk=alan_renk)
    plan.ekle("foto", kaynak=ic.kaynak_foto, kadraj=kad,
              x=(SAYFA - en) / 2.0, y=alan_boy - 4.0, en=en, boy=boy,
              tuy_px=0)

    m = ts.metin_rengi_sec(alan_renk)
    plan.ekle("metin", stil="ust_etiket", metin=ic.ust_etiket,
              x=KENAR, y=KENAR + 4, en=SAYFA * 0.7, renk=m)
    plan.ekle("metin", stil="devasa", metin=ic.ad,
              x=KENAR, y=KENAR + 34, en=SAYFA - 2 * KENAR, renk=m,
              punto=46.0, satir_pt=46.0, azami_satir=1)
    plan.ekle("metin", stil="display", metin=ic.manset,
              x=KENAR, y=KENAR + 56, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=2, punto=22.0, satir_pt=23.0)
    plan.ekle("metin", stil="alt_baslik", metin=ic.alt_ad,
              x=KENAR, y=alan_boy - 12, en=SAYFA - 2 * KENAR, renk=m,
              azami_satir=1)
    plan.olcumler = {"urun_en_mm": round(en, 1), "urun_boy_mm": round(boy, 1),
                     "urun_dpi": round(dpi, 1), "kadraj": kad["ad"],
                     "tip": "KAPAK_bolunmus"}
    return plan


KAPAK_KONSEPTLERI = (kapak_tam_bleed, kapak_bolunmus, konsept_d)
