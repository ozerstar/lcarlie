#!/usr/bin/env python3
"""Ankara Eczacı Odası kaynakları -> raw.eczane_kaynak -> core.eczane_hedef.

Kullanım:  aeo-ice.py <aeo-nobet.jsonl> <aeo-ilan.jsonl> <aeo-temsilci.json>

  AEO_NOBET     odanın nöbet servisi: ad, ilçe, adres, telefon, koordinat.
                Son nöbet tarihi = eczane AÇIK (odanın kendi kaydı).
  AEO_ILAN      İlan Panosu: eczacıların kendi yazdığı CEP numarası ve e-posta.
                Metinden eczane adı ("… ECZANESİ") çıkarılıp eşlenir.
  AEO_TEMSILCI  bölge temsilcileri: eczacı adı + eczanesi (kanaat önderi).
"""
import json
import re
import subprocess
import sys

PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
        "-v", "ON_ERROR_STOP=1", "-At"]


def tel10(t):
    d = re.sub(r"\D", "", t or "")
    return d[-10:] if len(d) >= 10 else ""


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read().splitlines()


def nobet(yol):
    son = {}
    for s in _oku(yol):
        k = json.loads(s)
        anahtar = k["telefon"] or k["ad"]
        if anahtar not in son or k["tarih"] > son[anahtar]["tarih"]:
            son[anahtar] = k
    for anahtar, k in son.items():
        yield {"kaynak": "AEO_NOBET", "kaynak_id": anahtar, "ad": k["ad"], "ilce": k["ilce"],
               "adres": k["adres"], "telefonlar": [k["telefon"]] if k["telefon"] else [],
               "epostalar": [], "enlem": k["enlem"], "boylam": k["boylam"],
               "ham": {"son_nobet": k["tarih"]}}


ECZ_ADI = re.compile(r"([A-ZÇĞİÖŞÜ0-9][\wÇĞİÖŞÜçğıöşü.&'-]+(?:\s+[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü.&'-]+)?)"
                     r"\s+(?:ECZANES[İI]|Eczanesi|eczanesi)")


def ilan(yol):
    for s in _oku(yol):
        k = json.loads(s)
        if not k["teller"] and not k["epostalar"]:
            continue
        adlar = [a for a in ECZ_ADI.findall(k["metin"]) if a.lower() not in ("ankara", "bir", "yeni")]
        yield {"kaynak": "AEO_ILAN", "kaynak_id": k["url"], "ad": adlar[0] + " ECZANESİ" if adlar else k["baslik"],
               "ilce": "", "adres": "", "telefonlar": k["teller"], "epostalar": k["epostalar"],
               "enlem": None, "boylam": None,
               "ham": {"tarih": k["tarih"], "baslik": k["baslik"], "eczane_adi_metinde": bool(adlar),
                       "metin": k["metin"][:800]}}


def temsilci(yol):
    with open(yol, encoding="utf-8") as f:
        bolgeler = json.load(f)
    for b in bolgeler:
        for k in b["veri"] if isinstance(b["veri"], list) else []:
            e = k.get("eczane") or {}
            yield {"kaynak": "AEO_TEMSILCI", "kaynak_id": f'{k.get("adi")} {k.get("soyadi")}',
                   "ad": (e.get("adi") or "") + " ECZANESİ", "ilce": "", "adres": e.get("adres") or "",
                   "telefonlar": [tel10(e.get("telefon"))] if tel10(e.get("telefon")) else [],
                   "epostalar": [], "enlem": e.get("lat"), "boylam": e.get("lng"),
                   "ham": {"eczaci": f'{k.get("unvan", "")} {k.get("adi")} {k.get("soyadi")}'.strip(),
                           "bolge": b["bolge"], "gorev": (k.get("bolge") or {}).get("gorev")}}


