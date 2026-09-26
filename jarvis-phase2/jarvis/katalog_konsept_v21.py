"""V2.1 -- 10 CHALLENGER. Urun kahraman, fotograf layout'u kuruyor.

Ne korunuyor (V2 kazanimlari):
  gercek kutu/dosya metni · bilgi mimarisi · INCI teknik bolgesi ·
  SANA NOT utility space · kernel · repertuar cesitliligi

Ne degisiyor (V2 kusuru):
  Fotograf yerlesimi buyuyor VE kadraj urune yaklasiyor.
  Olculdu: B (urun kutusu/sayfa) TUR3 0.273 -> V2 0.128.
  Ama C (urun/fotograf) V2'de daha iyi: 0.457 -> 0.561.
  Yani sorun kadraj degil OLCEK. V2.1 ikisini birlestiriyor.

FIZIKSEL TAKAS -- gizlenmiyor:
  >=250 PPI'da urun kutusu sayfanin ~%15-18'ini gecemiyor.
  TUR3'un %27'si ancak PRINT_EXCEPTION ile mumkun. Her sayfada
  hangi tarafin secildigi `takas` alaninda kayitli.
"""
from __future__ import annotations

from jarvis import katalog_render as rd
from jarvis import katalog_tasarim_sistemi as ts
from jarvis import katalog_urun_gercegi as ug
from jarvis.katalog_konsept3 import _olcu

SAYFA = ts.SAYFA_MM
GUVENLI = 11.0
IC = SAYFA - 2 * GUVENLI

MUR = (0.10, 0.10, 0.12)
SOLUK = (0.42, 0.42, 0.46)
BEYAZ = (1.0, 1.0, 1.0)


def urun_kadraji(yol: str, analiz: dict, en_mm: float, boy_mm: float,
                 pay: float = 0.22) -> dict:
    """Kadraji URUN KUTUSUNA gore kurar -- kareyi ortalamaz.

    pay: urun kutusunun etrafinda birakilacak goreli nefes.
    Kadraj orani yerlesim oranina zorlanir ve goruntu icinde kalir.
    """
    w, h = _olcu(yol)
    uk = analiz.get("urun_kutusu") or {"x": 0.3, "y": 0.3, "en": 0.4, "boy": 0.4}
    ux, uy = float(uk["x"]), float(uk["y"])
    uw, uh = float(uk["en"]), float(uk["boy"])
    cx, cy = ux + uw / 2, uy + uh / 2

    # urunu iceren, istenen orana sahip en kucuk kutu
    hedef = (en_mm / boy_mm) * (h / w)     # normalize koordinatta oran
    gw = uw * (1 + pay)
    gh = uh * (1 + pay)
    if gw / gh < hedef:
        gw = gh * hedef
    else:
        gh = gw / hedef
    # KIRPMA SONRASI ORANI GERI KUR: gw ya da gh 1.0'a kirpilirsa
    # oran bozuluyordu ve render motoru kadraj/yerlesim oran uyusmazligi
    # veriyordu. Kirpilan eksenden digerini yeniden turet.
    if gh > 1.0:
        gh = 1.0
        gw = gh * hedef
    if gw > 1.0:
        gw = 1.0
        gh = gw / hedef
    gw, gh = min(gw, 1.0), min(gh, 1.0)
    x0 = min(max(cx - gw / 2, 0.0), 1.0 - gw)
    y0 = min(max(cy - gh / 2, 0.0), 1.0 - gh)
    return {"ad": "urun_kadraji", "x": round(x0, 4), "y": round(y0, 4),
            "en": round(gw, 4), "boy": round(gh, 4),
            "piksel": [int(round(gw * w)), int(round(gh * h))]}


def ppi(kadraj: dict, en_mm: float, boy_mm: float) -> float:
    pw, ph = kadraj["piksel"]
    return min(pw * 25.4 / en_mm, ph * 25.4 / boy_mm)


def baski_durumu(p: float, insan: bool = False) -> tuple[str, str | None]:
    """Uc durum: DIGITAL_PROTOTYPE_OK / PRINT_EXCEPTION /
    PRINT_READY_CANDIDATE. FINAL_PRINT_APPROVED fiziksel prova ister."""
    if insan:
        return ("DIGITAL_PROTOTYPE_OK",
                "rights_status UNKNOWN (insan ozne) -- PRINT_READY olamaz")
    if p >= 250.0:
        return ("PRINT_READY_CANDIDATE", None)
    if p >= 150.0:
        return ("PRINT_EXCEPTION",
                "%.0f PPI, baski hedefi 250 PPI'nin altinda" % p)
    return ("REDDEDILDI", "%.0f PPI, prototip tabani 150'nin altinda" % p)


def _z(plan, rgb):
    plan.ekle("alan", x=0.0, y=0.0, en=SAYFA, boy=SAYFA, renk=rgb)


