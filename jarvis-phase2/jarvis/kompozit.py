"""MONTAJ — reklam karesini BİZ kuruyoruz, model değil.

🔴 NEDEN VAR
Mevcut hat görsel modeline *"You do the cut-out, the montage and the full
design"* diyordu. Yani ambalajı, üstündeki yazıyı ve Türkçe başlığı MODEL
çiziyordu. Ölçülen sonuçlar:
  · etiket "HYORAVIE" diye çıktı (otomatik denetim yakalayamadı — denendi)
  · sıcak sahne ışığı beyaz şişeyi krem rengine kaydırdı
  · Türkçe harfler modele bırakıldığı için her koşuda kumar

Burada o işlerin hiçbiri modele bırakılmıyor:
  ÜRÜN  gerçek fotoğrafın şeffaf kesimi YAPIŞTIRILIR (çizilmez)
  YAZI  gerçek fontla DİZİLİR (çizilmez)
  LOGO  gerçek dosyadan KONUR (çizilmez)
Modele kalan tek iş ARKA PLAN — içinde ne ürün ne yazı var, dolayısıyla
bozulacak bir şey de yok.

🔴 METROPOLIS'TE `·` GLİFİ YOK (ölçüldü). Ortada nokta kullanılmaz;
kullanılırsa Pillow sessizce boş bırakır ve bunu ancak baskıda görürsünüz.
Ayırıcı olarak ince boşluklu tire kullanılıyor.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
FONT_DIZIN = KOK / "varliklar" / "fontlar"

ORANLAR = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920)}

# 🔴 Ürün karenin en az bu kadarını kaplamalı. Mevcut inceleme kapısı
# (kreatif-inceleme.py) bunu ölçüyor ve altında kalanı düşürüyor; montaj
# da aynı eşiği tutmalı, yoksa kendi kapımızdan geçemeyiz.
ASGARI_URUN_ORANI = 0.40

AYIRAC = " — "          # `·` KULLANILMAZ: Metropolis'te yok.


def _font(ad: str, boy: int) -> ImageFont.FreeTypeFont:
    yol = FONT_DIZIN / ad
    if not yol.is_file():
        raise FileNotFoundError(f"font yok: {yol}")
    return ImageFont.truetype(str(yol), boy)


def _sigdir(cizim: ImageDraw.ImageDraw, metin: str, font_ad: str,
            azami_en: int, bas_boy: int, asgari_boy: int = 18
            ) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Metni verilen genişliğe sığdırır: önce sarar, gerekirse küçültür.

    🔴 Kırpmaz. Panelde metinlerin birbirini ezmesinin sebebi tam olarak
    kırpmaktı; burada aynı hatayı yapmıyoruz — sığmıyorsa punto iner.
    """
    boy = bas_boy
    while boy >= asgari_boy:
        font = _font(font_ad, boy)
        satirlar: list[str] = []
        su = ""
        for kelime in metin.split():
            aday = (su + " " + kelime).strip()
            if cizim.textlength(aday, font=font) <= azami_en or not su:
                su = aday
            else:
                satirlar.append(su)
                su = kelime
        if su:
            satirlar.append(su)
        if all(cizim.textlength(s, font=font) <= azami_en for s in satirlar):
            return font, satirlar
        boy -= 2
    return _font(font_ad, asgari_boy), [metin]


def _perde(kare: Image.Image, kutu: tuple[int, int, int, int]) -> Image.Image:
    """Metin alanının arkasına GEREKTİĞİ KADAR aydınlık perde koyar.

    🔴 Opaklık ÖLÇÜLÜR. Metin alanının parlaklığı ve hareketliliği
    okunurluğu belirler: açık ve sakin bir zeminde perde gereksiz bir
    kutu gibi durur, koyu ya da desenli zeminde yetersiz kalır.
    """
    import numpy as np
    from PIL import ImageFilter

    x0, y0, x1, y1 = kutu
    parca = np.asarray(kare.convert("L").crop(kutu)).astype(float)
    parlaklik = parca.mean()                       # 0 koyu, 255 açık
    hareket = float(np.abs(np.diff(parca, axis=1)).mean())

    # Koyu ya da hareketli zemin -> daha güçlü perde. Açık ve sakin -> az.
    guc = 0.0
    if parlaklik < 205:
        guc += (205 - parlaklik) / 205 * 0.55
    if hareket > 4:
        guc += min((hareket - 4) / 20, 1.0) * 0.25
    guc = max(0.0, min(guc, 0.62))
    if guc < 0.06:
        return kare                                # gerek yok

    en, boy = kare.size
    maske = Image.new("L", (en, boy), 0)
    ImageDraw.Draw(maske).rectangle(
        (x0 - int(en * 0.05), y0 - int(boy * 0.03), x1, y1 + int(boy * 0.03)),
        fill=int(255 * guc))
    maske = maske.filter(ImageFilter.GaussianBlur(int(en * 0.06)))
    beyaz = Image.new("RGB", (en, boy), (250, 251, 253))
    return Image.composite(beyaz, kare, maske)


