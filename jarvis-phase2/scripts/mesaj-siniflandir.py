#!/usr/bin/env python3
"""Sınıfı boş gelen müşteri mesajlarını sınıflandırır.

NEDEN SÜPÜRÜCÜ, NEDEN KUYRUĞA GÖMÜLÜ DEĞİL
Konuşmalar iki ayrı yoldan geliyor: webhook kuyruğu (`meta-kuyruk-yukle`)
ve Meta konuşma içe aktarıcısı (`lcarlie-meta-conversations`). Sınıflamayı
birine gömmek diğerinden geleni sessizce sınıfsız bırakırdı -- 15.10.2026'da
ölçülen durum tam buydu: 540 mesaj elle doldurulmuş, 783'ü boş kalmıştı ve
hiç kimse fark etmiyordu. Süpürücü kaynağı umursamaz.

🔴 MEVCUT ETİKETLERİ EZMEZ. Varsayılan olarak yalnız `sinif IS NULL`
satırlara yazar. `--tumu` ile hepsi yeniden sınıflanır; bu SAHİP KARARIDIR,
çünkü eldeki 540 etiket gürültülü de olsa bir insan/model emeğidir.

Çalıştırma:
    venv/bin/python scripts/mesaj-siniflandir.py [--kuru] [--tumu]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis import devir, mesaj_sinifi  # noqa: E402

PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At",
        "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n", "-f", "-"]


def _psql(sql: str) -> list[str]:
    sonuc = subprocess.run(PSQL, input=sql, capture_output=True, text=True,
                           check=False)
    if sonuc.returncode:
        raise SystemExit("psql hatasi: %s" % (sonuc.stderr or sonuc.stdout)[:400])
    return [s for s in sonuc.stdout.splitlines() if s.strip()]


def _tirnak(deger) -> str:
    if deger is None or deger == "":
        return "NULL"
    return "'" + str(deger).replace("'", "''") + "'"


def oku(tumu: bool) -> list[dict]:
    kosul = "" if tumu else "AND m.sinif IS NULL"
    satirlar = _psql(f"""
    SELECT row_to_json(t) FROM (
      SELECT m.id, m.metin
      FROM lcarlie.mesaj m
      WHERE m.yon = 'gelen' AND length(btrim(m.metin)) > 0 {kosul}
      ORDER BY m.id
    ) t;
    """)
    return [json.loads(s) for s in satirlar]


def yaz(atamalar: list[tuple[int, str]]) -> int:
    """Tek ifadede toplu güncelleme. Boş liste veritabanına gitmez."""
    if not atamalar:
        return 0
    degerler = ", ".join("(%d, %s)" % (mid, _tirnak(s)) for mid, s in atamalar)
    cikti = _psql(f"""
    WITH g(id, sinif) AS (VALUES {degerler})
    UPDATE lcarlie.mesaj m SET sinif = g.sinif
      FROM g WHERE m.id = g.id AND m.sinif IS DISTINCT FROM g.sinif
    RETURNING m.id;
    """)
    return len(cikti)


def main() -> None:
    kuru = "--kuru" in sys.argv
    tumu = "--tumu" in sys.argv

    kayitlar = oku(tumu)
    print("siniflanacak mesaj: %d%s" % (len(kayitlar), " (TUMU)" if tumu else ""))
    if not kayitlar:
        print("yapilacak is yok")
        return

    atamalar: list[tuple[int, str]] = []
    sayac: dict[str, int] = {}
    jarvis = sahip = 0
    for k in kayitlar:
        sinif = mesaj_sinifi.siniflandir(k["metin"])
        atamalar.append((int(k["id"]), sinif))
        sayac[sinif] = sayac.get(sinif, 0) + 1
        # Urun atamasi bugun YOK (olculdu: 0/535 konusmada ad_id var), bu
        # yuzden gercek yonlendirme urun_bilindi=False ile raporlanir.
        gerek, _ = devir.devir_gerekir(sinif, urun_bilindi=False)
        if gerek:
            sahip += 1
        else:
            jarvis += 1

    for sinif in sorted(sayac, key=lambda x: -sayac[x]):
        nerede = "Jarvis" if sinif in devir.JARVIS_SINIFLARI else "sahip"
        print("  %-14s %5d  -> %s" % (sinif, sayac[sinif], nerede))

    print("yonlendirme (urun bilinmiyor): Jarvis %d · sahip %d" % (jarvis, sahip))

    if kuru:
        print("--kuru: veritabanina YAZILMADI")
        return
    yazilan = yaz(atamalar)
    print("guncellenen satir: %d" % yazilan)


if __name__ == "__main__":
    main()
