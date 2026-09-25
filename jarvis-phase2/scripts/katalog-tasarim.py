#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KATALOG TASARIMI — mimariden basılabilir PDF'e.

Bu betik SAYFA ÇİZER. Kararlar `katalog_mimari.py`de; metin
`state/katalog.json`da (yayındaki Wix metninden ayıklanmış, mevzuat
denetiminden geçmiş); ürün pikselleri `gorsel-kompozit.py`nin kestiği
gerçek fotoğraflardan.

🔴 ÜÇ ŞEY BURADA ÜRETİLMEZ, OKUNUR: iddia, ürün pikseli, yaratıcı fikir.
Üretilen tek şey YERLEŞİMDİR.

═══ NEDEN VEKTÖR PDF ═══
Metin reportlab ile vektör çizilir ve fontlar GÖMÜLÜR. Sayfaları 300 DPI
raster üretip PDF'e koymak daha kolaydı; ama 9,5 puntoluk gövde metni
rasterde baskıda yumuşar. "Düşük çözünürlüklü görseli büyütüp print-ready
sayma" kuralının tipografi karşılığı budur.

═══ PREPRESS ═══
Her yerleştirilen görselin EFEKTİF DPI'ı hesaplanır ve eşiğin altında
kalan rapora yazılır. Taşma (bleed) ve güvenli alan ölçülerle uygulanır.
"PDF oluştu" PASS değildir; rapor okunur.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

from reportlab.lib.colors import Color
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "scripts"))

import katalog_mimari as KM  # noqa: E402

