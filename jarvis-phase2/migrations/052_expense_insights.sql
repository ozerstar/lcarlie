-- Para hareketi defteri + gider kategorisi + tek seferlik bildirim kaydı (02.11.2026).
-- Kaynak: hesap dökümü, kredi kartı ekstresi veya banka uygulaması ekran görüntüsü.
-- Sahip transferlerin de yorumlanmasını istedi: kişisel transferler dahil saklanır.
BEGIN;
ALTER TABLE core.jarvis_expense_document
    ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT '' CHECK (length(category) <= 30);
GRANT UPDATE (category) ON core.jarvis_expense_document TO jarvis_web;

CREATE TABLE IF NOT EXISTS core.jarvis_money_upload (
    owner text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 160),
    mime_type text NOT NULL CHECK (mime_type IN ('image/jpeg','image/png','image/webp','application/pdf')),
    content bytea NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 12582912),
    line_count integer NOT NULL CHECK (line_count >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, sha256)
);
REVOKE ALL ON core.jarvis_money_upload FROM PUBLIC;
GRANT SELECT, INSERT ON core.jarvis_money_upload TO jarvis_web;

CREATE TABLE IF NOT EXISTS core.jarvis_money_movement (
    movement_id text PRIMARY KEY CHECK (movement_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    source_sha256 text NOT NULL,
    account text NOT NULL CHECK (length(account) BETWEEN 1 AND 80),
    tx_date date NOT NULL,
    direction text NOT NULL CHECK (direction IN ('out','in')),
    kind text NOT NULL CHECK (kind IN ('kart','transfer','fatura','atm','banka','iade','taksit','ic_transfer','diger')),
    party text NOT NULL CHECK (length(party) BETWEEN 1 AND 160),
    party_key text NOT NULL,
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 300),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    -- "ANTHROPIC (20,00 USD) 994,10 TL": matched to the dollar invoice by this amount
    foreign_currency text CHECK (foreign_currency IN ('USD','EUR')),
    foreign_cents bigint CHECK (foreign_cents > 0),
    -- two identical rows on one day are two movements; the same row on two screenshots is one
    ordinal integer NOT NULL DEFAULT 1 CHECK (ordinal >= 1),
    category text NOT NULL DEFAULT '' CHECK (length(category) <= 30),
    scope text NOT NULL DEFAULT '' CHECK (scope IN ('','lemos','moy','lcarlie','kisisel')),
    receipt text NOT NULL DEFAULT 'not_needed' CHECK (receipt IN ('needed','matched','not_needed','ignored')),
    document_id text,
    manual boolean NOT NULL DEFAULT false,
    note text NOT NULL DEFAULT '' CHECK (length(note) <= 300),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((receipt = 'matched') = (document_id IS NOT NULL)),
    FOREIGN KEY (owner, source_sha256) REFERENCES core.jarvis_money_upload(owner, sha256),
    FOREIGN KEY (owner, document_id) REFERENCES core.jarvis_expense_document(owner, document_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_money_movement_once
    ON core.jarvis_money_movement(owner, account, tx_date, direction, amount_cents, party_key, ordinal);
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_money_movement_document_once
    ON core.jarvis_money_movement(owner, document_id) WHERE document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS jarvis_money_movement_day ON core.jarvis_money_movement(owner, tx_date DESC);
CREATE INDEX IF NOT EXISTS jarvis_money_movement_party ON core.jarvis_money_movement(owner, party_key);
REVOKE ALL ON core.jarvis_money_movement FROM PUBLIC;
GRANT SELECT, INSERT ON core.jarvis_money_movement TO jarvis_web;
GRANT UPDATE (category, scope, receipt, document_id, manual, note, updated_at)
    ON core.jarvis_money_movement TO jarvis_web;

-- Owner's answers per person/shop, and monthly agreements (Sinem Ağca 12.000 TL from 2026-09).
CREATE TABLE IF NOT EXISTS core.jarvis_money_rule (
    owner text NOT NULL,
    party_key text NOT NULL CHECK (length(party_key) BETWEEN 1 AND 24),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 80),
    category text NOT NULL DEFAULT '' CHECK (length(category) <= 30),
    scope text NOT NULL DEFAULT '' CHECK (scope IN ('','lemos','moy','lcarlie','kisisel')),
    receipt_policy text NOT NULL DEFAULT '' CHECK (receipt_policy IN ('','not_needed')),
    monthly_cents bigint CHECK (monthly_cents > 0),
    start_month date,
    end_month date,
    opening_cents bigint NOT NULL DEFAULT 0,
    note text NOT NULL DEFAULT '' CHECK (length(note) <= 300),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, party_key),
    CHECK (end_month IS NULL OR start_month IS NULL OR end_month >= start_month)
);
REVOKE ALL ON core.jarvis_money_rule FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON core.jarvis_money_rule TO jarvis_web;

CREATE TABLE IF NOT EXISTS core.jarvis_expense_notice (
    owner text NOT NULL,
    notice_key text NOT NULL CHECK (length(notice_key) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, notice_key)
);
REVOKE ALL ON core.jarvis_expense_notice FROM PUBLIC;
GRANT SELECT, INSERT ON core.jarvis_expense_notice TO jarvis_web;
COMMIT;
