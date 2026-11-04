-- Elle eklenen hareket (source_sha256='manual') hiç kaydedilemiyordu: 052'deki yabancı anahtar her satır için
-- core.jarvis_money_upload'da bir dosya arıyor, 'manual' ise 64 haneli sha256 kuralına uymadığı için orada
-- hiç olamaz (sahip, 02.11.2026: "düzelt"). Banka satırları dosyaya bağlı kalır; elle satırın dosyası yoktur.
BEGIN;
ALTER TABLE core.jarvis_money_movement
    ADD COLUMN IF NOT EXISTS upload_sha256 text
    GENERATED ALWAYS AS (NULLIF(source_sha256, 'manual')) STORED;
ALTER TABLE core.jarvis_money_movement DROP CONSTRAINT IF EXISTS jarvis_money_movement_owner_source_sha256_fkey;
ALTER TABLE core.jarvis_money_movement DROP CONSTRAINT IF EXISTS jarvis_money_movement_owner_upload_sha256_fkey;
ALTER TABLE core.jarvis_money_movement
    ADD CONSTRAINT jarvis_money_movement_owner_upload_sha256_fkey
    FOREIGN KEY (owner, upload_sha256) REFERENCES core.jarvis_money_upload(owner, sha256);
COMMIT;
