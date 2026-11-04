#!/usr/bin/env python3
"""Ham urun fotograflarindan urunun sinir kutusunu OLCEREK kirpar.

NEDEN
Ham cekimler 3072x4608 studyo kareleri; sise karenin ortasinda kucuk kaliyor.
Banner'da sise buyuk gorunmeli. Koordinati elle yazmak yerine her fotografta
urunun gercek sinir kutusu olculur: kose pikselinden fon rengi alinir, fondan
belirgin sapan pikseller urun sayilir.

CIKTI
  kaynak/urun/<ad>.png  -- sise sikica kirpilmis, alti/ustu esit bosluklu
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HAM = Path("/opt/lcarlie/urun-ham")
HEDEF = Path("/opt/lcarlie/idefix-vitrin/kaynak/urun")
ENK = 192          # analiz icin kucuk kopya genisligi
ESIK = 45          # satir kenarindan sapma esigi (3 kanal toplami)
PAY = 0.05         # kirpmaya eklenen bosluk orani
KENAR = 3          # her satirda fon referansi icin kullanilan kenar piksel sayisi
YOGUNLUK = 0.18    # sutun/satir en yogun degerin bu kadarinin altindaysa urun sayilmaz


def kucuk_rgb(dosya: Path) -> tuple[bytes, int, int]:
    """Kucuk RGB kopya. 🔴 Olcu ffprobe'dan DEGIL buradan okunur: ffprobe ham
    kare olcusunu verir, ffmpeg ise EXIF dondurmesini uygular -- ikisi
    cakistiginda crop 'invalid size' ile patliyor (lipvora'da olculdu)."""
    ham = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(dosya), "-vf", f"scale={ENK}:-1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    kh = len(ham) // (3 * ENK)
    return ham, ENK, kh


def sinir_kutusu(ham: bytes, w: int, h: int) -> tuple[int, int, int, int] | None:
    """Urunun sinir kutusu.

    Iki tuzak olculdu ve ikisi de burada cozuluyor:
    1) Studyo fonunda DIKEY GRADYAN var -> tek fon rengi tum kareyi urun sayar.
       Cozum: fon referansi her SATIRIN kendi kenar pikselleri.
    2) Karelerin cogunda masa/zemin cizgisi tum genisligi kat ediyor -> sinir
       kutusu hep 0.00-1.00 cikiyor. Cozum: satir/sutun YOGUNLUGU. Cizgi sutun
       basina 1-2 piksel birakir, sise onlarca; esigin altinda kalan sutun ve
       satirlar urun sayilmaz.
    """
    def px(x, y):
        i = (y * w + x) * 3
        return ham[i], ham[i+1], ham[i+2]

    maske = bytearray(w * h)
    for y in range(h):
        kenarlar = [px(x, y) for x in range(KENAR)] +                    [px(w - 1 - x, y) for x in range(KENAR)]
        fon = tuple(sum(k[i] for k in kenarlar) // len(kenarlar) for i in range(3))
        for x in range(w):
            r, g, b = px(x, y)
            if abs(r-fon[0]) + abs(g-fon[1]) + abs(b-fon[2]) > ESIK:
                maske[y * w + x] = 1

    sutun = [sum(maske[y * w + x] for y in range(h)) for x in range(w)]
    satir = [sum(maske[y * w + x] for x in range(w)) for y in range(h)]
    if not any(sutun):
        return None

    sx = max(sutun) * YOGUNLUK
    sy = max(satir) * YOGUNLUK
    xs = [x for x, d in enumerate(sutun) if d >= sx]
    ys = [y for y, d in enumerate(satir) if d >= sy]
    if not xs or not ys:
        return None
    return xs[0], ys[0], xs[-1], ys[-1]


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    fonlar: dict[str, str] = {}
    for dosya in sorted(HAM.glob("*.jpg")):
        ham, kw, kh = kucuk_rgb(dosya)
        kutu = sinir_kutusu(ham, kw, kh)
        if not kutu:
            print(f"{dosya.stem:<30} urun bulunamadi, atlandi")
            continue
        x0, y0, x1, y1 = kutu
        # 🔴 Kirpma ORAN olarak verilir; boylece EXIF dondurmesi sorun cikarmaz
        fx0 = max(0.0, x0 / kw - PAY)
        fy0 = max(0.0, y0 / kh - PAY)
        fx1 = min(1.0, (x1 + 1) / kw + PAY)
        fy1 = min(1.0, (y1 + 1) / kh + PAY)
        kirp = (f"crop=iw*{fx1-fx0:.4f}:ih*{fy1-fy0:.4f}"
                f":iw*{fx0:.4f}:ih*{fy0:.4f}")
        cikti = HEDEF / f"{dosya.stem}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(dosya),
             "-vf", f"{kirp},scale=-1:900", str(cikti)],
            check=True)
        # Fotografin kendi fon rengi: banner panelini bu renge boyayinca
        # fotografin kenari gorunmez, kutu gibi yuzmez.
        i = (int(kh * 0.06) * kw + int(kw * 0.5)) * 3
        fonlar[dosya.stem] = "#%02X%02X%02X" % (ham[i], ham[i+1], ham[i+2])
        oran = (fx1 - fx0) * (fy1 - fy0)
        print(f"{dosya.stem:<30} kutu %{oran*100:4.0f} alan  "
              f"x {fx0:.2f}-{fx1:.2f}  y {fy0:.2f}-{fy1:.2f}")
    (HEDEF / "fon.json").write_text(
        json.dumps(fonlar, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nkirpilan: {HEDEF}  ({len(fonlar)} fon rengi fon.json'a yazildi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
