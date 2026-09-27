-- =====================================================================
-- 028 GERİ ALMA
--
-- ⚠️ TABLO DÜŞÜRÜLÜR ama veri kaybı değildir: tek doğruluk kaynağı
--    `varliklar/kutu-gercegi/*.json` dosyalarıdır ve `inci-yukle.py`
--    tabloyu oradan yeniden kurar. Tablo bir kopyadır, orijinal değil.
-- =====================================================================
\set ON_ERROR_STOP on

BEGIN;
DROP VIEW  IF EXISTS mart.urun_inci_durum;
DROP TABLE IF EXISTS core.urun_inci;
COMMIT;
