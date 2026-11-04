-- Aylık kategori bütçeleri (02.11.2026). Harcama bütün hesap başlıklarında sayılır.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_money_budget (
    owner text NOT NULL,
    category text NOT NULL CHECK (length(category) BETWEEN 1 AND 30),
    monthly_cents bigint NOT NULL CHECK (monthly_cents > 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, category)
);
REVOKE ALL ON core.jarvis_money_budget FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.jarvis_money_budget TO jarvis_web;
COMMIT;
