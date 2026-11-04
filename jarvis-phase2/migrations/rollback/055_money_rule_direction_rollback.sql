-- 055 geri alma: gelen yönlü kurallar silinir, anahtar kişi başına teke döner.
BEGIN;
DELETE FROM core.jarvis_money_rule WHERE direction='in';
ALTER TABLE core.jarvis_money_rule DROP CONSTRAINT IF EXISTS jarvis_money_rule_pkey;
ALTER TABLE core.jarvis_money_rule ADD PRIMARY KEY (owner, party_key);
ALTER TABLE core.jarvis_money_rule DROP COLUMN IF EXISTS direction;
COMMIT;
