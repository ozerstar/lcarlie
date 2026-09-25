"""Sayfa ve acilim olcumleri + duzen tekrari (C08 kaniti).

BU MODUL KARAR VERMEZ. Sanat yonetmeninin yerine gecmez; ona kanit verir.

NEDEN VAR:
    OLCULDU -- scripts/katalog_mimari.py:85 ACILIS_DUZENLERI uc varyant
    tanimliyor ve bunlar 33 sayfaya dagitiliyor. Tekrarin olculdugu
    hicbir yer yok.

TEKRAR TEK SINYALLE OLCULMEZ. Uc ayri sinyal birlikte kullanilir:
    1. duzen geometrisi imzasi  -- bloklarin grid hucrelerindeki dizilimi
    2. oran imzasi              -- gorsel/metin/bosluk alan oranlari
    3. algisal karma            -- render edilmis sayfanin gorunumu
    Ikisi ayni, ucuncusu farkli olabilir: ayni duzen farkli gorsellerle,
    ya da farkli duzen ayni renklerle. Bu yuzden ucu de raporlanir.

BAGIMLILIK: pymupdf + Pillow + numpy (hepsi kurulu). Yeni bagimlilik YOK.
    Algisal karma icin dis kutuphane KURULMADI -- dHash 15 satir.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import asdict, dataclass

PT_MM = 25.4 / 72.0
IZGARA = 8          # imza icin sayfa kac hucreye bolunur


@dataclass(frozen=True)
class SayfaOlcumu:
    sayfa: int
    en_mm: float
    boy_mm: float
    gorsel_alan_orani: float
    cizim_alan_orani: float
    metin_alan_orani: float
    bosluk_orani: float
    ogeler: int
    metin_bloklari: int
    gorseller: int
    cizimler: int
    zemin_dolgusu: bool
    en_buyuk_punto: float
    baslik_alan_orani: float
    yogunluk: float
    kenar_bosluk_mm: tuple[float, float, float, float]
    duzen_imzasi: str
    oran_imzasi: str

    def sozluk(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AcilimOlcumu:
    sol_sayfa: int
    sag_sayfa: int
    sol_kutle: float
    sag_kutle: float
    kutle_farki: float
    yogunluk_farki: float
    ayni_duzen_imzasi: bool
    ayni_oran_imzasi: bool

    def sozluk(self) -> dict:
        return asdict(self)


# --- yardimcilar ---------------------------------------------------------

def _alan(kutu) -> float:
    return max(0.0, kutu[2] - kutu[0]) * max(0.0, kutu[3] - kutu[1])


def _imza_hucresi(kutu, sayfa_kutu) -> tuple[int, int, int, int]:
    en = max(sayfa_kutu.x1 - sayfa_kutu.x0, 1e-6)
    boy = max(sayfa_kutu.y1 - sayfa_kutu.y0, 1e-6)
    return (
        min(IZGARA - 1, int((kutu[0] - sayfa_kutu.x0) / en * IZGARA)),
        min(IZGARA - 1, int((kutu[1] - sayfa_kutu.y0) / boy * IZGARA)),
        min(IZGARA, max(1, round((kutu[2] - kutu[0]) / en * IZGARA))),
        min(IZGARA, max(1, round((kutu[3] - kutu[1]) / boy * IZGARA))),
    )


def _kova(deger: float, basamak: float = 0.1) -> int:
    return int(round(deger / basamak))


# --- sayfa olcumu --------------------------------------------------------

def sayfa_olcumleri(pdf_yolu: str | pathlib.Path) -> list[SayfaOlcumu]:
    import pymupdf

    sonuc: list[SayfaOlcumu] = []
    belge = pymupdf.open(str(pdf_yolu))
    try:
        for sno in range(len(belge)):
            sayfa = belge[sno]
            kutu = sayfa.rect
            sayfa_alani = max(_alan((kutu.x0, kutu.y0, kutu.x1, kutu.y1)), 1e-6)

            veri = sayfa.get_text("dict")
            metin_kutulari, gorsel_kutulari = [], []
            en_buyuk_punto, baslik_kutusu, karakter = 0.0, None, 0

            for blok in veri.get("blocks", []):
                bkutu = tuple(blok["bbox"])
                if blok.get("type") == 1:
                    gorsel_kutulari.append(bkutu)
                    continue
                dolu = False
                for satir in blok.get("lines", []):
                    for span in satir.get("spans", []):
                        yazi = span.get("text", "")
                        if not yazi.strip():
                            continue
                        dolu = True
                        karakter += len(yazi)
                        boyut = float(span.get("size", 0.0))
                        if boyut > en_buyuk_punto:
                            en_buyuk_punto, baslik_kutusu = boyut, tuple(span["bbox"])
                if dolu:
                    metin_kutulari.append(bkutu)

            for g in sayfa.get_image_info():
                gorsel_kutulari.append(tuple(g["bbox"]))

            # VEKTOR CIZIMLER -- reportlab hatti tam olarak bunu uretir.
            # OLCULDU: get_text('dict') ve get_image_info() vektor cizimi
            # HIC gormuyor; sayilmazsa renk bloklari ve cizgiler yok sayilir.
            cizim_kutulari = []
            zemin_dolgusu = False
            for c in sayfa.get_drawings():
                ckutu = (c["rect"].x0, c["rect"].y0, c["rect"].x1, c["rect"].y1)
                if _alan(ckutu) <= 0:
                    continue
                # Sayfayi kaplayan dolgu bir OGE degil, ZEMINDIR.
                if _alan(ckutu) / sayfa_alani >= 0.95:
                    zemin_dolgusu = True
                    continue
                cizim_kutulari.append(ckutu)

            gorsel_oran = min(1.0, sum(_alan(k) for k in gorsel_kutulari) / sayfa_alani)
            cizim_oran = min(1.0, sum(_alan(k) for k in cizim_kutulari) / sayfa_alani)
            metin_oran = min(1.0, sum(_alan(k) for k in metin_kutulari) / sayfa_alani)
            bosluk = max(0.0, 1.0 - min(1.0, gorsel_oran + cizim_oran + metin_oran))

            tum = metin_kutulari + gorsel_kutulari + cizim_kutulari
            if tum:
                sol = min(k[0] for k in tum) - kutu.x0
                ust = min(k[1] for k in tum) - kutu.y0
                sag = kutu.x1 - max(k[2] for k in tum)
                alt = kutu.y1 - max(k[3] for k in tum)
            else:
                sol = ust = sag = alt = 0.0

            imza = "|".join(sorted(
                "%d,%d,%d,%d%s" % (*_imza_hucresi(k, kutu),
                                   "G" if (k in gorsel_kutulari or k in cizim_kutulari) else "M")
                for k in tum)) or "BOS"
            oran_imza = "g%d-m%d-b%d-o%d" % (
                _kova(gorsel_oran + cizim_oran), _kova(metin_oran), _kova(bosluk),
                min(20, len(tum)))

            # Yogunluk: oge sayisi + karakter yogunlugu, LOGARITMIK.
            # OLCULDU: dogrusal olcek ust ucta doyuyordu -- gercek
            # katalogda 48-94 ogeli sayfalarin hepsi ayni kademeye
            # dusuyor ve ritim olcumu ayirt edici olmuyordu.
            yogunluk = (
                0.5 * min(1.0, math.log1p(len(tum)) / math.log1p(120))
                + 0.5 * min(1.0, math.log1p(karakter) / math.log1p(4000))
            )

            sonuc.append(SayfaOlcumu(
                sayfa=sno + 1,
                en_mm=round(kutu.width * PT_MM, 1),
                boy_mm=round(kutu.height * PT_MM, 1),
                gorsel_alan_orani=round(gorsel_oran, 4),
                cizim_alan_orani=round(cizim_oran, 4),
                metin_alan_orani=round(metin_oran, 4),
                bosluk_orani=round(bosluk, 4),
                ogeler=len(tum),
                metin_bloklari=len(metin_kutulari),
                gorseller=len(gorsel_kutulari),
                cizimler=len(cizim_kutulari),
                zemin_dolgusu=zemin_dolgusu,
                en_buyuk_punto=round(en_buyuk_punto, 2),
                baslik_alan_orani=round(_alan(baslik_kutusu) / sayfa_alani, 5)
                if baslik_kutusu else 0.0,
                yogunluk=round(yogunluk, 4),
                kenar_bosluk_mm=(round(sol * PT_MM, 1), round(ust * PT_MM, 1),
                                 round(sag * PT_MM, 1), round(alt * PT_MM, 1)),
                duzen_imzasi=imza,
                oran_imzasi=oran_imza,
            ))
    finally:
        belge.close()
    return sonuc


# --- algisal karma (dis kutuphane KURULMADI) -----------------------------

def algisal_karma(pdf_yolu: str | pathlib.Path, dpi: int = 36) -> list[str]:
    """Her sayfa icin dHash. 64 bit, onaltilik dize.

    dHash secildi cunku aHash'ten daha ayirt edici ve pHash'in DCT
    maliyeti olmadan calisiyor. 15 satir -- bagimlilik gerektirmiyor."""
    import numpy as np
    import pymupdf
    from PIL import Image

    karmalar: list[str] = []
    belge = pymupdf.open(str(pdf_yolu))
    try:
        for sno in range(len(belge)):
            pix = belge[sno].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            k = np.asarray(im.resize((9, 8), Image.BILINEAR), dtype="int16")
            bitler = (k[:, 1:] > k[:, :-1]).flatten()
            deger = 0
            for b in bitler:
                deger = (deger << 1) | int(b)
            karmalar.append("%016x" % deger)
    finally:
        belge.close()
    return karmalar


def karma_mesafesi(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# --- tekrar kaniti -------------------------------------------------------

def tekrar_kaniti(pdf_yolu: str | pathlib.Path,
                  karma_esigi: int = 6) -> dict:
    """Uc sinyalle tekrar kaniti uretir. YARGI ICERMEZ.

    karma_esigi: 64 bitte bu kadar veya daha az fark = gorsel olarak ayni.
    """
    olcumler = sayfa_olcumleri(pdf_yolu)
    try:
        karmalar = algisal_karma(pdf_yolu)
    except Exception as hata:                    # noqa: BLE001
        karmalar = []
        karma_hatasi = "%s: %s" % (hata.__class__.__name__, hata)
    else:
        karma_hatasi = None

    ardisik_ayni_duzen = []
    for i in range(len(olcumler) - 1):
        a, b = olcumler[i], olcumler[i + 1]
        if a.duzen_imzasi == b.duzen_imzasi and a.duzen_imzasi != "BOS":
            ardisik_ayni_duzen.append([a.sayfa, b.sayfa])

    benzersiz_duzen = len({o.duzen_imzasi for o in olcumler})
    benzersiz_oran = len({o.oran_imzasi for o in olcumler})

    gorsel_ayni = []
    if karmalar:
        for i in range(len(karmalar)):
            for j in range(i + 1, len(karmalar)):
                d = karma_mesafesi(karmalar[i], karmalar[j])
                if d <= karma_esigi:
                    gorsel_ayni.append({"sayfalar": [i + 1, j + 1], "mesafe": d})

    return {
        "sayfa_sayisi": len(olcumler),
        "benzersiz_duzen_imzasi": benzersiz_duzen,
        "benzersiz_oran_imzasi": benzersiz_oran,
        "duzen_cesitliligi": round(benzersiz_duzen / max(len(olcumler), 1), 3),
        "ardisik_ayni_duzen": ardisik_ayni_duzen,
        "gorsel_olarak_ayni_ciftler": gorsel_ayni[:40],
        "gorsel_ayni_cift_sayisi": len(gorsel_ayni),
        "algisal_karma_hatasi": karma_hatasi,
    }


# --- acilim --------------------------------------------------------------

def acilim_olcumleri(olcumler: list[SayfaOlcumu],
                     ilk_sayfa_tek: bool = True) -> list[AcilimOlcumu]:
    """Acilim = yan yana basilan iki sayfa. Kapak tek durur."""
    sonuc: list[AcilimOlcumu] = []
    baslangic = 1 if ilk_sayfa_tek else 0
    for i in range(baslangic, len(olcumler) - 1, 2):
        sol, sag = olcumler[i], olcumler[i + 1]
        sol_k = sol.gorsel_alan_orani + sol.cizim_alan_orani + sol.metin_alan_orani
        sag_k = sag.gorsel_alan_orani + sag.cizim_alan_orani + sag.metin_alan_orani
        sonuc.append(AcilimOlcumu(
            sol_sayfa=sol.sayfa, sag_sayfa=sag.sayfa,
            sol_kutle=round(sol_k, 4), sag_kutle=round(sag_k, 4),
            kutle_farki=round(abs(sol_k - sag_k), 4),
            yogunluk_farki=round(abs(sol.yogunluk - sag.yogunluk), 4),
            ayni_duzen_imzasi=sol.duzen_imzasi == sag.duzen_imzasi,
            ayni_oran_imzasi=sol.oran_imzasi == sag.oran_imzasi,
        ))
    return sonuc


def ritim_kaniti(olcumler: list[SayfaOlcumu]) -> dict:
    """Yogunluk dizisi ve ardisik tekrar. Esik uygulamaz, dizi verir."""
    dizi = [o.yogunluk for o in olcumler]
    kademe = [min(4, int(y * 5)) for y in dizi]
    ardisik_uc_ayni = [
        [olcumler[i].sayfa, olcumler[i + 1].sayfa, olcumler[i + 2].sayfa]
        for i in range(len(kademe) - 2)
        if kademe[i] == kademe[i + 1] == kademe[i + 2]
    ]
    return {
        "yogunluk_dizisi": [round(y, 3) for y in dizi],
        "yogunluk_kademeleri": kademe,
        "ardisik_uc_ayni_kademe": ardisik_uc_ayni,
        "en_dusuk": round(min(dizi), 3) if dizi else None,
        "en_yuksek": round(max(dizi), 3) if dizi else None,
    }