def _foto(plan, yol, analiz, x, y, en, boy, pay=0.22):
    k = urun_kadraji(yol, analiz, en, boy, pay)
    plan.ekle("foto", kaynak=yol, kadraj=k, x=x, y=y, en=en, boy=boy,
              tuy_px=0)
    return k


def _not(plan, x, y, en, renk=SOLUK, satir=2):
    plan.ekle("not_alani", x=x, y=y, en=en, etiket="SANA NOT", renk=renk,
              satir=satir, aralik=7.0)


def _meta(plan, **kw):
    plan.olcumler.update({"v21": True, **kw})
    return plan


def _bilesen_rayi(plan, one_cikan, x, y, en, renk=MUR, soluk=SOLUK,
                  punto=7.4, ara=9.5, azami=4):
    """TR adi / INCI adi -- dort esit ikon YOK, iki katmanli ray."""
    yy = y
    for tr, inci, oran in one_cikan[:azami]:
        plan.ekle("metin", stil="alt_yazi", metin=tr, x=x, y=yy, en=en,
                  renk=renk, punto=punto, azami_satir=1)
        et = inci if not oran else "%s · %%%s" % (inci, oran)
        plan.ekle("metin", stil="inci", metin=et, x=x, y=yy + 4.4, en=en,
                  renk=soluk, punto=5.8, azami_satir=1)
        yy += ara
    return yy


# =======================================================================
# KAPAK -- iki challenger. Cover coklu urun icerdigi icin urun-sayfa
# ortalamasina KARISTIRILMAZ; ayri degerlendirilir.
# =======================================================================

def vc1_nesne_ve_golge(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """NESNE VE GOLGE -- tek urun, gercek dokme golgesi, koyu malzeme.

    Kapak sorusu: WHAT WORLD ARE WE ENTERING? Cevap bir indeks degil bir
    NESNE: klinik isikta duran gercek bir urun ve onun gercek golgesi.
    """
    en, boy = 150.0, 150.0
    k = urun_kadraji(foto, analiz, en, boy, pay=0.55)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("cover", "v21_nesne_ve_golge", min(p, 300.0))
    _z(plan, (24, 26, 30))
    # OLCULDU: foto y=30 iken marka metninin ornekleme kutusu fotografin
    # ust kenarina degiyor ve zemin degiskenligi 0.466 (esik 0.42) cikiyordu.
    # Kontrast orani zaten 17.4 idi -- sorun kontrast degil DEGISKENLIK.
    plan.ekle("foto", kaynak=foto, kadraj=k, x=(SAYFA - en) / 2.0, y=38.0,
              en=en, boy=boy, tuy_px=0)
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI, y=24.0,
              en=IC, renk=BEYAZ, punto=19.0, azami_satir=1)
    # OLCULDU: sag ust etiket fotografin acik mavi alanina denk gelip
    # 3.2 kontrast esigini gecemiyordu. Koyu zemine, alt banda alindi.
    plan.ekle("metin", stil="not_etiketi", metin="DERMOKOZMETİK",
              x=SAYFA - GUVENLI - 60.0, y=204.0, en=60.0,
              renk=(0.70, 0.72, 0.74), punto=6.0, azami_satir=1, hiza="sag")
    plan.ekle("cizgi", x=GUVENLI, y=198.0, en=IC, renk=(0.42, 0.44, 0.48),
              kalinlik=0.4)
    plan.ekle("metin", stil="not_etiketi",
              metin="36 ÜRÜN · 9 BAKIM AİLESİ · 2026", x=GUVENLI, y=204.0,
              en=IC, renk=(0.70, 0.72, 0.74), punto=6.2, azami_satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="cover", fikir="Markaya giris bir indeksle "
                 "degil bir NESNEYLE olur: klinik isikta gercek urun ve "
                 "gercek golgesi.",
                 koreografi="FIRST=nesne · SECOND=marka · THIRD=kapsam",
                 iliski="MATERIAL_DERIVATION",
                 repertuar="IMAGE_INTEGRATED_TYPE",
                 bosluk="ACTIVE -- koyu alan nesneyi izole ediyor",
                 enerji="klinik-agir", urun_olcegi="BUYUK",
                 takas="Kadraj urune yakin tutuldu; golge icin pay birakildi",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=[])


