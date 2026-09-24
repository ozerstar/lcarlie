-- 034 geri alma. DIKKAT: toplanan lead verisi SILINIR.
BEGIN;
DROP VIEW IF EXISTS mart.lead_ozet;
DROP FUNCTION IF EXISTS core.lead_saklama_temizligi();
DROP TABLE IF EXISTS core.lead;
DROP TABLE IF EXISTS raw.lead_osm;
COMMIT;
