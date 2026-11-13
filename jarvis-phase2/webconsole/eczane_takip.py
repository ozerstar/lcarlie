"""ECZANELER sekmesi: eczane listesi ve her eczaneyle ne yapıldığı (tikli).

Sahip 13.11.2026: "Jarvis'te bir tabloda eczane listelerini koy, bilgilerini
koy, bu eczanelerle ilgili neler yapıldı tikli halde götürülsün."

YALNIZ OKUR ve yalnız mart.eczane_takip görünümünü okur. Panel rolü
(jarvis_web) ham tablolara erişmez; görünüm hesaplamayı kendisi yapar.
Arama metni SQL'e gömülmez, psql değişkeni (:'ara') olarak geçer.
"""
from __future__ import annotations

import json
import subprocess

from jarvis.db_transport import run as db_run

KAP = "lcarlie-postgres"
SAYFA = 100

# Süzgeç adı -> WHERE parçası. Yalnız bu sabit parçalar SQL'e girer.
SUZGEC = {
    "hepsi": "TRUE",
    "sirada": "wa_gonderildi IS NULL AND eposta_gonderildi IS NULL AND durum NOT IN ('CIKTI')",
    "wa": "wa_gonderildi IS NOT NULL",
    "teslim": "wa_durum IN ('DELIVERED','READ')",
    "okudu": "wa_durum = 'READ'",
    "ulasmadi": "wa_durum = 'FAILED'",
    "sayfa": "sayfa_sayisi > 0",
    "cevap": "yanit_son IS NOT NULL",
    "randevu": "randevu IS NOT NULL",
    "ziyaret": "ziyaret_edildi",
    "istemiyor": "cikis_zaman IS NOT NULL OR durum = 'CIKTI'",
    "cepli": "cep IS NOT NULL",
    "epostali": "eposta IS NOT NULL",
    "temsilci": "temsilci",
}
SIRALAMA = {
    "son": "son_islem DESC NULLS LAST, oncelik, id",
    "ad": "eczane, id",
    "ilce": "ilce NULLS LAST, eczane, id",
}


class TakipHatasi(RuntimeError):
    pass


def _calistir(sql: str, **degisken: str) -> list:
    arg = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
           "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n"]
    for k, v in degisken.items():
        arg += ["-v", "%s=%s" % (k, v)]
    arg += ["-f", "-"]
    try:
        p = db_run(arg, input=sql, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError) as hata:
        raise TakipHatasi("veritabani calistirilamadi: %s" % hata) from None
    if p.returncode:
        raise TakipHatasi((p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.split("\n") if s.strip()]


def liste(il: str = "Ankara", ilce: str = "", suzgec: str = "hepsi", ara: str = "",
          sirala: str = "son", sayfa: int = 0) -> dict:
    if suzgec not in SUZGEC:
        raise TakipHatasi("gecersiz suzgec: %s" % suzgec)
    sira = SIRALAMA.get(sirala, SIRALAMA["son"])
    sayfa = max(0, int(sayfa))
    kosul = SUZGEC[suzgec]
    satirlar = _calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT * FROM mart.eczane_takip
      WHERE il = :'il' AND (:'ilce' = '' OR ilce = :'ilce')
        AND (:'ara' = '' OR eczane ILIKE '%' || :'ara' || '%' OR eczaci ILIKE '%' || :'ara' || '%'
             OR telefon LIKE '%' || :'ara' || '%' OR cep LIKE '%' || :'ara' || '%')
        AND ({kosul})
      ORDER BY {sira}
      LIMIT {SAYFA + 1} OFFSET {sayfa * SAYFA}
    ) x;""", il=il, ilce=ilce or "", ara=(ara or "").strip()[:60])
    return {"satirlar": satirlar[:SAYFA], "devami_var": len(satirlar) > SAYFA,
            "sayfa": sayfa, "sayfa_boyu": SAYFA}


def ozet(il: str = "Ankara") -> dict:
    sayim = ", ".join("count(*) FILTER (WHERE %s) AS %s" % (v, k) for k, v in SUZGEC.items())
    r = _calistir(f"SELECT row_to_json(x) FROM (SELECT {sayim} FROM mart.eczane_takip"
                  f" WHERE il = :'il') x;", il=il)
    ilceler = _calistir("SELECT row_to_json(x) FROM (SELECT ilce, count(*) AS n FROM mart.eczane_takip"
                        " WHERE il = :'il' AND ilce IS NOT NULL GROUP BY ilce ORDER BY count(*) DESC) x;",
                        il=il)
    iller = _calistir("SELECT row_to_json(x) FROM (SELECT il, count(*) AS n FROM mart.eczane_takip"
                      " GROUP BY il ORDER BY min(oncelik) NULLS LAST, il) x;")
    return {"sayim": r[0] if r else {}, "ilceler": ilceler, "iller": iller}
