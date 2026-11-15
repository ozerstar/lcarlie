-- 076 geri alma: izleyicinin tablolari ve gorunumleri. raw.meta_reklam /
-- raw.meta_kreatif (gunluk ETL) DOKUNULMAZ.
BEGIN;
DROP VIEW IF EXISTS mart.meta_kreatif_ozet;
DROP VIEW IF EXISTS mart.meta_kreatif_gunluk;
DROP VIEW IF EXISTS mart.meta_yerlesim_gunluk;
DROP TABLE IF EXISTS raw.meta_izleme_uyari;
DROP TABLE IF EXISTS raw.meta_izleme_kosu;
DROP TABLE IF EXISTS raw.meta_izleme_yerlesim;
DROP TABLE IF EXISTS raw.meta_izleme_reklam;
COMMIT;
