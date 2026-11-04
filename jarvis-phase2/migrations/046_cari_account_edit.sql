-- Account details and product cover preferences are mutable; ledger entries stay immutable.
BEGIN;
ALTER TABLE core.jarvis_cari_account
    ADD COLUMN IF NOT EXISTS covers jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE core.jarvis_cari_account
    DROP CONSTRAINT IF EXISTS jarvis_cari_account_covers_object;
ALTER TABLE core.jarvis_cari_account
    ADD CONSTRAINT jarvis_cari_account_covers_object CHECK (jsonb_typeof(covers) = 'object');
GRANT UPDATE (name,name_key,role,contact,note,covers)
    ON core.jarvis_cari_account TO jarvis_web;
COMMIT;
