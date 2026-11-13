BEGIN;
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS kopya_of bigint REFERENCES core.eczane_hedef(id);
CREATE OR REPLACE FUNCTION pg_temp.nrm(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT regexp_replace(translate(lower(replace(replace(coalesce(t,''),'İ','i'),'I','ı')),
         'çğıöşüâî','cgiosuai'), '(\s|[^a-z0-9])', '', 'g') $$;
-- Aynı ilde aynı ad: telefonsuz kopya, telefonlu kayda bağlanır. Ad ilde iki
-- telefonlu kayıtla geçiyorsa (iki ayrı eczane olabilir) DOKUNULMAZ.
WITH telli AS (
  SELECT il, pg_temp.nrm(eczane) n, min(id) id FROM core.eczane_hedef
  WHERE telefon IS NOT NULL GROUP BY 1,2 HAVING count(*) = 1)
UPDATE core.eczane_hedef h SET durum = 'GECERSIZ', kopya_of = t.id, guncellendi = now()
FROM telli t
WHERE h.telefon IS NULL AND h.il = t.il AND pg_temp.nrm(h.eczane) = t.n
  AND h.durum = 'YENI' AND h.id <> t.id;
SELECT count(*) FILTER (WHERE kopya_of IS NOT NULL) kopya,
       count(*) FILTER (WHERE durum <> 'GECERSIZ') gecerli_hedef,
       count(*) FILTER (WHERE durum <> 'GECERSIZ' AND telefon IS NULL) telefonsuz
FROM core.eczane_hedef;
COMMIT;
