#!/usr/bin/env python3
"""Overture Places -> raw.eczane_kaynak (kaynak OVERTURE), TÜM TÜRKİYE, yalnız eczane.

SAHA taramasından (overture-tara.py) farkı: o Ankara'yı ve 16 türü tarar ve
`medical_supply` gibi kategorileri de ECZANE sayar. Ölçüldü (13.11): SAHA'da
"eczane" görünen 330 e-postalı kaydın yalnız 86'sı gerçek eczaneydi; kalanı
medikal firması, ecza deposu, aktar, gıda. Kampanya listesine o karışım
giremez. Burada YALNIZ birincil kategorisi `pharmacy` olan kayıt alınır.

Sürüm ve şema seçimi overture-tara.py'den alınır (en yeni sürüm, iki şema).
"""
import importlib.util
import json
import pathlib
import subprocess
import sys

import duckdb

_yol = pathlib.Path(__file__).with_name("overture-tara.py")
_spec = importlib.util.spec_from_file_location("overture_tara", _yol)
ot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ot)

TR = {"xmin": 25.6, "xmax": 44.9, "ymin": 35.8, "ymax": 42.2}
PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
        "-v", "ON_ERROR_STOP=1", "-At"]

SORGU = """
SELECT id, names.primary AS ad, {kat} AS kategori,
       list_transform(coalesce(phones, []), x -> x) AS telefonlar,
       list_transform(coalesce(emails, []), x -> x) AS epostalar,
       websites[1] AS web,
       list_transform(coalesce(socials, []), x -> x) AS sosyal,
       addresses[1].freeform AS adres, addresses[1].locality AS ilce,
       addresses[1].region AS bolge, addresses[1].country AS ulke,
       bbox.ymin AS enlem, bbox.xmin AS boylam, confidence AS guven
FROM read_parquet('{s3}')
WHERE bbox.xmin BETWEEN {xmin} AND {xmax} AND bbox.ymin BETWEEN {ymin} AND {ymax}
  AND {kat} = 'pharmacy'
  AND names.primary IS NOT NULL
"""

YUKLE = r"""
BEGIN;
CREATE TEMP TABLE y (j jsonb);
\copy y FROM STDIN
{GOVDE}
\.
INSERT INTO raw.eczane_kaynak (kaynak, kaynak_id, il, ilce, ad, kategori, telefonlar, epostalar,
                               web, sosyal, adres, enlem, boylam, ham)
SELECT 'OVERTURE', j->>'id', nullif(j->>'bolge',''), nullif(j->>'ilce',''), j->>'ad', 'pharmacy',
       ARRAY(SELECT right(regexp_replace(x,'\D','','g'),10)
             FROM jsonb_array_elements_text(j->'telefonlar') x
             WHERE length(regexp_replace(x,'\D','','g')) >= 10),
       ARRAY(SELECT lower(x) FROM jsonb_array_elements_text(j->'epostalar') x),
       nullif(j->>'web',''), ARRAY(SELECT jsonb_array_elements_text(j->'sosyal')),
       j->>'adres', (j->>'enlem')::float8, (j->>'boylam')::float8,
       jsonb_build_object('guven', j->'guven', 'surum', :'surum')
FROM y
ON CONFLICT (kaynak, kaynak_id) DO UPDATE SET
  telefonlar = EXCLUDED.telefonlar, epostalar = EXCLUDED.epostalar, web = EXCLUDED.web,
  sosyal = EXCLUDED.sosyal, adres = EXCLUDED.adres, ham = EXCLUDED.ham, son_gorulme = now();
SELECT count(*) || ' kayıt · ' || count(*) FILTER (WHERE cardinality(epostalar) > 0) || ' e-postalı · '
       || count(*) FILTER (WHERE cardinality(telefonlar) > 0) || ' telefonlu · '
       || count(DISTINCT il) || ' bölge'
FROM raw.eczane_kaynak WHERE kaynak = 'OVERTURE';
COMMIT;
"""


def main():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2'; "
                "SET memory_limit='1GB'; SET threads=2;")
    surum = ot.en_yeni_surum(con)
    s3 = "%s/%s/theme=places/type=place/*" % (ot.S3_KOK, surum)
    sutunlar = {r[0] for r in con.execute(
        "DESCRIBE SELECT * FROM read_parquet('%s') LIMIT 0" % s3).fetchall()}
    kat = "taxonomy.primary" if "taxonomy" in sutunlar else "categories.primary"
    sql = SORGU.format(kat=kat, s3=s3, **TR)
    cur = con.execute(sql)
    adlar = [d[0] for d in cur.description]
    kayit = [dict(zip(adlar, r, strict=True)) for r in cur.fetchall()]
    kayit = [k for k in kayit if (k["ulke"] or "TR") == "TR"]
    print(surum, len(kayit), "eczane okundu", file=sys.stderr)
    govde = "\n".join(json.dumps(k, ensure_ascii=False, default=str).replace("\\", "\\\\")
                      for k in kayit)
    cikti = subprocess.run(PSQL + ["-v", "surum=" + surum],
                           input=YUKLE.replace("{GOVDE}", govde),
                           capture_output=True, text=True)
    if cikti.returncode:
        sys.exit(cikti.stderr)
    print([s for s in cikti.stdout.splitlines() if "kayıt" in s][-1])


if __name__ == "__main__":
    main()
