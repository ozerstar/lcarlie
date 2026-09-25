#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gönderi görseli üretir: ürün + sahne + dizgi, ÜÇÜ AYRI KATMAN.

🔴 KURALIN TAM HALİ (14.09.2026, sahip düzeltmesi): kural "ürün karede
olmasın" DEĞİL. Kural şu: **ambalaj AI'ya yeniden çizdirilmez.** Ürünlü
kompozisyon serbesttir -- ürün katmanının GERÇEK FOTOĞRAFIN PİKSELLERİ
olması şartıyla. Görsel modeli ambalajı kopyalamaz, yeniden çizer: etiket,
harf ve oranlar her seferinde değişir. Bozulmuş bir etiket, sahte ürün
görseli demektir.

ÜÇ KATMAN, ASLA TEK PROMPT'A YIKILMAZ
  1. ÜRÜN     katalog fotoğrafının pikselleri (rembg ile maskelenir)
  2. SAHNE    ürünsüz AI sahnesi (PC-2/ComfyUI) ya da düz/gradyan zemin
  3. DİZGİ    diskteki gerçek Metropolis fontlarıyla, Pillow ile

METİN GÖRSEL MODELİNE YAZDIRILMAZ. Model marka fontunu yükleyemez;
"Metropolis karakterinde" demek hiçbir şey yapmaz.

🔴 DOĞRULAMA İDDİA DEĞİL ÖLÇÜMDÜR. Çıktının yanında bir rapor üretilir:
ürün bölgesindeki piksellerin kaynak kesimle BİREBİR aynı olma oranı,
SSIM, ve ürünün en sol/sağ/üst/alt koordinatı. Ürün yeniden çizilmiş
olsaydı birebir oran 1.0'ın çok altına düşerdi. "Ürünü korudum" cümlesi
kanıt değildir; bu rapor kanıttır.

KESİM ÖNBELLEĞE ALINIR. Aynı fotoğrafın maskesi her seferinde yeniden
hesaplanmaz; maske belirlenimseldir ve 0,5-0,7 sn tutar.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

KOK = Path(__file__).resolve().parents[1]
GORSEL = Path("/opt/lcarlie/katalog-gorsel")
KESIM = Path("/opt/lcarlie/katalog-kesim")
FONT_DIZIN = KOK / "webconsole" / "static" / "fonts"
CIKTI = Path("/opt/lcarlie/gorsel-kuyruk/cikti")

# Instagram biçimleri. Reels/story 9:16, akış 4:5, kare 1:1.
BICIMLER = {
    "REELS": (1080, 1920),
    "KARE": (1080, 1080),
    "AKIS": (1080, 1350),
}

# Ürünün kare yüksekliğine oranı. Çok büyük olursa dizgiye yer kalmaz,
# çok küçük olursa telefonda etiket okunmaz.
URUN_YUKSEKLIK_ORANI = {"REELS": 0.46, "KARE": 0.58, "AKIS": 0.56}

FONTLAR = {
    "bold": "Metropolis-Bold.otf",
    "semibold": "Metropolis-SemiBold.otf",
    "medium": "Metropolis-Medium.otf",
    "regular": "Metropolis-Regular.otf",
    "light": "Metropolis-Light.otf",
}


class GorselHatasi(ValueError):
    """İstek kabul edilmedi. Sessizce yutulmaz."""


