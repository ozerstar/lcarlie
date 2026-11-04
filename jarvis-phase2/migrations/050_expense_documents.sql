-- Receipts are shared; invoices are filed by company. Originals remain intact.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_expense_document (
    document_id text PRIMARY KEY CHECK (document_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('receipt','invoice')),
    company text NOT NULL CHECK (company IN ('common','lemos','moy','unknown')),
    origin text NOT NULL CHECK (origin IN ('upload','gmail')),
    source_message_id text NOT NULL DEFAULT '',
    source_attachment_id text NOT NULL DEFAULT '',
    filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 160),
    mime_type text NOT NULL CHECK (mime_type IN ('image/jpeg','image/png','image/webp','application/pdf')),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    content bytea NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 12582912),
    document_date date,
    supplier text NOT NULL DEFAULT '',
    buyer text NOT NULL DEFAULT '',
    invoice_number text NOT NULL DEFAULT '',
    currency text NOT NULL DEFAULT 'TRY' CHECK (currency ~ '^[A-Z]{3}$'),
    gross_cents bigint CHECK (gross_cents >= 0),
    tax_cents bigint CHECK (tax_cents >= 0),
    note text NOT NULL DEFAULT '',
    extracted jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded','review','ready','excluded')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((kind='receipt' AND company='common') OR (kind='invoice' AND company<>'common'))
);
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_expense_owner_sha
    ON core.jarvis_expense_document(owner,sha256);
CREATE UNIQUE INDEX IF NOT EXISTS jarvis_expense_gmail_source
    ON core.jarvis_expense_document(owner,source_message_id,source_attachment_id)
    WHERE origin='gmail';
CREATE INDEX IF NOT EXISTS jarvis_expense_month
    ON core.jarvis_expense_document(owner,created_at DESC);
REVOKE ALL ON core.jarvis_expense_document FROM PUBLIC;
GRANT SELECT,INSERT ON core.jarvis_expense_document TO jarvis_web;
GRANT UPDATE (kind,company,document_date,supplier,buyer,invoice_number,currency,
              gross_cents,tax_cents,note,extracted,status,updated_at)
    ON core.jarvis_expense_document TO jarvis_web;

CREATE TABLE IF NOT EXISTS core.jarvis_expense_dispatch (
    owner text NOT NULL,
    period text NOT NULL CHECK (period ~ '^[0-9]{4}-[0-9]{2}$'),
    part integer NOT NULL CHECK (part > 0),
    status text NOT NULL CHECK (status IN ('sending','sent','failed')),
    package_sha256 text NOT NULL CHECK (package_sha256 ~ '^[0-9a-f]{64}$'),
    document_count integer NOT NULL CHECK (document_count >= 0),
    sent_at timestamptz,
    error text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(owner,period,part)
);
REVOKE ALL ON core.jarvis_expense_dispatch FROM PUBLIC;
GRANT SELECT,INSERT ON core.jarvis_expense_dispatch TO jarvis_web;
GRANT UPDATE (status,error,sent_at) ON core.jarvis_expense_dispatch TO jarvis_web;
COMMIT;
