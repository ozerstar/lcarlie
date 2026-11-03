-- 071 geri alma: iki tur yeniden yalniz ONERI olur, uygulanmaz.
BEGIN;
UPDATE core.ai_action_type SET execution_enabled = false
 WHERE action_type IN ('META_CAMPAIGN_CHANGE', 'PRICE_CHANGE');
DELETE FROM core.ai_action_tavan WHERE action_type IN ('META_CAMPAIGN_CHANGE', 'PRICE_CHANGE');
COMMIT;
