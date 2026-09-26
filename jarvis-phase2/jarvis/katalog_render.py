"""Sayfa render motoru -- goruntu katmani PIL, metin katmani VEKTOR.

TEMEL KURAL: URUN PIKSELI ASLA YUKARI ORNEKLENMEZ.
    Goruntu tuvali, urunun NATIVE cozunurlugune gore kurulur.
    Urun 1029 px ve 131 mm isteniyorsa tuval 200 DPI'da kurulur ve
    urun 1:1 yapistirilir. Interpolasyon yok, uydurma piksel yok.
    Efektif DPI olculur ve QA'ya yazilir.

ZEMIN GENISLETME -- UYDURMA DEGIL, DEVAM ETTIRME:
    Urun fotografi kesilmez (TYPE B: kontrollu genisletme izinli,
    kesim degil). Fotografin kendi zemin gradyani olculur ve ayni
    kurala gore disari uzatilir. Difuzyon kullanilmaz.

METIN DIFUZYONA CIZDIRILMEZ.
    Tum yazi reportlab ile vektor olarak dizilir. PNG teslimati
    PDF'ten uretilir -- boylece PNG ile PDF birebir aynidir.
"""

from __future__ import annotations

import io
import pathlib
from dataclasses import dataclass, field

from jarvis import katalog_tasarim_sistemi as ts


# --- yerlesim sozlesmesi -------------------------------------------------

@dataclass
class Oge:
    tur: str            # alan | foto | metin | cizgi | not_alani
    veri: dict = field(default_factory=dict)


@dataclass
class SayfaPlani:
    kimlik: str
    konsept: str
    goruntu_dpi: float
    ogeler: list[Oge] = field(default_factory=list)
    olcumler: dict = field(default_factory=dict)

    def ekle(self, tur: str, **veri) -> None:
        self.ogeler.append(Oge(tur, veri))


# --- goruntu katmani -----------------------------------------------------

def _np():
    import numpy as np
    return np


def zemin_tuvali(np, en_px: int, boy_px: int, zemin: dict,
                 gurultu_orani: float = 1.0):
    """Fotografin kendi zemin gradyanini tuval boyutuna uzatir."""
    ust = np.array(zemin.get("ust_rgb") or (240, 237, 232), dtype="float32")
    alt = np.array(zemin.get("alt_rgb") or (234, 230, 224), dtype="float32")
    sol = np.array(zemin.get("sol_rgb") or ust, dtype="float32")
    sag = np.array(zemin.get("sag_rgb") or ust, dtype="float32")

    yy = np.linspace(0.0, 1.0, boy_px, dtype="float32")[:, None, None]
    xx = np.linspace(0.0, 1.0, en_px, dtype="float32")[None, :, None]

    dikey = ust[None, None, :] * (1 - yy) + alt[None, None, :] * yy
    yatay = sol[None, None, :] * (1 - xx) + sag[None, None, :] * xx
    tuval = dikey * 0.68 + yatay * 0.32

    # Fotografin kendi dokusunu esle -- plastik duzluk baskida ucuz durur
    g = float(zemin.get("gurultu") or 0.008) * 255.0 * gurultu_orani
    if g > 0.3:
        rng = np.random.default_rng(11)
        tuval = tuval + rng.normal(0.0, g * 0.55, tuval.shape).astype("float32")
    return np.clip(tuval, 0, 255).astype("uint8")


def kirp_native(yol, kadraj: dict):
    """Kaynaktan verilen normalize kadraji TAM COZUNURLUKTE keser."""
    from PIL import Image
    im = Image.open(yol)
    im.load()
    im = im.convert("RGB")
    w, h = im.size
    x0 = max(0, int(round(kadraj["x"] * w)))
    y0 = max(0, int(round(kadraj["y"] * h)))
    x1 = min(w, int(round((kadraj["x"] + kadraj["en"]) * w)))
    y1 = min(h, int(round((kadraj["y"] + kadraj["boy"]) * h)))
    return im.crop((x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)))


