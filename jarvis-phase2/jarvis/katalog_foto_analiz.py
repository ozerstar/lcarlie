"""Fotograf analizi -- FOTOGRAF -> ANALIZ -> SANAT YONU -> DUZEN akisinin ilk adimi.

Sablona fotograf konmaz. Duzen fotograftan TURER. Bu modul duzenin
turetilecegi olculeri cikarir.

CIKARILANLAR:
    urun sinir kutusu        konu maskesi -> siki kadraj
    baskin ve vurgu palet    Lab uzayinda, algisal olarak birlestirilmis
    isik yonu                parlaklik gradyaninin ana ekseni
    gorsel agirlik merkezi   saliency agirlikli moment
    saliency vekili          yerel kontrast + kenar enerjisi + merkez egilimi
    negatif alan             dusuk doku + dusuk saliency bitisik bolgeler
    metin guvenli bolgeler   negatif alan & yeterli kontrast  <- DUZENI URETEN
    ton hiyerarsisi          bolge histogramlari
    derinlik vekili          bulaniklik gradyani (arka plan yumusamasi)
    zemin modeli             fonun kendi gradyani -- GENISLETME ICIN
    kadraj firsatlari        urun sinirindan turetilen gecerli kadrajlar
    kenar gerilimi           konu-kenar mesafe dagilimi
    gorsel hareket           asimetri ekseni

ZEMIN MODELI NEDEN ONEMLI:
    Bu urun fotograflarinin hepsi ayni kesintisiz fonda cekilmis.
    Fonun kendi gradyani orneklenip uzatilabilir -- difuzyon
    GEREKMEZ, uydurma piksel URETILMEZ. Fotografin kendi zemini
    kendi kurallariyla devam ettirilir.

BAGIMLILIK: Pillow + numpy (kurulu). Yeni bagimlilik YOK.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import asdict, dataclass

from jarvis import katalog_renk as renk


@dataclass(frozen=True)
class Bolge:
    x: float
    y: float
    en: float
    boy: float

    def sozluk(self) -> dict:
        return asdict(self)

    @property
    def alan(self) -> float:
        return self.en * self.boy

    @property
    def merkez(self) -> tuple[float, float]:
        return (self.x + self.en / 2.0, self.y + self.boy / 2.0)


@dataclass(frozen=True)
class ZeminModeli:
    """Fonun kendi gradyani. Genisletme bunun devamidir, uydurma degil."""

    ust_rgb: tuple[int, int, int]
    alt_rgb: tuple[int, int, int]
    sol_rgb: tuple[int, int, int]
    sag_rgb: tuple[int, int, int]
    ufuk_y: float | None        # zemin-duvar kirilmasi (0-1), yoksa None
    gurultu: float              # fonun doku miktari
    duz_mu: bool

    def sozluk(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FotoAnaliz:
    yol: str
    en_px: int
    boy_px: int
    urun_kutusu: Bolge              # 0-1 normalize
    urun_alan_orani: float
    baskin_renkler: list[dict]
    vurgu_renkleri: list[dict]
    isik_yonu_derece: float | None
    isik_gucu: float
    agirlik_merkezi: tuple[float, float]
    negatif_bolgeler: list[dict]
    metin_guvenli_bolgeler: list[dict]
    ton_hiyerarsisi: dict
    derinlik_vekili: float
    zemin: dict
    kadraj_firsatlari: list[dict]
    kenar_gerilimi: dict
    gorsel_hareket: str
    saliency_urun_payi: float
    keskinlik: float

    def sozluk(self) -> dict:
        d = asdict(self)
        d["urun_kutusu"] = self.urun_kutusu.sozluk()
        return d


# --- yardimcilar ---------------------------------------------------------

def _dizi(yol, azami=900):
    import numpy as np
    from PIL import Image
    im = Image.open(yol)
    im.load()
    tam = (im.width, im.height)
    im = im.convert("RGB")
    if max(im.size) > azami:
        o = azami / max(im.size)
        im = im.resize((max(1, int(im.width * o)), max(1, int(im.height * o))),
                       Image.BILINEAR)
    return np, np.asarray(im, dtype="float32") / 255.0, tam


def _konu_maskesi(np, rgb):
    """Kesintisiz fondan konuyu ayirir.

    Fon kenarlardan orneklenir; konu, fondan algisal olarak uzaklasan
    piksellerdir. Kesintisiz stüdyo fonu icin guvenilirdir."""
    boy, en = rgb.shape[:2]
    bant = max(3, int(min(en, boy) * 0.05))
    kenar = np.concatenate([
        rgb[:bant].reshape(-1, 3), rgb[:, :bant].reshape(-1, 3),
        rgb[:, -bant:].reshape(-1, 3),
    ])
    zemin = np.median(kenar, axis=0)
    fark = np.sqrt(((rgb - zemin) ** 2).sum(axis=2))
    esik = max(0.055, float(np.percentile(fark, 88)) * 0.55)
    ham = fark > esik

    # Golge zeminle birlesir; en buyuk bitisik bileseni al
    from scipy import ndimage
    etiket, adet = ndimage.label(ham)
    if adet == 0:
        return ham, zemin
    boyutlar = ndimage.sum(ham, etiket, range(1, adet + 1))
    en_buyuk = int(np.argmax(boyutlar)) + 1
    maske = etiket == en_buyuk
    maske = ndimage.binary_closing(maske, np.ones((5, 5)))
    maske = ndimage.binary_fill_holes(maske)
    return maske, zemin


def _saliency(np, rgb, maske):
    """Saliency vekili: yerel kontrast + kenar enerjisi + konu agirligi.

    Egitilmis model DEGIL -- vekildir ve boyle adlandirilir."""
    gri = rgb.mean(axis=2)
    gx = np.zeros_like(gri); gy = np.zeros_like(gri)
    gx[:, 1:-1] = np.abs(gri[:, 2:] - gri[:, :-2])
    gy[1:-1] = np.abs(gri[2:] - gri[:-2])
    kenar = gx + gy
    from scipy import ndimage
    yerel = ndimage.uniform_filter(gri ** 2, 17) - ndimage.uniform_filter(gri, 17) ** 2
    yerel = np.sqrt(np.maximum(yerel, 0))
    s = 0.45 * (kenar / (kenar.max() + 1e-6)) + 0.35 * (yerel / (yerel.max() + 1e-6))
    s = s + 0.20 * maske.astype("float32")
    s = ndimage.gaussian_filter(s, 6)
    return s / (s.max() + 1e-6)


def _isik_yonu(np, rgb, maske):
    """Zemin parlakligi gradyaninin ana ekseni -> isik yonu (derece)."""
    gri = rgb.mean(axis=2)
    zemin = ~maske
    if zemin.sum() < 100:
        return None, 0.0
    boy, en = gri.shape
    yy, xx = np.mgrid[0:boy, 0:en]
    g = gri[zemin]; x = xx[zemin].astype("float32"); y = yy[zemin].astype("float32")
    x = (x - x.mean()) / (en + 1e-6); y = (y - y.mean()) / (boy + 1e-6)
    A = np.stack([x, y, np.ones_like(x)], axis=1)
    try:
        kats, *_ = np.linalg.lstsq(A, g - g.mean(), rcond=None)
    except Exception:                                # noqa: BLE001
        return None, 0.0
    dx, dy = float(kats[0]), float(kats[1])
    guc = math.hypot(dx, dy)
    if guc < 1e-4:
        return None, 0.0
    # Isik, parlakligin ARTTIGI yonden gelir
    aci = math.degrees(math.atan2(-dy, dx)) % 360.0
    return round(aci, 1), round(min(1.0, guc * 12), 4)


def _zemin_modeli(np, rgb, maske) -> ZeminModeli:
    boy, en = rgb.shape[:2]
    zemin = ~maske
    bant = max(3, int(min(en, boy) * 0.06))

    def ort(dilim, m):
        alt = dilim[m[:dilim.shape[0], :dilim.shape[1]]] if m.shape == dilim.shape[:2] else dilim.reshape(-1, 3)
        if alt.size == 0:
            alt = dilim.reshape(-1, 3)
        return tuple(int(v * 255) for v in np.median(alt.reshape(-1, 3), axis=0))

    ust = ort(rgb[:bant], zemin[:bant])
    alt = ort(rgb[-bant:], zemin[-bant:])
    sol = ort(rgb[:, :bant], zemin[:, :bant])
    sag = ort(rgb[:, -bant:], zemin[:, -bant:])

    # Ufuk: zemin satirlarinin parlaklik farkinin en buyuk oldugu yer
    gri = rgb.mean(axis=2)
    satir = []
    for i in range(boy):
        m = zemin[i]
        satir.append(float(gri[i][m].mean()) if m.sum() > en * 0.25 else np.nan)
    dizi = np.array(satir, dtype="float32")
    ufuk = None
    gecerli = ~np.isnan(dizi)
    if gecerli.sum() > boy * 0.4:
        d = np.abs(np.gradient(np.nan_to_num(dizi, nan=float(np.nanmean(dizi)))))
        d[:int(boy * 0.35)] = 0            # ust yari ufuk olamaz
        if d.max() > 0.004:
            ufuk = round(float(np.argmax(d)) / boy, 4)

    yayilim = max(abs(ust[0] - alt[0]), abs(ust[1] - alt[1]), abs(ust[2] - alt[2]))
    return ZeminModeli(ust, alt, sol, sag, ufuk,
                       round(float(gri[zemin].std()) if zemin.sum() else 0.0, 4),
                       duz_mu=bool(yayilim < 6 and ufuk is None))


def _bitisik_bolgeler(np, bayrak, en_az_oran=0.012, azami=8):
    from scipy import ndimage
    etiket, adet = ndimage.label(bayrak)
    boy, en = bayrak.shape
    toplam = boy * en
    sonuc = []
    for i in range(1, adet + 1):
        m = etiket == i
        if m.sum() / toplam < en_az_oran:
            continue
        ys, xs = np.nonzero(m)
        sonuc.append({
            "x": round(float(xs.min()) / en, 4), "y": round(float(ys.min()) / boy, 4),
            "en": round(float(xs.max() - xs.min() + 1) / en, 4),
            "boy": round(float(ys.max() - ys.min() + 1) / boy, 4),
            "doluluk": round(float(m.sum()) / max((xs.max() - xs.min() + 1)
                                                  * (ys.max() - ys.min() + 1), 1), 3),
            "alan_orani": round(float(m.sum()) / toplam, 4),
        })
    sonuc.sort(key=lambda b: -b["alan_orani"])
    return sonuc[:azami]


def analiz(yol: str | pathlib.Path) -> FotoAnaliz:
    np, rgb, tam = _dizi(yol)
    boy, en = rgb.shape[:2]
    gri = rgb.mean(axis=2)

    maske, zemin_rgb = _konu_maskesi(np, rgb)
    sal = _saliency(np, rgb, maske)

    # --- urun sinir kutusu
    if maske.any():
        ys, xs = np.nonzero(maske)
        kutu = Bolge(round(float(xs.min()) / en, 4), round(float(ys.min()) / boy, 4),
                     round(float(xs.max() - xs.min() + 1) / en, 4),
                     round(float(ys.max() - ys.min() + 1) / boy, 4))
        urun_alan = round(float(maske.mean()), 4)
    else:
        kutu, urun_alan = Bolge(0.0, 0.0, 1.0, 1.0), 1.0

    # --- agirlik merkezi (saliency agirlikli)
    yy, xx = np.mgrid[0:boy, 0:en]
    w = sal.sum() + 1e-6
    merkez = (round(float((xx * sal).sum() / w) / en, 4),
              round(float((yy * sal).sum() / w) / boy, 4))

    # --- saliency urun payi
    pay = float(sal[maske].sum() / w) if maske.any() else 0.0

    # --- negatif alan: dusuk saliency + dusuk doku + konu disi
    from scipy import ndimage
    yerel_std = np.sqrt(np.maximum(
        ndimage.uniform_filter(gri ** 2, 21) - ndimage.uniform_filter(gri, 21) ** 2, 0))
    sakin = (sal < 0.22) & (yerel_std < 0.028) & (~maske)
    negatif = _bitisik_bolgeler(np, sakin)

    # --- metin guvenli bolgeler: sakin VE yeterli kontrast tasiyabilen
    # Koyu metin icin acik zemin, acik metin icin koyu zemin gerekir.
    acik = sakin & (gri > 0.62)
    koyu = sakin & (gri < 0.34)
    guvenli = []
    for bayrak, tur in ((acik, "koyu_metin"), (koyu, "acik_metin")):
        for b in _bitisik_bolgeler(np, bayrak, en_az_oran=0.02, azami=5):
            b["metin_turu"] = tur
            guvenli.append(b)
    guvenli.sort(key=lambda b: -b["alan_orani"])

    # --- ton hiyerarsisi
    ton = {
        "ortalama": round(float(gri.mean()), 4),
        "std": round(float(gri.std()), 4),
        "urun_ortalama": round(float(gri[maske].mean()), 4) if maske.any() else None,
        "zemin_ortalama": round(float(gri[~maske].mean()), 4) if (~maske).any() else None,
        "kontrast_farki": None,
    }
    if ton["urun_ortalama"] is not None and ton["zemin_ortalama"] is not None:
        ton["kontrast_farki"] = round(abs(ton["urun_ortalama"] - ton["zemin_ortalama"]), 4)

    # --- derinlik vekili: ust bolge ile alt bolge keskinlik farki
    def keskin(b):
        lap = (-4 * b[1:-1, 1:-1] + b[:-2, 1:-1] + b[2:, 1:-1]
               + b[1:-1, :-2] + b[1:-1, 2:])
        return float(lap.var())
    ust_k = keskin(gri[:boy // 2]); alt_k = keskin(gri[boy // 2:])
    derinlik = round(float(abs(ust_k - alt_k) / (max(ust_k, alt_k) + 1e-9)), 4)

    # --- palet
    try:
        pal = renk.palet(yol, 7)
        baskin = [r.sozluk() for r in pal]
        vurgu = [r.sozluk() for r in renk.vurgu_renkleri(pal, asgari_kroma=14.0)]
    except Exception:                                # noqa: BLE001
        baskin, vurgu = [], []

    # --- kenar gerilimi
    kenar_ger = {
        "sol": round(kutu.x, 4), "ust": round(kutu.y, 4),
        "sag": round(1.0 - (kutu.x + kutu.en), 4),
        "alt": round(1.0 - (kutu.y + kutu.boy), 4),
    }
    kenar_ger["en_dar"] = round(min(kenar_ger["sol"], kenar_ger["ust"],
                                    kenar_ger["sag"], kenar_ger["alt"]), 4)
    kenar_ger["degiyor"] = bool(kenar_ger["en_dar"] < 0.005)

    # --- gorsel hareket
    sol_k = float(sal[:, :en // 2].sum()); sag_k = float(sal[:, en // 2:].sum())
    if abs(sol_k - sag_k) / max(sol_k + sag_k, 1e-6) < 0.08:
        hareket = "dengeli"
    else:
        hareket = "sola_agir" if sol_k > sag_k else "saga_agir"

    isik_aci, isik_guc = _isik_yonu(np, rgb, maske)
    zemin = _zemin_modeli(np, rgb, maske)

    # --- kadraj firsatlari (urun sinirindan turetilir)
    kadrajlar = _kadraj_firsatlari(kutu, zemin, tam)

    return FotoAnaliz(
        yol=str(yol), en_px=tam[0], boy_px=tam[1],
        urun_kutusu=kutu, urun_alan_orani=urun_alan,
        baskin_renkler=baskin, vurgu_renkleri=vurgu,
        isik_yonu_derece=isik_aci, isik_gucu=isik_guc,
        agirlik_merkezi=merkez,
        negatif_bolgeler=negatif, metin_guvenli_bolgeler=guvenli,
        ton_hiyerarsisi=ton, derinlik_vekili=derinlik,
        zemin=zemin.sozluk(), kadraj_firsatlari=kadrajlar,
        kenar_gerilimi=kenar_ger, gorsel_hareket=hareket,
        saliency_urun_payi=round(pay, 4),
        keskinlik=round(min(1.0, keskin(gri) / 0.002), 4),
    )


def _kadraj_firsatlari(kutu: Bolge, zemin: ZeminModeli,
                       tam_px: tuple[int, int]) -> list[dict]:
    """Urun sinirindan turetilen gecerli kadrajlar.

    Her kadraj icin gercek piksel olcusu ve 300 DPI'daki azami
    fiziksel yerlesim hesaplanir -- kadraj kararinin baski sonucu
    gorunur olsun diye."""
    en_px, boy_px = tam_px
    firsatlar = []

    def ekle(ad, x, y, w, h, gerekce):
        x = max(0.0, x); y = max(0.0, y)
        w = min(w, 1.0 - x); h = min(h, 1.0 - y)
        if w <= 0.02 or h <= 0.02:
            return
        pw, ph = int(w * en_px), int(h * boy_px)
        firsatlar.append({
            "ad": ad, "x": round(x, 4), "y": round(y, 4),
            "en": round(w, 4), "boy": round(h, 4),
            "piksel": [pw, ph],
            "azami_mm_300dpi": [round(pw / 300 * 25.4, 1), round(ph / 300 * 25.4, 1)],
            "gerekce": gerekce,
        })

    p = 0.06   # nefes payi
    ekle("tam", 0.0, 0.0, 1.0, 1.0, "Fotografin tamami; en cok cozunurluk.")
    ekle("siki", kutu.x - p, kutu.y - p, kutu.en + 2 * p, kutu.boy + 2 * p,
         "Urun siniri + nefes payi; urunu buyutur, zemini azaltir.")
    ekle("dikey_serit", kutu.x - p * 2, 0.0, kutu.en + 4 * p, 1.0,
         "Urun genisliginde tam boy serit; dikey ritim ve kenar gerilimi.")
    ekle("yatay_bant", 0.0, kutu.y - p, 1.0, kutu.boy + 2 * p,
         "Urun yuksekliginde tam genislik bant; yatay sakinlik.")
    # Agresif: urunun ust ucundan asagi -- sayfayi asan kadraj icin
    ekle("agresif_ust", kutu.x + kutu.en * 0.05, kutu.y + kutu.boy * 0.02,
         kutu.en * 0.9, kutu.boy * 0.62,
         "Urunun ust yarisi; olcek kontrasti ve editoryal gerilim.")
    if zemin.ufuk_y:
        ekle("ufuk_ustu", 0.0, 0.0, 1.0, min(1.0, zemin.ufuk_y + 0.05),
             "Zemin kirilmasinin ustu; duvar yuzeyi tek dokuya iner.")
    return firsatlar


def toplu_analiz(yollar) -> dict:
    return {str(y): analiz(y).sozluk() for y in yollar}
