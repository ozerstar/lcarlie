-- 021 geri alma. Sırayla: görünüm, sonra tablolar (bağımlılık yönünde).
\set ON_ERROR_STOP on
BEGIN;
DROP VIEW IF EXISTS mart.satis_kohort;
DROP TABLE IF EXISTS lcarlie.satis_cevap;
DROP TABLE IF EXISTS lcarlie.satis_yaklasim;
COMMIT;
