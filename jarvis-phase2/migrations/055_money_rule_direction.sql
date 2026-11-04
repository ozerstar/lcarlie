-- Kişi kuralı yöne göre (02.11.2026): "Macit'e giden = kişisel/diğer" kuralı, Macit'ten GELEN paraya
-- da uygulanıyor ve gelen 42.200 TL'yi gider kategorisiyle etiketliyordu.
BEGIN;
ALTER TABLE core.jarvis_money_rule
    ADD COLUMN IF NOT EXISTS direction text NOT NULL DEFAULT 'out' CHECK (direction IN ('out','in'));
UPDATE core.jarvis_money_rule SET direction='in'
    WHERE category IN ('gelir','aile_gelen','tahsilat','iade','borc_donus','diger_gelen');
ALTER TABLE core.jarvis_money_rule DROP CONSTRAINT IF EXISTS jarvis_money_rule_pkey;
ALTER TABLE core.jarvis_money_rule ADD PRIMARY KEY (owner, party_key, direction);
-- onarım: bir gider kuralıyla etiketlenmiş GELEN hareketler (elle değiştirilmemişler) yeniden sorulur
UPDATE core.jarvis_money_movement SET category='', updated_at=clock_timestamp()
    WHERE direction='in' AND NOT manual
    AND category NOT IN ('','ic_transfer','gelir','aile_gelen','tahsilat','iade','borc_donus','diger_gelen');
COMMIT;
