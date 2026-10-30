-- Geri alma: günlük paket satırları SİLİNMEZ (onaylı olabilirler);
-- yalnız kısıtlar eski hâline döner. Önce STORY satırı varsa durur.
BEGIN;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM core.ig_gonderi_plani WHERE bicim = 'STORY') THEN
    RAISE EXCEPTION 'STORY satırı var; önce onları elle taşıyın';
  END IF;
END $$;
DROP INDEX IF EXISTS core.ig_plan_gun_sira_uq;
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_gunluk_ck;
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_uzman_ck;
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_kaynak_ck;
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_bicim_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_bicim_ck
  CHECK (bicim IN ('REELS', 'KARUSEL', 'TEK_GORSEL'));
DELETE FROM core.model_kademe WHERE is_anahtari = 'ig_gunluk';
COMMIT;