def vc2_uc_nesne(g: dict, fotolar: list[tuple[str, dict, str]]) -> rd.SayfaPlani:
    """UC NESNE -- uc urun, TEK isik disiplini, naturmort dizilimi.

    Grid degil: uc pano farkli yukseklikte ve farkli taban cizgisinde
    durur; ortak olan isik yonu ve malzeme dili.
    """
    olcu = [(64.0, 96.0), (72.0, 112.0), (60.0, 88.0)]
    ust = [78.0, 60.0, 92.0]
    kadrajlar, ppiler = [], []
    for (yol, an, _et), (e, b) in zip(fotolar[:3], olcu, strict=True):
        k = urun_kadraji(yol, an, e, b, pay=0.18)
        kadrajlar.append(k)
        ppiler.append(ppi(k, e, b))
    plan = rd.SayfaPlani("cover", "v21_uc_nesne", min(min(ppiler), 300.0))
    _z(plan, (238, 236, 231))
    x = 14.0
    for i, ((yol, _an, et), (e, b)) in enumerate(
            zip(fotolar[:3], olcu, strict=True)):
        plan.ekle("foto", kaynak=yol, kadraj=kadrajlar[i], x=x, y=ust[i],
                  en=e, boy=b, tuy_px=0)
        plan.ekle("metin", stil="not_etiketi", metin=et, x=x,
                  y=ust[i] + b + 6.0, en=e + 12.0, renk=SOLUK, punto=5.6,
                  azami_satir=1)
        x += e + 10.0
    plan.ekle("metin", stil="devasa", metin="L'CARLIÉ", x=GUVENLI, y=34.0,
              en=IC, renk=MUR, punto=24.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi",
              metin="BOTANİK × KLİNİK · DERMOKOZMETİK ÜRÜN KATALOĞU",
              x=GUVENLI, y=42.0, en=IC, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="2026", x=GUVENLI,
              y=SAYFA - GUVENLI - 2.0, en=40.0, renk=SOLUK, punto=6.2,
              azami_satir=1)
    durum, istisna = baski_durumu(min(ppiler))
    return _meta(plan, kernel="cover",
                 fikir="Uc urun, uc ayri malzeme, TEK isik disiplini. "
                       "Marka tutarliligi renkte degil isikta.",
                 koreografi="FIRST=uc nesne · SECOND=marka · THIRD=kapsam",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- farkli taban cizgileri grid hissini kiriyor",
                 enerji="sakin-coklu", urun_olcegi="ORTA",
                 takas="Uc urun icin pano kuculdu; her biri kendi kadrajinda "
                       "tam ve kesilmemis",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=[])


# =======================================================================
# HYDRAVIE -- kernel: nem tutulan bir seydir
# Master: hydravie-a3794e3f48 (1254x1254, urun 1210 px) -> 123 mm @250
# =======================================================================

def vh1_su_ve_cam(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """SU VE CAM -- cam blok, soguk isik, urun sayfanin kahramani."""
    en, boy = 126.0, 126.0   # 249 -> 253 PPI (1 mm, kompozisyon ayni)
    k = urun_kadraji(foto, analiz, en, boy, pay=0.10)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("hydravie", "v21_su_ve_cam", min(p, 300.0))
    _z(plan, (211, 223, 234))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=SAYFA - en - 6.0, y=30.0,
              en=en, boy=boy, tuy_px=0)

    plan.ekle("metin", stil="urun_ad", metin="HYDRAVIE", x=GUVENLI, y=38.0,
              en=90.0, renk=MUR, punto=20.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin=ug.deger(g, "kategori",
              "YÜZ VE EL BAKIMI"), x=GUVENLI, y=46.0, en=90.0, renk=SOLUK,
              punto=5.8, azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=GUVENLI, y=53.0,
                  en=40.0, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik",
              metin=ug.kisalt(ug.deger(g, "tanim"), 96), x=GUVENLI, y=66.0,
              en=76.0, renk=MUR, punto=9.5, satir_pt=13.5, azami_satir=5)

    y = _bilesen_rayi(plan, g["one_cikan"], GUVENLI, 118.0, 76.0)
    plan.ekle("cizgi", x=GUVENLI, y=y + 2.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM", x=GUVENLI,
              y=y + 11.0, en=60.0, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "kullanim"), 110), x=GUVENLI,
              y=y + 18.0, en=96.0, renk=(0.22, 0.26, 0.30), punto=6.8,
              satir_pt=8.8, azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 260),
              x=GUVENLI, y=y + 44.0, en=IC, renk=(0.34, 0.36, 0.40),
              punto=5.7, satir_pt=7.4, azami_satir=4)
    _not(plan, SAYFA - GUVENLI - 72.0, y + 11.0, 72.0)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="hydravie",
                 fikir="Nem tutulan bir seydir: cam blok ve soguk isik "
                       "tutulmayi gosterir; urun o tutmanin nesnesidir.",
                 koreografi="FIRST=urun · SECOND=ad ve tanim · "
                            "THIRD=bilesen rayi · TECHNICAL=INCI · "
                            "UTILITY=not alani",
                 iliski="TONAL_CONTINUITY",
                 repertuar="PRODUCT_NAME_DOMINANCE",
                 bosluk="ACTIVE -- fotografin sol kenarindaki bosluk metni "
                        "urunden ayiriyor",
                 enerji="soguk-sakin", urun_olcegi="BUYUK",
                 takas="Kadraj payi %10'a indirildi: urun buyudu, cevre "
                       "malzeme azaldi",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "kullanim", "inci", "one_cikan"])


