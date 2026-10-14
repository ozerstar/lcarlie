#!/usr/bin/env python3
"""Urun x MADDE haritasi: hangi madde hangi urunde.

SAHIP 22.09.2026: "Fikir uretmesini dusunmesini istiyorum. Urunler nelere
iyi gelir, iclerinde ne var, hangi madde nerede kullanilir. Belki OPTYWAVE
goz sagligina iyi gelir veya DERMABED kirisiklik gecirmede LIFTELLE'den
daha iyi, ona gore reklam yapacagiz."

Bu sorunun cevabi icin once VERI lazim: bugun her urunun INCI listesi ayri
bir metin blogu olarak duruyor ve hicbir yerde YAN YANA konmuyor. Kreatif
ekibi "bu madde baska hangi urunumuzde var" sorusunu soramiyordu cunku
soracagi tablo yoktu.

🔴 BU TABLO NE SOYLER, NE SOYLEMEZ.
SOYLER : hangi urunde hangi madde YAZIYOR, hangi maddeler ORTAK.
SOYLEMEZ: o maddenin ne ISE YARADIGI. Kutu metninde oran yok, etki yok.
"Ayni madde var" demek "ayni ise yarar" demek DEGILDIR -- oran, formul ve
tasiyici sistem belirleyicidir ve bunlar elimizde yok. Iki urunu "su
maddede ayni" diye kiyaslamak buradan CIKARILAMAZ; tablo yalnizca nereye
BAKILACAGINI soyler.

🔴 TR ve INCI adlari KARISIK. Bazi kutular "Jojoba Yagi", bazilari
"Simmondsia Chinensis Seed Oil" yaziyor. Ikisi ayni sey ama metin olarak
eslesmez. Eslestirme sozlugu kapsadigi kadarini birlestirir; kapsam
raporlanir ki "ortak madde yok" sonucu kapsam eksikligiyle karistirilmasin.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

KUTU = Path("/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi")

# TR -> INCI koprusu. Elle kuruldu, kapsam sinirli ve bu BILEREK boyle:
# tahmini eslestirme yanlis "ortak madde" uretir, o da yanlis reklam fikri.
TR_INCI = {
    "jojoba yagi": "simmondsia chinensis seed oil",
    "shea yagi": "butyrospermum parkii butter",
    "tatli badem yagi": "prunus amygdalus dulcis oil",
    "hindistan cevizi yagi": "cocos nucifera oil",
    "uzum cekirdegi yagi": "vitis vinifera seed oil",
    "avokado yagi": "persea gratissima oil",
    "aloe vera jel": "aloe barbadensis leaf juice",
    "e vitamini": "tocopherol",
    "tokoferol": "tocopherol",
    "gliserin": "glycerin",
    "saf su": "aqua",
    "su": "aqua",
    "lavanta yagi": "lavandula angustifolia oil",
    "nane yagi": "mentha piperita oil",
    "biberiye yagi": "rosmarinus officinalis leaf oil",
    "okaliptus yapragi yagi": "eucalyptus globulus leaf oil",
    "ylang ylang yagi": "cananga odorata flower oil",
    "karanfil yagi": "eugenia caryophyllus flower oil",
    "papatya ekstresi": "chamomilla recutita flower extract",
    "arnika ekstresi": "arnica montana flower extract",
    "zencefil yagi": "zingiber officinale root oil",
    "tarcin kabuk yagi": "cinnamomum zeylanicum bark oil",
    "hodan yagi": "borago officinalis seed oil",
    "hashas yagi": "papaver somniferum seed oil",
    "havuc tohumu yagi": "daucus carota sativa seed oil",
    "cinko oksit": "zinc oxide",
    "salisilik asit": "salicylic acid",
    "sorbik asit": "sorbic acid",
    "benzil alkol": "benzyl alcohol",
    "ksilitol": "xylitol",
}

# Madde sayilmayacak kaliplar: basliklar, aciklama cumleleri, uyum notlari.
COP = re.compile(
    r"^(tr|en|inci|icindekiler|ingredients|uts|cpnp|fda|not|aciklama)\b|"
    r"^\(|uyumlu|formulated|enriched|helps|supports|provides|specially|"
    r"^[0-9.,\s]+$", re.I)


def sade(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ı", "i").replace("İ", "i")
    s = re.sub(r"\([^)]*\)", " ", s)          # parantez ici atilir
    s = re.sub(r"[^A-Za-z0-9\s-]", " ", s)
    return " ".join(s.lower().split())


def maddeleri_ayikla(inci: str) -> list[str]:
    # Once TR/EN bolumlerini ayir: bazi kutularda "(EN)..." pazarlama metni
    # INCI'nin arkasina yapismis; o metin madde degildir.
    metin = re.split(r"\(EN\)|\(TR\)", inci)
    parcalar: list[str] = []
    for blok in metin:
        # Ingilizce pazarlama cumlesi olan bloklari atla.
        if re.search(r"\b(helps|supports|provides|formulated|enriched)\b", blok, re.I):
            continue
        parcalar.extend(re.split(r"[,;·]|\n", blok))
    out: list[str] = []
    for ham in parcalar:
        ad = sade(ham)
        if not ad or len(ad) < 3 or len(ad) > 60:
            continue
        if COP.search(ad):
            continue
        out.append(TR_INCI.get(ad, ad))
    return out


def main() -> int:
    dosyalar = sorted(p for p in KUTU.glob("*.json")
                      if not p.name.startswith("_"))
    urun_madde: dict[str, list[str]] = {}
    incisiz: list[str] = []
    for f in dosyalar:
        j = json.loads(f.read_text(encoding="utf-8"))
        inci = (j.get("bolumler") or {}).get("inci", "")
        ad = str(j.get("urun_adi") or f.stem)
        if not inci.strip():
            incisiz.append(ad)
            continue
        m = maddeleri_ayikla(inci)
        if m:
            urun_madde[f.stem] = sorted(set(m))
        else:
            incisiz.append(ad)

    # Ters indeks: madde -> hangi urunlerde
    madde_urun: dict[str, list[str]] = {}
    for u, ms in urun_madde.items():
        for m in ms:
            madde_urun.setdefault(m, []).append(u)

    ortak = {m: u for m, u in madde_urun.items() if len(u) > 1}
    tekil = {m: u[0] for m, u in madde_urun.items() if len(u) == 1}

    print(f"INCI okunan urun : {len(urun_madde)}")
    print(f"INCI bolumu yok  : {len(incisiz)} -> {', '.join(incisiz[:6])}")
    print(f"farkli madde     : {len(madde_urun)}")
    print(f"birden fazla urunde geceni: {len(ortak)}")
    print(f"tek urune ozgu   : {len(tekil)}")
    print("\n--- en yaygin 12 madde ---")
    for m, u in sorted(ortak.items(), key=lambda x: -len(x[1]))[:12]:
        print(f"  {len(u):>2} urun · {m[:44]:<44} {', '.join(sorted(u)[:4])}")

    cikti = {
        "uretildi": __import__("datetime").date.today().isoformat(),
        "urun_madde": urun_madde,
        "madde_urun": madde_urun,
        "inci_okunamayan": incisiz,
        "kapsam_notu": (
            "TR ve INCI adlari karisik yazilmis; eslestirme sozlugu "
            f"{len(TR_INCI)} cifti kapsiyor. Kapsam disindaki ayni madde iki "
            "farkli adla iki ayri satir olarak gorunur. 'Ortak madde yok' "
            "sonucu bu kapsam eksikligiyle KARISTIRILMAMALI."),
        "kullanim_uyarisi": (
            "Bu tablo hangi maddenin nerede YAZDIGINI soyler; o maddenin ne "
            "ISE YARADIGINI soylemez. Oran ve formul elimizde yok, bu yuzden "
            "iki urun 'su maddede ayni' diye kiyaslanamaz."),
    }
    hedef = Path("/opt/lcarlie/jarvis-phase2/varliklar/madde-haritasi.json")
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    print(f"\nyazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
