#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ürün fotoğraflarını BASKI çözünürlüğünde indirir.

🔴 NEDEN AYRI BİR SET. Saha kataloğu için görselleri 1400 piksele
küçültmüştüm; sebebi haklıydı (187,6 MB -> 6,4 MB, eczanenin bodrumunda
mobil veriyle açılsın). Ama baskı kataloğunda ürün kesimi kırpılınca
şişe kaynak karenin küçük bir parçası kalıyor: 1400 pikselden kırpınca
230-400 piksel ediyor ve 43-61 mm'ye yerleşince 130-170 DPI çıkıyor.
Ölçüldü ve prepress denetimi yakaladı.

İki ayrı amaç, iki ayrı varlık seti:
  katalog-gorsel/       1400 px WebP  · panel, saha, mobil
  katalog-baski-gorsel/ tam çözünürlük PNG · baskı

Wix orijinali 2000-4000 piksel veriyor; adresteki boyut parçası
KALDIRILIR ve kaynak ne veriyorsa o alınır. Küçültme yok, kayıp yok.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

KAP = "lcarlie-postgres"
HEDEF = Path("/opt/lcarlie/katalog-baski-gorsel")
TANITIM = "LCARLIE-Katalog-Baski/1.0 (+https://jarvis.lcarlie.shop)"
ZAMAN_ASIMI = 60
EN_AZ_PIKSEL = 1500        # bunun altındaki kaynak baskı için şüphelidir

SORGU = """
SELECT row_to_json(t) FROM (
  SELECT w.sku, w.ad, w.slug,
         i->'image'->>'url'  AS adres,
         (i->'image'->>'width')::int  AS genislik,
         (i->'image'->>'height')::int AS yukseklik,
         (i->>'id') = (w.ham->'media'->'mainMedia'->>'id') AS ana
    FROM raw.wix_urun w,
         jsonb_array_elements(w.ham->'media'->'items') i
   WHERE i->>'mediaType' = 'image'
     AND (i->>'id') = (w.ham->'media'->'mainMedia'->>'id')
) t;
"""


def oku(sql: str) -> list:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input="\\set ON_ERROR_STOP on\n" + sql, capture_output=True,
        text=True, timeout=90, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def tam_boy_adresi(adres: str, g: int, y: int) -> str:
    """Wix adresindeki boyut parçasını KAYNAK boyutuna çeker."""
    if not g or not y:
        return adres
    return re.sub(r"/w_\d+,h_\d+,", "/w_%d,h_%d," % (g, y), adres, count=1)


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    kayitlar = oku(SORGU)
    if not kayitlar:
        print("DURDU: ana gorsel bulunamadi")
        return 1

    dizin, inen, atlanan, hatali, kucuk = [], 0, 0, 0, []
    for k in kayitlar:
        adres = tam_boy_adresi(k["adres"], k["genislik"], k["yukseklik"])
        ad = "%s-%s.png" % (k["slug"],
                            hashlib.sha256(adres.encode()).hexdigest()[:10])
        yol = HEDEF / ad
        if not yol.exists():
            try:
                istek = urllib.request.Request(adres, headers={"User-Agent": TANITIM})
                with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
                    veri = y.read()
                if len(veri) < 2000:
                    raise ValueError("govde cok kucuk (%d bayt)" % len(veri))
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(veri))
                im.load()
                gecici = yol.with_suffix(".png.tmp")
                im.save(gecici, "PNG")       # kayipsiz: kesim bunun uzerinde
                gecici.replace(yol)
                inen += 1
            except (urllib.error.URLError, OSError, ValueError) as hata:
                print("  HATA %s: %s" % (k["ad"][:36], str(hata)[:80]))
                hatali += 1
                continue
        else:
            atlanan += 1
        from PIL import Image
        with Image.open(yol) as im:
            en, boy = im.size
        if max(en, boy) < EN_AZ_PIKSEL:
            kucuk.append("%s (%dx%d)" % (k["slug"], en, boy))
        dizin.append({"slug": k["slug"], "sku": k["sku"], "dosya": ad,
                      "piksel": [en, boy], "bayt": yol.stat().st_size})

    dizin.sort(key=lambda d: d["slug"])
    (HEDEF / "dizin.json").write_text(
        json.dumps(dizin, ensure_ascii=False, indent=1), encoding="utf-8")
    toplam = sum(d["bayt"] for d in dizin)
    print("baski gorseli: %d indi · %d vardi · %d hatali" % (inen, atlanan, hatali))
    print("dizin: %d urun · %.0f MB · en kucuk kaynak %d px"
          % (len(dizin), toplam / 1048576.0,
             min(max(d["piksel"]) for d in dizin) if dizin else 0))
    if kucuk:
        # Sessizce gecilmez: bu urunlerin baski kalitesi kaynaktan sinirli.
        print("🔴 %d URUNUN KAYNAGI %d PIKSELIN ALTINDA -- baskida sinirli:"
              % (len(kucuk), EN_AZ_PIKSEL))
        for s in kucuk:
            print("   " + s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
