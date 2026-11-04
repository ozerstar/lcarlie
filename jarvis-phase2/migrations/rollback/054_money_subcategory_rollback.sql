BEGIN;
ALTER TABLE core.jarvis_money_movement DROP COLUMN IF EXISTS subcategory;
ALTER TABLE core.jarvis_money_rule DROP COLUMN IF EXISTS subcategory;
COMMIT;
