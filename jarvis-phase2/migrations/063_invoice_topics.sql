-- Fatura kalemlerinin konusu ve hangi işe ait olduğu (sahip, 02.11.2026: Lemos ve L'CARLIÉ
-- aynı şirket ama iki ayrı iş; içeriğe göre ayıkla, ortak gideri pay et).
BEGIN;
ALTER TABLE core.jarvis_invoice_line ADD COLUMN IF NOT EXISTS theme text NOT NULL DEFAULT '';
ALTER TABLE core.jarvis_invoice_line ADD COLUMN IF NOT EXISTS business text NOT NULL DEFAULT '';
ALTER TABLE core.jarvis_invoice_line ADD COLUMN IF NOT EXISTS product text NOT NULL DEFAULT '';
-- kalemleri okunamayan faturalar tedarikçiye göre tek parça sınıflanır
ALTER TABLE core.jarvis_invoice ADD COLUMN IF NOT EXISTS theme text NOT NULL DEFAULT '';
ALTER TABLE core.jarvis_invoice ADD COLUMN IF NOT EXISTS business text NOT NULL DEFAULT '';
GRANT UPDATE (theme, business, product) ON core.jarvis_invoice_line TO jarvis_web;
GRANT UPDATE (theme, business) ON core.jarvis_invoice TO jarvis_web;
COMMIT;
