"""Renk temeli -- paylasilan capability, AYRI AGENT DEGIL.

NEDEN AYRI AGENT DEGIL:
    Yaratici renk yonu rol 07'nin (Art Director), baski renk QA'si
    rol 15'in (Prepress) yetenegidir. Ikisinin de kendi basina ozgun
    veri kaynagi ve bagimsiz ret alani yok -- ayri rol acmak agent
    theater olurdu. Ama YETENEK olarak ikisi de zorunludur.

NEDEN KENDIMIZ YAZDIK:
    colour-science kurulabilirdi. Once mevcut araclarla cozmek
    kuralinin geregi olarak numpy ile yazildi ve CIEDE2000
    YAYIMLANMIS REFERANS VERIYE KARSI dogrulandi (Sharma, Wu, Dalal
    2005 test kumesi -- bkz. tests/test_katalog_renk.py).
    Yeni bagimlilik EKLENMEDI.

KAPSAM DISI: ICC profil donusumu, CMYK ayrimi, toplam murekkep ortusu.
    Bunlar prepress katmanina aittir ve bu fazda YAZILMADI.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

# D65 beyaz noktasi, 2 derece gozlemci
D65 = (95.047, 100.000, 108.883)


@dataclass(frozen=True)
class Renk:
    rgb: tuple[int, int, int]
    lab: tuple[float, float, float]
    lch: tuple[float, float, float]
    oran: float = 0.0            # sayfadaki payi

    def sozluk(self) -> dict:
        return asdict(self)


# --- donusumler ----------------------------------------------------------

def _dogrusal(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_dogrusal(v / 255.0) for v in rgb)
    return (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) * 100.0,
        (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) * 100.0,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) * 100.0,
    )


def _f(t: float) -> float:
    return t ** (1.0 / 3.0) if t > 216 / 24389 else (841 / 108) * t + 4 / 29


def xyz_lab(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    fx, fy, fz = (_f(v / w) for v, w in zip(xyz, D65, strict=True))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def srgb_lab(rgb) -> tuple[float, float, float]:
    return xyz_lab(srgb_xyz(rgb))


def lab_lch(lab) -> tuple[float, float, float]:
    L, a, b = lab
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0
    return (L, C, h)


# --- CIEDE2000 -----------------------------------------------------------

def delta_e2000(lab1, lab2, kL: float = 1.0, kC: float = 1.0,
                kH: float = 1.0) -> float:
    """CIE Delta E 2000. Sharma/Wu/Dalal referans kumesiyle dogrulandi."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cort = (C1 + C2) / 2.0
    G = 0.5 * (1 - math.sqrt(Cort ** 7 / (Cort ** 7 + 25.0 ** 7))) if Cort else 0.5

    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0 if (b1 or a1p) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0 if (b2 or a2p) else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    Lort = (L1 + L2) / 2.0
    Cortp = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hortp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hortp = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        hortp = (h1p + h2p + 360) / 2.0
    else:
        hortp = (h1p + h2p - 360) / 2.0

    T = (1
         - 0.17 * math.cos(math.radians(hortp - 30))
         + 0.24 * math.cos(math.radians(2 * hortp))
         + 0.32 * math.cos(math.radians(3 * hortp + 6))
         - 0.20 * math.cos(math.radians(4 * hortp - 63)))

    dTheta = 30 * math.exp(-(((hortp - 275) / 25.0) ** 2))
    RC = 2 * math.sqrt(Cortp ** 7 / (Cortp ** 7 + 25.0 ** 7)) if Cortp else 0.0
    SL = 1 + (0.015 * (Lort - 50) ** 2) / math.sqrt(20 + (Lort - 50) ** 2)
    SC = 1 + 0.045 * Cortp
    SH = 1 + 0.015 * Cortp * T
    RT = -math.sin(math.radians(2 * dTheta)) * RC

    return math.sqrt(
        (dLp / (kL * SL)) ** 2
        + (dCp / (kC * SC)) ** 2
        + (dHp / (kH * SH)) ** 2
        + RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
    )


def rgb_delta_e(rgb1, rgb2) -> float:
    return delta_e2000(srgb_lab(rgb1), srgb_lab(rgb2))


# --- kontrast ------------------------------------------------------------

def bagil_parlaklik(rgb) -> float:
    r, g, b = (_dogrusal(v / 255.0) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast_orani(rgb1, rgb2) -> float:
    """WCAG bagil kontrast orani (1:1 - 21:1)."""
    a, b = bagil_parlaklik(rgb1), bagil_parlaklik(rgb2)
    ac, ka = max(a, b), min(a, b)
    return (ac + 0.05) / (ka + 0.05)


# --- palet ---------------------------------------------------------------

def palet(gorsel_yolu, renk_sayisi: int = 8, azami_kenar: int = 220) -> list[Renk]:
    """Baskin renkleri algisal olarak anlamli sirayla dondurur."""
    from PIL import Image

    im = Image.open(gorsel_yolu)
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        arka = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        arka.paste(im, mask=im.split()[-1])
        im = arka
    else:
        im = im.convert("RGB")
    if max(im.size) > azami_kenar:
        oran = azami_kenar / max(im.size)
        im = im.resize((max(1, int(im.width * oran)), max(1, int(im.height * oran))),
                       Image.BILINEAR)

    nicel = im.quantize(colors=max(2, renk_sayisi * 2), method=2).convert("RGB")
    sayimlar = nicel.getcolors(nicel.width * nicel.height) or []
    toplam = sum(s for s, _ in sayimlar) or 1
    sayimlar.sort(reverse=True)

    sonuc: list[Renk] = []
    for adet, rgb in sayimlar:
        lab = srgb_lab(rgb)
        # algisal olarak cok yakin renkleri birlestir
        if any(delta_e2000(lab, r.lab) < 3.0 for r in sonuc):
            continue
        sonuc.append(Renk(tuple(int(v) for v in rgb), tuple(round(v, 3) for v in lab),
                          tuple(round(v, 3) for v in lab_lch(lab)),
                          round(adet / toplam, 4)))
        if len(sonuc) >= renk_sayisi:
            break
    return sonuc


def vurgu_renkleri(p: list[Renk], asgari_kroma: float = 20.0) -> list[Renk]:
    """Doygunlugu yuksek, payi dusuk renkler -- vurgu adaylari."""
    return [r for r in p if r.lch[1] >= asgari_kroma and r.oran < 0.25]


def baskin_renk(p: list[Renk]) -> Renk | None:
    return p[0] if p else None


def palet_iliskisi(gorsel_paleti: list[Renk], sayfa_rengi) -> dict:
    """Gorsel ile sayfa zemini arasindaki renk iliskisi -- KANIT, yargi degil."""
    if not gorsel_paleti:
        return {"durum": "VERI_YOK", "sebep": "palet bos"}
    sayfa_lab = srgb_lab(sayfa_rengi)
    mesafeler = [delta_e2000(r.lab, sayfa_lab) for r in gorsel_paleti]
    return {
        "durum": "OK",
        "en_yakin_dE": round(min(mesafeler), 2),
        "en_uzak_dE": round(max(mesafeler), 2),
        "baskin_dE": round(mesafeler[0], 2),
        "kontrast_orani": round(kontrast_orani(gorsel_paleti[0].rgb, sayfa_rengi), 2),
        "sayfa_lab": tuple(round(v, 2) for v in sayfa_lab),
    }