# --- katman 1: URUN -------------------------------------------------------
def urun_kesimi(kaynak: Path) -> Image.Image:
    """Ürünü fondan ayırır. Ürün pikseli DEĞİŞMEZ, yalnız alfa hesaplanır.

    Ölçüldü (25.09.2026): u2net modeliyle 0,5-0,7 sn/görsel. Zor vaka olan
    INTIMBLANC (beyaz gövde + açık fon + şeffaf kapak) dahil üç üründe de
    kenarlar temiz çıktı. 14.09.2026 tarihli "otomatik kesim yapılamıyor,
    Photoshop pen tool gerekir" notu bu ölçümle GEÇERSİZ.
    """
    KESIM.mkdir(parents=True, exist_ok=True)
    hedef = KESIM / (kaynak.stem + ".png")
    if hedef.exists():
        return Image.open(hedef).convert("RGBA")
    try:
        from rembg import new_session, remove
    except ImportError:
        raise GorselHatasi("rembg kurulu degil -- kesim yapilamaz") from None
    kaynak_im = Image.open(kaynak).convert("RGBA")
    kesik = maskeyi_sertlestir(remove(kaynak_im, session=new_session("u2net")))
    # Pillow bicimi UZANTIDAN cikariyor; ".tmp" uzantisi "bilinmeyen bicim"
    # hatasi veriyor. Bicim acikca soylenir, yarim dosya yine okunmaz.
    gecici = hedef.with_suffix(".png.tmp")
    kesik.save(gecici, "PNG")
    gecici.replace(hedef)
    return kesik


# Bu iki esik arasi GERCEK kenar gecisidir ve yumusak birakilir; disi
# govde (tam opak) ve fon (tam saydam) olarak sabitlenir.
KENAR_ALT, KENAR_UST = 8, 250


def maskeyi_sertlestir(im: Image.Image) -> Image.Image:
    """Gövdeyi tam opak, fonu tam saydam yapar; yalnız kenar yumuşak kalır.

    🔴 BU DUZELTMENIN SEBEBI OLCULDU. rembg/u2net maskesinde ürünün
    GÖVDESİ bile tam opak değil: piksellerin %17,4'ü alfa 255, %51'i
    250-254 arası. Yapıştırma sırasında o %51 arka planla HARMANLANIYOR --
    yani ürünün iç pikselleri değişiyor. Ölçüldü: alfa==255'te fark
    %0,000, alfa>=250'de fark %73,2.

    Gözle görünmüyor ve SSIM 0,9999 diyor; ama "ambalaj değişmez" kuralı
    göz kararıyla değil piksel kararıyla tutulur. Bozulmuş bir etiket,
    sahte ürün görseli demektir -- harmanlama da bir bozulmadır.
    """
    r, g, b, a = im.split()
    a = a.point(lambda p: 0 if p <= KENAR_ALT else (255 if p >= KENAR_UST else p))
    return Image.merge("RGBA", (r, g, b, a))


def ana_gorsel(slug: str) -> Path:
    """Ürünün ANA fotoğrafı. Alfabetik ilk dosya DEĞİL.

    🔴 İlk sürümde `sorted(glob(...))[0]` yazıyordu, yani dosya adının
    karmasına göre rastgele bir kare seçiliyordu. FEMISIA'da bu, ürünü
    ELDE TUTAN bir kareyi seçti; kesim eli yarım aldı ve gönderi
    görselinde şişenin arkasında kopuk bir parmak kaldı. Wix zaten hangi
    karenin ana görsel olduğunu söylüyor (`media.mainMedia`) ve indirici
    bunu `dizin.json`a `ana` alanı olarak yazıyor -- kullanmamak, elimizde
    duran bilgiyi görmezden gelmekti.
    """
    dizin = GORSEL / "dizin.json"
    if dizin.exists():
        try:
            kayitlar = json.loads(dizin.read_text(encoding="utf-8"))
        except ValueError:
            kayitlar = []
        uygun = [k for k in kayitlar if k.get("slug") == slug]
        uygun.sort(key=lambda k: (not k.get("ana"), k.get("sira", 99)))
        for k in uygun:
            yol = GORSEL / k["dosya"]
            if yol.is_file():
                return yol
    adaylar = sorted(GORSEL.glob(slug + "-*.webp"))
    if not adaylar:
        raise GorselHatasi("urun gorseli yok: %s" % slug)
    return adaylar[0]


def kirp(im: Image.Image) -> Image.Image:
    """Saydam kenar boşluğunu atar; ölçek hesabı gövdeye göre yapılsın."""
    kutu = im.getbbox()
    return im.crop(kutu) if kutu else im