YUKLE = r"""
BEGIN;
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS etiketler text[] NOT NULL DEFAULT '{}';
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS son_nobet date;
CREATE TEMP TABLE y (j jsonb);
\copy y FROM STDIN
{GOVDE}
\.
INSERT INTO raw.eczane_kaynak (kaynak, kaynak_id, il, ilce, ad, telefonlar, epostalar, adres, enlem, boylam, ham)
SELECT j->>'kaynak', j->>'kaynak_id', 'Ankara', nullif(j->>'ilce',''), j->>'ad',
       ARRAY(SELECT jsonb_array_elements_text(j->'telefonlar')),
       ARRAY(SELECT lower(jsonb_array_elements_text(j->'epostalar'))),
       nullif(j->>'adres',''), (j->>'enlem')::float8, (j->>'boylam')::float8, j->'ham'
FROM y
ON CONFLICT (kaynak, kaynak_id) DO UPDATE SET telefonlar = EXCLUDED.telefonlar,
  epostalar = EXCLUDED.epostalar, adres = EXCLUDED.adres, ham = EXCLUDED.ham, son_gorulme = now();

CREATE OR REPLACE FUNCTION pg_temp.nrm(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT regexp_replace(translate(lower(replace(replace(coalesce(t,''),'İ','i'),'I','ı')),
         'çğıöşüâî','cgiosuai'), '(eczanesi|eczane|pharmacy|ecz\.?|\s|[^a-z0-9])', '', 'g') $$;

-- 1) Telefonla (Ankara içinde, tekil numara). Kaynak tablosundaki numaralar da sayılır:
--    Google'dan gelen cep numarası ilan sahibinin numarasıyla eşleşebilir.
WITH t AS (
  SELECT tel, min(hid) hid FROM (
    SELECT right(regexp_replace(telefon,'\D','','g'),10) tel, id hid FROM core.eczane_hedef
     WHERE il='Ankara' AND durum <> 'GECERSIZ' AND telefon IS NOT NULL
    UNION
    SELECT unnest(telefonlar), hedef_id FROM raw.eczane_kaynak
     WHERE il='Ankara' AND hedef_id IS NOT NULL AND kaynak IN ('GMAPS','OVERTURE')) x
  GROUP BY tel HAVING count(DISTINCT hid) = 1)
UPDATE raw.eczane_kaynak k SET hedef_id = t.hid, eslesme = 'TELEFON'
FROM t WHERE k.kaynak LIKE 'AEO_%' AND k.hedef_id IS NULL AND t.tel = ANY (k.telefonlar);

-- 2) Adla (Ankara'da tekil ad). İlanda ad metinden çıkarıldıysa.
WITH hk AS (SELECT id, pg_temp.nrm(eczane) n FROM core.eczane_hedef WHERE il='Ankara' AND durum <> 'GECERSIZ'),
     hs AS (SELECT n FROM hk GROUP BY n HAVING count(*) = 1)
UPDATE raw.eczane_kaynak k SET hedef_id = hk.id, eslesme = 'AD'
FROM hk JOIN hs USING (n)
WHERE k.kaynak LIKE 'AEO_%' AND k.hedef_id IS NULL AND pg_temp.nrm(k.ad) = hk.n AND length(hk.n) >= 3
  AND (k.kaynak <> 'AEO_ILAN' OR (k.ham->>'eczane_adi_metinde')::bool);

-- 3) Nöbet listesinde olup hedefte olmayan = odanın kaydında AÇIK eczane -> yeni hedef
WITH yeni AS (
  INSERT INTO core.eczane_hedef (il, eczane, telefon, adres, ilce, kaynak, oncelik)
  SELECT 'Ankara', k.ad, k.telefonlar[1], k.adres, k.ilce, 'AEO_NOBET', 1
  FROM raw.eczane_kaynak k WHERE k.kaynak = 'AEO_NOBET' AND k.hedef_id IS NULL
  ON CONFLICT (il, eczane, telefon) DO NOTHING RETURNING id, eczane, telefon)
UPDATE raw.eczane_kaynak k SET hedef_id = yeni.id, eslesme = 'YENI'
FROM yeni WHERE k.kaynak = 'AEO_NOBET' AND k.hedef_id IS NULL AND k.ad = yeni.eczane
  AND k.telefonlar[1] IS NOT DISTINCT FROM yeni.telefon;

-- Odanın kaydı ilçe ve son nöbet için OTORİTE (beyan); eczacı adı temsilciden
UPDATE core.eczane_hedef h SET ilce = coalesce(k.ilce, h.ilce),
       son_nobet = greatest(h.son_nobet, (k.ham->>'son_nobet')::date), guncellendi = now()
FROM raw.eczane_kaynak k WHERE k.kaynak = 'AEO_NOBET' AND k.hedef_id = h.id;
UPDATE core.eczane_hedef h SET eczaci = coalesce(h.eczaci, k.ham->>'eczaci'),
       etiketler = (SELECT array_agg(DISTINCT e) FROM unnest(h.etiketler || ARRAY['AEO_TEMSILCI']) e),
       guncellendi = now()
FROM raw.eczane_kaynak k WHERE k.kaynak = 'AEO_TEMSILCI' AND k.hedef_id = h.id;
UPDATE core.eczane_hedef h SET
       etiketler = (SELECT array_agg(DISTINCT e) FROM unnest(h.etiketler || ARRAY['AEO_ILAN']) e)
FROM raw.eczane_kaynak k WHERE k.kaynak = 'AEO_ILAN' AND k.hedef_id = h.id;

INSERT INTO core.eczane_eposta (hedef_id, eposta, kaynak)
SELECT k.hedef_id, e, k.kaynak FROM raw.eczane_kaynak k, unnest(k.epostalar) e
WHERE k.kaynak LIKE 'AEO_%' AND k.hedef_id IS NOT NULL ON CONFLICT DO NOTHING;

SELECT kaynak || ': ' || count(*) || ' kayıt · ' || count(*) FILTER (WHERE eslesme='TELEFON') || ' tel · '
       || count(*) FILTER (WHERE eslesme='AD') || ' ad · ' || count(*) FILTER (WHERE eslesme='YENI') || ' yeni · '
       || count(*) FILTER (WHERE hedef_id IS NULL) || ' eşleşmedi'
FROM raw.eczane_kaynak WHERE kaynak LIKE 'AEO_%' GROUP BY kaynak;
COMMIT;
"""


def main():
    veri = list(nobet(sys.argv[1])) + list(ilan(sys.argv[2])) + list(temsilci(sys.argv[3]))
    veri = list({(v["kaynak"], v["kaynak_id"]): v for v in veri}.values())
    govde = "\n".join(json.dumps(v, ensure_ascii=False).replace("\\", "\\\\") for v in veri)
    c = subprocess.run(PSQL, input=YUKLE.replace("{GOVDE}", govde), capture_output=True, text=True)
    if c.returncode:
        sys.exit(c.stderr)
    print("\n".join(s for s in c.stdout.splitlines() if "kayıt" in s))


if __name__ == "__main__":
    main()
