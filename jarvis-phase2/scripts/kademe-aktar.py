#!/usr/bin/env python3
"""state/kademe.jsonl -> core.kademe_denemesi aktarimi.

NEDEN AYRI BIR BETIK. Uretim makinesinde psycopg kurulu degil (bkz.
scripts/psql_session.py basligi), o yuzden model katmani JSONL'e yaziyor.
Bu betik o dosyayi veritabanina tasir ki sorulabilir olsun: "gecen hafta
kac cagri hangi kademeye dustu" sorusunun cevabi bir metin dosyasinda
aranmamali.

YONTEM: COPY ... FROM STDIN (FORMAT csv) ile gecici tabloya, oradan
ON CONFLICT DO NOTHING ile hedefe. Elle INSERT metni kurmak, model adinda
bir tirnak yuzunden butun aktarimi dusururdu -- bu projede daha once
yasanmis bir hata sinifi.

TEKRAR CALISTIRMAK GUVENLI: her satirin icerik hash'i UNIQUE. Filigran ya
da ofset tutulmaz; dosya donduruldugunde ofset yaniltir, hash yaniltmaz.

KAPSAM: yalniz tasir. Ayiklama yapmaz, ozet cikarmaz, hicbir satiri
"onemsiz" diye atmaz -- aktarilmayan satirin sebebini sonradan kimse
goremezdi.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import kademe_kaydi  # noqa: E402

KAP = "lcarlie-postgres"
KULLANICI = "n8n"
VERITABANI = "n8n"

SQL_BASLIK = """\\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE _gelen (
  ts timestamptz, uc text, kademe text, model text, sonuc text,
  gecikme_ms numeric, gerekce text, deneme integer, escalate boolean,
  is_anahtari text, kayit_hash text
) ON COMMIT DROP;
COPY _gelen FROM STDIN WITH (FORMAT csv);
"""

SQL_KUYRUK = """\\.
INSERT INTO core.kademe_denemesi
  (ts, uc, kademe, model, sonuc, gecikme_ms, gerekce, deneme, escalate,
   is_anahtari, kayit_hash)
SELECT ts, uc, kademe, model, sonuc, gecikme_ms, gerekce, deneme, escalate,
       is_anahtari, kayit_hash
FROM _gelen
ON CONFLICT (kayit_hash) DO NOTHING;
COMMIT;
"""


def sayim() -> int:
    """Hedef tablodaki satir sayisi. Okunamazsa -1 -- sifir DEGIL."""
    try:
        cikti = subprocess.run(
            ["docker", "exec", "-i", KAP, "psql", "-U", KULLANICI, "-d", VERITABANI,
             "-tAc", "select count(*) from core.kademe_denemesi"],
            capture_output=True, text=True, timeout=30)
        return int(cikti.stdout.strip())
    except Exception:  # noqa: BLE001 - okunamamak ayri bir durum
        return -1


def main() -> int:
    kayitlar = kademe_kaydi.tum_kayitlar()
    if not kayitlar:
        print("aktarilacak kayit yok (dosya bos ya da okunamadi)")
        return 0

    csv_metni = kademe_kaydi.aktarim_csv(kayitlar)
    if not csv_metni.strip():
        print("kayit var ama hicbiri aktarilabilir degil (ts/sonuc eksik)")
        return 0

    once = sayim()
    govde = SQL_BASLIK + csv_metni + SQL_KUYRUK

    sonuc = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", KULLANICI, "-d", VERITABANI],
        input=govde, capture_output=True, text=True, timeout=180)

    if sonuc.returncode != 0:
        # Hatayi yutmak, "aktarildi" yazip hicbir sey yazmamak olurdu.
        print("AKTARIM BASARISIZ (psql cikis %d)" % sonuc.returncode)
        print((sonuc.stderr or "").strip()[:600])
        return 1

    sonra = sayim()
    if once < 0 or sonra < 0:
        print("aktarildi; satir sayisi OKUNAMADI (dosyada %d kayit vardi)"
              % len(kayitlar))
        return 0
    print("dosyada %d kayit · tabloda %d -> %d · yeni %d"
          % (len(kayitlar), once, sonra, sonra - once))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
