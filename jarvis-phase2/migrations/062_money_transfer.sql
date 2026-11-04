-- Şirket ↔ şahsi aktarım: aynı para iki defterde (sahip, 02.11.2026: "MOY'a Enpara'dan giriyor").
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_money_transfer (
    owner        text NOT NULL,
    company_id   text NOT NULL,
    personal_id  text NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    status       text NOT NULL DEFAULT 'auto' CHECK (status IN ('auto','ok','rejected')),
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, company_id, personal_id)
);
CREATE INDEX IF NOT EXISTS jarvis_money_transfer_personal ON core.jarvis_money_transfer (owner, personal_id);
GRANT SELECT, INSERT ON core.jarvis_money_transfer TO jarvis_web;
GRANT UPDATE (status, updated_at) ON core.jarvis_money_transfer TO jarvis_web;
COMMIT;
