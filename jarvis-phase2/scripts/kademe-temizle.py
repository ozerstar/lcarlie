#!/usr/bin/env python3
"""Test artigi olcumleri kademe.jsonl'den ayiklar.

NEDEN. 24.09.2026'da olculdu: kademe_kaydi mutlak bir varsayilan yol
kullandigi icin her test kosusu URETIM gunlugune yaziyordu. O satirlar
"uc kademe de UNAVAILABLE -> ZINCIR_TUKENDI" gibi gorunuyor ve gercek bir
kesinti gibi okunuyor. 307 kaydin 278'i (%91) boyleydi.

IMZA. Uretimde .env'de anahtarlar var, bu yuzden external kademesi KIMLIK
YOKLUGUNDAN asla UNAVAILABLE olamaz. Bir zaman damgasinda
(external, ATLANDI, UNAVAILABLE) varsa o AN bir test kosusudur; o ana ait
butun satirlar birlikte ayiklanir -- yoksa oksuz gpu/local satirlari kalir
ve dagilim yine yaniltir.

KAPSAM. Silmez, AYIRIR: temizlenen satirlar .test-artigi uzantili dosyaya
tasinir. Olcum verisini geri donulemez bicimde atmak, kirli veriyi tutmak
kadar kotudur -- teshis yanlissa geri alinabilmeli.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def kirli_anlar(kayitlar: list[dict]) -> set:
    return {
        k.get("ts") for k in kayitlar
        if k.get("uc") == "external"
        and k.get("sonuc") == "ATLANDI"
        and k.get("gerekce") == "UNAVAILABLE"
    }


def main() -> int:
    yol = Path(sys.argv[1] if len(sys.argv) > 1
               else "/opt/lcarlie/jarvis-phase2/state/kademe.jsonl")
    if not yol.exists():
        print("dosya yok: %s" % yol)
        return 1

    ham = [s for s in yol.read_text(encoding="utf-8").splitlines() if s.strip()]
    kayitlar = []
    bozuk = 0
    for s in ham:
        try:
            kayitlar.append(json.loads(s))
        except json.JSONDecodeError:
            bozuk += 1
            kayitlar.append(None)

    kirli = kirli_anlar([k for k in kayitlar if k])
    tutulan, ayiklanan = [], []
    # strict=True: kayitlar her ham satir icin bir kez append ediliyor,
    # yani uzunluklar esit OLMAK ZORUNDA. Esit degilse sessizce kirpmak
    # olcumun bir kismini kaybetmek demektir -- gurultulu dusmesi dogrusu.
    for satir, kayit in zip(ham, kayitlar, strict=True):
        if kayit is None:
            tutulan.append(satir)          # bozuk satir da bir olcumdur
            continue
        # 'sinav' benim dogrulama satirlarim; onlar da uretim verisi degil
        if kayit.get("ts") in kirli or kayit.get("uc") == "sinav":
            ayiklanan.append(satir)
        else:
            tutulan.append(satir)

    yedek = yol.with_suffix(".jsonl.yedek-temizlik")
    shutil.copy2(str(yol), str(yedek))
    yol.write_text("\n".join(tutulan) + ("\n" if tutulan else ""), encoding="utf-8")
    Path(str(yol) + ".test-artigi").write_text(
        "\n".join(ayiklanan) + ("\n" if ayiklanan else ""), encoding="utf-8")

    print("toplam %d satir · kirli an %d · ayiklanan %d · kalan %d · bozuk %d"
          % (len(ham), len(kirli), len(ayiklanan), len(tutulan), bozuk))
    print("yedek : %s" % yedek)
    print("artik : %s.test-artigi" % yol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
