-- 031 GERİ ALMA. Eklenen sütunları ve görünümü düşürür.
-- 🔴 Veri kaybı: şablon şartnameleri (ölçü, kural, versiyon) silinir.
BEGIN;
DROP VIEW IF EXISTS mart.tasarim_sablon_kutuk;
ALTER TABLE core.tasarim_sablon
  DROP CONSTRAINT IF EXISTS tasarim_sablon_hazir_tasarimli,
  DROP CONSTRAINT IF EXISTS tasarim_sablon_durum_izinli;
ALTER TABLE core.tasarim_sablon
  DROP COLUMN IF EXISTS sablon_kodu, DROP COLUMN IF EXISTS kategori,
  DROP COLUMN IF EXISTS platform,    DROP COLUMN IF EXISTS bicim,
  DROP COLUMN IF EXISTS en_mm,       DROP COLUMN IF EXISTS boy_mm,
  DROP COLUMN IF EXISTS dpi,         DROP COLUMN IF EXISTS beklenen_alanlar,
  DROP COLUMN IF EXISTS marka_kurallari, DROP COLUMN IF EXISTS mevzuat_kurallari,
  DROP COLUMN IF EXISTS surum,       DROP COLUMN IF EXISTS durum,
  DROP COLUMN IF EXISTS motor,       DROP COLUMN IF EXISTS onay_zorunlu,
  DROP COLUMN IF EXISTS faz;
COMMIT;