def kur(*, arka_plan: Image.Image, urun_kesim: Path, logo: Path,
        ust_yazi: str, alt_yazi: str, oran: str = "4:5",
        metin_rengi: tuple[int, int, int] = (26, 26, 30)) -> Image.Image:
    """Bitmiş reklam karesi. Ürün ve yazı ASLA yeniden çizilmez."""
    if oran not in ORANLAR:
        raise ValueError(f"oran {', '.join(ORANLAR)} olmalı")
    W, H = ORANLAR[oran]

    kare = arka_plan.convert("RGB").resize((W, H), Image.LANCZOS)

    # --- ürün ---
    urun = Image.open(urun_kesim).convert("RGBA")
    # Ürün yüksekliği karenin %62'si; genişlik oranı korunur. Bu değer
    # ASGARI_URUN_ORANI kapısını geçecek şekilde seçildi, aşağıda ölçülüyor.
    # 🔴 %62 DENENDI VE KAPIDAN GECMEDI. Ince-uzun bir sise karenin
    # ALANINA gore yalniz %14.8'ini kapliyordu; inceleme kapisi %40
    # istiyor. Yukseklik buyutuldu ve oran YENIDEN OLCULUYOR --
    # "buyuttum, herhalde gecer" demek bu projede birkac kez yanildi.
    # Fotoğraf zeminde ürün sahneyi örtmemeli; %86 denendi, arka planı
    # tamamen yutuyordu. %70 hem ürünü baskın tutuyor hem sahneyi bırakıyor.
    hedef_boy = int(H * 0.70)
    olcek = hedef_boy / urun.height
    urun = urun.resize((max(1, int(urun.width * olcek)), hedef_boy), Image.LANCZOS)

    ux = int(W * 0.72) - urun.width // 2
    uy = int(H * 0.42) - urun.height // 2
    ux = max(int(W * 0.04), min(ux, W - urun.width - int(W * 0.04)))
    uy = max(int(H * 0.10), min(uy, H - urun.height - int(H * 0.06)))

    # Yumuşak gölge: ürünün "yapıştırılmış" durmasını engeller.
    golge = Image.new("RGBA", kare.size, (0, 0, 0, 0))
    from PIL import ImageFilter
    g = Image.new("RGBA", urun.size, (0, 0, 0, 0))
    g.paste((0, 0, 0, 70), (0, 0), urun)
    golge.paste(g, (ux + int(W * 0.012), uy + int(H * 0.012)), g)
    golge = golge.filter(ImageFilter.GaussianBlur(int(W * 0.018)))
    kare = Image.alpha_composite(kare.convert("RGBA"), golge)
    kare.paste(urun, (ux, uy), urun)
    kare = kare.convert("RGB")

    # --- ürün oranı ÖLÇÜLÜR, varsayılmaz ---
    urun_orani = (urun.width * urun.height) / (W * H)

    cizim = ImageDraw.Draw(kare)

    # --- logo ---
    lg = Image.open(logo).convert("RGBA")
    lg_en = int(W * 0.26)
    lg = lg.resize((lg_en, max(1, int(lg.height * lg_en / lg.width))), Image.LANCZOS)
    kare.paste(lg, (int(W * 0.07), int(H * 0.06)), lg)

    # --- yazı ---
    kenar = int(W * 0.07)
    # Ürün sağda %72'de duruyor; metin sütunu ona DEĞMEYECEK kadar dar.
    # Eskiden %52'ydi ve şişenin üstüne biniyordu (ekranda görüldü).
    metin_en = int(W * 0.44)
    ust_font, ust_satir = _sigdir(cizim, (ust_yazi or "").strip(),
                                  "Metropolis-Bold.otf", metin_en, int(W * 0.072))
    alt_font, alt_satir = _sigdir(cizim, (alt_yazi or "").strip(),
                                  "Metropolis-Regular.otf", metin_en, int(W * 0.030))

    ust_sat_boy = int(ust_font.size * 1.14)
    alt_sat_boy = int(alt_font.size * 1.45)
    toplam = len(ust_satir) * ust_sat_boy + int(W * 0.022) + len(alt_satir) * alt_sat_boy
    y = H - int(H * 0.08) - toplam

    # Perde metin YAZILMADAN önce konur, yoksa yazının üstünü örter.
    kare = _perde(kare, (kenar, y, kenar + metin_en, y + toplam))
    cizim = ImageDraw.Draw(kare)

    for s in ust_satir:
        cizim.text((kenar, y), s, font=ust_font, fill=metin_rengi)
        y += ust_sat_boy
    y += int(W * 0.022)
    for s in alt_satir:
        cizim.text((kenar, y), s, font=alt_font, fill=metin_rengi)
        y += alt_sat_boy

    kare.info["urun_orani"] = round(urun_orani, 3)
    kare.info["urun_orani_gecti"] = urun_orani >= ASGARI_URUN_ORANI
    return kare
