-- Apply manually to the existing database after review. No sample data.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_cari_account (
    account_id text PRIMARY KEY CHECK (account_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
    name_key text NOT NULL,
    role text NOT NULL CHECK (role IN ('customer','supplier','both')),
    contact text NOT NULL DEFAULT '',
    note text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (owner,account_id), UNIQUE (owner,name_key)
);
CREATE TABLE IF NOT EXISTS core.jarvis_cari_entry (
    entry_id text PRIMARY KEY CHECK (entry_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    account_id text NOT NULL,
    request_id text NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    document_date date NOT NULL,
    payload jsonb NOT NULL,
    signed_cents bigint NOT NULL CHECK (abs(signed_cents) <= 1000000000000),
    unknown_tax boolean NOT NULL,
    reverses text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (owner,account_id,entry_id),
    UNIQUE (owner,account_id,request_id),
    UNIQUE (reverses),
    FOREIGN KEY (owner,account_id) REFERENCES core.jarvis_cari_account(owner,account_id),
    FOREIGN KEY (owner,account_id,reverses)
        REFERENCES core.jarvis_cari_entry(owner,account_id,entry_id),
    CHECK (reverses IS NULL OR reverses <> entry_id)
);
CREATE INDEX IF NOT EXISTS jarvis_cari_account_entries
    ON core.jarvis_cari_entry(owner,account_id,document_date,created_at);

-- The web role cannot overwrite or delete financial history.
REVOKE ALL ON core.jarvis_cari_account,core.jarvis_cari_entry FROM PUBLIC;
REVOKE UPDATE,DELETE,TRUNCATE ON core.jarvis_cari_account,core.jarvis_cari_entry FROM jarvis_web;
GRANT SELECT,INSERT ON core.jarvis_cari_account,core.jarvis_cari_entry TO jarvis_web;
COMMIT;
