"""L'CARLIE katalog tasarim sistemi -- 210x210 mm kare.

FORMAT KARARI OLCUME DAYANIR:
    Diskteki dort gercek L'CARLIE katalogunun dordu de 210x210 mm.
    A4 uretim kodunun istisnasidir. Bu pilot kare formattadir.

COZUNURLUK GERCEGI -- OLCULDU 26.09.2026:
    Bes pilot urunun kaynak fotograflari 1254x1254 px ve bundan
    buyugu sistemde YOK (gorsel eslestirmeyle dogrulandi: birebir
    eslesmelerin hepsi 1254x1254).

    Siki kadraj sonrasi urun genisligi 405-753 px.

    KRITIK AYRIM: BUYUK YERLESTIRMEK != BUYUTMEK.
    Buyutme piksel UYDURUR. Dusuk DPI'da yerlestirme gercek pikselleri
    daha genis alana yayar -- yeni bilgi uydurmaz.

    Bu sistem urun piksellerini ASLA yukari orneklemez. Bunun yerine
    yerlesim DPI'ini olcer ve rapor eder. Urun icin taban 200 DPI:
    yumusak isikli urun fotografi icin baski kabul olcusudur ve
    FEMISIA'yi 52x131 mm yapar -- sayfa yuksekliginin %62'si.
"""

from __future__ import annotations

from dataclasses import dataclass

MM = 72.0 / 25.4          # mm -> punto
DPI = 300.0

# --- sayfa geometrisi ----------------------------------------------------
KESIM_MM = 210.0
TASMA_MM = 3.0
SAYFA_MM = KESIM_MM + 2 * TASMA_MM          # 216
GUVENLI_MM = 8.0                             # kesimden ice
PIKSEL = int(round(SAYFA_MM / 25.4 * DPI))   # 2551

# --- grid ----------------------------------------------------------------
# Kare sayfada 12 sutun fazla incedir; 8 sutun daha guclu bloklar verir.
KENAR_MM = 16.0
SUTUN = 8
OLUK_MM = 4.0
ICERIK_MM = KESIM_MM - 2 * KENAR_MM                       # 178
SUTUN_MM = (ICERIK_MM - (SUTUN - 1) * OLUK_MM) / SUTUN    # 18.75
TABAN_MM = 4.2                                            # taban cizgisi

# --- baski esikleri ------------------------------------------------------
URUN_TABAN_DPI = 200.0      # urun goruntusu icin mutlak taban
SAHNE_TABAN_DPI = 150.0     # uretilen/genisletilmis zemin icin taban
HEDEF_DPI = 300.0

# --- tipografi -----------------------------------------------------------
# (dosya, punto, satir_araligi_pt, harf_araligi_pt)
# Kare sayfa A4'ten kucuk oldugu icin olcek kontrasti daha sert kurulur:
# display ile govde arasinda ~5x fark. Eski katalogda bu fark ~4x idi.
TIP = {
    "devasa":      ("MonumentExtended-Ultrabold", 54.0, 52.0, 0.4),
    "display":     ("MonumentExtended-Ultrabold", 38.0, 38.0, 0.2),
    "urun_ad":     ("MonumentExtended-Ultrabold", 21.0, 24.0, 0.4),
    "urun_ad_kucuk": ("MonumentExtended-Ultrabold", 15.0, 18.0, 0.4),
    "alt_baslik":  ("MonumentExtended-Regular",   11.0, 15.0, 0.5),
    "ust_etiket":  ("Metropolis-SemiBold",         7.5, 10.0, 2.4),
    "govde":       ("Metropolis-Regular",          9.5, 14.5, 0.0),
    "govde_hafif": ("Metropolis-Light",            9.5, 14.5, 0.0),
    "alt_yazi":    ("Metropolis-Medium",           7.5, 10.5, 0.2),
    # FAZ -1'de eksik oldugu tespit edilen rol: fiziksel not alani etiketi
    "not_etiketi": ("Metropolis-Light",            6.5,  9.0, 1.8),
    "inci":        ("Metropolis-Light",            6.2,  8.4, 0.1),
    "folio":       ("Metropolis-Medium",           7.0,  9.0, 0.8),
}

FONT_KOK = "/opt/lcarlie/jarvis-phase2/varliklar/fontlar"
FONT_TTF_KOK = "/opt/lcarlie/jarvis-phase2/varliklar/fontlar-ttf"

