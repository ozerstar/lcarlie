#!/usr/bin/env python3
"""WhatsApp siparis teyidi sablonu icin 1200x628 yatay urun basligi uretir.

WhatsApp sablon basligi yatay (yakl. 1.91:1) gosterilir; urun fotograflari
dikey (3000x3750). Dogrudan verilirse ust ve alt kirpilir, urun kesilir.
Bu yuzden urun BEYAZ tuvale TAMAMEN sigdirilir, yani asla kirpilmaz.

Kullanim: wa-teyit-gorsel.py "<urun adi parcasi>" [cikti-adi]
Cikti   : /opt/lcarlie/urun-gorsel/teyit/<ad>.jpg
Adres   : https://n8n.lcarlie.shop/urun-gorsel/teyit/<ad>.jpg
"""
from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GEN, YUK = 1200, 628
TUVAL = (255, 255, 255)
MUREKKEP = (26, 26, 26)
ESKIZ = (150, 150, 150)
FONT_DIZIN = Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar")
CIKTI_DIZIN = Path("/opt/lcarlie/urun-gorsel/teyit")


def slug(metin: str) -> str:
    ayri = unicodedata.normalize("NFKD", metin.replace("ı", "i").replace("İ", "I"))
    sade = "".join(k for k in ayri if not unicodedata.combining(k))
    return re.sub(r"[^a-z0-9]+", "-", sade.lower()).strip("-")


def gorsel_adresi(parca: str) -> tuple[str, str]:
    sql = (
        "select (ham->>'name') || '|' || "
        "(ham->'media'->'mainMedia'->'image'->>'url') "
        "from raw.wix_urun where ham->>'name' ilike '%%%s%%' "
        "and ham->'media'->'mainMedia'->'image'->>'url' is not null limit 2"
    ) % parca.replace("'", "")
    cikti = subprocess.run(
        ["docker", "exec", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=True).stdout.strip()
    satirlar = [s for s in cikti.splitlines() if s.strip()]
    if not satirlar:
        raise SystemExit("urun bulunamadi: " + parca)
    if len(satirlar) > 1:
        raise SystemExit("birden fazla urun esledi:\n" + "\n".join(satirlar))
    ad, adres = satirlar[0].split("|", 1)
    # Wix donusumu: 3000 piksel gereksiz, 1400 yeter.
    adres = re.sub(r"/v1/fit/w_\d+,h_\d+", "/v1/fit/w_1400,h_1750", adres)
    return ad, adres


def font(ad: str, boy: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIZIN / ad), boy)


def arali(cizim: ImageDraw.ImageDraw, konum: tuple[int, int], metin: str,
          yazi: ImageFont.FreeTypeFont, renk, aralik: int) -> None:
    x, y = konum
    for karakter in metin:
        cizim.text((x, y), karakter, font=yazi, fill=renk)
        x += cizim.textlength(karakter, font=yazi) + aralik


def uret(parca: str, cikti_adi: str = "") -> Path:
    """parca "genel" ise urunsuz marka karti uretir -- urun gorseli
    bulunamayan siparislerde mesaj gorselsiz kalmasin diye yedek."""
    genel = parca.strip().lower() == "genel"
    ad, urun = "GENEL", None
    if not genel:
        ad, adres = gorsel_adresi(parca)
        with urllib.request.urlopen(adres, timeout=60) as yanit:
            urun = Image.open(BytesIO(yanit.read())).convert("RGB")

    tuval = Image.new("RGB", (GEN, YUK), TUVAL)
    cizim = ImageDraw.Draw(tuval)

    # Urun sag yarida, TAM sigdirilarak (kirpma yok).
    kutu_gen, kutu_yuk = 470, 548
    if urun is None:
        arali(cizim, (380, 260), "L’CARLIÉ", font("Metropolis-Light.otf", 52),
              MUREKKEP, 7)
        cizim.line([(382, 348), (820, 348)], fill=MUREKKEP, width=1)
        arali(cizim, (382, 376), "SİPARİŞ TEYİDİ",
              font("Metropolis-Medium.otf", 19), MUREKKEP, 4)
        CIKTI_DIZIN.mkdir(parents=True, exist_ok=True)
        yol = CIKTI_DIZIN / ((cikti_adi or "genel") + ".jpg")
        tuval.save(yol, "JPEG", quality=88, optimize=True)
        print(ad); print(yol)
        print("https://n8n.lcarlie.shop/urun-gorsel/teyit/" + yol.name)
        return yol
    oran = min(kutu_gen / urun.width, kutu_yuk / urun.height)
    yeni = urun.resize((max(1, int(urun.width * oran)), max(1, int(urun.height * oran))),
                       Image.LANCZOS)
    tuval.paste(yeni, (GEN - 96 - kutu_gen + (kutu_gen - yeni.width) // 2,
                       (YUK - yeni.height) // 2))

    # Sol kolon. Urun karti zaten marka adini tasiyor; buyuk logo tekrar
    # olurdu, bu yuzden basligi ISIN ADI tasir, marka altta kucuk durur.
    arali(cizim, (112, 232), "SİPARİŞ", font("Metropolis-Light.otf", 46), MUREKKEP, 6)
    arali(cizim, (112, 292), "TEYİDİ", font("Metropolis-Light.otf", 46), MUREKKEP, 6)
    cizim.line([(114, 372), (300, 372)], fill=MUREKKEP, width=1)
    arali(cizim, (114, 400), "L’CARLIÉ", font("Metropolis-Medium.otf", 17), MUREKKEP, 4)
    arali(cizim, (114, 432), "ADRES ONAYINIZI BEKLİYORUZ",
          font("Metropolis-Light.otf", 13), ESKIZ, 2)

    CIKTI_DIZIN.mkdir(parents=True, exist_ok=True)
    yol = CIKTI_DIZIN / ((cikti_adi or slug(ad.split("(")[0])) + ".jpg")
    tuval.save(yol, "JPEG", quality=88, optimize=True)
    print(ad)
    print(yol)
    print("https://n8n.lcarlie.shop/urun-gorsel/teyit/" + yol.name)
    return yol


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    uret(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
