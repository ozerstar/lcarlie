"""Tipografi QA Motoru (C09B) -- TAMAMEN DETERMINISTIK.

BU MODUL HICBIR MODELE SORMAZ.
    Olculebilir seyi modele sormak hem pahali hem guvenilmezdir.
    Burada tek satir yargi yoktur: kural uygular, ihlal listeler.

    Yaratici tipografi karari (baslik nerede kirilacak, olcek kontrasti
    yeterli mi) C09A'nin isidir ve BU MODULE AIT DEGILDIR.

NEDEN VAR:
    OLCULDU 25.09.2026 -- scripts/katalog-tasarim.py 991 satir ve
    icinde TEK BIR denetim islevi yok. DPI disinda hicbir tipografik
    olcum yapilmiyor; taskin metin, carpisma, eksik glif ve dul satir
    sessizce baskiya gidiyor.

GLIF DENETIMI NEREDE YAPILIR -- OLCULDU 25.09.2026:
    PDF'e GOMULU alt kume fontun cmap'i UNICODE DEGILDIR. Olculdu:
    katalog PDF'indeki Metropolis-Medium alt kumesi 101 kod tasiyor ama
    kodlar 1,2,3... seklinde yeniden numaralanmis; ord('u umlaut') cmapte
    YOK. Hem fontTools hem pymupdf.Font.has_glyph False doner -- oysa
    sayfa render edildiginde Turkce karakterler DOGRU basiliyor
    (dogrulandi: sayfa 2 goruntusu).

    Bu yuzden PDF uzerinden glif kapsamasi denetlenemez; denendi ve
    258 YANLIS POZITIF uretti. Glif denetimi KAYNAK font dosyalari
    uzerinde, dizgiden ONCE yapilir: bkz. glif_kapsama().

GIRDI: uretilmis PDF + kullanilan font dosyalari.
BAGIMLILIK: pymupdf + fonttools (ikisi de kurulu). Yeni bagimlilik YOK.
"""

from __future__ import annotations

import pathlib
from dataclasses import asdict, dataclass

PT_MM = 25.4 / 72.0

# Turkce'nin tam kapsamasi. Eksik tek glif = baskida .notdef kutusu.
TURKCE_GLIFLER = "çÇğĞıİöÖşŞüÜÂâÎîÛû"
TEMEL_GLIFLER = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
NOKTALAMA = ".,;:!?()[]{}\"'’“”–—…%&/+-*=<>@#"

ESIK = {
    "asgari_punto_govde": 8.5,      # pt -- baskida okunur alt sinir
    "asgari_punto_herhangi": 5.5,   # pt -- altyazi/dipnot dahi bunun altina inemez
    "satir_uzunlugu_alt": 30,       # karakter -- govde metni icin
    "satir_uzunlugu_ust": 78,       # karakter
    "guvenli_alan_mm": 5.0,
    "tasma_mm": 3.0,
    "carpisma_toleransi_pt": 0.5,   # bu kadar ortusme yuvarlama sayilir
    "kisa_son_satir_orani": 0.25,   # blok genisliginin altinda kalan son satir
    "taban_sapmasi_pt": 0.75,
}

AGIRLIK_DURDURUR = "DURDURUR"
AGIRLIK_UYARI = "UYARI"


@dataclass(frozen=True)
class Ihlal:
    sayfa: int
    ihlal_tipi: str
    olculen: object
    esik: object
    konum: tuple[float, float, float, float] | None
    agirlik: str
    ayrinti: str = ""

    def sozluk(self) -> dict:
        return asdict(self)


# --- font kapsama --------------------------------------------------------

