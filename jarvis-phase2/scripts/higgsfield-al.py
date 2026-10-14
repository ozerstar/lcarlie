#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Higgsfield'dan gelen sahneyi denetler, ürünü ve yazıyı basar.

Sahip Higgsfield'da sahneyi üretir (orada Unlimited bedava, Seedream 4.5
4K veriyor); bu betik gerisini yapar:

    1. DENETLE   OWLv2 kapısı (ayrı venv) -- davetsiz ürün, uydurma yazı,
                 insan, klişe. Kalan kare `elenen/`e gider, raporuyla.
    2. KOMPOZIT  geçen sahne + GERÇEK ürün pikselleri + dizgi.
    3. KAYIT     `core.tasarim_isi`'ne yazılır.

🔴 3. ADIM NEDEN VAR: tasarım departmanı kendi işine kördü. 26.09'da
sahip "neden arka plan yok" diye sorunca departmana sordum, cevabı
"kayıtlarımızda 2 iş var" oldu -- oysa sistem 7 gönderi görseli üretmişti.
`ig-gorsel-uret.py` deftere hiç yazmıyordu. Buradan geçen her kare
yazılır.

🔴 YAZIYI AI YAZMAZ. Sahip 26.09: "yazı yazmada problem var, bizim
repoları kullanarak üzerlerine yazılar yazılabilir." Ölçüm bunu
doğruladı: model "samgliac-intogoraation" yazdı, marka uydurdu. Dizgi
Monument Extended + Metropolis ile bizim motorumuzda yapılır; glif
koruması ve 4,5:1 kontrast ölçümü orada zaten var.

DOSYA ADI SÖZLEŞMESİ: gelen dosya `<plan_id>-<serbest metin>.<uzanti>`
olmalı (örn. `8-beton.png`). plan_id okunamazsa dosya İŞLENMEZ --
hangi ürünün hangi yazının basılacağını tahmin etmek, yanlış ürüne
yanlış yazı basmaktır.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KAP = "lcarlie-postgres"
GELEN = Path("/opt/lcarlie/higgsfield-gelen")
ELENEN = GELEN / "elenen"
ISLENEN = GELEN / "islenen"
CIKTI = Path("/opt/lcarlie/gonderi-gorsel")
DENETIM_PY = KOK / "venv-gorsel" / "bin" / "python"
DENETIM_BETIK = KOK / "scripts" / "gorsel-denetim.py"

_AD = re.compile(r"^(\d+)[-_]")


def calistir(sql: str, degiskenler: dict | None = None) -> list:
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in (degiskenler or {}).items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=90, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def denetle(yol: Path, klise_serbest: bool) -> dict:
    """Kapıyı AYRI venv'de çalıştırır (torch orada)."""
    if not DENETIM_PY.is_file():
        raise SystemExit("venv-gorsel yok: %s" % DENETIM_PY)
    komut = [str(DENETIM_PY), str(DENETIM_BETIK), str(yol), "--json"]
    if klise_serbest:
        komut.append("--klise-serbest")
    p = subprocess.run(komut, capture_output=True, text=True,
                       timeout=600, check=False)
    if p.returncode:
        raise SystemExit("denetim kosmadi: " + (p.stderr or "")[-400:])
    govde = p.stdout[p.stdout.find("["):]
    return json.loads(govde)[0]


def paket_oku(plan_id: int) -> dict:
    satir = calistir(
        "SELECT row_to_json(t) FROM (SELECT plan_id, urun_slug, bicim, kanca,"
        " caption, konsept_id FROM core.ig_gonderi_plani"
        " WHERE plan_id = %d) t;" % plan_id)
    if not satir:
        raise SystemExit("plan bulunamadi: %d" % plan_id)
    return satir[0]


def kompozit(paket: dict, sahne: Path) -> dict:
    """Sahne + gerçek ürün + dizgi. Ürün pikselleri AI'dan gelmez."""
    yol = KOK / "scripts" / "gorsel-kompozit.py"
    sp = importlib.util.spec_from_file_location("gorsel_kompozit", str(yol))
    gk = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(gk)

    bicim = {"REELS": "REELS", "KARUSEL": "AKIS",
             "TEK_GORSEL": "KARE"}.get(paket["bicim"], "AKIS")
    baslik = (paket.get("kanca") or "").split("—")[0].strip() \
        or paket["urun_slug"]
    cumleler = [s.strip() for s in (paket.get("caption") or "").split("\n")
                if s.strip() and s.strip() != paket.get("kanca")]
    return gk.uret(paket["urun_slug"], bicim=bicim, baslik=baslik,
                   alt=(cumleler[0] if cumleler else ""),
                   sahne=sahne, cikti_dizin=CIKTI)


