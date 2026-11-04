-- 056 geri alma: aile → kişisel, kısıt eski haline.
BEGIN;
UPDATE core.jarvis_money_movement SET scope='kisisel' WHERE scope='aile';
UPDATE core.jarvis_money_rule SET scope='kisisel' WHERE scope='aile';
ALTER TABLE core.jarvis_money_movement DROP CONSTRAINT IF EXISTS jarvis_money_movement_scope_check;
ALTER TABLE core.jarvis_money_movement ADD CONSTRAINT jarvis_money_movement_scope_check
    CHECK (scope IN ('','lemos','moy','lcarlie','kisisel'));
ALTER TABLE core.jarvis_money_rule DROP CONSTRAINT IF EXISTS jarvis_money_rule_scope_check;
ALTER TABLE core.jarvis_money_rule ADD CONSTRAINT jarvis_money_rule_scope_check
    CHECK (scope IN ('','lemos','moy','lcarlie','kisisel'));
COMMIT;