def glif_kapsama(font_yolu: str | pathlib.Path,
                 gerekli: str = TURKCE_GLIFLER + TEMEL_GLIFLER) -> dict:
    """Font dosyasinin gerekli glifleri tasiyip tasimadigini olcer.

    DURUM AYRIMI: font okunamazsa 'okunamadi' doner -- 'eksik' ile ayni
    sey degildir."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:                                  # pragma: no cover
        return {"durum": "OKUNAMADI", "sebep": "fonttools yok"}
    try:
        tf = TTFont(str(font_yolu), lazy=True, fontNumber=0)
        kapsam: set[int] = set()
        for tablo in tf["cmap"].tables:
            kapsam |= set(tablo.cmap.keys())
        tf.close()
    except Exception as hata:                            # noqa: BLE001
        return {"durum": "OKUNAMADI",
                "sebep": "%s: %s" % (hata.__class__.__name__, hata)}

    eksik = sorted({c for c in gerekli if ord(c) not in kapsam})
    return {
        "durum": "OK" if not eksik else "EKSIK",
        "font": str(font_yolu),
        "eksik_glifler": "".join(eksik),
        "eksik_sayisi": len(eksik),
        "kapsam_buyuklugu": len(kapsam),
    }


# --- PDF denetimi --------------------------------------------------------

def _belge(pdf_yolu):
    import pymupdf
    return pymupdf.open(str(pdf_yolu))


def _kesisim_alani(a, b) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def denetle(pdf_yolu: str | pathlib.Path,
            tasma_mm: float | None = None,
            guvenli_mm: float | None = None,
            esikler: dict | None = None) -> list[Ihlal]:
    """PDF'i tipografik olarak denetler. Bos liste = temiz.

    tasma_mm verilirse sayfa kutusunun tasma icerdigi varsayilir ve
    guvenli alan kesim cizgisinden ice dogru hesaplanir."""
    e = dict(ESIK)
    if esikler:
        e.update(esikler)
    tasma = e["tasma_mm"] if tasma_mm is None else tasma_mm
    guvenli = e["guvenli_alan_mm"] if guvenli_mm is None else guvenli_mm

    ihlaller: list[Ihlal] = []
    belge = _belge(pdf_yolu)
    try:
        # --- metinde gercekten kullanilan fontlari topla
        kullanilan_fontlar: set[str] = set()
        for sno in range(len(belge)):
            for blok in belge[sno].get_text("dict").get("blocks", []):
                if blok.get("type") != 0:
                    continue
                for satir in blok.get("lines", []):
                    for span in satir.get("spans", []):
                        if span.get("text", "").strip():
                            kullanilan_fontlar.add(
                                str(span.get("font", "")).split("+")[-1])

        # --- font gomme
        gomulmeyen: set[str] = set()
        for sno in range(len(belge)):
            for f in belge[sno].get_fonts(full=True):
                xref, ext, _tip, basefont = f[0], f[1], f[2], f[3]
                if not ext or xref == 0:
                    gomulmeyen.add(basefont)
                    continue
                try:
                    _ad, _uzanti, _tip2, tampon = belge.extract_font(xref)
                    if not tampon:
                        gomulmeyen.add(basefont)
                except Exception:                        # noqa: BLE001
                    gomulmeyen.add(basefont)
        for ad in sorted(gomulmeyen):
            sade = ad.split("+")[-1]
            # OLCULDU: katalog PDF'inde Helvetica her sayfanin kaynak
            # listesinde var ama HICBIR metin span'i onu kullanmiyor.
            # Kullanilmayan kaynak girdisi uretimi durdurmaz -- ama
            # prepload araclari da isaretler, o yuzden uyari kalir.
            kullaniliyor = any(sade in k or k in sade for k in kullanilan_fontlar)
            ihlaller.append(Ihlal(
                0, "font_gomulmemis" if kullaniliyor else "font_gomulmemis_kullanilmiyor",
                ad, "gomulu olmali", None,
                AGIRLIK_DURDURUR if kullaniliyor else AGIRLIK_UYARI,
                "matbaa bu fontu bulamaz" if kullaniliyor
                else "kaynakta tanimli ama metinde kullanilmiyor"))

        # --- sayfa duzeyi
        for sno in range(len(belge)):
            sayfa = belge[sno]
            kutu = sayfa.rect
            tasma_pt = tasma / PT_MM
            guvenli_pt = guvenli / PT_MM
            guvenli_kutu = (kutu.x0 + tasma_pt + guvenli_pt,
                            kutu.y0 + tasma_pt + guvenli_pt,
                            kutu.x1 - tasma_pt - guvenli_pt,
                            kutu.y1 - tasma_pt - guvenli_pt)

            veri = sayfa.get_text("dict")
            span_kutulari: list[tuple[tuple, str, float]] = []

            for blok in veri.get("blocks", []):
                if blok.get("type") != 0:
                    continue
                satirlar = blok.get("lines", [])
                satir_genislikleri: list[float] = []

                for satir in satirlar:
                    metin = "".join(s.get("text", "") for s in satir.get("spans", []))
                    if metin.strip():
                        satir_genislikleri.append(satir["bbox"][2] - satir["bbox"][0])

                    for span in satir.get("spans", []):
                        yazi = span.get("text", "")
                        if not yazi.strip():
                            continue
                        boyut = float(span.get("size", 0.0))
                        kutucuk = tuple(span["bbox"])
                        span_kutulari.append((kutucuk, yazi, boyut))

                        # punto
                        if boyut < e["asgari_punto_herhangi"]:
                            ihlaller.append(Ihlal(
                                sno + 1, "punto_cok_kucuk", round(boyut, 2),
                                e["asgari_punto_herhangi"], kutucuk, AGIRLIK_DURDURUR,
                                yazi[:40]))
                        elif boyut < e["asgari_punto_govde"] and len(yazi) > 60:
                            ihlaller.append(Ihlal(
                                sno + 1, "govde_puntosu_kucuk", round(boyut, 2),
                                e["asgari_punto_govde"], kutucuk, AGIRLIK_UYARI,
                                yazi[:40]))

                        # GLIF DENETIMI BURADA YAPILAMAZ -- bkz. modul basligi.
                        # Kullanilan fontu kayda gec; gomme denetimi icin gerekli.
                        kullanilan_fontlar.add(str(span.get("font", "")).split("+")[-1])
                        if "�" in yazi:
                            ihlaller.append(Ihlal(
                                sno + 1, "degistirme_karakteri", "U+FFFD", "olmamali",
                                kutucuk, AGIRLIK_DURDURUR, yazi[:40]))

                        # guvenli alan
                        if (kutucuk[0] < guvenli_kutu[0] - 0.5
                                or kutucuk[1] < guvenli_kutu[1] - 0.5
                                or kutucuk[2] > guvenli_kutu[2] + 0.5
                                or kutucuk[3] > guvenli_kutu[3] + 0.5):
                            ihlaller.append(Ihlal(
                                sno + 1, "guvenli_alan_ihlali",
                                [round(v, 1) for v in kutucuk],
                                [round(v, 1) for v in guvenli_kutu],
                                kutucuk, AGIRLIK_DURDURUR, yazi[:40]))

                        # sayfa disi tasma
                        if (kutucuk[2] < kutu.x0 or kutucuk[0] > kutu.x1
                                or kutucuk[3] < kutu.y0 or kutucuk[1] > kutu.y1):
                            ihlaller.append(Ihlal(
                                sno + 1, "sayfa_disi_metin",
                                [round(v, 1) for v in kutucuk], "sayfa icinde olmali",
                                kutucuk, AGIRLIK_DURDURUR, yazi[:40]))

                # satir uzunlugu -- yalniz cok satirli govde bloklarinda anlamli
                if len(satir_genislikleri) >= 3:
                    for satir in satirlar:
                        metin = "".join(s.get("text", "") for s in satir.get("spans", []))
                        n = len(metin.strip())
                        if n and n > e["satir_uzunlugu_ust"]:
                            ihlaller.append(Ihlal(
                                sno + 1, "satir_cok_uzun", n, e["satir_uzunlugu_ust"],
                                tuple(satir["bbox"]), AGIRLIK_UYARI, metin[:40]))

                # kisa son satir (dul satir vekili -- PDF paragraf sinirini kaybeder)
                if len(satir_genislikleri) >= 2:
                    blok_genislik = max(satir_genislikleri)
                    son = satir_genislikleri[-1]
                    if blok_genislik > 0 and son / blok_genislik < e["kisa_son_satir_orani"]:
                        ihlaller.append(Ihlal(
                            sno + 1, "kisa_son_satir",
                            round(son / blok_genislik, 3), e["kisa_son_satir_orani"],
                            tuple(blok["bbox"]), AGIRLIK_UYARI,
                            "dul satir vekili -- PDF paragraf sinirini tasimaz"))

            # --- carpisma: ayni sayfada ortusen metin kutulari
            for i in range(len(span_kutulari)):
                ka, ya, _ = span_kutulari[i]
                for j in range(i + 1, len(span_kutulari)):
                    kb, yb, _ = span_kutulari[j]
                    ortusme = _kesisim_alani(ka, kb)
                    if ortusme <= e["carpisma_toleransi_pt"] ** 2:
                        continue
                    kucuk = min((ka[2] - ka[0]) * (ka[3] - ka[1]),
                                (kb[2] - kb[0]) * (kb[3] - kb[1]))
                    if kucuk > 0 and ortusme / kucuk > 0.20:
                        ihlaller.append(Ihlal(
                            sno + 1, "metin_carpismasi", round(ortusme / kucuk, 3),
                            0.20, ka, AGIRLIK_DURDURUR,
                            "%r <-> %r" % (ya[:20], yb[:20])))
    finally:
        belge.close()
    return ihlaller


def durduruculari_ayir(ihlaller: list[Ihlal]) -> tuple[list[Ihlal], list[Ihlal]]:
    durdurur = [i for i in ihlaller if i.agirlik == AGIRLIK_DURDURUR]
    uyari = [i for i in ihlaller if i.agirlik != AGIRLIK_DURDURUR]
    return durdurur, uyari


def kapi(pdf_yolu: str | pathlib.Path, **kw) -> dict:
    """C09B'nin uretim kapisi. `gecti=False` ise PDF uretimi DURUR."""
    ihlaller = denetle(pdf_yolu, **kw)
    durdurur, uyari = durduruculari_ayir(ihlaller)
    ozet: dict[str, int] = {}
    for i in ihlaller:
        ozet[i.ihlal_tipi] = ozet.get(i.ihlal_tipi, 0) + 1
    return {
        "gecti": not durdurur,
        "durduran_ihlal": len(durdurur),
        "uyari": len(uyari),
        "tip_dagilimi": ozet,
        "ihlaller": [i.sozluk() for i in ihlaller],
    }
