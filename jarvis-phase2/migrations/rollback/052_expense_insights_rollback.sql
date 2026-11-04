-- 052 geri alma: para hareketleri, kurallar ve bildirim kaydı silinir, kategori sütunu düşer.
BEGIN;
DROP TABLE IF EXISTS core.jarvis_money_movement;
DROP TABLE IF EXISTS core.jarvis_money_upload;
DROP TABLE IF EXISTS core.jarvis_money_rule;
DROP TABLE IF EXISTS core.jarvis_expense_notice;
ALTER TABLE core.jarvis_expense_document DROP COLUMN IF EXISTS category;
COMMIT;
