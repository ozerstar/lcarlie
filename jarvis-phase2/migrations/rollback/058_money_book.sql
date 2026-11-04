BEGIN;
REVOKE DELETE ON core.jarvis_money_movement FROM jarvis_web;
DROP INDEX IF EXISTS core.jarvis_money_movement_book;
ALTER TABLE core.jarvis_money_upload DROP COLUMN IF EXISTS book;
ALTER TABLE core.jarvis_money_movement DROP COLUMN IF EXISTS book;
COMMIT;