def deftere_yaz(paket: dict, rapor: dict, cikti_adi: str) -> None:
    """🔴 Tasarım departmanı kendi işini görebilsin diye."""
    calistir("""
      INSERT INTO core.tasarim_isi
        (is_turu, isteyen, istek, veri, durum, denetim, maliyet_tl)
      VALUES ('instagram_post', 'higgsfield-al', :'istek',
              :'veri'::jsonb, 'URETILDI', :'denetim'::jsonb, 0);""",
        {"istek": "plan %s · %s" % (paket["plan_id"], paket["urun_slug"]),
         "veri": json.dumps({"plan_id": paket["plan_id"],
                             "urun_slug": paket["urun_slug"],
                             "cikti": cikti_adi,
                             "kaynak": "higgsfield/seedream"},
                            ensure_ascii=False),
         "denetim": json.dumps({"bulgu": [], "engel": False,
                                "kapilar": rapor.get("kapilar", []),
                                "kaynak": "gorsel-denetim.py (OWLv2)"},
                               ensure_ascii=False)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dizin", default=str(GELEN))
    ap.add_argument("--klise-serbest", action="store_true",
                    help="konsept cicek/tas istiyorsa klise kapisini atla")
    ap.add_argument("--yalniz-denetle", action="store_true")
    a = ap.parse_args()

    gelen = Path(a.dizin)
    if not gelen.is_dir():
        print("DIZIN YOK: %s -- once olustur, sonra gorselleri birak"
              % gelen)
        return 2
    ELENEN.mkdir(parents=True, exist_ok=True)
    ISLENEN.mkdir(parents=True, exist_ok=True)

    dosyalar = sorted(y for y in gelen.iterdir()
                      if y.is_file()
                      and y.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not dosyalar:
        print("BOS: %s icinde islenecek gorsel yok" % gelen)
        return 0

    gecen = elenen = atlanan = 0
    for yol in dosyalar:
        m = _AD.match(yol.name)
        if not m:
            print("  ATLANDI (plan_id okunamadi): %s" % yol.name)
            print("     dosya adi '<plan_id>-<ad>.png' olmali")
            atlanan += 1
            continue
        plan_id = int(m.group(1))
        print("\n%s  -> paket %d" % (yol.name, plan_id))

        rapor = denetle(yol, a.klise_serbest)
        for k in rapor["kapilar"]:
            iz = ", ".join("%s %.2f" % (b["ne"], b["puan"])
                           for b in (k.get("bulunan") or []))
            print("   %-22s %-8s %s" % (k["etiket"], k["sonuc"],
                                        iz or k.get("gerekce", "")))
        if rapor["sonuc"] == "RET":
            for s in rapor["red_sebepleri"]:
                print("   🔴 " + s)
            hedef = ELENEN / yol.name
            shutil.move(str(yol), str(hedef))
            (ELENEN / (yol.stem + ".rapor.json")).write_text(
                json.dumps(rapor, ensure_ascii=False, indent=1),
                encoding="utf-8")
            elenen += 1
            continue

        if a.yalniz_denetle:
            print("   GECTI (yalniz denetlendi, kompozit yapilmadi)")
            gecen += 1
            continue

        paket = paket_oku(plan_id)
        sonuc = kompozit(paket, yol)
        print("   kompozit: %s  birebir_oran=%s ssim=%s"
              % (sonuc.get("dosya"), sonuc.get("birebir_oran"),
                 sonuc.get("ssim")))
        deftere_yaz(paket, rapor, str(sonuc.get("dosya")))
        shutil.move(str(yol), str(ISLENEN / yol.name))
        gecen += 1

    print("\n%d gorsel · %d gecti · %d elendi · %d atlandi"
          % (len(dosyalar), gecen, elenen, atlanan))
    if elenen:
        print("elenenler ve sebepleri: %s" % ELENEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