def vh2_nesne_ve_sema(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """NESNE VE SEMA -- gercek capraz golge sayfanin yapisal cizgisi."""
    en, boy = 118.0, 118.0
    k = urun_kadraji(foto, analiz, en, boy, pay=0.14)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("hydravie", "v21_nesne_ve_sema", min(p, 300.0))
    _z(plan, (246, 247, 248))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=0.0, y=26.0, en=en, boy=boy,
              tuy_px=0)

    sag = en + 8.0
    sag_en = SAYFA - sag - GUVENLI
    plan.ekle("metin", stil="urun_ad_kucuk", metin="HYDRAVIE", x=sag, y=38.0,
              en=sag_en, renk=MUR, punto=13.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="YÜZ VE EL BAKIMI", x=sag,
              y=45.0, en=sag_en, renk=SOLUK, punto=5.6, azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=sag, y=52.0,
                  en=sag_en, renk=SOLUK, punto=5.6, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "tanim"), 150), x=sag, y=64.0,
              en=sag_en, renk=(0.24, 0.24, 0.28), punto=6.8, satir_pt=9.0,
              azami_satir=6)
    _bilesen_rayi(plan, g["one_cikan"], sag, 112.0, sag_en, punto=6.8,
                  ara=8.6, azami=3)

    plan.ekle("cizgi", x=GUVENLI, y=158.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM", x=GUVENLI, y=166.0,
              en=60.0, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "kullanim"), 100), x=GUVENLI,
              y=173.0, en=88.0, renk=MUR, punto=6.8, satir_pt=8.8,
              azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 240),
              x=GUVENLI + 96.0, y=166.0, en=IC - 96.0,
              renk=(0.36, 0.36, 0.40), punto=5.7, satir_pt=7.2, azami_satir=5)
    _not(plan, GUVENLI, 198.0, 88.0, satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="hydravie",
                 fikir="Karenin gercek capraz golgesi sayfanin yapisal "
                       "cizgisi olur; bilgi o cizgiye asilir.",
                 koreografi="FIRST=nesne+golge · SECOND=ad · THIRD=tanim · "
                            "TECHNICAL=INCI · UTILITY=not alani",
                 iliski="PHOTOGRAPHIC_CONTINUATION",
                 repertuar="TECHNICAL_TYPOGRAPHY",
                 bosluk="ACTIVE -- golgenin uzandigi alan bos birakildi",
                 enerji="notr-teknik", urun_olcegi="BUYUK",
                 takas="Foto sol kenardan tasiyor; urun kesilmiyor",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "kullanim", "inci", "one_cikan"])


# =======================================================================
# KINESIS+ -- kernel: bakim caba aninda baslar
# Artik URUN DOSYASINDAN tam INCI, tanim ve 7 denetimli satis cumlesi VAR.
# V2'de "icerik yok" demistim; kutu-gercegi icin dogruydu, SISTEM icin
# yanlisti. Bu iki challenger o bilgiyi gercekten kullaniyor.
# =======================================================================