# --- katman 2: SAHNE ------------------------------------------------------
def sahne_kur(bicim: str, sahne_yolu: Path | None, renk: str) -> Image.Image:
    """AI sahnesi ya da düz/gradyan zemin.

    🔴 SAHNE ÜRÜNSÜZ OLMALI. Ölçüldü (24.09.2026): negatif istemde
    `product, bottle, jar` yazmasına rağmen SDXL mermer bir şişe üretti.
    "Ürün üretme" dediğine güvenme, çıktıya bak. Bu yüzden sahne dosyası
    dışarıdan verilir ve insan gözüyle onaylanmış olması beklenir; bu
    işlev sahnede ürün olup olmadığını KONTROL EDEMEZ ve etmediğini
    söyler.
    """
    g, y = BICIMLER[bicim]
    if sahne_yolu:
        if not sahne_yolu.is_file():
            raise GorselHatasi("sahne dosyasi yok: %s" % sahne_yolu)
        s = Image.open(sahne_yolu).convert("RGB")
        # Kareye doldur: oranı koru, taşanı kırp.
        oran = max(g / s.width, y / s.height)
        s = s.resize((max(1, round(s.width * oran)), max(1, round(s.height * oran))),
                     Image.LANCZOS)
        sol, ust = (s.width - g) // 2, (s.height - y) // 2
        return s.crop((sol, ust, sol + g, ust + y))

    # Sahne verilmediyse düz zemin: dürüst ve ucuz. Uydurma bir arka plan
    # uretmektense boş bırakmak, dizginin okunurluğunu da artırır.
    taban = Image.new("RGB", (g, y), renk)
    ust_katman = Image.new("RGB", (g, y), "#ffffff")
    maske = Image.linear_gradient("L").resize((g, y))
    return Image.composite(taban, ust_katman, maske.point(lambda p: 255 - p // 3))


# --- katman 3: DIZGI ------------------------------------------------------
# 🔴 MARKA FONTUNDA OLMAYAN KARAKTERLER. Ölçüldü (25.09.2026, fontTools
# ile beş ağırlığın cmap tablosu okundu): Metropolis'te şunlar YOK --
#
#     ·   ortadaki nokta      (marka metinlerinde ayraç olarak kullanılıyor)
#     •   madde imi
#     ₺   TÜRK LİRASI İŞARETİ
#     ™ © °
#
# Pillow eksik glif yerine .notdef kutusu çizer ve HATA VERMEZ. Yani fiyat
# yazan bir gönderi "1.950 ₺" yerine "1.950 □" basar ve bu ancak yayına
# çıktıktan sonra fark edilir. `·` tuzağı bu projede daha önce de
# yaşanmıştı (INTIMBLANC sayfa çalışması); bu gece ilk denemede yine
# kutuyla karşılaştım.
#
# Çözüm iki katmanlı: bilinen karakterler GÜVENLİ KARŞILIĞIYLA değişir,
# bilinmeyen eksik karakter varsa motor ÜRETMEYİ REDDEDER. Kutu basmak,
# yanlış görseli yayınlamaktır.
GLIF_KARSILIK = {
    "·": "–", "•": "–", "₺": "TL", "™": "", "©": "(c)", "°": "",
    "\u00a0": " ", "\u2009": " ", "\u202f": " ",
}

_glif_onbellek: dict = {}


def _font_glifleri(yol: Path) -> set:
    """Fontun gerçekten çizebildiği kod noktaları."""
    if yol in _glif_onbellek:
        return _glif_onbellek[yol]
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        # fontTools yoksa koruma yapilamaz; SESSIZCE gecmek yerine bunu
        # soyleyip bos kume donuyoruz -- metin_guvenli() o zaman hicbir
        # karakteri eksik saymaz ama neden koruyamadigini yazar.
        print("UYARI: fontTools yok -- glif korumasi YAPILAMADI")
        _glif_onbellek[yol] = set()
        return _glif_onbellek[yol]
    t = TTFont(str(yol))
    kod = set()
    for tablo in t["cmap"].tables:
        kod |= set(tablo.cmap)
    _glif_onbellek[yol] = kod
    return kod


def metin_guvenli(metin: str, font_adi: str = "bold") -> str:
    """Eksik glifleri güvenli karşılığıyla değiştirir, kalanı reddeder."""
    if not metin:
        return metin
    yol = FONT_DIZIN / FONTLAR[font_adi]
    kod = _font_glifleri(yol)
    if not kod:
        return metin
    cikti, eksik = [], []
    for ch in metin:
        if ord(ch) in kod or ch in ("\n", "\t"):
            cikti.append(ch)
        elif ch in GLIF_KARSILIK:
            cikti.append(GLIF_KARSILIK[ch])
        else:
            eksik.append(ch)
    if eksik:
        raise GorselHatasi(
            "fontta olmayan karakter: %s -- kutu basmamak icin uretim "
            "durduruldu (GLIF_KARSILIK tablosuna ekleyin)"
            % " ".join(sorted(set(eksik))))
    return "".join(cikti)


def font(ad: str, punto: int) -> ImageFont.FreeTypeFont:
    yol = FONT_DIZIN / FONTLAR[ad]
    if not yol.is_file():
        raise GorselHatasi("font yok: %s" % yol)
    return ImageFont.truetype(str(yol), punto)


def _sar(cizici, metin: str, yazi, en_fazla_genislik: int) -> list:
    kelimeler, satirlar, aktif = metin.split(), [], ""
    for k in kelimeler:
        deneme = (aktif + " " + k).strip()
        if cizici.textlength(deneme, font=yazi) <= en_fazla_genislik:
            aktif = deneme
        else:
            if aktif:
                satirlar.append(aktif)
            aktif = k
    if aktif:
        satirlar.append(aktif)
    return satirlar


def dizgi_yerlesim(tuval: Image.Image, baslik: str, alt: str, bicim: str) -> dict:
    """Metnin nereye düşeceğini HESAPLAR, hiçbir piksele dokunmaz.

    Ayrı bir işlev çünkü perdenin nereye çizileceğini ürünü yapıştırmadan
    ÖNCE bilmemiz gerekiyor (bkz. `uret` içindeki katman sırası).
    """
    g, y = tuval.size
    cizici = ImageDraw.Draw(tuval)
    kenar = round(g * 0.075)
    genislik = g - 2 * kenar

    b_punto = round(g * (0.062 if bicim == "REELS" else 0.070))
    a_punto = round(g * 0.030)
    b_font, a_font = font("bold", b_punto), font("light", a_punto)

    # Eksik glifler BURADA temizlenir; asagisi artik cizilebilir metin.
    baslik = metin_guvenli(baslik, "bold")
    alt = metin_guvenli(alt, "light")
    satirlar = _sar(cizici, baslik, b_font, genislik) if baslik else []
    alt_satirlar = _sar(cizici, alt, a_font, genislik) if alt else []
    b_yukseklik = round(b_punto * 1.16)
    a_yukseklik = round(a_punto * 1.45)
    toplam = len(satirlar) * b_yukseklik + (
        round(a_punto * 0.9) + len(alt_satirlar) * a_yukseklik if alt_satirlar else 0)

    # Metin ALTTA: ürün üstte durur, telefonda başparmak altını kapatmaz.
    tepe = y - kenar - toplam if toplam else y
    return {"kenar": kenar, "tepe": tepe, "satirlar": satirlar,
            "alt_satirlar": alt_satirlar, "b_font": b_font, "a_font": a_font,
            "b_yukseklik": b_yukseklik, "a_yukseklik": a_yukseklik,
            "a_punto": a_punto, "var": bool(toplam),
            "perde_tepe": max(0, tepe - round(y * 0.06))}


def _isik(renk) -> float:
    """WCAG bagil parlaklik."""
    def k(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * k(renk[0]) + 0.7152 * k(renk[1]) + 0.0722 * k(renk[2])


def kontrast(a, b) -> float:
    ia, ib = _isik(a), _isik(b)
    return (max(ia, ib) + 0.05) / (min(ia, ib) + 0.05)


# Metin renkleri: acik zeminde koyu, koyu zeminde acik.
ACIK_METIN = (242, 239, 233)
KOYU_METIN = (18, 18, 20)
ACIK_ALT = (201, 169, 97)
KOYU_ALT = (120, 92, 30)
EN_AZ_KONTRAST = 4.5          # WCAG AA (buyuk metin icin fazlasiyla yeterli)


def okunurluk_ayarla(tuval: Image.Image, yerlesim: dict) -> tuple:
    """Perdeyi ve metin rengini ÖLÇEREK seçer.

    🔴 BU ISLEVIN SEBEBI GOZLE GORULDU, SAYIYLA DEGIL. Ilk surumde metin
    her zaman acik renkti ve perde sabit sertlikteydi; acik bej zeminde
    beyaz yazi neredeyse okunmuyordu. Urun pikseli dogru oldugu icin
    birebir=1.0 diyordu ve kusur sayilarda GORUNMUYORDU.

    🔴 IKINCI DENEME DE YETMEDI. Gradyan perde denendi, olculen kontrast
    1,51-1,85 cikti (esik 4,5). Sebep: gradyan yazinin UST kenarinda hala
    saydamdi -- perde metnin altinda degil, metne DOGRU koyulasıyordu.

    Dogrusu iki parcali: perde `perde_tepe`den `tepe`ye ramp yapar, yazinin
    ALTINDA duz kalir. Ve once PERDESIZ KOYU YAZI denenir: acik bir sahnede
    koyu yazi hem okunur hem daha temiz durur; perde ancak gerekince gelir.
    """
    import numpy as _np
    g, y = tuval.size
    if not yerlesim["var"]:
        return tuval, ACIK_METIN, ACIK_ALT, None

    def olc(aday):
        band = aday.crop((0, yerlesim["tepe"], g, y))
        return tuple(int(v) for v in _np.array(band).reshape(-1, 3).mean(axis=0))

    # Aday sirasi: once mudahalesiz, sonra artan perde.
    adaylar = [(tuval, KOYU_METIN, KOYU_ALT), (tuval, ACIK_METIN, ACIK_ALT)]
    for sertlik in (150, 190, 225, 250):
        perdeli = _perde_ciz(tuval, yerlesim, sertlik)
        adaylar.append((perdeli, ACIK_METIN, ACIK_ALT))

    en_iyi = None
    for aday, metin, alt in adaylar:
        ort = olc(aday)
        oran = min(kontrast(metin, ort), kontrast(alt, ort))
        if en_iyi is None or oran > en_iyi[3]:
            en_iyi = (aday, metin, alt, oran)
        if oran >= EN_AZ_KONTRAST:
            return aday, metin, alt, round(oran, 2)

    # Esik tutmadiysa EN YUKSEK kontrastli secilir ve sayi rapora yazilir.
    # Sessizce gecmek, okunmayan bir gonderi yayinlamak olurdu.
    print("UYARI: kontrast esigi (%.1f) tutmadi, en iyisi %.2f"
          % (EN_AZ_KONTRAST, en_iyi[3]))
    return en_iyi[0], en_iyi[1], en_iyi[2], round(en_iyi[3], 2)


def _perde_ciz(tuval: Image.Image, yerlesim: dict, sertlik: int) -> Image.Image:
    """Perde: boslukta ramp, YAZININ ALTINDA duz.

    Gradyanin yaziya kadar surmesi, yazinin ust satirini saydam zeminde
    birakiyordu. Ramp yalnizca `perde_tepe` ile `tepe` arasinda; `tepe`den
    asagisi sabit sertlikte.
    """
    if not yerlesim["var"]:
        return tuval
    g, y = tuval.size
    tepe_perde, tepe_yazi = yerlesim["perde_tepe"], yerlesim["tepe"]
    perde = Image.new("RGBA", (1, y), (0, 0, 0, 0))
    gecis = max(1, tepe_yazi - tepe_perde)
    for i in range(tepe_perde, y):
        if i < tepe_yazi:
            oran = (i - tepe_perde) / gecis
            a = int(sertlik * (oran ** 1.4))
        else:
            a = sertlik
        perde.putpixel((0, i), (10, 10, 12, a))
    return Image.alpha_composite(
        tuval.convert("RGBA"), perde.resize((g, y))).convert("RGB")


def dizgi_perde(tuval: Image.Image, yerlesim: dict) -> Image.Image:
    """Metnin arkasındaki yumuşak koyu katman.

    🔴 BU KATMAN ÜRÜNDEN ÖNCE ÇİZİLİR. İlk sürümde ürünün üstüne
    çiziliyordu ve bulanıklık ürün alanına taşıyordu: doğrulama
    "birebir oran 0.371" dedi, yani piksellerin %63'ü değişmişti.
    Gözle fark edilmiyordu ve SSIM 0.9999 gösteriyordu -- tam da bu
    yüzden ölçüm iki ayrı sayı istiyor. Ambalajı bozan bir bulanıklık,
    AI'nın yeniden çizmesinden farksızdır.
    """
    if not yerlesim["var"]:
        return tuval
    g, y = tuval.size
    tepe = yerlesim["perde_tepe"]
    # 🔴 DUZ DIKDORTGEN DEGIL, GECISLI. Ilk surumde bulanik bir dikdortgen
    # ciziliyordu ve ciktida DUZ GRI BLOK gibi duruyordu: bulaniklik
    # kenari yumusatiyor ama basladigi yeri gizlemiyor. Gozle bakinca
    # goruldu -- sayilar (birebir 1.0) o kusuru gostermez, cunku urun
    # pikseli zaten dogruydu. Olcum her seyi soylemez; cikti da izlenir.
    perde = Image.new("RGBA", (1, y), (0, 0, 0, 0))
    for i in range(tepe, y):
        # Ustte tamamen saydam, altta koyu: gecis egrisi karesel, yani
        # baslangic fark edilmez.
        oran = (i - tepe) / max(1, y - tepe)
        perde.putpixel((0, i), (10, 10, 12, int(165 * (oran ** 1.6))))
    return Image.alpha_composite(
        tuval.convert("RGBA"), perde.resize((g, y))).convert("RGB")


def dizgi_yaz(tuval: Image.Image, yerlesim: dict,
              metin_renk=ACIK_METIN, alt_renk=ACIK_ALT) -> None:
    """Metni GERÇEK FONTLARLA dizer. Model marka fontunu yükleyemez."""
    if not yerlesim["var"]:
        return
    cizici = ImageDraw.Draw(tuval)
    imlec = yerlesim["tepe"]
    for s in yerlesim["satirlar"]:
        cizici.text((yerlesim["kenar"], imlec), s,
                    font=yerlesim["b_font"], fill=metin_renk)
        imlec += yerlesim["b_yukseklik"]
    if yerlesim["alt_satirlar"]:
        imlec += round(yerlesim["a_punto"] * 0.9)
        for s in yerlesim["alt_satirlar"]:
            cizici.text((yerlesim["kenar"], imlec), s,
                        font=yerlesim["a_font"], fill=alt_renk)
            imlec += yerlesim["a_yukseklik"]


# --- dogrulama -------------------------------------------------------------
def _ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Gri tonda global SSIM. Kütüphane yok, formül açık."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    kov = ((a - ma) * (b - mb)).mean()
    return float(((2 * ma * mb + c1) * (2 * kov + c2)) /
                 ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2)))


def dogrula(cikti: Image.Image, urun: Image.Image, konum: tuple) -> dict:
    """Ürün pikselleri korundu mu -- ÖLÇÜLÜR, iddia edilmez.

    Ürün katmanı tuvale opak alfa ile yapıştırıldığı için, çıktıdaki ürün
    bölgesi yeniden ölçeklenmiş kesimle BİREBİR aynı olmalıdır. Model
    ambalajı yeniden çizseydi bu oran 1.0'ın çok altına düşerdi.
    """
    x, yy = konum
    kesit = cikti.crop((x, yy, x + urun.width, yy + urun.height)).convert("RGB")
    kaynak = urun.convert("RGB")
    alfa = np.array(urun.split()[-1])
    # 🔴 ESIK 255, 250 DEGIL. Ilk surumde >=250 yazmistim ve olcum
    # yaniltici cikti: 250-254 arasi pikseller yapistirmada HARMANLANIR,
    # yani zaten degismis olmalari BEKLENIR. Onlari "korunmasi gereken"
    # kumeye koymak, korunmayan bir seyi korunmus sanmak kadar kotudur --
    # ters yonde ama ayni hata.
    opak = alfa == 255
    yumusak = int(((alfa > 0) & (alfa < 255)).sum())
    if not opak.any():
        return {"opak_piksel": 0, "birebir_oran": None, "ssim": None,
                "yumusak_kenar_piksel": yumusak,
                "not": "urunun tam opak pikseli yok -- olcum yapilamadi"}

    a = np.array(kesit)[opak]
    b = np.array(kaynak)[opak]
    birebir = float((a == b).all(axis=1).mean())
    gri_a = a.astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    gri_b = b.astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    return {
        "opak_piksel": int(opak.sum()),
        # Kenar yumusatma kasitlidir: sert kenar kompozitte makasla
        # kesilmis gorunur. Bu pikseller harmanlanir ve olcume girmez.
        "yumusak_kenar_piksel": yumusak,
        "birebir_oran": round(birebir, 6),
        "ssim": round(_ssim(gri_a, gri_b), 6),
        "urun_kutusu": {"sol": x, "ust": yy,
                        "sag": x + urun.width, "alt": yy + urun.height},
        "urun_boyut": [urun.width, urun.height],
    }


# --- ana akis --------------------------------------------------------------
def uret(slug: str, bicim: str = "AKIS", baslik: str = "", alt: str = "",
         sahne: Path | None = None, zemin: str = "#e9e6e0",
         golge: bool = True, cikti_dizin: Path = CIKTI) -> dict:
    if bicim not in BICIMLER:
        raise GorselHatasi("gecersiz bicim: %s" % bicim)
    kaynak = ana_gorsel(slug)

    t0 = time.time()
    urun = kirp(urun_kesimi(kaynak))
    tuval = sahne_kur(bicim, sahne, zemin).convert("RGB")
    g, y = tuval.size

    # 🔴 YAZI ONCE OLCULUR, URUN SONRA OLCEKLENIR.
    #
    # Ilk surumde urun sabit oranla buyutuluyor, yazi da alta yaziliyordu.
    # KARE bicimde iki satirlik baslikla ikisi CAKISTI: urun alt kenari
    # 756, yazi perdesi 637. Piksel denetimi yakaladi (birebir 0,983) ve
    # gorsel reddedildi -- ama dogru davranis reddetmek degil, cakismayi
    # hic uretmemek. Yazi uzunlugu iceriktir ve degismez; degisebilen sey
    # urunun boyudur.
    yerlesim = dizgi_yerlesim(tuval, baslik, alt, bicim)
    ust_bosluk = round(y * (0.16 if bicim == "REELS" else 0.10))
    # Yazi perdesinin uzerinde nefes payi birakilir.
    alt_sinir = (yerlesim["perde_tepe"] - round(y * 0.03)) if yerlesim["var"] else y
    kullanilabilir = max(round(y * 0.25), alt_sinir - ust_bosluk)

    hedef_y = min(round(y * URUN_YUKSEKLIK_ORANI[bicim]), kullanilabilir)
    oran = hedef_y / urun.height
    urun = urun.resize((max(1, round(urun.width * oran)), hedef_y), Image.LANCZOS)
    if urun.width > g * 0.86:                       # geniş ürün taşmasın
        oran2 = (g * 0.86) / urun.width
        urun = urun.resize((round(urun.width * oran2), round(urun.height * oran2)),
                           Image.LANCZOS)

    x = (g - urun.width) // 2
    # Kalan alanda dikey ortala: urun kucultuldugunde tepeye yapismasin.
    yy = ust_bosluk + max(0, (kullanilabilir - urun.height) // 2)

    # 🔴 KATMAN SIRASI ÜRÜN PİKSELİNİ KORUMAK İÇİN BÖYLE.
    #   sahne -> gölge -> yazı perdesi -> ÜRÜN -> yazı
    # Ürün SONDAN BİR ÖNCE yapıştırılır; ondan sonra yalnız harfler
    # çizilir ve harfler ürüne değmez (ürün üstte, yazı altta). İlk
    # sürümde perde üründen SONRA geliyordu ve bulanıklığı ürünü
    # kirletiyordu -- doğrulama yakaladı (birebir oran 0.371).
    if golge:
        # Gölge MASKEDEN türetilir, AI'dan değil: ürünün kendi silueti.
        s = Image.new("RGBA", tuval.size, (0, 0, 0, 0))
        siluet = Image.new("RGBA", urun.size, (0, 0, 0, 90))
        s.paste(siluet, (x, yy + round(urun.height * 0.02)), urun)
        tuval = Image.alpha_composite(
            tuval.convert("RGBA"), s.filter(ImageFilter.GaussianBlur(26))).convert("RGB")

    tuval, metin_renk, alt_renk, kontrast_orani = okunurluk_ayarla(tuval, yerlesim)

    # Ürün, perde çizildikten SONRA yapıştırılır.
    tuval.paste(urun, (x, yy), urun)

    # Yazı ürünün altına düşmeli; düşmüyorsa ürün fazla büyük demektir ve
    # bu SESSİZCE geçilmez.
    # Bu artik olmamali (urun yaziya gore olceklendi); olursa hesapta
    # bir kusur var demektir ve sessizce gecilmez.
    if yerlesim["var"] and yerlesim["perde_tepe"] < yy + urun.height:
        print("UYARI: yazi hala urunle cakisiyor -- yerlesim hesabinda kusur "
              "(urun alt %d, yazi perdesi %d)"
              % (yy + urun.height, yerlesim["perde_tepe"]))
    dizgi_yaz(tuval, yerlesim, metin_renk, alt_renk)

    rapor = dogrula(tuval, urun, (x, yy))
    cikti_dizin.mkdir(parents=True, exist_ok=True)
    damga = time.strftime("%Y%m%dT%H%M%S")
    ad = "%s-%s-%s" % (slug, bicim.lower(), damga)
    tuval.save(cikti_dizin / (ad + ".jpg"), quality=92, subsampling=1)

    rapor.update({
        "urun": slug, "bicim": bicim, "boyut": [g, y],
        # Okunurluk OLCULDU: metin ile arkasindaki bandin kontrast orani.
        "kontrast_orani": kontrast_orani,
        "kontrast_esigi": EN_AZ_KONTRAST,
        "kaynak_fotograf": kaynak.name,
        "sahne": sahne.name if sahne else "duz-zemin",
        "dosya": ad + ".jpg",
        "sure_sn": round(time.time() - t0, 2),
        "katmanlar": ["urun=gercek fotograf pikselleri",
                      "sahne=" + ("AI/dosya" if sahne else "duz zemin"),
                      "dizgi=Metropolis .otf (Pillow)"],
    })
    (cikti_dizin / (ad + ".json")).write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    return rapor


def main() -> int:
    a = argparse.ArgumentParser(description="Gonderi gorseli uret (3 katman)")
    a.add_argument("slug")
    a.add_argument("--bicim", default="AKIS", choices=sorted(BICIMLER))
    a.add_argument("--baslik", default="")
    a.add_argument("--alt", default="")
    a.add_argument("--sahne", type=Path, default=None)
    a.add_argument("--zemin", default="#e9e6e0")
    a.add_argument("--golgesiz", action="store_true")
    n = a.parse_args()
    try:
        r = uret(n.slug, n.bicim, n.baslik, n.alt, n.sahne, n.zemin,
                 golge=not n.golgesiz)
    except GorselHatasi as hata:
        print("HATA:", hata)
        return 1
    print("%s · %s · %.2f sn" % (r["dosya"], r["boyut"], r["sure_sn"]))
    print("  urun pikseli birebir: %s · SSIM %s · opak piksel %s"
          % (r["birebir_oran"], r["ssim"], r["opak_piksel"]))
    print("  kutu: %s" % r["urun_kutusu"])
    if r["birebir_oran"] is not None and r["birebir_oran"] < 0.999:
        print("🔴 URUN PIKSELLERI DEGISMIS -- bu gorsel kullanilamaz")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
