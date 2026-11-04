-- Şirket hesapları ayrı defter (sahip, 02.11.2026: "ayrı ayrı olsun").
BEGIN;
ALTER TABLE core.jarvis_money_movement ADD COLUMN IF NOT EXISTS book text NOT NULL DEFAULT 'kisisel'
    CHECK (book IN ('kisisel','lemos','moy'));
ALTER TABLE core.jarvis_money_upload ADD COLUMN IF NOT EXISTS book text NOT NULL DEFAULT 'kisisel'
    CHECK (book IN ('kisisel','lemos','moy'));
CREATE INDEX IF NOT EXISTS jarvis_money_movement_book ON core.jarvis_money_movement (owner, book, tx_date DESC);
-- elle eklenen hareketi silme (kod yalnız source_sha256='manual' satırı siler) — 057'de unutulmuştu
GRANT DELETE ON core.jarvis_money_movement TO jarvis_web;
COMMIT;
