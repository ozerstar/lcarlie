-- GEO F1 rollback. Run only after a verified backup and after checking
-- that no GEO observations need to be retained.
BEGIN;

DROP TABLE IF EXISTS core.geo_karar_kapsami;
DROP TABLE IF EXISTS core.geo_gap;
DROP TABLE IF EXISTS core.geo_entity_conflict;
DROP TABLE IF EXISTS core.geo_citation_mention;
DROP TABLE IF EXISTS core.geo_citation;
DROP TABLE IF EXISTS core.geo_source;
DROP TABLE IF EXISTS core.geo_mention;
DROP TABLE IF EXISTS core.geo_observation;
DROP FUNCTION IF EXISTS core.geo_obs_immutable();
DROP TABLE IF EXISTS core.geo_query;
DROP TABLE IF EXISTS core.geo_alias;
DROP TABLE IF EXISTS core.geo_brand;
DROP TABLE IF EXISTS raw.geo_response;

ALTER TABLE core.sayfa_olcum
  DROP COLUMN IF EXISTS robots_durumu,
  DROP COLUMN IF EXISTS sitemap_var,
  DROP COLUMN IF EXISTS jsonld_turleri,
  DROP COLUMN IF EXISTS hreflang_sayisi,
  DROP COLUMN IF EXISTS yonlendirme_zinciri;

COMMIT;
