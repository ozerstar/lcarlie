-- Sahibin elle seçtiği fatura kategorisi tahmin değişince ezilmesin.
BEGIN;
ALTER TABLE core.jarvis_invoice ADD COLUMN IF NOT EXISTS category_set boolean NOT NULL DEFAULT false;
GRANT UPDATE (category, category_set) ON core.jarvis_invoice TO jarvis_web;
COMMIT;
