"""Gorsel olcum: KAYNAK KALITESI ile YERLESIM KALITESI ayri olculur.

NEDEN AYRI:
    OLCULDU 25.09.2026 -- lcarlie-katalog.rapor.json:
      43 gorsel yerlesiminin 14'u (%33) buyutulmus, buna ragmen
      rapor "dusuk_dpi: 0" diyordu. Mevcut esik yerlestirilen piksel
      sayisini olcuyor; interpolasyonla uretilen pikseli de sayiyor.

    Bir goruntunun buyutulmesi "source quality passed" sonucu
    URETMEMELIDIR. Bu modul ikisini yapisal olarak ayirir:

      KaynakKalite    -- dosyada gercekte ne kadar bilgi var
      YerlesimKalite  -- o bilgi hedef olcude yetiyor mu

KIRPMA KORUNUMU:
    OLCULDU: varliklar/urun/ham medyan genislik 1254 px,
             varliklar/urun/kesim medyan genislik 299 px.
    Kirpma kaybi bir HATA DEGILDIR -- olcumdur. Bilincli editoryal
    kirpma da dusuk korunum uretir. Bu yuzden bu modul yargi vermez,
    yalniz kanit uretir; yargi sanat yonu katmanina aittir.

BAGIMLILIK: Pillow (kurulu). numpy yalnizca varsa kullanilir.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import asdict, dataclass

MM_INC = 25.4

# Baski esikleri. Kaynak: prepress pratiginde 300 dpi kabul olcusu.
HEDEF_DPI = 300.0
ASGARI_DPI = 250.0
# Mutlak taban: bunun altindaki hicbir yerlesim icin kullanilamaz.
MUTLAK_TABAN_PX = 400


@dataclass(frozen=True)
class KaynakKalite:
    """Dosyanin kendisinde ne var. Yerlesimden bagimsizdir."""

    yol: str
    genislik_px: int
    yukseklik_px: int
    kanal: str
    alfa_var: bool
    bayt: int
    biim: str
    # kalite gostergeleri
    keskinlik: float | None          # yuksek frekans enerjisi, 0-1 olceginde
    sikistirma_izi: float | None     # blok artefakti gostergesi, 0-1
    okunamadi: str | None = None     # DURUM AYRIMI: hata sebebi

    def sozluk(self) -> dict:
        return asdict(self)

    @property
    def kisa_kenar(self) -> int:
        return min(self.genislik_px, self.yukseklik_px)

    def azami_yerlesim_mm(self, dpi: float = HEDEF_DPI) -> tuple[float, float]:
        """Buyutmeden basilabilecek en buyuk olcu."""
        return (self.genislik_px / dpi * MM_INC, self.yukseklik_px / dpi * MM_INC)


@dataclass(frozen=True)
class YerlesimKalite:
    """Kaynak, hedef olcude yetiyor mu."""

    yerlesim_en_mm: float
    yerlesim_boy_mm: float
    efektif_dpi: float
    buyutme_katsayisi: float     # 1.0 = buyutme yok, 2.0 = iki kat buyutulmus
    buyutuldu: bool
    esik_dpi: float
    gecti: bool
    gerekce: str

    def sozluk(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KirpmaKorunumu:
    """Kirpmanin ne kadarini korudugu. Yargi DEGIL, olcumdur."""

    ozgun_alan_px: int
    korunan_alan_px: int
    atilan_alan_px: int
    korunum_orani: float
    cikti_genislik_px: int
    cikti_yukseklik_px: int
    en_boy_degisti: bool

    def sozluk(self) -> dict:
        return asdict(self)


# --- yardimcilar ---------------------------------------------------------

def _pillow():
    from PIL import Image
    return Image


def _numpy():
    try:
        import numpy
        return numpy
    except ImportError:          # pragma: no cover -- kurulu, ama zorunlu degil
        return None


def _gri_dizi(im, azami: int = 512):
    """Griye cevrilmis, kucultulmus numpy dizisi (0-1). numpy yoksa None."""
    np = _numpy()
    if np is None:
        return None, None
    kopya = im.convert("L")
    if max(kopya.size) > azami:
        oran = azami / max(kopya.size)
        kopya = kopya.resize(
            (max(1, int(kopya.width * oran)), max(1, int(kopya.height * oran))),
            _pillow().BILINEAR,
        )
    return np, np.asarray(kopya, dtype="float32") / 255.0


def _keskinlik(im) -> float | None:
    """Laplacian varyansi benzeri olcu, 0-1 araligina sikistirilmis.

    Mutlak deger tasimaz; ayni hatta karsilastirma icindir."""
    np, g = _gri_dizi(im)
    if np is None or g is None or g.size < 16:
        return None
    # 4-komsu Laplacian
    lap = (-4.0 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    v = float(lap.var())
    # 0.02 pratikte "net" esigi; tanh ile sikistir
    return round(float(math.tanh(v / 0.002)), 4)


def _sikistirma_izi(im) -> float | None:
    """8x8 blok sinirlarindaki enerji fazlaligi -- JPEG blok artefakti izi."""
    np, g = _gri_dizi(im, azami=512)
    if np is None or g is None or min(g.shape) < 24:
        return None
    dx = np.abs(np.diff(g, axis=1))
    if dx.shape[1] < 16:
        return None
    sutun = dx.mean(axis=0)
    blok = sutun[7::8]
    digerleri = np.delete(sutun, np.arange(7, sutun.size, 8))
    if digerleri.size == 0 or digerleri.mean() <= 0:
        return None
    oran = float(blok.mean() / digerleri.mean())
    return round(max(0.0, min(1.0, (oran - 1.0))), 4)


# --- kaynak kalitesi -----------------------------------------------------

def kaynak_kalite(yol: str | pathlib.Path) -> KaynakKalite:
    """Dosyayi oku ve kaynak gostergelerini cikar.

    Okunamazsa alanlar 0/None kalir ve `okunamadi` sebebi tasir --
    'olculemedi' ile 'kotu' ayri durumlardir."""
    p = pathlib.Path(yol)
    try:
        bayt = p.stat().st_size
    except OSError as hata:
        return KaynakKalite(str(p), 0, 0, "", False, 0, "", None, None,
                            okunamadi="stat: %s" % hata.__class__.__name__)
    try:
        Image = _pillow()
        with Image.open(p) as im:
            im.load()
            kanal = im.mode
            en, boy = im.size
            biim = (im.format or "").upper()
            alfa = "A" in kanal or kanal == "P" and "transparency" in im.info
            keskin = _keskinlik(im)
            sikis = _sikistirma_izi(im) if biim in ("JPEG", "JPG") else None
    except Exception as hata:          # noqa: BLE001 -- sebebi kaydediyoruz
        return KaynakKalite(str(p), 0, 0, "", False, bayt, "", None, None,
                            okunamadi="%s: %s" % (hata.__class__.__name__, hata))

    return KaynakKalite(str(p), en, boy, kanal, bool(alfa), bayt, biim,
                        keskin, sikis)


# --- yerlesim kalitesi ---------------------------------------------------

def yerlesim_kalite(kaynak: KaynakKalite, en_mm: float, boy_mm: float,
                    esik_dpi: float = ASGARI_DPI) -> YerlesimKalite:
    """Kaynagin verilen fiziksel olcude yetip yetmedigini olcer.

    KRITIK: buyutme, gecme sebebi olamaz. `buyutuldu` dogruysa
    `gecti` her zaman False'tur."""
    if kaynak.okunamadi or kaynak.genislik_px == 0:
        return YerlesimKalite(en_mm, boy_mm, 0.0, 0.0, False, esik_dpi, False,
                              "kaynak okunamadi: %s" % (kaynak.okunamadi or "bilinmiyor"))
    if en_mm <= 0 or boy_mm <= 0:
        return YerlesimKalite(en_mm, boy_mm, 0.0, 0.0, False, esik_dpi, False,
                              "gecersiz yerlesim olcusu")

    dpi_en = kaynak.genislik_px / (en_mm / MM_INC)
    dpi_boy = kaynak.yukseklik_px / (boy_mm / MM_INC)
    efektif = min(dpi_en, dpi_boy)

    # Hedef DPI'ya ulasmak icin gereken buyutme
    katsayi = HEDEF_DPI / efektif if efektif > 0 else 0.0
    buyutuldu = katsayi > 1.0 + 1e-6

    if efektif < esik_dpi:
        return YerlesimKalite(
            en_mm, boy_mm, round(efektif, 1), round(katsayi, 3), buyutuldu,
            esik_dpi, False,
            "efektif DPI %.0f < esik %.0f -- kaynak bu olcu icin yetersiz"
            % (efektif, esik_dpi))

    if buyutuldu:
        return YerlesimKalite(
            en_mm, boy_mm, round(efektif, 1), round(katsayi, 3), True,
            esik_dpi, False,
            "esigi geciyor ama hedef %.0f DPI icin %.2fx buyutme gerekir -- "
            "buyutme gecme sebebi degildir" % (HEDEF_DPI, katsayi))

    return YerlesimKalite(en_mm, boy_mm, round(efektif, 1), round(katsayi, 3),
                          False, esik_dpi, True,
                          "efektif DPI %.0f, buyutme yok" % efektif)


