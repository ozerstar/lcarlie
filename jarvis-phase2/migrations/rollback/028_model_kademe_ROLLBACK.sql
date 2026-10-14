-- 028 GERİ ALMA
-- Tablo, hangi işin hangi modelle yapıldığının gerekçeli kaydını tutar.
-- Silmek, o gerekçeleri silmektir. Önce bakın:
--   SELECT count(*) FROM core.model_kademe;
-- Kod tabloyu okuyamazsa gömülü varsayılana düşer, yani sistem susmaz.
BEGIN;
DROP VIEW IF EXISTS mart.model_kademe_guncel;
DROP TABLE IF EXISTS core.model_kademe;
COMMIT;
