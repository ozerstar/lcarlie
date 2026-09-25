#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wix ürün görsellerini KENDİ SUNUCUMUZA indirir.

NEDEN İNDİRİYORUZ, DOĞRUDAN BAĞLAMIYORUZ:

1. Panelin içerik güvenliği ilkesi `img-src 'self' data:`. Wix'ten doğrudan
   görsel çekmek ilkeyi gevşetmeyi gerektirirdi.
2. Katalog SAHADA açılacak. Eczanenin bodrumunda, sinyalin olmadığı yerde
   ürün fotoğrafı yüklenmezse sunum yarıda kalır.
3. Wix hesabı ya da görsel adresi değişirse katalog bir sabah sessizce boş
   kalırdı. Kendi kopyamız buna bağımlı değil.

ÖLÇÜ: Wix 2000-4000 piksel genişlikte PNG veriyor -- 124 görsel 187 MB
tutuyordu. Saha elemanı bunu mobil veriyle açamaz. Her görsel en büyük
kenarı 1400 piksel olacak şekilde WebP'ye çevrilir; ölçülen kazanç
3.459 KB -> 83 KB (41 kat). Saydamlık WebP'de korunur, JPEG'de siyah
zemine dönerdi -- ürün kupürlerinde bu görünür bir kusur olurdu.

YENİDEN ÇALIŞTIRILABİLİR: var olan dosya yeniden indirilmez. Ürün görseli
Wix'te değişirse dosya adı da değişir (adres karması), yenisi iner, eskisi
kalır -- silmek, hangi görselin ne zaman kullanıldığını okunamaz kılardı.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

KAP = "lcarlie-postgres"
HEDEF = Path("/opt/lcarlie/katalog-gorsel")
EN_BUYUK_KENAR = 1400
WEBP_KALITE = 82
ZAMAN_ASIMI = 30
TANITIM = "LCARLIE-Katalog/1.0 (+https://jarvis.lcarlie.shop)"

SORGU = """
SELECT row_to_json(t) FROM (
  SELECT w.sku, w.ad, w.slug,
         i->'image'->>'url'  AS adres,
         (i->'image'->>'width')::int  AS genislik,
         (i->'image'->>'height')::int AS yukseklik,
         (i->>'id') = (w.ham->'media'->'mainMedia'->>'id') AS ana,
         row_number() OVER (PARTITION BY w.sku ORDER BY
             ((i->>'id') = (w.ham->'media'->'mainMedia'->>'id')) DESC) AS sira
    FROM raw.wix_urun w,
         jsonb_array_elements(w.ham->'media'->'items') i
   WHERE i->>'mediaType' = 'image'
) t;
"""


def oku(sql: str) -> list[dict]:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input="\\set ON_ERROR_STOP on\n" + sql, capture_output=True,
        text=True, timeout=60, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def kucult_adresi(adres: str, genislik: int, yukseklik: int) -> str:
    """Wix adresindeki boyut parçasını küçültür.

    Wix adresi `/v1/fit/w_2000,h_2299,q_90/file.png` biçiminde; boyutu
    adresten istemek, tam boyutu indirip yerelde küçültmekten hem hızlı
    hem de Pillow bağımlılığı getirmiyor.
    """
    if not genislik or not yukseklik:
        return adres
    oran = min(1.0, EN_BUYUK_KENAR / float(max(genislik, yukseklik)))
    if oran >= 1.0:
        return adres
    yeni_g, yeni_y = int(genislik * oran), int(yukseklik * oran)
    import re
    return re.sub(r"/w_\d+,h_\d+,", "/w_%d,h_%d," % (yeni_g, yeni_y), adres, count=1)


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    kayitlar = oku(SORGU)
    if not kayitlar:
        print("DURDU: hic gorsel bulunamadi -- raw.wix_urun bos olabilir")
        return 1

    dizin = []
    inen = atlanan = hatali = 0
    for k in kayitlar:
        adres = kucult_adresi(k["adres"], k["genislik"], k["yukseklik"])
        # Dosya adı ADRESİN karmasıdır: görsel Wix'te değişirse ad da
        # değişir ve tarayıcı önbelleği eskisini göstermeye devam edemez.
        ad = "%s-%s.webp" % (k["slug"] or k["sku"],
                             hashlib.sha256(adres.encode()).hexdigest()[:10])
        yol = HEDEF / ad
        if not yol.exists():
            try:
                istek = urllib.request.Request(adres, headers={"User-Agent": TANITIM})
                with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
                    veri = y.read()
                if len(veri) < 500:
                    raise ValueError("govde cok kucuk (%d bayt)" % len(veri))
                from PIL import Image
                gorsel = Image.open(io.BytesIO(veri))
                gorsel.load()                # bozuk dosya BURADA patlasin
                gorsel.thumbnail((EN_BUYUK_KENAR, EN_BUYUK_KENAR))
                gecici = yol.with_suffix(".webp.tmp")
                gorsel.save(gecici, "WEBP", quality=WEBP_KALITE, method=4)
                gecici.replace(yol)          # yarim dosya okunmaz
                inen += 1
            except (urllib.error.URLError, OSError, ValueError) as hata:
                print("  HATA %s: %s" % (k["ad"][:40], str(hata)[:90]))
                hatali += 1
                continue
        else:
            atlanan += 1
        dizin.append({"sku": k["sku"], "ad": k["ad"], "slug": k["slug"],
                      "dosya": ad, "ana": bool(k["ana"]), "sira": k["sira"],
                      "bayt": yol.stat().st_size})

    dizin.sort(key=lambda d: (d["slug"] or "", d["sira"]))
    (HEDEF / "dizin.json").write_text(
        json.dumps(dizin, ensure_ascii=False, indent=1), encoding="utf-8")

    toplam = sum(d["bayt"] for d in dizin)
    urun = len({d["sku"] for d in dizin})
    print("gorsel: %d indi · %d zaten vardi · %d hatali" % (inen, atlanan, hatali))
    print("dizin: %d gorsel · %d urun · %.1f MB · %s"
          % (len(dizin), urun, toplam / 1048576.0, HEDEF))
    # Ana gorseli olmayan urun sunumda bosluk birakir -- sessizce gecilmez.
    anasiz = sorted({d["ad"] for d in dizin} -
                    {d["ad"] for d in dizin if d["ana"]})
    if anasiz:
        print("UYARI: ana gorseli isaretli olmayan urun: %s" % ", ".join(anasiz[:5]))
    return 0 if not hatali else 2


if __name__ == "__main__":
    raise SystemExit(main())