def azami_guvenli_yerlesim_mm(kaynak: KaynakKalite,
                              dpi: float = HEDEF_DPI) -> tuple[float, float]:
    """Buyutmeden basilabilecek en buyuk fiziksel olcu."""
    if kaynak.genislik_px == 0:
        return (0.0, 0.0)
    return (round(kaynak.genislik_px / dpi * MM_INC, 1),
            round(kaynak.yukseklik_px / dpi * MM_INC, 1))


# --- kirpma korunumu -----------------------------------------------------

def kirpma_korunumu(ozgun: KaynakKalite, kirpilmis: KaynakKalite) -> KirpmaKorunumu:
    """Kirpmanin ne kadarini korudugunu olcer. YARGI ICERMEZ.

    Dusuk korunum otomatik kotu DEGILDIR: bilincli editoryal kirpma da
    dusuk korunum uretir. Karar sanat yonu katmanina aittir."""
    oz_alan = ozgun.genislik_px * ozgun.yukseklik_px
    kr_alan = kirpilmis.genislik_px * kirpilmis.yukseklik_px
    oran = (kr_alan / oz_alan) if oz_alan else 0.0

    oz_en_boy = (ozgun.genislik_px / ozgun.yukseklik_px) if ozgun.yukseklik_px else 0.0
    kr_en_boy = (kirpilmis.genislik_px / kirpilmis.yukseklik_px) if kirpilmis.yukseklik_px else 0.0
    degisti = abs(oz_en_boy - kr_en_boy) > 0.01 * max(oz_en_boy, 1e-6)

    return KirpmaKorunumu(
        ozgun_alan_px=oz_alan,
        korunan_alan_px=kr_alan,
        atilan_alan_px=max(0, oz_alan - kr_alan),
        korunum_orani=round(oran, 4),
        cikti_genislik_px=kirpilmis.genislik_px,
        cikti_yukseklik_px=kirpilmis.yukseklik_px,
        en_boy_degisti=bool(degisti),
    )


# --- birlesik kanit ------------------------------------------------------

def gorsel_kaniti(yol: str | pathlib.Path,
                  en_mm: float | None = None,
                  boy_mm: float | None = None,
                  kirpilmis_yol: str | pathlib.Path | None = None) -> dict:
    """Bir gorsel icin tam olcum kaniti. Karar vermez."""
    kay = kaynak_kalite(yol)
    kanit: dict = {
        "kaynak_kalite": kay.sozluk(),
        "azami_guvenli_yerlesim_mm": azami_guvenli_yerlesim_mm(kay),
        "mutlak_taban_altinda": bool(kay.kisa_kenar and kay.kisa_kenar < MUTLAK_TABAN_PX),
    }
    if en_mm is not None and boy_mm is not None:
        kanit["yerlesim_kalite"] = yerlesim_kalite(kay, en_mm, boy_mm).sozluk()
    if kirpilmis_yol is not None:
        kir = kaynak_kalite(kirpilmis_yol)
        kanit["kirpilmis_kaynak"] = kir.sozluk()
        kanit["kirpma_korunumu"] = kirpma_korunumu(kay, kir).sozluk()
    return kanit
