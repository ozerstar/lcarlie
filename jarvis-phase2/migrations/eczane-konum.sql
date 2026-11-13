-- Eczane konumu (randevu rotası için). Kaynak önceliği: odanın kaydı > Google > Overture.
BEGIN;
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS enlem double precision;
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS boylam double precision;
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS konum_kaynak text;
WITH k AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, enlem, boylam, kaynak
  FROM raw.eczane_kaynak
  WHERE hedef_id IS NOT NULL AND enlem IS NOT NULL AND boylam IS NOT NULL
  ORDER BY hedef_id, CASE kaynak WHEN 'AEO_NOBET' THEN 1 WHEN 'AEO_TEMSILCI' THEN 2
                                  WHEN 'GMAPS' THEN 3 WHEN 'OVERTURE' THEN 4 ELSE 9 END)
UPDATE core.eczane_hedef h SET enlem = k.enlem, boylam = k.boylam, konum_kaynak = k.kaynak
FROM k WHERE h.id = k.hedef_id AND h.konum_kaynak IS DISTINCT FROM 'ELLE';
SELECT il = 'Ankara' AS ankara, count(*) hedef, count(enlem) konumlu
FROM core.eczane_hedef WHERE durum <> 'GECERSIZ' GROUP BY 1;
COMMIT;
