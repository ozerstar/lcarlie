-- 029 GERİ ALMA
-- Tablo, sahibin kreatif itirazlarını ve muhatabın cevaplarını tutar.
-- Silmek, "bu görselde logo yanlıştı" kaydını silmektir; bir sonraki koşu
-- aynı hatayı tekrarlar. Önce bakın:
--   SELECT count(*) FROM core.kreatif_itiraz;
BEGIN;
DROP VIEW IF EXISTS mart.kreatif_itiraz_guncel;
DROP TRIGGER IF EXISTS kreatif_itiraz_kapatma ON core.kreatif_itiraz;
DROP FUNCTION IF EXISTS core.kreatif_itiraz_kapatma_kontrol();
DROP TABLE IF EXISTS core.kreatif_itiraz;
COMMIT;
