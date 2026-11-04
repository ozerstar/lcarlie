BEGIN;
UPDATE core.jarvis_money_movement SET category='gelir' WHERE category='gelir_destegi';
UPDATE core.jarvis_money_rule SET category='gelir' WHERE category='gelir_destegi';
DROP TABLE IF EXISTS core.jarvis_money_link;
COMMIT;
