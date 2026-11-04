BEGIN;
REVOKE SELECT ON raw.wix_order, raw.wix_order_item, raw.trendyol_urun FROM jarvis_web;
REVOKE USAGE ON SCHEMA raw FROM jarvis_web;
DROP TABLE IF EXISTS core.jarvis_channel_sale;
ALTER TABLE core.jarvis_invoice DROP COLUMN IF EXISTS order_no;
COMMIT;
