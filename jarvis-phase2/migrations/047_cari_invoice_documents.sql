-- Invoice evidence and richer counterparty identity. Financial entries remain append-only.
BEGIN;
ALTER TABLE core.jarvis_cari_account
    ADD COLUMN IF NOT EXISTS tax_id text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS address text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS email text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS phone text NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_cari_owner_tax_id
    ON core.jarvis_cari_account(owner,tax_id) WHERE tax_id <> '';
GRANT UPDATE (tax_id,address,email,phone) ON core.jarvis_cari_account TO jarvis_web;

CREATE TABLE IF NOT EXISTS core.jarvis_cari_document (
    document_id text PRIMARY KEY CHECK (document_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    account_id text,
    entry_id text,
    source text NOT NULL CHECK (source IN ('invoice','attachment')),
    filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 160),
    mime_type text NOT NULL CHECK (mime_type IN ('image/jpeg','image/png','image/webp','application/pdf')),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    content bytea NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 8388608),
    status text NOT NULL CHECK (status IN ('uploaded','review','posted','rejected')),
    extracted jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (entry_id IS NULL OR account_id IS NOT NULL),
    FOREIGN KEY (owner,account_id) REFERENCES core.jarvis_cari_account(owner,account_id),
    FOREIGN KEY (owner,account_id,entry_id)
        REFERENCES core.jarvis_cari_entry(owner,account_id,entry_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_cari_invoice_hash
    ON core.jarvis_cari_document(owner,sha256) WHERE source='invoice';
CREATE INDEX IF NOT EXISTS jarvis_cari_document_lookup
    ON core.jarvis_cari_document(owner,account_id,created_at DESC);
CREATE INDEX IF NOT EXISTS jarvis_cari_entry_applies_to
    ON core.jarvis_cari_entry(owner,account_id,((payload->>'applies_to')))
    WHERE payload ? 'applies_to';
REVOKE ALL ON core.jarvis_cari_document FROM PUBLIC;
REVOKE DELETE,TRUNCATE ON core.jarvis_cari_document FROM jarvis_web;
GRANT SELECT,INSERT ON core.jarvis_cari_document TO jarvis_web;
GRANT UPDATE (account_id,entry_id,status,extracted,updated_at)
    ON core.jarvis_cari_document TO jarvis_web;
COMMIT;
