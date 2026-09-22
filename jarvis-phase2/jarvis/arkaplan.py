"""ARKA PLAN — model çağrısı YOK, para YOK, PC'nin açık olması gerekmez.

🔴 NEDEN BU DOSYA VAR
Sahip yerel üretim (ComfyUI) ve tarayıcı otomasyonu seçeneklerini sordu.
Ama montaj katmanı devreye girince modelden istenen iş küçüldü: ürün
gerçek fotoğraftan yapıştırılıyor, yazı gerçek fontla diziliyor. Geriye
yalnız ARKA PLAN kalıyor ve bu tarz minimal kozmetik reklamında arka
plan zaten sade olmak zorunda — gradyan, stüdyo süpürgesi, yumuşak ışık
havuzu, ince doku.

Bunlar için üretici model gerekmiyor. Kodla üretiliyor:
  · maliyet 0 TL (görsel başına 7 TL yerine)
  · GPU gerekmiyor, PC açık olmak zorunda değil
  · kullanım şartları sorunu yok
  · her seferinde AYNI çıkıyor — reklam serisi tutarlı olur

⚠️ Bu, üretici modeli gereksiz kılmaz. Karmaşık sahne (mermer tezgâh,
havlu, yaprak, su damlası) isteniyorsa model gerekir. Sade zemin için
gerekmiyor ve şu ana kadar üretilen dört görselin dördü de sade zemindi.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

# Marka paleti: soğuk, nötr, açık. Sıcak tonlar BİLEREK yok — ölçüldü,
# sıcak sahne ışığı beyaz şişeyi krem rengine kaydırıyor.
PALET = {
    "buz": ((242, 246, 250), (214, 226, 236)),
    "sis": ((238, 238, 240), (206, 210, 216)),
    "kum": ((244, 241, 236), (222, 216, 208)),
    "mint": ((238, 246, 244), (208, 228, 224)),
    "gece": ((232, 236, 242), (186, 198, 212)),
}


def _dikey_gradyan(en: int, boy: int, ust, alt) -> Image.Image:
    im = Image.new("RGB", (1, boy))
    ç = im.load()
    for y in range(boy):
        t = y / max(1, boy - 1)
        ç[0, y] = tuple(int(ust[i] + (alt[i] - ust[i]) * t) for i in range(3))
    return im.resize((en, boy), Image.BILINEAR)


def _isik_havuzu(im: Image.Image, güç: float = 0.22) -> Image.Image:
    """Üst-orta noktadan yumuşak bir aydınlık. Düz gradyanı 'stüdyo' yapar."""
    en, boy = im.size
    maske = Image.new("L", (en, boy), 0)
    ç = ImageDraw.Draw(maske)
    mx, my = int(en * 0.58), int(boy * 0.30)
    r = int(max(en, boy) * 0.55)
    ç.ellipse((mx - r, my - r, mx + r, my + r), fill=255)
    maske = maske.filter(ImageFilter.GaussianBlur(int(r * 0.45)))
    beyaz = Image.new("RGB", (en, boy), (255, 255, 255))
    return Image.blend(im, Image.composite(beyaz, im, maske), güç)


def _zemin_cizgisi(im: Image.Image, y_oran: float = 0.72) -> Image.Image:
    """Ufuk: ürünün havada durmasını engelleyen yumuşak yüzey ayrımı."""
    en, boy = im.size
    y = int(boy * y_oran)
    kat = im.copy()
    ç = ImageDraw.Draw(kat)
    ç.rectangle((0, y, en, boy), fill=(0, 0, 0))
    maske = Image.new("L", (en, boy), 0)
    ImageDraw.Draw(maske).rectangle((0, y, en, boy), fill=38)
    maske = maske.filter(ImageFilter.GaussianBlur(int(boy * 0.035)))
    return Image.composite(Image.blend(im, kat, 0.16), im, maske)


def _grain(im: Image.Image, miktar: int = 5) -> Image.Image:
    """İnce kumlanma: düz gradyanın 'dijital' görünmesini engeller."""
    en, boy = im.size
    g = Image.effect_noise((en, boy), miktar).convert("L")
    return Image.composite(im, im, g).point(lambda v: v) if False else Image.blend(
        im, Image.merge("RGB", (g, g, g)), 0.045)


def uret(oran: str = "4:5", stil: str = "buz", tohum: int = 0) -> Image.Image:
    """Tek arka plan. Aynı tohum AYNI görseli verir -- seri tutarlılığı."""
    boyut = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920)}
    if oran not in boyut:
        raise ValueError("oran 1:1 / 4:5 / 9:16 olmalı")
    if stil not in PALET:
        raise ValueError(f"stil şunlardan biri: {', '.join(PALET)}")
    rnd = random.Random(tohum)
    en, boy = boyut[oran]
    ust, alt = PALET[stil]
    # Tohuma göre hafif ton kaydırması: seriler birbirinin kopyası olmasın.
    kay = rnd.randint(-5, 5)
    ust = tuple(max(0, min(255, c + kay)) for c in ust)
    alt = tuple(max(0, min(255, c - kay)) for c in alt)

    im = _dikey_gradyan(en, boy, ust, alt)
    im = _isik_havuzu(im, 0.18 + rnd.random() * 0.10)
    im = _zemin_cizgisi(im, 0.68 + rnd.random() * 0.08)
    im = _grain(im)
    return im


if __name__ == "__main__":
    import sys
    from pathlib import Path
    hedef = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    hedef.mkdir(parents=True, exist_ok=True)
    for i, stil in enumerate(PALET):
        uret("4:5", stil, tohum=i).save(hedef / f"arkaplan-{stil}.jpg", quality=92)
        print("yazildi:", f"arkaplan-{stil}.jpg")
