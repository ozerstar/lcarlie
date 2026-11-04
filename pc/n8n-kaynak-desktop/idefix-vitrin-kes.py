#!/usr/bin/env python3
"""Urun fotograflarini fondan ayirip SAYDAM PNG uretir.

NEDEN
Banner panellerinde fotografi oldugu gibi kullanmak ise yaramiyor: her
fotografin kendi studyo fonu var ve kagidin uzerinde dikdortgen kutu gibi
duruyor. Panel rengini olcup boyamak da, ayni fotografin bulanik kopyasini
arkaya koymak da dikis izini kapatmadi (ikisi de denendi). Tek dogru yol
fonu gercekten kaldirmak.

🔴 AMBALAJ: burada ambalaj yeniden CIZILMIYOR, yalnizca gercek fotografin
fonu siliniyor. Ambalajin kendisi dokunulmadan kaliyor.

YONTEM
Fon referansi her SATIRIN kendi kenar pikselleri (studyo fonunda dikey gradyan
var, tek fon rengi ise yaramaz). Fondan sapma yumusak bir esikten gecirilerek
alfaya cevriliyor; boylece kenarlar tirtikli olmuyor.

PIL yok, PNG elle yaziliyor (zlib + struct).

CIKTI
  kaynak/urun-kesik/<ad>.png   RGBA
  kaynak/urun-kesik/ortu.json  her urun icin alfa kapsama orani
"""
from __future__ import annotations

import json
import struct
import subprocess
import zlib
from pathlib import Path

HAM = Path("/opt/lcarlie/urun-ham")
HEDEF = Path("/opt/lcarlie/idefix-vitrin/kaynak/urun-kesik")
GEN = 760          # calisma genisligi (banner'larda en fazla ~330 px gorunuyor)
KENAR = 4          # satir basina fon referansi icin kenar piksel sayisi
T0, T1 = 26, 86    # yumusak esik: T0 alti saydam, T1 ustu tam opak
PAY = 0.03


def rgb(dosya: Path, genislik: int) -> tuple[bytearray, int, int]:
    ham = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(dosya), "-vf", f"scale={genislik}:-1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    h = len(ham) // (3 * genislik)
    return bytearray(ham), genislik, h


def alfa_uret(veri: bytearray, w: int, h: int) -> bytearray:
    """Her piksel icin 0-255 alfa."""
    alfa = bytearray(w * h)
    for y in range(h):
        taban = y * w * 3
        kenarlar = []
        for x in range(KENAR):
            i = taban + x * 3
            j = taban + (w - 1 - x) * 3
            kenarlar.append((veri[i], veri[i+1], veri[i+2]))
            kenarlar.append((veri[j], veri[j+1], veri[j+2]))
        fr = sum(k[0] for k in kenarlar) // len(kenarlar)
        fg = sum(k[1] for k in kenarlar) // len(kenarlar)
        fb = sum(k[2] for k in kenarlar) // len(kenarlar)
        for x in range(w):
            i = taban + x * 3
            fark = abs(veri[i]-fr) + abs(veri[i+1]-fg) + abs(veri[i+2]-fb)
            if fark <= T0:
                a = 0
            elif fark >= T1:
                a = 255
            else:
                a = int((fark - T0) * 255 / (T1 - T0))
            alfa[y * w + x] = a
    return alfa


def govde_kutusu(alfa: bytearray, w: int, h: int) -> tuple[int, int, int, int] | None:
    """Alfasi belirgin olan asil govdenin sinir kutusu. Yogunluk suzgeci
    masa/zemin cizgisini eler (cizgi sutun basina birkac piksel birakir)."""
    sutun = [0] * w
    satir = [0] * h
    for y in range(h):
        s = 0
        for x in range(w):
            if alfa[y * w + x] > 140:
                sutun[x] += 1
                s += 1
        satir[y] = s
    if not any(sutun):
        return None
    sx, sy = max(sutun) * 0.18, max(satir) * 0.18
    xs = [x for x, d in enumerate(sutun) if d >= sx]
    ys = [y for y, d in enumerate(satir) if d >= sy]
    if not xs or not ys:
        return None
    return xs[0], ys[0], xs[-1], ys[-1]


def png_yaz(yol: Path, w: int, h: int, rgba: bytearray) -> None:
    satirlar = bytearray()
    for y in range(h):
        satirlar.append(0)                       # filtre: None
        satirlar += rgba[y * w * 4:(y + 1) * w * 4]

    def parca(tur: bytes, govde: bytes) -> bytes:
        return (struct.pack(">I", len(govde)) + tur + govde
                + struct.pack(">I", zlib.crc32(tur + govde) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)   # 8 bit, RGBA
    yol.write_bytes(b"\x89PNG\r\n\x1a\n"
                    + parca(b"IHDR", ihdr)
                    + parca(b"IDAT", zlib.compress(bytes(satirlar), 9))
                    + parca(b"IEND", b""))


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    ortu: dict[str, float] = {}
    for dosya in sorted(HAM.glob("*.jpg")):
        veri, w, h = rgb(dosya, GEN)
        alfa = alfa_uret(veri, w, h)
        kutu = govde_kutusu(alfa, w, h)
        if not kutu:
            print(f"{dosya.stem:<30} govde bulunamadi, atlandi")
            continue
        x0, y0, x1, y1 = kutu
        px = int((x1 - x0) * PAY) + 1
        py = int((y1 - y0) * PAY) + 1
        x0 = max(0, x0 - px); y0 = max(0, y0 - py)
        x1 = min(w - 1, x1 + px); y1 = min(h - 1, y1 + py)
        kw, kh = x1 - x0 + 1, y1 - y0 + 1

        rgba = bytearray(kw * kh * 4)
        dolu = 0
        for y in range(kh):
            for x in range(kw):
                si = ((y + y0) * w + (x + x0))
                hi = (y * kw + x) * 4
                rgba[hi] = veri[si * 3]
                rgba[hi+1] = veri[si * 3 + 1]
                rgba[hi+2] = veri[si * 3 + 2]
                a = alfa[si]
                rgba[hi+3] = a
                if a > 140:
                    dolu += 1
        png_yaz(HEDEF / f"{dosya.stem}.png", kw, kh, rgba)
        oran = dolu / (kw * kh)
        ortu[dosya.stem] = round(oran, 3)
        isaret = "  ZAYIF" if oran < 0.22 else ""
        print(f"{dosya.stem:<30} {kw}x{kh}  dolu %{oran*100:4.0f}{isaret}")

    (HEDEF / "ortu.json").write_text(
        json.dumps(ortu, ensure_ascii=False, indent=1), encoding="utf-8")
    zayif = [a for a, o in ortu.items() if o < 0.22]
    print(f"\nkesilen: {len(ortu)}  ·  zayif kesim: {len(zayif)} {zayif}")
    print(f"dizin: {HEDEF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
