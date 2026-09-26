# -*- coding: utf-8 -*-
"""Çekim arşivini ürün slug'larıyla eşler.

🔴 KAYITLI SORUN ÇÖZÜLDÜ. Bilgi dosyasında "36 üründen 27'sinin
fotoğrafı yalnız 1254 px -- web çözünürlüğü; baskı için YENİDEN ÇEKİM
gerekiyor" yazıyordu. Yeniden çekim gerekmiyor: orijinaller sahibin
masaüstünde duruyor, 3072x4608 (14,2 MP) -- web kopyasının 9 KATI piksel.

Arşiv adları slug değil, elden yazılmış: "caljaw" (slug calmjaw),
"hair nourshier" (slug hair-nouriher), "femisia" (femisia-for-women),
"vireon" (vireon-for-men). Eşleme ELLE yazıldı; tahmin eden bir
algoritma yanlış ürüne yanlış fotoğrafı bağlardı ve bunu kimse fark
etmezdi.
"""
import json
import shutil
import sys
import unicodedata
from pathlib import Path

ARSIV = Path(sys.argv[1])
HEDEF = Path(sys.argv[2])

# arsiv adi (uzantisiz, kucuk harf) -> urun slug
ESLEME = {
    "babyrescue": "baby-rescue",
    "babyshower": "babyshower",
    "babysoft": "babysoft",
    "babysol": "babysol",
    "buguard": "buguard",
    "caljaw": "calmjaw",
    "calmaros": "calmaros",
    "calmoris": "calmoris",
    "dermabed": "dermabed",
    "dermacorn": "dermacorn",
    "dermaguard": "dermaguard",
    "dermamovera": "dermamovera",
    "dermanova": "dermanova",
    "dermarnica": "dermarnica",
    "dermastra": "dermastra",
    "dermavasc": "dermavasc",
    "dorsivia": "dorsivia",
    "easycomb": "easycomb",
    "femisia": "femisia-for-women",
    "hair nourshier": "hair-nouriher",
    "hydravie": "hydravie",
    "intimblanc": "intimblanc",
    "kinesis": "kinesis",
    "liftelle": "liftelle",
    "lipvora": "lipvora",
    "luciderm": "luciderm",
    "menthalis": "menthalis",
    "minisooth": "minisooth-bebek-pişik-kremi",
    "optywave": "optywave",
    "oragarde": "oragarde",
    "seralimbo": "seralimbo",
    "softguard": "softguard",
    "sunacnea": "sunacnea-30-spf",
    "vireon": "vireon-for-men",
}

# Katalogda karsiligi OLMAYAN arsiv dosyalari. Atilmiyor, yalniz
# raporlaniyor: "bilmiyorum" ile "yok" ayri seyler.
KATALOG_DISI = {"aurolis", "earclia", "nomore", "menthaliskutulu"}


def govde(ad: str) -> str:
    """'babysoft kopya.jpg' -> 'babysoft', 'dermacorn2 kopya' -> 'dermacorn2'."""
    t = unicodedata.normalize("NFC", Path(ad).stem).lower().strip()
    for ek in (" kopyası kopya", " kopya1", " kopya", " acık", " açık"):
        if t.endswith(ek):
            t = t[: -len(ek)].strip()
    return t


def main() -> int:
    if not ARSIV.is_dir():
        print("ARSIV YOK: %s" % ARSIV)
        return 2
    HEDEF.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    # Her slug icin EN BUYUK dosyayi sec: "kopya" surumleri genelde
    # duzenlenmis ve daha buyuk oluyor.
    adaylar = {}
    eslesmeyen, katalog_disi, dsc = [], [], []
    for yol in sorted(ARSIV.iterdir()):
        if not yol.is_file() or yol.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        g = govde(yol.name)
        if g.startswith("dsc"):
            dsc.append(yol.name)
            continue
        if g in KATALOG_DISI:
            katalog_disi.append(yol.name)
            continue
        slug = ESLEME.get(g) or ESLEME.get(g.rstrip("0123456789"))
        if not slug:
            eslesmeyen.append(yol.name)
            continue
        onceki = adaylar.get(slug)
        if onceki is None or yol.stat().st_size > onceki.stat().st_size:
            adaylar[slug] = yol

    rapor = []
    for slug, yol in sorted(adaylar.items()):
        im = Image.open(yol)
        hedef = HEDEF / ("%s.jpg" % slug)
        shutil.copy2(yol, hedef)
        rapor.append({"slug": slug, "kaynak": yol.name,
                      "en": im.width, "boy": im.height,
                      "mp": round(im.width * im.height / 1e6, 1),
                      "mb": round(yol.stat().st_size / 1048576.0, 1)})
        print("  %-28s %sx%s  %.1f MP  <- %s"
              % (slug, im.width, im.height, rapor[-1]["mp"], yol.name))

    print("\n%d urun eslendi" % len(rapor))
    if dsc:
        print("adsiz cekim (DSC...): %d dosya -- hangi urun oldugu belli "
              "degil, ELLE bakilmali" % len(dsc))
    if katalog_disi:
        print("katalog disi: %s" % ", ".join(sorted(set(
            govde(a) for a in katalog_disi))))
    if eslesmeyen:
        print("🔴 ESLESMEYEN: %s" % ", ".join(eslesmeyen))

    (HEDEF / "arsiv-rapor.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