def vk1_salon(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """SALON -- insan karesi, urun kadrajda BUYUK.

    rights_status UNKNOWN (insan ozne) -> DIGITAL_PROTOTYPE_OK.
    PRINT_READY_CANDIDATE OLAMAZ. Gizlenmiyor.
    """
    en, boy = 140.0, 140.0
    k = urun_kadraji(foto, analiz, en, boy, pay=0.95)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("kinesis", "v21_salon", min(p, 300.0))
    _z(plan, (22, 23, 25))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=SAYFA - en, y=0.0, en=en,
              boy=boy, tuy_px=0)

    plan.ekle("metin", stil="urun_ad", metin="KINESIS +", x=GUVENLI, y=34.0,
              en=80.0, renk=BEYAZ, punto=18.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="SPOR VE MASAJ", x=GUVENLI,
              y=42.0, en=80.0, renk=(0.72, 0.73, 0.75), punto=5.8,
              azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=GUVENLI, y=49.0,
                  en=40.0, renk=(0.72, 0.73, 0.75), punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "tanim"), 140), x=GUVENLI, y=62.0,
              en=66.0, renk=(0.84, 0.85, 0.86), punto=7.0, satir_pt=9.2,
              azami_satir=6)
    plan.ekle("cizgi", x=GUVENLI, y=152.0, en=IC, renk=(0.40, 0.42, 0.44),
              kalinlik=0.4)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM", x=GUVENLI, y=160.0,
              en=60.0, renk=(0.66, 0.68, 0.70), punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "kullanim"), 120), x=GUVENLI,
              y=167.0, en=96.0, renk=(0.82, 0.83, 0.85), punto=6.8,
              satir_pt=8.8, azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 220),
              x=GUVENLI, y=192.0, en=IC, renk=(0.62, 0.64, 0.66), punto=5.6,
              satir_pt=7.0, azami_satir=3)
    _not(plan, SAYFA - GUVENLI - 66.0, 160.0, 66.0, renk=(0.60, 0.62, 0.64))
    durum, istisna = baski_durumu(p, insan=True)
    return _meta(plan, kernel="kinesis+",
                 fikir="Bakim caba aninda baslar: urun sahnede, calisan "
                       "bedenin yanindadir -- yanina yapistirilmis degil.",
                 koreografi="FIRST=sahne · SECOND=ad · THIRD=tanim · "
                            "TECHNICAL=INCI · UTILITY=not alani",
                 iliski="NO_REPETITION",
                 repertuar="IMAGE_INTEGRATED_TYPE",
                 bosluk="ACTIVE -- sol koyu kolon metni tasiyor",
                 enerji="yuksek", urun_olcegi="ORTA",
                 takas="Insan karesi kullanildi: rights UNKNOWN, "
                       "PRINT_READY olamaz. Yaratici deger icin prototipte "
                       "tutuldu.",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 rights_notu="UNKNOWN_HUMAN_SUBJECT",
                 gerekli_icerik=["tanim", "kullanim", "inci"])


def vk2_nesne(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """NESNE -- haklari temiz studyo karesi, urun buyuk, tam bilgi."""
    # SABLON KIRILDI: urun SOLA alindi ve sol kenardan tasiyor;
    # metin sagda; ad 26 pt (H1'in 20 pt adindan ayrilir).
    en, boy = 106.0, 95.0    # 237 -> 250 PPI; sol tasma korundu
    k = urun_kadraji(foto, analiz, en, boy, pay=0.12)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("kinesis", "v21_nesne", min(p, 300.0))
    _z(plan, (233, 230, 222))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=-6.0, y=58.0, en=en,
              boy=boy, tuy_px=0)

    sag = en - 6.0 + 10.0
    sag_en = SAYFA - sag - GUVENLI
    plan.ekle("metin", stil="devasa", metin="KINESIS +", x=GUVENLI, y=36.0,
              en=IC, renk=MUR, punto=26.0, satir_pt=27.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="SPOR VE MASAJ · MASAJLA",
              x=GUVENLI, y=44.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=sag, y=60.0,
                  en=sag_en, renk=SOLUK, punto=5.8, azami_satir=1)
    # OLCULDU: sag ust ceyrek bostu ve govde 6.8 punto ile kayboluyordu.
    # KINESIS+ icin URUN DOSYASINDA mevzuat denetcisinden gecmis 7 satis
    # cumlesi var ve hic kullanilmamisti. Iki tanesi buraya alindi.
    plan.ekle("metin", stil="alt_baslik",
              metin=ug.kisalt(ug.deger(g, "tanim"), 120), x=sag, y=74.0,
              en=sag_en, renk=MUR, punto=8.6, satir_pt=12.0, azami_satir=5)
    sc = g["alanlar"].get("satis_cumleleri", {}).get("value") or []
    if sc:
        plan.ekle("cizgi", x=sag, y=124.0, en=sag_en,
                  renk=(0.68, 0.66, 0.62), kalinlik=0.3)
        plan.ekle("metin", stil="govde_hafif",
                  metin=ug.kisalt(sc[0], 165), x=sag, y=133.0, en=sag_en,
                  renk=(0.26, 0.26, 0.28), punto=7.0, satir_pt=9.2,
                  azami_satir=5)
    plan.ekle("cizgi", x=sag, y=172.0, en=sag_en, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="alt_yazi", metin="KULLANIM", x=sag, y=180.0,
              en=sag_en, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "kullanim"), 110), x=sag, y=187.0,
              en=sag_en, renk=(0.24, 0.24, 0.26), punto=6.6, satir_pt=8.6,
              azami_satir=3)
    # OLCULDU: tam genislikteki INCI sag kolondaki KULLANIM ile
    # carpisiyordu (3 durduran ihlal). INCI SOL kolona hapsedildi;
    # iki blok artik ayri sutunlarda.
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 280),
              x=GUVENLI, y=166.0, en=sag - GUVENLI - 8.0,
              renk=(0.34, 0.34, 0.36), punto=5.7, satir_pt=7.2,
              azami_satir=5)
    _not(plan, GUVENLI, 202.0, 88.0, satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="kinesis+",
                 fikir="Caba sahnesi olmadan da urun kendi kutlesiyle "
                       "konusur: lime karton ve amber cam, sicak zeminde.",
                 koreografi="FIRST=urun · SECOND=ad · THIRD=tanim · "
                            "TECHNICAL=INCI · UTILITY=not alani",
                 iliski="MATERIAL_DERIVATION",
                 repertuar="TECHNICAL_TYPOGRAPHY",
                 bosluk="ACTIVE -- sol ust bosluk ada nefes veriyor",
                 enerji="sicak-kararli", urun_olcegi="BUYUK",
                 takas="Haklari temiz aset secildi; insan karesinin "
                       "enerjisinden vazgecildi",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "kullanim", "inci"])


