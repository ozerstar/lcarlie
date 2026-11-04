BEGIN;
ALTER TABLE core.jarvis_invoice DROP COLUMN IF EXISTS category_set;
COMMIT;