FONT_DIZIN = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar-ttf")
KESIM = pathlib.Path("/opt/lcarlie/katalog-kesim")
SAHNE = pathlib.Path("/opt/lcarlie/gorsel-kuyruk/cikti")
KATALOG_JSON = pathlib.Path(
    os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "katalog.json"
CIKTI = pathlib.Path("/opt/lcarlie/katalog-baski")
# Kirpilmis + baski cozunurlugune getirilmis zemin gorselleri.
BASKI_ONBELLEK = pathlib.Path("/opt/lcarlie/katalog-baski/gorsel")

EN_AZ_DPI = 250.0        # baskı eşiği; altında kalan rapora yazılır

# Tuval ölçüleri (taşma dahil)
TUVAL_EN = KM.SAYFA_EN_MM + 2 * KM.TASMA_MM
TUVAL_BOY = KM.SAYFA_BOY_MM + 2 * KM.TASMA_MM


class TasarimHatasi(ValueError):
    """Sayfa çizilemedi. Sessizce boş sayfa üretilmez."""


# ── yardımcılar ──────────────────────────────────────────────────────────
def fontlari_yukle() -> None:
    for yol in sorted(FONT_DIZIN.glob("*.ttf")):
        pdfmetrics.registerFont(TTFont(yol.stem, str(yol)))


def _y(ust_mm: float) -> float:
    """Üstten ölçülen mm -> reportlab'in alttan y'si (taşma dahil)."""
    return (TUVAL_BOY - ust_mm) * mm


class Sayfa:
    """Tek sayfa. Koordinatlar ÜSTTEN mm; tasarım böyle düşünülür."""

    def __init__(self, c: rl_canvas.Canvas, no: int, tek: bool):
        self.c = c
        self.no = no
        self.tek = tek           # tek sayfa = sağ sayfa (iç kenar solda)
        self.gorsel_raporu: list = []
        # Kaynak cozunurlugu yetmedigi icin KUCULTULEN urunler.
        self.kisitli: list = []

    # -- geometri --
    @property
    def sol_kenar(self) -> float:
        return KM.TASMA_MM + (KM.IC_MM if self.tek else KM.DIS_MM)

    @property
    def sag_kenar(self) -> float:
        return KM.TASMA_MM + (KM.DIS_MM if self.tek else KM.IC_MM)

    @property
    def metin_en(self) -> float:
        return TUVAL_EN - self.sol_kenar - self.sag_kenar

    def sutun_x(self, sutun: int) -> float:
        """0-tabanlı sütunun sol kenarı (mm, taşma dahil)."""
        birim = (self.metin_en - (KM.SUTUN - 1) * KM.OLUK_MM) / KM.SUTUN
        return self.sol_kenar + sutun * (birim + KM.OLUK_MM)

    def sutun_en(self, adet: int) -> float:
        birim = (self.metin_en - (KM.SUTUN - 1) * KM.OLUK_MM) / KM.SUTUN
        return adet * birim + (adet - 1) * KM.OLUK_MM

    # -- boyama --
    def zemin(self, renk, tasmali: bool = True) -> None:
        self.c.setFillColor(Color(*renk))
        if tasmali:
            self.c.rect(0, 0, TUVAL_EN * mm, TUVAL_BOY * mm, stroke=0, fill=1)
        else:
            self.c.rect(KM.TASMA_MM * mm, KM.TASMA_MM * mm,
                        KM.SAYFA_EN_MM * mm, KM.SAYFA_BOY_MM * mm,
                        stroke=0, fill=1)

    def gorsel(self, yol: pathlib.Path, x_mm: float, ust_mm: float,
               en_mm: float, boy_mm: float, maske: bool = False) -> None:
        """Görsel yerleştirir, ORANI KORUR ve EFEKTİF DPI'ını kaydeder.

        🔴 ILK SURUM GORSELI EZIYORDU. reportlab drawImage verilen en/boy'a
        TAM oturtur; kaynak orani farkliysa gerer. Bant duzeninde 0,70
        oranli doku 1,32'ye sikisiyordu -- goz bunu hemen yakalar, mineral
        doku yatay cizgilere doner. Artik kaynak once hedef orana KIRPILIR
        (CSS object-fit: cover mantigi), sonra yerlesir.

        🔴 IKINCI KUSUR: DPI yalniz genislige bakiyordu. Sutun duzeninde
        genislik yetiyordu ama YUKSEKLIK yetmiyordu (197 DPI). Artik iki
        boyut da olculur ve KUCUK olani raporlanir.

        Saydam urun kesimleri PNG kalir (alfa gerekli); zemin gorselleri
        baski JPEG'ine cevrilir -- PDF 138 MB'tan makul boyuta iner ve
        300 DPI q92 JPEG baskida kayipsizla ayirt edilmez.
        """
        if not yol.is_file():
            raise TasarimHatasi("gorsel yok: %s" % yol)

        from PIL import Image
        hedef_oran = en_mm / boy_mm
        kullanilacak = yol

        if not maske:
            with Image.open(yol) as im:
                kaynak_oran = im.width / im.height
                gerekli_en = int(round(en_mm / 25.4 * 300))
                gerekli_boy = int(round(boy_mm / 25.4 * 300))
                imza = "%s-%dx%d" % (yol.stem, gerekli_en, gerekli_boy)
                onbellek = BASKI_ONBELLEK / (imza + ".jpg")
                if not onbellek.is_file():
                    calisma = im.convert("RGB")
                    # 1) hedef orana kirp (merkezden)
                    if abs(kaynak_oran - hedef_oran) > 0.01:
                        if kaynak_oran > hedef_oran:
                            yeni_en = int(calisma.height * hedef_oran)
                            sol = (calisma.width - yeni_en) // 2
                            calisma = calisma.crop(
                                (sol, 0, sol + yeni_en, calisma.height))
                        else:
                            yeni_boy = int(calisma.width / hedef_oran)
                            ust = (calisma.height - yeni_boy) // 2
                            calisma = calisma.crop(
                                (0, ust, calisma.width, ust + yeni_boy))
                    # 2) baski cozunurluguna getir
                    if calisma.width < gerekli_en:
                        calisma = calisma.resize(
                            (gerekli_en, gerekli_boy), Image.LANCZOS)
                    elif calisma.width > gerekli_en * 1.15:
                        calisma = calisma.resize(
                            (gerekli_en, gerekli_boy), Image.LANCZOS)
                    BASKI_ONBELLEK.mkdir(parents=True, exist_ok=True)
                    gecici = onbellek.with_suffix(".jpg.tmp")
                    calisma.save(gecici, "JPEG", quality=92, subsampling=0,
                                 optimize=True, dpi=(300, 300))
                    gecici.replace(onbellek)
                kullanilacak = onbellek

        okuyucu = ImageReader(str(kullanilacak))
        px_en, px_boy = okuyucu.getSize()
        dpi_en = px_en / (en_mm / 25.4)
        dpi_boy = px_boy / (boy_mm / 25.4)
        self.gorsel_raporu.append({
            "sayfa": self.no, "dosya": kullanilacak.name,
            "kaynak": yol.name,
            "piksel": [px_en, px_boy],
            "yerlesim_mm": [round(en_mm, 1), round(boy_mm, 1)],
            "efektif_dpi": round(min(dpi_en, dpi_boy), 1),
            "buyutuldu": kullanilacak != yol,
        })
        self.c.drawImage(okuyucu, x_mm * mm, _y(ust_mm + boy_mm),
                         en_mm * mm, boy_mm * mm,
                         mask="auto" if maske else None)

    def yazi(self, metin: str, stil: str, x_mm: float, ust_mm: float,
             renk=KM.MUREKKEP, hiza: str = "sol") -> float:
        """Tek satirlik metin. Harf araligi (tracking) UYGULANIR.

        🔴 Canvas'in setCharSpace'i YOK (olculdu: AttributeError); tracking
        yalniz metin nesnesinde ayarlanir. Atlayip "dogru fontu kullandim"
        demek, tipografi sistemini yazip uygulamamak olurdu -- ust
        etiketler 2,2 birim acik, baslıklar 0,4-1,2 arasi.
        """
        font, punto, satir, aralik = KM.TIP[stil]
        bosluk = aralik * punto / 100.0
        self.c.setFillColor(Color(*renk))
        y = ust_mm
        for parca in metin.split(chr(10)):
            genislik = (pdfmetrics.stringWidth(parca, font, punto)
                        + bosluk * max(0, len(parca) - 1))
            x = x_mm * mm
            if hiza == "sag":
                x = x_mm * mm - genislik
            elif hiza == "orta":
                x = x_mm * mm - genislik / 2.0
            t = self.c.beginText(x, _y(y + punto * 0.352778))
            t.setFont(font, punto)
            t.setCharSpace(bosluk)
            t.textOut(parca)
            self.c.drawText(t)
            y += satir * 0.352778
        return y

    def paragraf(self, metin: str, stil: str, x_mm: float, ust_mm: float,
                 en_mm: float, renk=KM.MUREKKEP) -> float:
        """Sarmalı metin. Dönen değer: metnin bittiği ÜST mm."""
        font, punto, satir, _ = KM.TIP[stil]
        self.c.setFont(font, punto)
        self.c.setFillColor(Color(*renk))
        y = ust_mm
        for blok in metin.split("\n"):
            if not blok.strip():
                y += satir * 0.352778 * 0.6
                continue
            aktif = ""
            for kelime in blok.split():
                deneme = (aktif + " " + kelime).strip()
                if pdfmetrics.stringWidth(deneme, font, punto) <= en_mm * mm:
                    aktif = deneme
                else:
                    self.c.drawString(x_mm * mm, _y(y + punto * 0.352778), aktif)
                    y += satir * 0.352778
                    aktif = kelime
            if aktif:
                self.c.drawString(x_mm * mm, _y(y + punto * 0.352778), aktif)
                y += satir * 0.352778
        return y

    def urun_zemini(self, x_mm: float, ust_mm: float, en_mm: float,
                    boy_mm: float, vurgu) -> None:
        """Ürünün oturacağı yumuşak renkli alan.

        🔴 BEYAZ URUN BEYAZ KAGITTA KAYBOLUYORDU. LUCIDERM, HYDRAVIE,
        INTIMBLANC gibi beyaz ambalajlar krem rengi kagit uzerinde
        neredeyse gorunmuyordu -- gozle goruldu, DPI raporu bunu
        soylemez. Urun bir zemine oturmali.

        Zemin bolumun VURGU renginden turetilir ve cok dusuk yogunlukta
        kullanilir: sayfalar farklidir ama ayni markaya ait olduklari
        anlasilir (Color Director kurali). Sert bir kutu degil, yumusak
        bir alan: kenarlarda yogunluk azalir.
        """
        self.c.saveState()
        adim = 26
        for i in range(adim):
            oran = i / (adim - 1.0)
            # Disa dogru soluyan katmanlar
            pay = oran * 0.5
            alfa = 0.085 * (1.0 - oran) ** 1.2
            self.c.setFillColor(Color(vurgu[0], vurgu[1], vurgu[2], alpha=alfa))
            self.c.rect((x_mm - en_mm * pay * 0.16) * mm,
                        _y(ust_mm + boy_mm + boy_mm * pay * 0.10),
                        (en_mm * (1 + pay * 0.32)) * mm,
                        (boy_mm * (1 + pay * 0.20)) * mm,
                        stroke=0, fill=1)
        self.c.restoreState()

    def temas_golgesi(self, x_mm: float, alt_mm: float, en_mm: float) -> None:
        """Ürünün zemine değdiği yerde dar, koyu gölge.

        Olmayinca urun havada duruyor -- Instagram motorunda ayni kusuru
        olcup duzelttik, katalogda tekrarlamanin anlami yok.
        """
        self.c.saveState()
        adim = 14
        for i in range(adim):
            oran = i / (adim - 1.0)
            yayilma = 1.0 + oran * 1.8
            self.c.setFillColor(Color(0.12, 0.11, 0.10,
                                      alpha=0.16 * (1.0 - oran) ** 1.5))
            g = en_mm * 0.62 * yayilma
            self.c.ellipse((x_mm + en_mm / 2 - g / 2) * mm,
                           _y(alt_mm + 1.4 + oran * 1.6),
                           (x_mm + en_mm / 2 + g / 2) * mm,
                           _y(alt_mm - 0.6 - oran * 1.2),
                           stroke=0, fill=1)
        self.c.restoreState()

    def cizgi(self, x_mm: float, ust_mm: float, en_mm: float,
              renk=KM.MUREKKEP_SOLUK, kalinlik: float = 0.25) -> None:
        self.c.setStrokeColor(Color(*renk))
        self.c.setLineWidth(kalinlik)
        self.c.line(x_mm * mm, _y(ust_mm), (x_mm + en_mm) * mm, _y(ust_mm))

    def sayfa_numarasi(self, vurgu) -> None:
        """Sayfa numarası DIŞ kenarda: kapalı katalogda başparmak orada."""
        x = (TUVAL_EN - self.sag_kenar) if self.tek else self.sol_kenar
        self.yazi(str(self.no), "sayfa_no", x,
                  TUVAL_BOY - KM.TASMA_MM - KM.ALT_MM + 10,
                  renk=vurgu, hiza="sag" if self.tek else "sol")


# ── içerik erişimi ───────────────────────────────────────────────────────
def katalog_oku() -> dict:
    if not KATALOG_JSON.is_file():
        raise TasarimHatasi("katalog.json yok -- once scripts/katalog-uret.py")
    veri = json.loads(KATALOG_JSON.read_text(encoding="utf-8"))
    return {u["slug"]: u for u in veri["urunler"]}


# Baski icin buyutulmus sahnelerin saklandigi yer.
SAHNE_BASKI = pathlib.Path("/opt/lcarlie/katalog-sahne")


def sahne_bul(onek: str, en_az_px: int = 0) -> pathlib.Path | None:
    """Sahne dosyasi. Baski cozunurlugu gerekiyorsa buyutulmus surumu.

    🔴 PREPRESS DENETIMI BUNU YAKALADI: 896x1280 sahne 216 mm genisliginde
    yerlesince EFEKTIF DPI 105 cikti. Kendi kuralimiz: "dusuk cozunurluklu
    AI gorselini buyutup print-ready sayma."
    Cozum iki katli: (1) sahneler 1280x1792'de YENIDEN uretildi (ktb-*),
    (2) yine yetmiyorsa Lanczos ile buyutulur. Ikincisi yumusak soyut doku
    icin savunulabilir -- kaybolacak ince ayrinti yok -- ama rapora
    "buyutuldu" diye YAZILIR, gizlenmez.
    """
    # Once baski surumu (ktb-), sonra taslak (kt-).
    for on in ("ktb-" + onek.split("-", 1)[-1], onek):
        adaylar = sorted(SAHNE.glob(on + "_*.png"))
        if not adaylar:
            continue
        kaynak = adaylar[0]
        if not en_az_px:
            return kaynak
        from PIL import Image
        with Image.open(kaynak) as im:
            if im.width >= en_az_px:
                return kaynak
            SAHNE_BASKI.mkdir(parents=True, exist_ok=True)
            hedef = SAHNE_BASKI / (kaynak.stem + "-x%d.png" % en_az_px)
            if not hedef.is_file():
                oran = en_az_px / im.width
                buyuk = im.resize((en_az_px, round(im.height * oran)),
                                  Image.LANCZOS)
                gecici = hedef.with_suffix(".png.tmp")
                buyuk.save(gecici, "PNG")
                gecici.replace(hedef)
            return hedef
    return None


KESIM_KIRPILMIS = pathlib.Path("/opt/lcarlie/katalog-kesim-kirpik")
BASKI_GORSEL = pathlib.Path("/opt/lcarlie/katalog-baski-gorsel")

# Baski esigi: bunun altina dusen yerlesim KUCULTULUR, buyutulmez.
BASKI_DPI = 250.0


def _baski_kaynagi(slug: str) -> pathlib.Path | None:
    """Urunun tam cozunurluklu ana fotografi (varsa)."""
    dizin = BASKI_GORSEL / "dizin.json"
    if not dizin.is_file():
        return None
    try:
        kayitlar = json.loads(dizin.read_text(encoding="utf-8"))
    except ValueError:
        return None
    for k in kayitlar:
        if k.get("slug") == slug:
            yol = BASKI_GORSEL / k["dosya"]
            if yol.is_file():
                return yol
    return None


def en_fazla_yerlesim(kesim: pathlib.Path) -> tuple:
    """Bu kesimin BASKI_DPI'yi tutturan en buyuk yerlesimi (mm).

    🔴 SESSIZCE BUYUTMEK YERINE OLCEGI SINIRLAMAK. Kaynak fotograflarin
    27'si 1254 piksel -- Wix'in kucultmesi degil, YUKLENEN ORIJINALIN
    kendisi; fotograflar web icin cekilmis. Buyutup "print-ready" demek
    kendi kuralimizi cignerdi. Bunun yerine urun o sayfada daha kucuk
    yerlesir ve hangi urunlerin kaynaktan sinirli oldugu rapora yazilir.
    """
    from PIL import Image
    with Image.open(kesim) as im:
        return (im.width / BASKI_DPI * 25.4, im.height / BASKI_DPI * 25.4)


def kesim_bul(urun: dict) -> pathlib.Path | None:
    """Ürünün kesilmiş VE SAYDAM KENARI ATILMIŞ fotoğrafı.

    🔴 BU KATALOGUN EN BUYUK KUSURUYDU. rembg kesimi, kaynak karenin
    tamamini korur: sise ortada kucuk bir nesne, etrafi saydam alfa.
    Sayfaya oldugu gibi yerlesince urun sayfa yuksekliginin %52'sine
    olceklenmis GORUNUYOR ama gercekte gorunur sise %15'ini kapliyordu --
    A4'te kaybolmus bir kucuk resim.
    Gozle goruldu, sayilarla degil: DPI raporu "her sey 250 ustunde" diyordu
    ve teknik olarak dogruydu. Teknik basari yaratici basari degildir.

    Kirpilmis surum ayri onbellekte tutulur; kesim maskesi degismedikce
    yeniden hesaplanmaz.
    """
    if not urun.get("gorseller"):
        return None
    import importlib.util
    sp = importlib.util.spec_from_file_location(
        "gk", str(KOK / "scripts" / "gorsel-kompozit.py"))
    gk = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(gk)
    # 🔴 BASKI KAYNAGI AYRI. Panel/saha seti 1400 piksele kuculttugumuz
    # WebP; kirpinca sise 230-400 piksel kaliyor ve 43-61 mm'ye yerlesince
    # 130-170 DPI ediyor (olculdu). Baski seti Wix orijinalidir.
    kaynak = _baski_kaynagi(urun["slug"]) or gk.ana_gorsel(urun["slug"])
    gk.urun_kesimi(kaynak)                      # onbellege yazar
    ham = KESIM / (kaynak.stem + ".png")
    if not ham.is_file():
        return None

    KESIM_KIRPILMIS.mkdir(parents=True, exist_ok=True)
    kirpik = KESIM_KIRPILMIS / ham.name
    if not kirpik.is_file():
        from PIL import Image
        with Image.open(ham) as im:
            kutu = im.getbbox()
            kesilmis = im.crop(kutu) if kutu else im.copy()
            gecici = kirpik.with_suffix(".png.tmp")
            kesilmis.save(gecici, "PNG")
            gecici.replace(kirpik)
    return kirpik


def _yariya_bol(metin: str) -> tuple:
    """Uzun içerik listesini iki sütuna böler (virgül sınırında)."""
    parcalar = [p.strip() for p in metin.split(",") if p.strip()]
    if len(parcalar) < 4:
        return metin, ""
    orta = len(parcalar) // 2
    return ", ".join(parcalar[:orta]), ", ".join(parcalar[orta:])


def _ad_sar(ad: str, stil: str, en_mm: float) -> str:
    """Urun adini sutuna sigdirir; sigmiyorsa SATIRA BOLER.

    🔴 "HYDRAVIE | YOGUN NEMLENDIRICI YUZ" iki'li sayfada metin sutununu
    tasip sayfa kenarindan cikiyordu. Monument Extended cok genis bir yuz;
    uzun urun adlari 7 sutunu rahatca asiyor. Kirpmak yerine boluyoruz --
    urun adi kisaltilacak bir sey degil.
    """
    font, punto, _, _ = KM.TIP[stil]
    sinir = en_mm * mm
    if pdfmetrics.stringWidth(ad, font, punto) <= sinir:
        return ad
    parcalar, aktif = [], ""
    for kelime in ad.replace("|", " ").split():
        deneme = (aktif + " " + kelime).strip()
        if pdfmetrics.stringWidth(deneme, font, punto) <= sinir:
            aktif = deneme
        else:
            if aktif:
                parcalar.append(aktif)
            aktif = kelime
    if aktif:
        parcalar.append(aktif)
    return chr(10).join(parcalar[:3])


def _kisalt(metin: str, en_fazla: int) -> str:
    metin = (metin or "").strip()
    if len(metin) <= en_fazla:
        return metin
    return metin[:en_fazla].rsplit(" ", 1)[0] + "…"


# ── sayfa tipleri ────────────────────────────────────────────────────────
def kapak_ciz(s: Sayfa, kapak: dict) -> None:
    """KAPAK -- full bleed malzeme etüdü + tek büyük ifade.

    Kompozisyon: görsel tam taşma, üstte marka, altta dev başlık.
    Negatif alan ortada: göz önce boşluğa girer, sonra başlığa iner.
    """
    s.zemin((0.06, 0.06, 0.07))
    yol = sahne_bul(kapak["sahne"], en_az_px=2551)
    if yol:
        s.gorsel(yol, 0, 0, TUVAL_EN, TUVAL_BOY)
    # Alt yarıda okunurluk için koyu geçiş (metin oraya oturuyor).
    s.c.saveState()
    for i in range(80):
        oran = i / 79.0
        s.c.setFillColor(Color(0.04, 0.04, 0.05, alpha=0.90 * (oran ** 1.5)))
        h = TUVAL_BOY * 0.55 / 80.0
        s.c.rect(0, _y(TUVAL_BOY * 0.45 + (i + 1) * h), TUVAL_EN * mm, h * mm + 1,
                 stroke=0, fill=1)
    s.c.restoreState()

    s.yazi(kapak["ust"], "ust_etiket", s.sol_kenar, KM.TASMA_MM + 18,
           renk=(0.93, 0.92, 0.90))
    s.yazi(kapak["dev"], "kapak_dev", s.sol_kenar, TUVAL_BOY * 0.60,
           renk=(0.96, 0.95, 0.93))
    s.yazi(kapak["alt"], "alt_yazi", s.sol_kenar,
           TUVAL_BOY - KM.TASMA_MM - KM.ALT_MM,
           renk=(0.78, 0.76, 0.73))


def manifesto_ciz(s: Sayfa, metin: str) -> None:
    """MANİFESTO -- aşırı negatif alan. Sayfanın işi az söylemek.

    Metin 6 sütuna sıkışır ve sayfanın alt yarısına oturur: üstteki büyük
    boşluk kasıtlıdır, okuma ritmini yavaşlatır.
    """
    s.zemin(KM.KAGIT)
    s.yazi("MANİFESTO", "ust_etiket", s.sol_kenar, KM.TASMA_MM + KM.UST_MM,
           renk=KM.MUREKKEP_SOLUK)
    s.cizgi(s.sol_kenar, KM.TASMA_MM + KM.UST_MM + 6, s.sutun_en(2))
    # 🔴 ILK SURUMDE metin sayfanin ortasinda kucuk bir blok olarak
    # kaliyordu ve "asiri negatif alan" degil "bitmemis sayfa" gibi
    # duruyordu. Bosluk aktif olmali: metin artik daha buyuk puntoda, daha
    # genis sutunda ve sayfanin ust ucte birine CAPA atiyor.
    s.yazi("Bir bitkiyi tanımak,", "sayfa_basli", s.sol_kenar, TUVAL_BOY * 0.20)
    s.yazi("onu bir kremin içine", "sayfa_basli", s.sol_kenar, TUVAL_BOY * 0.20 + 9)
    s.yazi("koymak demek değildir.", "sayfa_basli", s.sol_kenar, TUVAL_BOY * 0.20 + 18)
    s.paragraf(metin.split("\n\n", 1)[1] if "\n\n" in metin else metin,
               "govde", s.sutun_x(0), TUVAL_BOY * 0.46, s.sutun_en(6))
    s.sayfa_numarasi(KM.MUREKKEP_SOLUK)


def bilim_ciz(s: Sayfa, urunler: dict) -> None:
    """FORMÜLASYON -- botanik yaklaşımın anlatısı.

    🔴 ILK SURUM BIR SUNUM DESTESIYDI: "36 / 29 / 26 / 24" diye dev
    rakamlar ve yanlarinda kucuk etiketler. Red team hakli olarak reddetti:
    o rakamlar bizim IC ENVANTERIMIZ ("29 uründe INCI listesi var") ve
    musteriyi ilgilendirmiyor. Dogru ama ilgisiz bilgi, sayfada yerini hak
    etmez.

    Yerine: markanin botanik yaklasimini anlatan, iki sutunlu editoryal
    metin. Tek sayi kaldi -- 36 urun -- ve o da bir baslik olarak, istatistik
    olarak degil.
    """
    s.zemin(KM.KAGIT)
    ust = KM.TASMA_MM + KM.UST_MM
    s.yazi("YAKLAŞIM", "ust_etiket", s.sol_kenar, ust, renk=KM.MUREKKEP_SOLUK)
    s.cizgi(s.sol_kenar, ust + 6, s.sutun_en(2))

    s.yazi("Bitki bir süs değil,\nbir karardır", "sayfa_basli",
           s.sol_kenar, TUVAL_BOY * 0.22)

    sol = (
        "Bir formülasyonda hangi bitkinin bulunacağı, o bitkinin güzel "
        "kokmasıyla değil, uygulanacağı yerle ilgilidir.\n\n"
        "Arnica montana morarmaya eğilimli bölgelerin bakımında yüzyıllardır "
        "kullanılır. Tamanu (Calophyllum inophyllum) basınç ve sürtünmeye "
        "maruz kalan cildin bakımında tercih edilir. Lavanta gece rutinine, "
        "papatya bebeğin ilk banyosuna aittir."
    )
    sag = (
        "L'CARLIÉ formülasyonları bu tercihleri bir araya getirir ve bir "
        "yere uygular: belirli bir bölgeye, belirli bir ana, belirli bir "
        "ihtiyaca.\n\n"
        "Katalogdaki her ürün bu mantıkla okunabilir. Ürün adının yanındaki "
        "kullanım açıklaması nereye, içindekiler listesi neyle sorusunu "
        "yanıtlar.\n\n"
        "İçerik listeleri uluslararası INCI adlandırmasıyla ve Türkçe "
        "karşılıklarıyla birlikte verilir."
    )
    ust_metin = TUVAL_BOY * 0.40
    s.paragraf(sol, "govde", s.sutun_x(0), ust_metin, s.sutun_en(5))
    s.paragraf(sag, "govde_hafif", s.sutun_x(6), ust_metin, s.sutun_en(6),
               renk=KM.MUREKKEP_SOLUK)

    alt = TUVAL_BOY - KM.TASMA_MM - KM.ALT_MM - 18
    s.cizgi(s.sol_kenar, alt, s.metin_en)
    s.yazi("ALTI KULLANIM ALANI · 36 ÜRÜN", "ust_etiket", s.sol_kenar,
           alt + 6, renk=KM.MUREKKEP_SOLUK)
    s.sayfa_numarasi(KM.MUREKKEP_SOLUK)


def bolum_acilisi_ciz(s: Sayfa, bolum: dict) -> None:
    """BÖLÜM AÇILIŞI -- üç düzenden biri.

    Her bölüm ayrı malzeme dünyası: su, bazalt, kil, tekstil, pamuk,
    mineral. Ama düzen de değişir -- altı sayfanın da aynı kompozisyonda
    olması, farklı malzemeye rağmen TEKRAR olurdu.
    """
    duzen = bolum.get("duzen", "tam")
    if duzen == "bant":
        _acilis_bant(s, bolum)
    elif duzen == "sutun":
        _acilis_sutun(s, bolum)
    else:
        _acilis_tam(s, bolum)


def _koyu_gecis(s: Sayfa, baslangic_orani: float, guc: float = 0.88) -> None:
    """Metnin okunacagi bolgeye yumusak koyu gecis."""
    s.c.saveState()
    adim = 70
    yukseklik = TUVAL_BOY * (1.0 - baslangic_orani)
    for i in range(adim):
        oran = i / (adim - 1.0)
        s.c.setFillColor(Color(0.04, 0.04, 0.05, alpha=guc * (oran ** 1.6)))
        h = yukseklik / adim
        s.c.rect(0, _y(TUVAL_BOY * baslangic_orani + (i + 1) * h),
                 TUVAL_EN * mm, h * mm + 1, stroke=0, fill=1)
    s.c.restoreState()


def _acilis_basliklar(s: Sayfa, bolum: dict, ust_orani: float,
                      acik: bool = True, en_fazla_sutun: int = 9) -> None:
    beyaz = (0.96, 0.95, 0.93) if acik else KM.MUREKKEP
    soluk = (0.84, 0.82, 0.79) if acik else KM.MUREKKEP_SOLUK
    s.yazi(bolum["ustyazi"], "ust_etiket", s.sol_kenar,
           TUVAL_BOY * ust_orani, renk=bolum["vurgu"])

    # Uzun bolum adi kendi alanini asarsa SATIRA BOLUNUR, gorsele girmez.
    font, punto, satir, _ = KM.TIP["bolum_dev"]
    sinir = s.sutun_en(en_fazla_sutun) * mm
    ad = bolum["ad"]
    if pdfmetrics.stringWidth(ad, font, punto) > sinir and " " in ad:
        parcalar, aktif = [], ""
        for kelime in ad.split():
            deneme = (aktif + " " + kelime).strip()
            if pdfmetrics.stringWidth(deneme, font, punto) <= sinir:
                aktif = deneme
            else:
                parcalar.append(aktif)
                aktif = kelime
        parcalar.append(aktif)
        ad = "\n".join(p for p in parcalar if p)
    y = s.yazi(ad, "bolum_dev", s.sol_kenar, TUVAL_BOY * ust_orani + 4,
               renk=beyaz)
    s.paragraf(bolum["acilis"], "govde_hafif", s.sol_kenar, y + 5,
               s.sutun_en(min(7, en_fazla_sutun)), renk=soluk)


def _acilis_tam(s: Sayfa, bolum: dict) -> None:
    """TAM TAŞMA -- bölümün ağırlık merkezi."""
    s.zemin((0.08, 0.08, 0.09))
    yol = sahne_bul(bolum["sahne"], en_az_px=2551)
    if yol:
        s.gorsel(yol, 0, 0, TUVAL_EN, TUVAL_BOY)
    _koyu_gecis(s, 0.50)
    _acilis_basliklar(s, bolum, 0.60, acik=True)


def _acilis_bant(s: Sayfa, bolum: dict) -> None:
    """BANT -- görsel üstte, altta geniş negatif alan.

    Boşluk tasarımın aktif parçası: sayfanın alt %45'i kasıtlı olarak boş
    kâğıt. Göz görselden iner, başlıkta durur, boşlukta dinlenir.
    """
    s.zemin(KM.KAGIT)
    bant_boy = TUVAL_BOY * 0.55
    yol = sahne_bul(bolum["sahne"], en_az_px=2551)
    if yol:
        s.gorsel(yol, 0, 0, TUVAL_EN, bant_boy)
    _acilis_basliklar(s, bolum, 0.62, acik=False)
    s.cizgi(s.sol_kenar, TUVAL_BOY * 0.60, s.sutun_en(3),
            renk=bolum["vurgu"], kalinlik=0.8)
    s.sayfa_numarasi(bolum["vurgu"])


def _acilis_sutun(s: Sayfa, bolum: dict) -> None:
    # 🔴 "CILT BARIYERI" basliginin son harfi gorsel sutununa giriyordu.
    # Baslik alani gorsel sutununun SOLUNDA bitmeli; bolum_dev 40 punto ve
    # uzun adlar 8 sutunu asiyor. Cozum: baslik alani 6 sutuna sabitlenir
    # ve gerekirse ad iki satira boluner.
    """SÜTUN -- dar dikey görsel + AŞIRI negatif alan.

    Sayfanın üçte ikisi boş. Bu, katalogdaki en sessiz sayfa tipidir ve
    ritimde nefes aldırmak için var.
    """
    s.zemin(KM.KAGIT)
    sutun_en = s.sutun_en(4)
    x = TUVAL_EN - s.sag_kenar - sutun_en
    ust = KM.TASMA_MM + KM.UST_MM
    boy = TUVAL_BOY - ust - KM.TASMA_MM - KM.ALT_MM
    yol = sahne_bul(bolum["sahne"], en_az_px=max(1400, int(sutun_en / 25.4 * 300)))
    if yol:
        s.gorsel(yol, x, ust, sutun_en, boy)
    _acilis_basliklar(s, bolum, 0.34, acik=False, en_fazla_sutun=6)
    s.cizgi(s.sol_kenar, TUVAL_BOY * 0.32, s.sutun_en(2),
            renk=bolum["vurgu"], kalinlik=0.8)
    s.sayfa_numarasi(bolum["vurgu"])


def urun_tam_ciz(s: Sayfa, urun: dict, bolum: dict) -> None:
    """ÜRÜN -- tam sayfa. Bölümün başını çeken ürün.

    Kompozisyon asimetrik: ürün sağda ve büyük, metin solda dar sütunda.
    Göz yolu: ürün (birincil odak) -> ad -> gövde -> INCI.
    """
    s.zemin(KM.KAGIT)
    kesim = kesim_bul(urun)
    if kesim:
        from PIL import Image
        with Image.open(kesim) as im:
            oran = im.width / im.height
        boy = TUVAL_BOY * 0.56
        en = boy * oran
        if en > s.sutun_en(6):
            en = s.sutun_en(6)
            boy = en / oran
        # Kaynak yetmiyorsa KUCULT, buyutme.
        en_fazla_en, en_fazla_boy = en_fazla_yerlesim(kesim)
        if en > en_fazla_en or boy > en_fazla_boy:
            k = min(en_fazla_en / en, en_fazla_boy / boy)
            en, boy = en * k, boy * k
            s.kisitli.append(urun["slug"])
        gx = TUVAL_EN - s.sag_kenar - en
        gy = TUVAL_BOY * 0.16 + max(0, (TUVAL_BOY * 0.56 - boy) / 2)
        s.urun_zemini(gx, gy, en, boy, bolum["vurgu"])
        s.temas_golgesi(gx, gy + boy, en)
        s.gorsel(kesim, gx, gy, en, boy, maske=True)

    ust = KM.TASMA_MM + KM.UST_MM
    s.yazi(bolum["ad"], "ust_etiket", s.sol_kenar, ust, renk=bolum["vurgu"])
    s.cizgi(s.sol_kenar, ust + 6, s.sutun_en(2), renk=bolum["vurgu"], kalinlik=0.6)

    ad = urun["ad"].split("(")[0].strip()
    y = s.yazi(_ad_sar(ad.upper(), "urun_ad", s.sutun_en(5)), "urun_ad",
               s.sol_kenar, TUVAL_BOY * 0.40)
    alt_ad = urun["ad"][urun["ad"].find("(") + 1:].rstrip(")") if "(" in urun["ad"] else ""
    if alt_ad:
        y = s.yazi(_kisalt(alt_ad, 44), "alt_yazi", s.sol_kenar, y + 1,
                   renk=KM.MUREKKEP_SOLUK)
    y = s.paragraf(_kisalt(urun.get("ozet") or "", 320), "govde",
                   s.sol_kenar, y + 6, s.sutun_en(5))

    if urun.get("kullanim"):
        y += 6
        s.yazi("KULLANIM", "ust_etiket", s.sol_kenar, y, renk=bolum["vurgu"])
        y = s.paragraf(_kisalt(urun["kullanim"], 200), "govde_hafif",
                       s.sol_kenar, y + 6, s.sutun_en(5))

    # 🔴 INCI BLOGU KIRLI BIR GRI LEKEYDI: tek genis sutunda, yapisiz,
    # sayfanin ayaginda. Artik ustunde ince bir cizgi var ve IKI SUTUNA
    # bolunuyor -- satir uzunlugu kisaliyor, blok okunur bir ayak notuna
    # donuyor. Icerik listesi okunmak icin degil DOGRULANMAK icin orada;
    # ama okunamaz olmasi ayri sey.
    icerik = urun.get("inci") or urun.get("icindekiler")
    if icerik:
        etiket = "INCI" if urun.get("inci") else "İÇİNDEKİLER"
        alt = TUVAL_BOY - KM.TASMA_MM - KM.ALT_MM - 30
        s.cizgi(s.sol_kenar, alt - 3, s.metin_en, renk=(0.78, 0.77, 0.75))
        s.yazi(etiket, "ust_etiket", s.sol_kenar, alt, renk=KM.MUREKKEP_SOLUK)
        yarim = _yariya_bol(_kisalt(icerik, 380))
        s.paragraf(yarim[0], "inci", s.sutun_x(0), alt + 6, s.sutun_en(5),
                   renk=KM.MUREKKEP_SOLUK)
        s.paragraf(yarim[1], "inci", s.sutun_x(6), alt + 6, s.sutun_en(6),
                   renk=KM.MUREKKEP_SOLUK)
    s.sayfa_numarasi(bolum["vurgu"])


def urun_ikili_ciz(s: Sayfa, urunler: list, bolum: dict) -> None:
    """ÜRÜN -- iki'li sayfa. Ritim: tam sayfadan sonra yoğunluk artar."""
    s.zemin(KM.KAGIT)
    ust = KM.TASMA_MM + KM.UST_MM
    s.yazi(bolum["ad"], "ust_etiket", s.sol_kenar, ust, renk=bolum["vurgu"])
    s.cizgi(s.sol_kenar, ust + 6, s.metin_en, renk=bolum["vurgu"], kalinlik=0.6)

    tepe = ust + 16
    yukseklik = (TUVAL_BOY - tepe - KM.TASMA_MM - KM.ALT_MM - 6) / 2.0
    for i, urun in enumerate(urunler[:2]):
        y0 = tepe + i * yukseklik
        kesim = kesim_bul(urun)
        if kesim:
            from PIL import Image
            with Image.open(kesim) as im:
                oran = im.width / im.height
            boy = yukseklik * 0.74
            en = boy * oran
            if en > s.sutun_en(4):
                en = s.sutun_en(4)
                boy = en / oran
            en_fazla_en, en_fazla_boy = en_fazla_yerlesim(kesim)
            if en > en_fazla_en or boy > en_fazla_boy:
                k = min(en_fazla_en / en, en_fazla_boy / boy)
                en, boy = en * k, boy * k
                s.kisitli.append(urun["slug"])
            gx = s.sutun_x(0) + (s.sutun_en(4) - en) / 2
            gy = y0 + max(0, (yukseklik * 0.74 - boy) / 2)
            s.urun_zemini(gx, gy, en, boy, bolum["vurgu"])
            s.temas_golgesi(gx, gy + boy, en)
            s.gorsel(kesim, gx, gy, en, boy, maske=True)

        mx = s.sutun_x(5)
        men = s.sutun_en(7)
        ad = urun["ad"].split("(")[0].strip()
        y = s.yazi(_ad_sar(ad.upper(), "urun_ad", men), "urun_ad", mx, y0 + 2)
        y = s.paragraf(_kisalt(urun.get("ozet") or "", 210), "govde",
                       mx, y + 4, men)
        icerik = urun.get("inci") or urun.get("icindekiler")
        if icerik:
            etiket = "INCI" if urun.get("inci") else "İÇİNDEKİLER"
            s.yazi(etiket, "ust_etiket", mx, y + 4, renk=KM.MUREKKEP_SOLUK)
            s.paragraf(_kisalt(icerik, 190), "inci", mx, y + 9, men,
                       renk=KM.MUREKKEP_SOLUK)
        if i == 0:
            s.cizgi(s.sol_kenar, y0 + yukseklik - 6, s.metin_en,
                    renk=(0.80, 0.79, 0.77))
    s.sayfa_numarasi(bolum["vurgu"])


def kapanis_ciz(s: Sayfa) -> None:
    s.zemin((0.07, 0.07, 0.08))
    s.yazi("L'CARLIÉ", "ust_etiket", s.sol_kenar, TUVAL_BOY * 0.42,
           renk=(0.79, 0.66, 0.38))
    s.yazi("BİTKİNİN\nBİLDİĞİ YER", "bolum_dev", s.sol_kenar, TUVAL_BOY * 0.46,
           renk=(0.96, 0.95, 0.93))
    s.paragraf("lcarlie.com.tr\ninfo@lcarlie.com.tr", "govde_hafif",
               s.sol_kenar, TUVAL_BOY * 0.70, s.sutun_en(6),
               renk=(0.80, 0.78, 0.75))


# ── kurulum ──────────────────────────────────────────────────────────────
def uret(cikti: pathlib.Path) -> dict:
    fontlari_yukle()
    urunler = katalog_oku()
    cikti.parent.mkdir(parents=True, exist_ok=True)

    c = rl_canvas.Canvas(str(cikti), pagesize=(TUVAL_EN * mm, TUVAL_BOY * mm))
    c.setTitle("L'CARLIÉ — Bitkinin Bildiği Yer")
    c.setAuthor("L'CARLIÉ")
    c.setSubject("Dermokozmetik ürün kataloğu")

    rapor = {"sayfalar": [], "gorseller": [], "eksik": []}
    no = 0

    def yeni() -> Sayfa:
        nonlocal no
        no += 1
        return Sayfa(c, no, tek=(no % 2 == 1))

    # 1 kapak
    s = yeni(); kapak_ciz(s, KM.KAPAK); rapor["sayfalar"].append("kapak")
    rapor["gorseller"] += s.gorsel_raporu
    rapor.setdefault("kaynaktan_kisitli", []).extend(
        s.kisitli)
    c.showPage()

    # 2 manifesto
    s = yeni(); manifesto_ciz(s, KM.MANIFESTO); rapor["sayfalar"].append("manifesto")
    rapor["gorseller"] += s.gorsel_raporu
    rapor.setdefault("kaynaktan_kisitli", []).extend(
        s.kisitli)
    c.showPage()

    # 3 formulasyon
    s = yeni(); bilim_ciz(s, urunler); rapor["sayfalar"].append("formulasyon")
    rapor["gorseller"] += s.gorsel_raporu
    rapor.setdefault("kaynaktan_kisitli", []).extend(
        s.kisitli)
    c.showPage()

    for bolum in KM.BOLUMLER:
        s = yeni(); bolum_acilisi_ciz(s, bolum)
        rapor["sayfalar"].append("acilis:" + bolum["kod"])
        rapor["gorseller"] += s.gorsel_raporu
        rapor.setdefault("kaynaktan_kisitli", []).extend(
            s.kisitli)
        c.showPage()

        kayitlar = []
        for slug in bolum["urunler"]:
            u = urunler.get(slug)
            if u is None:
                rapor["eksik"].append(slug)
                continue
            kayitlar.append(u)
        if not kayitlar:
            continue

        s = yeni(); urun_tam_ciz(s, kayitlar[0], bolum)
        rapor["sayfalar"].append("urun:" + kayitlar[0]["slug"])
        rapor["gorseller"] += s.gorsel_raporu
        rapor.setdefault("kaynaktan_kisitli", []).extend(
            s.kisitli)
        c.showPage()

        kalan = kayitlar[1:]
        for i in range(0, len(kalan), 2):
            s = yeni(); urun_ikili_ciz(s, kalan[i:i + 2], bolum)
            rapor["sayfalar"].append(
                "ikili:" + ",".join(u["slug"] for u in kalan[i:i + 2]))
            rapor["gorseller"] += s.gorsel_raporu
            rapor.setdefault("kaynaktan_kisitli", []).extend(
                s.kisitli)
            c.showPage()

    s = yeni(); kapanis_ciz(s); rapor["sayfalar"].append("kapanis")
    rapor["gorseller"] += s.gorsel_raporu
    rapor.setdefault("kaynaktan_kisitli", []).extend(
        s.kisitli)
    c.showPage()

    c.save()
    rapor["sayfa_sayisi"] = no
    rapor["dusuk_dpi"] = [g for g in rapor["gorseller"]
                          if g["efektif_dpi"] < EN_AZ_DPI]
    rapor["olcu_mm"] = [KM.SAYFA_EN_MM, KM.SAYFA_BOY_MM]
    rapor["tasma_mm"] = KM.TASMA_MM
    rapor["bayt"] = cikti.stat().st_size
    return rapor


def main() -> int:
    a = argparse.ArgumentParser(description="L'CARLIE katalog PDF")
    a.add_argument("--cikti", type=pathlib.Path,
                   default=CIKTI / "lcarlie-katalog.pdf")
    n = a.parse_args()
    t0 = time.time()
    try:
        r = uret(n.cikti)
    except TasarimHatasi as hata:
        print("HATA:", hata)
        return 1

    print("%s · %d sayfa · %.1f MB · %.1f sn"
          % (n.cikti.name, r["sayfa_sayisi"], r["bayt"] / 1048576.0,
             time.time() - t0))
    print("  sayfa olcusu %.0f x %.0f mm + %.0f mm tasma"
          % (r["olcu_mm"][0], r["olcu_mm"][1], r["tasma_mm"]))
    print("  yerlestirilen gorsel: %d" % len(r["gorseller"]))
    if r["eksik"]:
        print("  🔴 KATALOGDA BULUNAMAYAN URUN: %s" % ", ".join(r["eksik"]))
    kisitli = sorted(set(r.get("kaynaktan_kisitli") or []))
    if kisitli:
        print("  ⚠ %d urun KAYNAK COZUNURLUGU yetmedigi icin kucultuldu "
              "(buyutulmedi):" % len(kisitli))
        print("     " + ", ".join(kisitli[:10])
              + (" …" if len(kisitli) > 10 else ""))
    if r["dusuk_dpi"]:
        print("  🔴 %d GORSEL %d DPI ALTINDA (baski icin yetersiz):"
              % (len(r["dusuk_dpi"]), EN_AZ_DPI))
        for g in r["dusuk_dpi"][:6]:
            print("     s%-3d %-34s %5.0f DPI  (%dx%d px -> %.0fx%.0f mm)"
                  % (g["sayfa"], g["dosya"][:34], g["efektif_dpi"],
                     g["piksel"][0], g["piksel"][1],
                     g["yerlesim_mm"][0], g["yerlesim_mm"][1]))
    else:
        print("  tum gorseller %d DPI ustunde" % EN_AZ_DPI)
    (n.cikti.with_suffix(".rapor.json")).write_text(
        json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
