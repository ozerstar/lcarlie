-- Alt kalem (02.11.2026): "ofisin içinde kira, muhasebe ödemesi gibi ödemeler var ama seçemedim".
BEGIN;
ALTER TABLE core.jarvis_money_movement
    ADD COLUMN IF NOT EXISTS subcategory text NOT NULL DEFAULT '' CHECK (length(subcategory) <= 40);
GRANT UPDATE (subcategory) ON core.jarvis_money_movement TO jarvis_web;
ALTER TABLE core.jarvis_money_rule
    ADD COLUMN IF NOT EXISTS subcategory text NOT NULL DEFAULT '' CHECK (length(subcategory) <= 40);
COMMIT;