# --- marka murekkebi -----------------------------------------------------
MUREKKEP = (0.09, 0.09, 0.10)
# OLCULDU: 0.44 gri krem zemin uzerinde 3.0 kontrast veriyordu --
# 7,5 punto yan metin icin baskida okunmaz. 0.30'a koyulastirildi.
MUREKKEP_SOLUK = (0.30, 0.30, 0.32)
KAGIT = (0.960, 0.953, 0.940)
BEYAZ = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class SayfaGeometri:
    """Tum olculer mm; kokeni SOL UST, tasma dahil sayfa kutusu."""

    sayfa_mm: float = SAYFA_MM
    tasma_mm: float = TASMA_MM
    kesim_mm: float = KESIM_MM
    guvenli_mm: float = GUVENLI_MM

    @property
    def kesim_kutusu(self) -> tuple[float, float, float, float]:
        t = self.tasma_mm
        return (t, t, t + self.kesim_mm, t + self.kesim_mm)

    @property
    def guvenli_kutu(self) -> tuple[float, float, float, float]:
        t = self.tasma_mm + self.guvenli_mm
        return (t, t, self.sayfa_mm - t, self.sayfa_mm - t)

    @property
    def icerik_kutusu(self) -> tuple[float, float, float, float]:
        t = self.tasma_mm + KENAR_MM
        return (t, t, self.sayfa_mm - t, self.sayfa_mm - t)

    def sutun_x(self, indeks: int) -> float:
        x0 = self.tasma_mm + KENAR_MM
        return x0 + indeks * (SUTUN_MM + OLUK_MM)

    def sutun_genislik(self, adet: int) -> float:
        return adet * SUTUN_MM + (adet - 1) * OLUK_MM

    def taban(self, n: int) -> float:
        """n'inci taban cizgisinin y konumu."""
        return self.tasma_mm + KENAR_MM + n * TABAN_MM


GEO = SayfaGeometri()


# --- renk turetme --------------------------------------------------------

def _luma(rgb) -> float:
    r, g, b = (v / 255.0 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def sayfa_paleti(analiz_sozluk: dict) -> dict:
    """Sayfa paletini URUN FOTOGRAFININ KENDI renginden turetir.

    Palet uydurulmaz: baskin ve vurgu renkler fotografin olcumunden
    gelir. Marka murekkebi sabit kalir -- degisken olan zemin ve vurgu."""
    baskin = analiz_sozluk.get("baskin_renkler") or []
    vurgular = analiz_sozluk.get("vurgu_renkleri") or []
    zemin = analiz_sozluk.get("zemin") or {}

    foto_zemin = tuple(zemin.get("ust_rgb") or (240, 236, 230))
    # Vurgu: en doygun, payi dusuk renk. Yoksa baskin ikinci renk.
    vurgu = tuple(vurgular[0]["rgb"]) if vurgular else (
        tuple(baskin[1]["rgb"]) if len(baskin) > 1 else (150, 120, 60))

    # Alan rengi: vurgunun cok soluk hali -- sayfa zemini olarak kullanilabilir
    def soluklastir(rgb, oran):
        return tuple(int(round(v + (250 - v) * oran)) for v in rgb)

    return {
        "foto_zemin": foto_zemin,
        "vurgu": vurgu,
        "alan_acik": soluklastir(vurgu, 0.90),
        "alan_orta": soluklastir(vurgu, 0.74),
        "alan_koyu": tuple(int(round(v * 0.42)) for v in vurgu),
        "vurgu_luma": round(_luma(vurgu), 4),
        "baskin": [tuple(r["rgb"]) for r in baskin[:5]],
    }


def metin_rengi_sec(zemin_rgb) -> tuple[float, float, float]:
    """Zemine gore okunur murekkep. WCAG degil baski kontrasti."""
    return MUREKKEP if _luma(zemin_rgb) > 0.45 else BEYAZ


# --- yerlesim olcegi -----------------------------------------------------

def yerlesim_dpi(piksel: int, mm: float) -> float:
    return piksel / (mm / 25.4) if mm > 0 else 0.0


def azami_mm(piksel: int, taban_dpi: float = URUN_TABAN_DPI) -> float:
    """Yukari ornekleme YAPMADAN kullanilabilecek en buyuk fiziksel olcu."""
    return piksel / taban_dpi * 25.4


def zemin_murekkebi(palet: dict) -> tuple[tuple, tuple]:
    """Sayfanin OLCULEN zeminine gore ana ve ikincil murekkep.

    Anayasa md.25: tipografi gorselin uzerine atilmaz. Murekkep
    varsayilmaz, zeminin parlakligindan TURETILIR. Kapak sayfasinda
    koyu spor salonu fotografi zemin oldugunda koyu murekkep
    kullanmak -- olculdu -- 2.6 kontrast uretiyordu."""
    zemin = palet.get("foto_zemin") or (240, 236, 230)
    if _luma(zemin) > 0.45:
        return MUREKKEP, MUREKKEP_SOLUK
    return BEYAZ, (0.84, 0.84, 0.86)