def _yumusak_maske(np, en, boy, tuy, kenarlar=("sol", "sag", "ust", "alt")):
    """Kenarlari yumusatan alfa.

    YALNIZ IC KENARLAR tuylenmelidir. Sayfadan tasan kenari tuylemek
    sayfa kenarinda soluk bir seffaflik seridi birakir -- baskida
    gorunur kusurdur."""
    m = np.ones((boy, en), dtype="float32")
    t = max(1, int(tuy))
    ramp = np.linspace(0.0, 1.0, t, dtype="float32")
    if "ust" in kenarlar:
        m[:t] *= ramp[:, None]
    if "alt" in kenarlar:
        m[-t:] *= ramp[::-1][:, None]
    if "sol" in kenarlar:
        m[:, :t] *= ramp[None, :]
    if "sag" in kenarlar:
        m[:, -t:] *= ramp[::-1][None, :]
    return m


def goruntu_katmani(plan: SayfaPlani, analiz: dict) -> "object":
    """Sayfanin goruntu katmanini plan DPI'inda kurar."""
    from PIL import Image
    np = _np()
    dpi = plan.goruntu_dpi
    px = int(round(ts.SAYFA_MM / 25.4 * dpi))

    zemin = analiz.get("zemin") or {}
    tuval = zemin_tuvali(np, px, px, zemin)

    for oge in plan.ogeler:
        if oge.tur == "alan":
            v = oge.veri
            x0 = int(round(v["x"] / 25.4 * dpi)); y0 = int(round(v["y"] / 25.4 * dpi))
            x1 = int(round((v["x"] + v["en"]) / 25.4 * dpi))
            y1 = int(round((v["y"] + v["boy"]) / 25.4 * dpi))
            x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(px, x1), min(px, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            renk = np.array(v["renk"], dtype="float32")
            alfa = float(v.get("alfa", 1.0))
            bolge = tuval[y0:y1, x0:x1].astype("float32")
            tuval[y0:y1, x0:x1] = np.clip(
                bolge * (1 - alfa) + renk[None, None, :] * alfa, 0, 255).astype("uint8")

        elif oge.tur == "foto":
            v = oge.veri
            kirp = kirp_native(v["kaynak"], v["kadraj"])
            hedef_en = int(round(v["en"] / 25.4 * dpi))
            hedef_boy = int(round(v["boy"] / 25.4 * dpi))
            # YUKARI ORNEKLEME YASAK: hedef kaynagi asiyorsa kucult, buyutme.
            if hedef_en > kirp.width or hedef_boy > kirp.height:
                raise ValueError(
                    "yukari ornekleme reddedildi: kaynak %dx%d, hedef %dx%d "
                    "(%.1f DPI gerekirdi)"
                    % (kirp.width, kirp.height, hedef_en, hedef_boy,
                       ts.yerlesim_dpi(kirp.width, v["en"])))
            if (hedef_en, hedef_boy) != kirp.size:
                kirp = kirp.resize((hedef_en, hedef_boy), Image.LANCZOS)

            x0 = int(round(v["x"] / 25.4 * dpi)); y0 = int(round(v["y"] / 25.4 * dpi))
            parca = np.asarray(kirp, dtype="float32")
            ph, pw = parca.shape[:2]
            # tuval sinirlarina kirp
            kx0, ky0 = max(0, x0), max(0, y0)
            kx1, ky1 = min(px, x0 + pw), min(px, y0 + ph)
            if kx1 <= kx0 or ky1 <= ky0:
                continue
            parca = parca[ky0 - y0:ky1 - y0, kx0 - x0:kx1 - x0]
            kenarlar = v.get("tuy_kenar")
            if kenarlar is None:
                kenarlar = ("sol", "sag", "ust", "alt")
            tuy = v.get("tuy_px", max(8, int(dpi / 25.4 * 3.0)))
            if not kenarlar or v.get("tuy_px") == 0:
                m = np.ones((parca.shape[0], parca.shape[1], 1), dtype="float32")
            else:
                m = _yumusak_maske(np, parca.shape[1], parca.shape[0], tuy,
                                   kenarlar)[..., None]
            alt = tuval[ky0:ky1, kx0:kx1].astype("float32")
            tuval[ky0:ky1, kx0:kx1] = np.clip(
                alt * (1 - m) + parca * m, 0, 255).astype("uint8")

    return Image.fromarray(tuval)


# --- PDF katmani ---------------------------------------------------------

_KAYITLI = set()


def _font_kaydet():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    kok = pathlib.Path(ts.FONT_TTF_KOK)
    for p in sorted(kok.glob("*.ttf")):
        ad = p.stem
        if ad in _KAYITLI:
            continue
        try:
            pdfmetrics.registerFont(TTFont(ad, str(p)))
            _KAYITLI.add(ad)
        except Exception:                            # noqa: BLE001
            pass


def _font_adi(stil: str) -> tuple[str, float, float, float]:
    dosya, punto, satir, harf = ts.TIP[stil]
    if dosya not in _KAYITLI:
        # MonumentExtended-Ultrabold TTF yoksa Bold'a dus
        yedek = {"MonumentExtended-Ultrabold": "MonumentExtended-Regular",
                 "Metropolis-ExtraBold": "Metropolis-Bold"}.get(dosya)
        if yedek and yedek in _KAYITLI:
            dosya = yedek
    return dosya, punto, satir, harf


# OLCULDU 26.09.2026: Metropolis ailesinde U+00B7 (·) ve U+2022 (•)
# GLIFI YOK. Bu karakterler .notdef kutusu olarak basiliyordu ve
# tipografi QA carpisma olarak isaretliyordu. Metropolis ile dizilen
# her metinde guvenli ayraca cevrilir.
AYRAC_YEDEGI = {"·": "–", "•": "–"}


def guvenli_metin(metin: str, font: str) -> str:
    if not metin or not font.startswith("Metropolis"):
        return metin
    for k, v in AYRAC_YEDEGI.items():
        metin = metin.replace(k, v)
    return metin


def satir_sayisi(metin: str, stil: str, en_mm: float,
                 punto: float | None = None, harf: float | None = None) -> int:
    """Blogun kac satira sardigini ONCEDEN olcer -- akis hesabi icin."""
    _font_kaydet()
    f, p0, _s, h0 = _font_adi(stil)
    p0 = punto if punto is not None else p0
    h0 = harf if harf is not None else h0
    return len(_sar(None, guvenli_metin(metin, f), f, p0, h0, en_mm * ts.MM))


def blok_yuksekligi_mm(metin: str, stil: str, en_mm: float,
                       punto: float | None = None,
                       satir_pt: float | None = None,
                       azami_satir: int | None = None) -> float:
    _f, p0, s0, _h = ts.TIP[stil]
    s0 = satir_pt if satir_pt is not None else s0
    n = satir_sayisi(metin, stil, en_mm, punto)
    if azami_satir:
        n = min(n, int(azami_satir))
    return n * s0 / ts.MM


def _sar(tuval, metin: str, font: str, punto: float, harf: float,
         genislik_pt: float) -> list[str]:
    from reportlab.pdfbase import pdfmetrics
    satirlar: list[str] = []
    for paragraf in (metin or "").split("\n"):
        kelimeler = paragraf.split()
        if not kelimeler:
            satirlar.append("")
            continue
        kuyruk = ""
        for k in kelimeler:
            aday = (kuyruk + " " + k).strip()
            w = pdfmetrics.stringWidth(aday, font, punto) + harf * max(0, len(aday) - 1)
            if w <= genislik_pt or not kuyruk:
                kuyruk = aday
            else:
                satirlar.append(kuyruk)
                kuyruk = k
        satirlar.append(kuyruk)
    return satirlar


def pdf_uret(plan: SayfaPlani, goruntu, cikti_yolu) -> dict:
    """Goruntu katmani + vektor metin -> baskiya hazir PDF."""
    from reportlab.lib.colors import Color
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    _font_kaydet()
    sayfa_pt = ts.SAYFA_MM * ts.MM
    c = rl_canvas.Canvas(str(cikti_yolu), pagesize=(sayfa_pt, sayfa_pt))
    c.setTitle(plan.kimlik)

    tampon = io.BytesIO()
    goruntu.save(tampon, format="PNG", optimize=False)
    tampon.seek(0)
    c.drawImage(ImageReader(tampon), 0, 0, width=sayfa_pt, height=sayfa_pt,
                mask=None)

    def Y(y_mm: float) -> float:
        return sayfa_pt - y_mm * ts.MM

    metin_kayit: list[dict] = []

    for oge in plan.ogeler:
        v = oge.veri
        if oge.tur == "cizgi":
            c.setStrokeColor(Color(*v.get("renk", ts.MUREKKEP)))
            c.setLineWidth(v.get("kalinlik", 0.5))
            c.line(v["x"] * ts.MM, Y(v["y"]),
                   (v["x"] + v["en"]) * ts.MM, Y(v["y"] + v.get("boy", 0.0)))

        elif oge.tur == "not_alani":
            renk = Color(*v.get("renk", ts.MUREKKEP_SOLUK))
            c.setStrokeColor(renk)
            c.setLineWidth(0.4)
            satir_sayisi = int(v.get("satir", 3))
            aralik = v.get("aralik", 7.0)
            for i in range(satir_sayisi):
                yy = v["y"] + i * aralik
                c.line(v["x"] * ts.MM, Y(yy), (v["x"] + v["en"]) * ts.MM, Y(yy))
            if v.get("etiket"):
                f, punto, _s, harf = _font_adi("not_etiketi")
                t = c.beginText(v["x"] * ts.MM, Y(v["y"] - 2.6))
                t.setFont(f, punto)
                t.setCharSpace(harf)
                t.setFillColor(renk)
                t.textOut(guvenli_metin(v["etiket"], f))
                c.drawText(t)

        elif oge.tur == "metin":
            f, punto, satir_pt, harf = _font_adi(v["stil"])
            punto = v.get("punto", punto)
            satir_pt = v.get("satir_pt", satir_pt)
            harf = v.get("harf", harf)
            renk = v.get("renk", ts.MUREKKEP)
            genislik_pt = v["en"] * ts.MM
            satirlar = _sar(c, guvenli_metin(v["metin"], f), f, punto,
                            harf, genislik_pt)
            if v.get("azami_satir"):
                satirlar = satirlar[:int(v["azami_satir"])]
            from reportlab.pdfbase import pdfmetrics as _pm
            y = v["y"]
            hiza = v.get("hiza", "sol")
            for s in satirlar:
                if not s:
                    y += satir_pt / ts.MM
                    continue
                genislik = _pm.stringWidth(s, f, punto) + harf * max(0, len(s) - 1)
                if hiza == "sag":
                    bx = (v["x"] + v["en"]) * ts.MM - genislik
                elif hiza == "orta":
                    bx = (v["x"] + v["en"] / 2) * ts.MM - genislik / 2
                else:
                    bx = v["x"] * ts.MM
                t = c.beginText(bx, Y(y))
                t.setFont(f, punto)
                t.setCharSpace(harf)
                t.setFillColor(Color(*renk))
                t.textOut(s)
                c.drawText(t)
                y += satir_pt / ts.MM
            metin_kayit.append({
                "stil": v["stil"], "punto": punto, "satir": len(satirlar),
                "x_mm": v["x"], "y_mm": v["y"], "en_mm": v["en"],
                "yukseklik_mm": len(satirlar) * satir_pt / ts.MM,
            })

    c.showPage()
    c.save()
    return {"metin_bloklari": metin_kayit}

# --- metin/goruntu kontrast denetimi -------------------------------------

def _luma255(rgb):
    r, g, b = (v / 255.0 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def metin_kontrast_denetimi(plan: SayfaPlani, goruntu, esik: float = 3.2) -> list[dict]:
    """Her metin blogunun ALTINDAKI goruntuye karsi kontrastini olcer.

    NEDEN GEREKLI -- OLCULDU 26.09.2026:
        Tipografi QA metin-metin carpismasini yakaliyor ama metnin
        GORUNTU uzerinde okunup okunmadigini olcmuyordu. Kapak
        sayfasinda koyu baslik koyu spor salonu fotografinin uzerine
        dustu ve hicbir kapi yakalamadi.

    Anayasa madde 25: tipografi gorselin uzerine 'atilmaz'; olculen
    metin guvenli bolgelere yerlestirilir. Bu islev o kuralin
    olculebilir yarisidir.

    WCAG bagil kontrast orani kullanilir; baski icin esik 3.2
    (buyuk punto) -- ekran metni esiginden dusuk, cunku baskida
    yansima yoktur."""
    np = _np()
    dpi = plan.goruntu_dpi
    kare = np.asarray(goruntu.convert("RGB"), dtype="float32")
    boy_px, en_px = kare.shape[:2]
    ihlaller: list[dict] = []

    for oge in plan.ogeler:
        if oge.tur not in ("metin", "not_alani"):
            continue
        v = oge.veri
        if oge.tur == "metin" and not (v.get("metin") or "").strip():
            continue
        _d, punto, satir, _h = ts.TIP[v.get("stil", "govde")]
        punto = v.get("punto", punto)
        satir = v.get("satir_pt", satir)
        # Blok kutusu: yaklasik -- satir sayisi bilinmiyorsa tek satir
        yukseklik_mm = v.get("_yukseklik_mm") or (satir / ts.MM)
        x0 = int(max(0, v["x"] / 25.4 * dpi))
        y0 = int(max(0, (v["y"] - punto / ts.MM) / 25.4 * dpi))
        x1 = int(min(en_px, (v["x"] + v.get("en", 40)) / 25.4 * dpi))
        y1 = int(min(boy_px, (v["y"] + yukseklik_mm) / 25.4 * dpi))
        if x1 <= x0 or y1 <= y0:
            continue
        bolge = kare[y0:y1, x0:x1].reshape(-1, 3) / 255.0
        lin = np.where(bolge <= 0.04045, bolge / 12.92,
                       ((bolge + 0.055) / 1.055) ** 2.4)
        L = (0.2126 * lin[:, 0] + 0.7152 * lin[:, 1] + 0.0722 * lin[:, 2])
        zemin_L = float(np.median(L))
        # Zeminin ic degiskenligi: cok degiskense metin zaten okunmaz
        degiskenlik = float(np.percentile(L, 90) - np.percentile(L, 10))

        mr = v.get("renk", ts.MUREKKEP)
        mlin = [c if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in mr]
        metin_L = 0.2126 * mlin[0] + 0.7152 * mlin[1] + 0.0722 * mlin[2]

        ac, ka = max(metin_L, zemin_L), min(metin_L, zemin_L)
        oran = (ac + 0.05) / (ka + 0.05)
        if oran < esik or degiskenlik > 0.42:
            ihlaller.append({
                "stil": v.get("stil"), "metin": (v.get("metin") or
                                                 v.get("etiket") or "")[:40],
                "kontrast_orani": round(oran, 2), "esik": esik,
                "zemin_degiskenligi": round(degiskenlik, 3),
                "konum_mm": [round(v["x"], 1), round(v["y"], 1)],
                "sebep": ("kontrast yetersiz" if oran < esik
                          else "zemin cok degisken -- metin okunmaz"),
            })
    return ihlaller
