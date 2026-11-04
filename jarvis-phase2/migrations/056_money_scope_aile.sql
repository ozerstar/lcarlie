-- "Kişisel harcama ve aileyi de ayır" (sahip, 02.11.2026): yeni hesap başlığı "aile".
BEGIN;
ALTER TABLE core.jarvis_money_movement DROP CONSTRAINT IF EXISTS jarvis_money_movement_scope_check;
ALTER TABLE core.jarvis_money_movement ADD CONSTRAINT jarvis_money_movement_scope_check
    CHECK (scope IN ('','lemos','moy','lcarlie','kisisel','aile'));
ALTER TABLE core.jarvis_money_rule DROP CONSTRAINT IF EXISTS jarvis_money_rule_scope_check;
ALTER TABLE core.jarvis_money_rule ADD CONSTRAINT jarvis_money_rule_scope_check
    CHECK (scope IN ('','lemos','moy','lcarlie','kisisel','aile'));
-- what is already labelled as family moves to the family heading
UPDATE core.jarvis_money_rule SET scope='aile', updated_at=clock_timestamp()
    WHERE category IN ('aile','aile_gelen') AND scope IN ('','kisisel');
UPDATE core.jarvis_money_movement SET scope='aile', updated_at=clock_timestamp()
    WHERE category IN ('aile','aile_gelen') AND scope IN ('','kisisel');
COMMIT;