# =======================================================================
# FEMISIA -- urun TEKRAR ana kahraman. VIREON yarismiyor.
# Pembe klise, bordo blok, literal cinsellik YOK.
# =======================================================================

def vf1_amber(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """AMBER -- sicak malzeme, sessizlik, urun buyuk ve yalniz."""
    # SABLON KIRILDI: acilis cumlesi USTTE ve tek basina; urun ASAGI
    # indi ve buyudu; ad KUCUK ve altta -- sayfanin en sessiz hiyerarsisi.
    en, boy = 100.0, 121.0   # 242 -> 252 PPI
    k = urun_kadraji(foto, analiz, en, boy, pay=0.12)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("private-care", "v21_amber", min(p, 300.0))
    _z(plan, (226, 214, 203))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=SAYFA - en - 10.0, y=74.0,
              en=en, boy=boy, tuy_px=0)

    plan.ekle("metin", stil="not_etiketi", metin="HASSAS BÖLGE · KADIN",
              x=GUVENLI, y=30.0, en=IC, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="alt_baslik",
              metin=ug.kisalt(ug.deger(g, "tanim"), 104), x=GUVENLI, y=46.0,
              en=150.0, renk=MUR, punto=11.5, satir_pt=16.0, azami_satir=4)
    _bilesen_rayi(plan, g["one_cikan"], GUVENLI, 116.0, 84.0, punto=7.0,
                  ara=8.8, azami=3)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="FEMISIA", x=GUVENLI,
              y=156.0, en=86.0, renk=MUR, punto=11.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="for WOMEN", x=GUVENLI,
              y=163.0, en=86.0, renk=SOLUK, punto=5.6, azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=GUVENLI + 46.0,
                  y=156.0, en=40.0, renk=SOLUK, punto=5.6, azami_satir=1)

    plan.ekle("cizgi", x=GUVENLI, y=170.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "uyari"), 150), x=GUVENLI, y=178.0,
              en=100.0, renk=(0.30, 0.28, 0.26), punto=6.4, satir_pt=8.2,
              azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 250),
              x=GUVENLI, y=200.0, en=IC, renk=(0.40, 0.38, 0.36), punto=5.6,
              satir_pt=7.0, azami_satir=2)
    # OLCULDU: not alani x=139'da fotografin uzerine dusuyor ve
    # kontrast 2.69 (esik 3.2) veriyordu. Sol kolona alindi.
    _not(plan, GUVENLI, 196.0, 94.0, satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="femisia",
                 fikir="Mahremiyet sessizliktir: urun tek basina, sicak "
                       "malzemede, buyuk ve dingin durur.",
                 koreografi="FIRST=urun · SECOND=ad · THIRD=tanim · "
                            "TECHNICAL=INCI+uyari · UTILITY=not alani",
                 iliski="MATERIAL_DERIVATION",
                 repertuar="QUIET_EDITORIAL",
                 bosluk="ACTIVE -- urunun etrafindaki sicak alan izolasyon",
                 enerji="sicak-sessiz", urun_olcegi="BUYUK",
                 takas="VIREON sayfadan cikarildi: capraz satis bu sayfanin "
                       "art direction'ini yonetmemeli",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "uyari", "inci", "one_cikan"])


