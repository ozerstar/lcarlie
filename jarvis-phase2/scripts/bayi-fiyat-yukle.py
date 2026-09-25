#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Satış fiyat listesini core.urun_bayi_fiyat'a yükler.

Liste GÖRSEL geldiği için önce `fiyat-listesi-dogrula.py` mantığıyla her
hücre yeniden hesaplanır. Tutmayan satır yüklenir AMA `celiskili`
işaretlenir; mart.bayi_fiyat_gecerli o satırda kademe fiyatı GÖSTERMEZ.

Yanlış fiyat vermek, fiyat verememekten pahalıdır.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp")
from importlib.machinery import SourceFileLoader  # noqa: E402

_d = SourceFileLoader("dog", "/tmp/fiyat-listesi-dogrula.py").load_module()

KAP = "lcarlie-postgres"
KAYNAK = "lcarlie_satis_fiyat_listesi_2.pdf (25.09.2026)"
TOLERANS = 1.0

KAMPANYALAR = [
    (1, "70.000 TL üzeri siparişlerde ücretsiz stand ve görsel materyal desteği",
     "sipariş ≥ 70.000 TL"),
    (2, "100.000 TL üzeri toplu alımlarda ek %5 nakit ödeme indirimi",
     "toplu alım ≥ 100.000 TL, nakit"),
    (3, "Ürün alımlarında 10+1 destek ürünü kampanyası", "10 alana 1 destek"),
    (4, "Belirli ürün gruplarında dönemsel fırsat fiyatları", "dönemsel"),
    (5, "Klinik ve eczanelere özel tanıtım materyali desteği",
     "klinik / eczane"),
    (6, "Düzenli alım yapan satış noktalarına dönemsel sadakat indirimi, "
        "satış artırıcı reklam kampanyaları ve sosyal medya desteği",
     "düzenli alım"),
]


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


def main() -> int:
    eslesme = json.loads(Path("/tmp/fiyat-eslesme.json").read_text(encoding="utf-8"))
    slug_ile = {ad: slug for ad, slug, _psf, _w in eslesme["eslesen"]}

    # Hangi satirin hangi hucresi celiskili
    celiski = {}
    for ad, etiket, listede, olmasi in eslesme["hatali_hucre"]:
        celiski.setdefault(ad, []).append(
            "%s: listede %d, hesaba gore %d" % (etiket, listede, olmasi))

    yazilan = celiskili_sayi = atlanan = 0
    for satir in _d.SATIRLAR:
        ad, barkod, psf = satir[0], satir[1], satir[2]
        slug = slug_ile.get(ad)
        if not slug:
            print("  ATLANDI (katalogda yok): %s" % ad)
            atlanan += 1
            continue
        notlar = celiski.get(ad) or []
        bayrak = bool(notlar)
        if bayrak:
            celiskili_sayi += 1

        calistir("""
          INSERT INTO core.urun_bayi_fiyat
            (urun_slug, barkod, psf, isk30_haric, isk30_dahil,
             isk40_haric, isk40_dahil, trendyol, bayi_fiyat,
             celiskili, celiski_notu, kaynak, giren)
          VALUES (:'slug', :'barkod', %d, %d, %d, %d, %d, %d, %d,
                  %s, NULLIF(:'not',''), :'kaynak', 'fiyat-listesi')
          ON CONFLICT (urun_slug) DO UPDATE SET
            barkod = EXCLUDED.barkod, psf = EXCLUDED.psf,
            isk30_haric = EXCLUDED.isk30_haric,
            isk30_dahil = EXCLUDED.isk30_dahil,
            isk40_haric = EXCLUDED.isk40_haric,
            isk40_dahil = EXCLUDED.isk40_dahil,
            trendyol = EXCLUDED.trendyol, bayi_fiyat = EXCLUDED.bayi_fiyat,
            celiskili = EXCLUDED.celiskili,
            celiski_notu = EXCLUDED.celiski_notu,
            kaynak = EXCLUDED.kaynak, giren = EXCLUDED.giren,
            girildi = now();""" % (
            psf, satir[3], satir[4], satir[5], satir[6], satir[7],
            satir[5],           # bayi_fiyat = en dusuk kademe (KDV haric %40)
            "true" if bayrak else "false"),
            {"slug": slug, "barkod": barkod,
             "not": " · ".join(notlar), "kaynak": KAYNAK})
        yazilan += 1

    for sira, baslik, kosul in KAMPANYALAR:
        calistir("""
          INSERT INTO core.bayi_kampanya (sira, baslik, kosul, kaynak)
          VALUES (%d, :'baslik', :'kosul', :'kaynak')
          ON CONFLICT (sira) DO UPDATE SET
            baslik = EXCLUDED.baslik, kosul = EXCLUDED.kosul,
            kaynak = EXCLUDED.kaynak, girildi = now();""" % sira,
            {"baslik": baslik, "kosul": kosul, "kaynak": KAYNAK})

    ozet = calistir("""SELECT row_to_json(t) FROM (
      SELECT count(*) AS toplam,
             count(*) FILTER (WHERE celiskili) AS celiskili,
             min(psf) AS en_dusuk_psf, max(psf) AS en_yuksek_psf
        FROM core.urun_bayi_fiyat) t;""")[0]
    print("\nyazilan: %d urun · celiskili: %d · atlanan: %d"
          % (yazilan, celiskili_sayi, atlanan))
    print("tabloda: %s urun · celiskili %s · PSF %s-%s TL"
          % (ozet["toplam"], ozet["celiskili"],
             int(ozet["en_dusuk_psf"]), int(ozet["en_yuksek_psf"])))
    print("kampanya: %d madde" % len(KAMPANYALAR))

    eksik = calistir("""SELECT row_to_json(t) FROM (
      SELECT h.slug FROM (SELECT DISTINCT slug FROM raw.wix_urun) h
       WHERE NOT EXISTS (SELECT 1 FROM core.urun_bayi_fiyat b
                          WHERE b.urun_slug = h.slug)
       ORDER BY 1) t;""")
    if eksik:
        print("\n🔴 BAYI FIYATI OLMAYAN URUN: %s"
              % ", ".join(e["slug"] for e in eksik))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
