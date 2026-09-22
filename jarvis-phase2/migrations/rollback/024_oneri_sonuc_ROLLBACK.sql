-- 024 GERİ ALMA. Görünüm düşer, core.ai_action_proposal kapalı kalmaya
-- devam eder (zaten hiç açılmadı).
BEGIN;
REVOKE SELECT ON mart.ai_oneri_sonuc FROM ai_reader;
DROP VIEW IF EXISTS mart.ai_oneri_sonuc;
COMMIT;