def vf2_mahremiyet(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """MAHREMIYET -- kutu buyuk ve koyu; bilgi kenarda, sayfa ketum.

    BRIEF IHLALI DUZELTILDI: ilk surumde DSC04316 kullanilmisti ve
    karede VIREON'un mavi kutusu FEMISIA ile YARISIYORDU. Capraz satis
    bu sayfanin art direction'ini yonetemez -- FEMISIA'nin tek basina
    oldugu kareye gecildi.
    """
    en, boy = 118.0, 90.0    # 248 -> 252 PPI
    k = urun_kadraji(foto, analiz, en, boy, pay=0.10)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("private-care", "v21_mahremiyet", min(p, 300.0))
    _z(plan, (34, 31, 30))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=0.0, y=58.0, en=en, boy=boy,
              tuy_px=0)

    sag = en + 8.0
    sag_en = SAYFA - sag - GUVENLI
    plan.ekle("metin", stil="urun_ad_kucuk", metin="FEMISIA", x=sag, y=66.0,
              en=sag_en, renk=BEYAZ, punto=14.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="for WOMEN", x=sag, y=73.0,
              en=sag_en, renk=(0.72, 0.70, 0.68), punto=5.6, azami_satir=1)
    net = ug.deger(g, "net_miktar")
    if net != ug.BILINMIYOR:
        plan.ekle("metin", stil="not_etiketi", metin=net, x=sag, y=80.0,
                  en=sag_en, renk=(0.72, 0.70, 0.68), punto=5.6,
                  azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "tanim"), 120), x=sag, y=92.0,
              en=sag_en, renk=(0.84, 0.82, 0.80), punto=6.6, satir_pt=8.6,
              azami_satir=6)
    plan.ekle("metin", stil="alt_yazi", metin="HASSAS BÖLGE BAKIMI",
              x=GUVENLI, y=42.0, en=IC, renk=(0.70, 0.68, 0.66), punto=6.2,
              azami_satir=1)
    plan.ekle("cizgi", x=GUVENLI, y=166.0, en=IC, renk=(0.46, 0.44, 0.42),
              kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "kullanim"), 110), x=GUVENLI,
              y=175.0, en=94.0, renk=(0.82, 0.80, 0.78), punto=6.6,
              satir_pt=8.4, azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 230),
              x=GUVENLI + 102.0, y=175.0, en=IC - 102.0,
              renk=(0.66, 0.64, 0.62), punto=5.6, satir_pt=7.0, azami_satir=4)
    _not(plan, GUVENLI, 200.0, 94.0, renk=(0.60, 0.58, 0.56), satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="femisia",
                 fikir="Ketumluk koyuluktur: kutu koyu zeminde buyur, "
                       "bilgi kenara cekilir.",
                 koreografi="FIRST=kutu · SECOND=kategori · THIRD=ad · "
                            "TECHNICAL=INCI · UTILITY=not alani",
                 iliski="TONAL_CONTINUITY",
                 repertuar="MONUMENTAL_DISPLAY",
                 bosluk="ACTIVE -- ust koyu bant sayfayi sessizlestiriyor",
                 enerji="koyu-ketum", urun_olcegi="BUYUK",
                 takas="Koyu zemin secildi: urun kontrasti artti, sayfa "
                       "dizide ikinci koyu sayfa oluyor",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "kullanim", "inci"])


# =======================================================================
# BABYSOL -- sari urun = sari sayfa YOK. Cocuksu grafik YOK.
# net_miktar CONFLICT -> BASILMIYOR. Mevzuat bulgusu BLOCKED kayitli.
# =======================================================================

def vb1_isik(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """ISIK -- fildisi/mineral zemin, gunes isigi, urun buyuk."""
    # SABLON KIRILDI: urun SAG-UST kenardan tasiyor; ad 34 pt ile
    # dizinin EN BUYUK tipografisi -- kapanis sayfasi yukseliyor.
    en, boy = 115.0, 103.0
    k = urun_kadraji(foto, analiz, en, boy, pay=0.12)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("daily-care", "v21_isik", min(p, 300.0))
    _z(plan, (240, 235, 226))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=SAYFA - en + 4.0, y=-4.0,
              en=en, boy=boy, tuy_px=0)

    plan.ekle("metin", stil="devasa", metin="BABYSOL", x=GUVENLI, y=120.0,
              en=IC, renk=MUR, punto=34.0, satir_pt=35.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi",
              metin="BEBEK · GÜNEŞ KORUMA · NON-NANO ÇİNKO OKSİT",
              x=GUVENLI, y=130.0, en=IC, renk=SOLUK, punto=6.0, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "tanim"), 112), x=GUVENLI, y=44.0,
              en=86.0, renk=MUR, punto=7.2, satir_pt=9.6, azami_satir=5)
    _bilesen_rayi(plan, g["one_cikan"], GUVENLI + 100.0, 120.0, 86.0,
                  punto=6.8, ara=8.4, azami=3)

    plan.ekle("cizgi", x=GUVENLI, y=158.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="alt_yazi", metin="ZORUNLU UYARI", x=GUVENLI,
              y=166.0, en=70.0, renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "uyari"), 190), x=GUVENLI, y=173.0,
              en=118.0, renk=(0.26, 0.25, 0.23), punto=6.6, satir_pt=8.4,
              azami_satir=3)
    # OLCULDU: INCI y=205'te guvenli alan tavanini asiyordu (1 durduran).
    # Uyari blogu 3 satira indirildi, INCI 200'e cekildi.
    plan.ekle("metin", stil="inci",
              metin="INCI — " + ug.kisalt(ug.deger(g, "inci"), 200),
              x=GUVENLI, y=200.0, en=IC, renk=(0.40, 0.38, 0.35), punto=5.6,
              satir_pt=7.0, azami_satir=1)
    _not(plan, SAYFA - GUVENLI - 62.0, 166.0, 62.0, satir=2)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="babysol",
                 fikir="Koruma gorunmez ama isik gorunur: fildisi mineral "
                       "zemin gunesi tasir, sari yalniz uruntedir.",
                 koreografi="FIRST=urun · SECOND=ad · THIRD=tanim · "
                            "TECHNICAL=zorunlu uyari + INCI · "
                            "UTILITY=not alani",
                 iliski="COMPLEMENTARY_CONTRAST",
                 repertuar="MONUMENTAL_DISPLAY",
                 bosluk="ACTIVE -- fildisi alan urunun sarisini yalniz "
                        "birakiyor",
                 enerji="parlak-korumaci", urun_olcegi="BUYUK",
                 takas="Sari zemin REDDEDILDI: urun tek renk kaynagi kalsin "
                       "diye zemin fildisi mineral",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "uyari", "inci", "one_cikan"])


