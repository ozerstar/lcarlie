-- Editable account drafts do not affect the immutable financial ledger.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_cari_draft (
    draft_id text PRIMARY KEY CHECK (draft_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    account_id text NOT NULL,
    body jsonb NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted')),
    posted_entry_id text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (owner,account_id,draft_id),
    FOREIGN KEY (owner,account_id) REFERENCES core.jarvis_cari_account(owner,account_id),
    FOREIGN KEY (owner,account_id,posted_entry_id)
        REFERENCES core.jarvis_cari_entry(owner,account_id,entry_id),
    CHECK ((status='draft' AND posted_entry_id IS NULL) OR
           (status='posted' AND posted_entry_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS jarvis_cari_draft_open
    ON core.jarvis_cari_draft(owner,account_id,created_at DESC) WHERE status='draft';
REVOKE ALL ON core.jarvis_cari_draft FROM PUBLIC;
REVOKE DELETE,TRUNCATE ON core.jarvis_cari_draft FROM jarvis_web;
GRANT SELECT,INSERT ON core.jarvis_cari_draft TO jarvis_web;
GRANT UPDATE (body,status,posted_entry_id,updated_at)
    ON core.jarvis_cari_draft TO jarvis_web;
COMMIT;
