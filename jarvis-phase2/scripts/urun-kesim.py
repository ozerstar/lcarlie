"""ÜRÜN KESİMİ — gerçek ambalajı koruyarak şeffaf PNG üretir.

🔴 NEDEN BU ADIM HER ŞEYİ DEĞİŞTİRİYOR
Mevcut hat ürün fotoğrafını görsel modeline verip "kesimi, montajı ve
tasarımı sen yap" diyor. Yani ambalajı ve üstündeki yazıyı MODEL YENİDEN
ÇİZİYOR. Ölçülen sonuç: etiket "HYORAVIE" diye çıktı ve otomatik denetim
bunu yakalayamadı (denendi, çalışmıyor — gorsel-uret.py'deki uzun not).

Kesim yapıldığında o hata sınıfı tamamen ortadan kalkar: ambalaj
yeniden çizilmez, gerçek pikselleri taşınır.

🔴 KAYNAK BİR REKLAM, ÜRÜN ÇEKİMİ DEĞİL.
`hydravie.png` üstünde zaten logo, Türkçe başlık ve site adresi var.
Arka plan kaldırılınca bu yazıların parçaları da kalıyor ("ONFO").
Bu yüzden maskeden yalnız EN BÜYÜK BAĞLI PARÇA alınır — şişe.
Yazı parçaları küçük ve ayrık olduğu için elenir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = "isnet-general-use"


def _en_buyuk_parca(alfa: np.ndarray) -> np.ndarray:
    """Maskedeki en büyük bağlı bileşen. Yazı artıkları böyle elenir.

    Kendi etiketlemesi: scipy bağımlılığı eklemek için tek sebep bu
    olurdu ve taşıma maliyeti buna değmez.
    """
    dolu = alfa > 24
    h, w = dolu.shape
    etiket = np.zeros((h, w), dtype=np.int32)
    su = 0
    en_iyi, en_iyi_boy = 0, 0
    komsu = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for by in range(h):
        for bx in range(w):
            if not dolu[by, bx] or etiket[by, bx]:
                continue
            su += 1
            yigin = [(by, bx)]
            etiket[by, bx] = su
            boy = 0
            while yigin:
                y, x = yigin.pop()
                boy += 1
                for dy, dx in komsu:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and dolu[ny, nx] and not etiket[ny, nx]:
                        etiket[ny, nx] = su
                        yigin.append((ny, nx))
            if boy > en_iyi_boy:
                en_iyi, en_iyi_boy = su, boy
    return (etiket == en_iyi)


def kes(kaynak: Path, hedef: Path | None = None) -> Path:
    from rembg import new_session, remove

    im = Image.open(kaynak)
    ses = new_session(MODEL)
    out = remove(im, session=ses, alpha_matting=True,
                 alpha_matting_foreground_threshold=250,
                 alpha_matting_background_threshold=15,
                 alpha_matting_erode_size=8)

    a = np.asarray(out).copy()
    # 🔴 Hız için önce 1/4 ölçekte bileşen bul; tam çözünürlükte piksel
    # piksel dolaşmak bu boyutta dakikalar sürüyor.
    kucuk = Image.fromarray(a[:, :, 3]).resize(
        (a.shape[1] // 4, a.shape[0] // 4), Image.NEAREST)
    maske_k = _en_buyuk_parca(np.asarray(kucuk))
    maske = np.asarray(Image.fromarray((maske_k * 255).astype(np.uint8)).resize(
        (a.shape[1], a.shape[0]), Image.BILINEAR)) > 100

    a[:, :, 3] = np.where(maske, a[:, :, 3], 0)
    temiz = Image.fromarray(a, "RGBA")
    kutu = temiz.getbbox()
    if kutu:
        temiz = temiz.crop(kutu)

    hedef = hedef or kaynak.with_name(kaynak.stem + ".kesim.png")
    temiz.save(hedef)
    return hedef


if __name__ == "__main__":
    k = Path(sys.argv[1])
    h = kes(k)
    im = Image.open(h)
    print(f"kesim: {h.name}  {im.size}  mod={im.mode}")