def vb2_fiziksel_filtre(g: dict, foto: str, analiz: dict) -> rd.SayfaPlani:
    """FIZIKSEL FILTRE -- %30 cinko oksit teknik bilgi olarak tasarlanir."""
    en, boy = 102.0, 114.0   # 242 -> 251 PPI
    k = urun_kadraji(foto, analiz, en, boy, pay=0.10)
    p = ppi(k, en, boy)
    plan = rd.SayfaPlani("daily-care", "v21_fiziksel_filtre", min(p, 300.0))
    _z(plan, (231, 233, 232))
    plan.ekle("foto", kaynak=foto, kadraj=k, x=0.0, y=48.0, en=en, boy=boy,
              tuy_px=0)

    sag = en + 10.0
    sag_en = SAYFA - sag - GUVENLI
    tr, inci, oran = g["one_cikan"][0]
    plan.ekle("metin", stil="devasa", metin="%" + (oran or "30").split(".")[0],
              x=sag, y=78.0, en=sag_en, renk=MUR, punto=34.0, azami_satir=1)
    plan.ekle("metin", stil="alt_yazi", metin=tr, x=sag, y=88.0, en=sag_en,
              renk=MUR, punto=7.6, azami_satir=1)
    plan.ekle("metin", stil="inci", metin=inci, x=sag, y=93.5, en=sag_en,
              renk=SOLUK, punto=5.8, azami_satir=1)
    plan.ekle("metin", stil="urun_ad_kucuk", metin="BABYSOL", x=sag, y=58.0,
              en=sag_en, renk=MUR, punto=13.0, azami_satir=1)
    plan.ekle("metin", stil="not_etiketi", metin="BEBEK · GÜNEŞ KORUMA",
              x=sag, y=65.0, en=sag_en, renk=SOLUK, punto=5.6, azami_satir=1)
    _bilesen_rayi(plan, g["one_cikan"][1:], sag, 106.0, sag_en, punto=6.6,
                  ara=8.4, azami=3)

    plan.ekle("cizgi", x=GUVENLI, y=176.0, en=IC, renk=MUR, kalinlik=0.4)
    plan.ekle("metin", stil="govde_hafif",
              metin=ug.kisalt(ug.deger(g, "tanim"), 130), x=GUVENLI, y=184.0,
              en=100.0, renk=(0.24, 0.26, 0.25), punto=6.6, satir_pt=8.4,
              azami_satir=3)
    plan.ekle("metin", stil="inci",
              metin=ug.kisalt(ug.deger(g, "uyari"), 190), x=GUVENLI + 106.0,
              y=184.0, en=IC - 106.0, renk=(0.38, 0.40, 0.39), punto=5.6,
              satir_pt=7.0, azami_satir=4)
    _not(plan, GUVENLI, 206.0, 96.0, satir=1)
    durum, istisna = baski_durumu(p)
    return _meta(plan, kernel="babysol",
                 fikir="Fiziksel filtre bir orandir: %30 non-nano cinko "
                       "oksit. Iddia degil formul konusur.",
                 koreografi="FIRST=urun · SECOND=oran · THIRD=ad · "
                            "TECHNICAL=uyari · UTILITY=not alani",
                 iliski="NEUTRAL_ISOLATION",
                 repertuar="NUMBER_DRIVEN",
                 bosluk="ACTIVE -- oranin etrafi bos",
                 enerji="serin-teknik", urun_olcegi="BUYUK",
                 takas="Oran 34 punto ile sinirlandi: urunle yarismiyor",
                 baski_durumu=durum, baski_istisnasi=istisna,
                 gerekli_icerik=["tanim", "uyari", "one_cikan"])
