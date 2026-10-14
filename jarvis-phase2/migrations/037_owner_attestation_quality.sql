-- Read current owner attestations instead of stale hardcoded quantities.
-- No stock/cost values are seeded by this migration.
BEGIN;
CREATE OR REPLACE VIEW mart.ai_data_quality_gate AS
SELECT 'REAL_STOCK'::text AS check_name,
 EXISTS(SELECT 1 FROM core.ai_human_data_attestation WHERE attestation_type='STOCK_CONFIRMATION' AND active) AS passed,
 (SELECT format('%s urun / her biri %s / OWNER_ATTESTED',value_json->>'product_count',value_json->>'stock_each') FROM core.ai_human_data_attestation WHERE attestation_type='STOCK_CONFIRMATION' AND scope='ALL_PRODUCTS' AND active) AS detail,clock_timestamp() AS checked_at
UNION ALL SELECT 'PRODUCT_COGS',EXISTS(SELECT 1 FROM core.ai_human_data_attestation WHERE attestation_type='COGS_CONFIRMATION' AND active),
 (SELECT format('%s urun / her biri %s TL / OWNER_ATTESTED',value_json->>'product_count',value_json->>'cogs_each_try') FROM core.ai_human_data_attestation WHERE attestation_type='COGS_CONFIRMATION' AND scope='ALL_PRODUCTS' AND active),clock_timestamp()
UNION ALL SELECT 'OFFLINE_PAYMENT_VERIFICATION',EXISTS(SELECT 1 FROM core.ai_human_data_attestation WHERE attestation_type='OFFLINE_PAYMENT_CONFIRMATION' AND active AND (value_json->>'collected')::boolean),
 (SELECT format('%s siparis / %s TL / COLLECTED',value_json->>'order_count',value_json->>'total_try') FROM core.ai_human_data_attestation WHERE attestation_type='OFFLINE_PAYMENT_CONFIRMATION' AND active LIMIT 1),clock_timestamp();
COMMIT;
