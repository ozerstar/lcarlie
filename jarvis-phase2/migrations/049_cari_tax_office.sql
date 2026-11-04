-- Keep the tax office shown on invoices with the editable cari identity.
BEGIN;
ALTER TABLE core.jarvis_cari_account
    ADD COLUMN IF NOT EXISTS tax_office text NOT NULL DEFAULT '';
GRANT UPDATE (tax_office) ON core.jarvis_cari_account TO jarvis_web;
COMMIT;
