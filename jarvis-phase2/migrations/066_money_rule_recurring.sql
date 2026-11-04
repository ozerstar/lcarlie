-- Düzenli ödemeler sahibin beyanıyla (sahip, 02.11.2026): "bunlar düzenli ödeme değil" -> recurring=false;
-- aylık anlaşmada çalışma olmayan ay borç yazmaz (Mina Dilara: "geçen ay çalışma olmadı bu ay olacak").
BEGIN;
ALTER TABLE core.jarvis_money_rule ADD COLUMN IF NOT EXISTS recurring boolean;
ALTER TABLE core.jarvis_money_rule ADD COLUMN IF NOT EXISTS skip_months date[] NOT NULL DEFAULT '{}';
COMMIT;
