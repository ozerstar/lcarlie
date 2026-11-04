-- MOY e-faturaları (Uyumsoft, salt okuma) ve ödemeleriyle eşleşmesi (sahip, 02.11.2026: "kur ve canlıya al").
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_invoice (
    owner         text NOT NULL,
    document_id   text NOT NULL CHECK (document_id ~ '^[0-9A-Za-z-]{8,64}$'),  -- ETTN
    book          text NOT NULL CHECK (book IN ('kisisel','lemos','moy')),
    box           text NOT NULL CHECK (box IN ('in','out')),
    scenario      text NOT NULL DEFAULT '',
    number        text NOT NULL DEFAULT '',
    issue_date    date NOT NULL,
    party         text NOT NULL DEFAULT '',
    party_key     text NOT NULL DEFAULT '',
    party_vkn     text NOT NULL DEFAULT '',
    payable_cents bigint NOT NULL,
    tax_cents     bigint NOT NULL DEFAULT 0,
    currency      text NOT NULL DEFAULT 'TRY',
    status        text NOT NULL DEFAULT '',
    category      text NOT NULL DEFAULT '',
    ubl           bytea,
    fetched_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, document_id)
);
CREATE INDEX IF NOT EXISTS jarvis_invoice_day ON core.jarvis_invoice (owner, book, issue_date DESC);

CREATE TABLE IF NOT EXISTS core.jarvis_invoice_line (
    owner       text NOT NULL,
    document_id text NOT NULL,
    line_no     integer NOT NULL,
    name        text NOT NULL DEFAULT '',
    quantity    numeric NOT NULL DEFAULT 0,
    unit        text NOT NULL DEFAULT '',
    net_cents   bigint NOT NULL DEFAULT 0,
    vat_percent numeric,
    vat_cents   bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, document_id, line_no),
    FOREIGN KEY (owner, document_id) REFERENCES core.jarvis_invoice (owner, document_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS core.jarvis_invoice_payment (
    owner       text NOT NULL,
    document_id text NOT NULL,
    movement_id text NOT NULL,
    status      text NOT NULL DEFAULT 'auto' CHECK (status IN ('auto','ok','rejected')),
    created_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, document_id, movement_id),
    FOREIGN KEY (owner, document_id) REFERENCES core.jarvis_invoice (owner, document_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS jarvis_invoice_payment_movement ON core.jarvis_invoice_payment (owner, movement_id);

-- web: okur, eşleşmeyi onaylar/reddeder, kategori düzeltir. Faturayı yalnız root'un iş betiği yazar.
GRANT SELECT ON core.jarvis_invoice, core.jarvis_invoice_line, core.jarvis_invoice_payment TO jarvis_web;
GRANT UPDATE (category) ON core.jarvis_invoice TO jarvis_web;
GRANT INSERT, UPDATE (status, updated_at) ON core.jarvis_invoice_payment TO jarvis_web;
-- iş betiği de jarvis_web rolüyle bağlanıyor (JARVIS_DB_PASSWORD_FILE=jarvis-web-db.pass)
GRANT INSERT, UPDATE ON core.jarvis_invoice, core.jarvis_invoice_line TO jarvis_web;
COMMIT;
