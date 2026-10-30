-- GÜNLÜK INSTAGRAM PAKETİ (30.10.2026)
--
-- Sahip: "günlük kendi kendine çalışsın, başına uzman ver, günlük bir ürün
-- için kapsamlı 4-5 içerik çıkartsın."
--
-- AYRI TABLO DEĞİL, AYNI TABLO. Günlük paket de bir gönderi paketidir ve
-- haftalık paketle AYNI onay kapılarından geçmeli: bulgulu paket
-- onaylanamaz, itirazı yanıtlanmamış paket onaylanamaz. Ayrı tablo, bu iki
-- kısıtın ikinci bir kopyası demekti -- biri gevşerse diğeri fark etmez.
--
-- Geri alma: migrations/rollback/ig-gunluk-sema_ROLLBACK.sql

BEGIN;

ALTER TABLE core.ig_gonderi_plani
  ADD COLUMN IF NOT EXISTS kaynak        text NOT NULL DEFAULT 'HAFTALIK',
  ADD COLUMN IF NOT EXISTS gun           date,
  ADD COLUMN IF NOT EXISTS sira          smallint,
  ADD COLUMN IF NOT EXISTS ekran_kancasi text,
  ADD COLUMN IF NOT EXISTS kanca_formulu text,
  -- Kanca puanı ELEME içindir, izlenme tahmini değil (kaynağın kendi
  -- ölçümü: iki iyi kancayı ayırmada AUC 0,56).
  ADD COLUMN IF NOT EXISTS kanca_puani   smallint,
  -- {"senaryo": [{sn, goruntu, ses, ekran}], "kareler": [{no, baslik, metin, etkilesim}]}
  ADD COLUMN IF NOT EXISTS senaryo       jsonb,
  ADD COLUMN IF NOT EXISTS uzman         text,
  ADD COLUMN IF NOT EXISTS uzman_karari  text,
  ADD COLUMN IF NOT EXISTS uzman_notu    text,
  ADD COLUMN IF NOT EXISTS bicim_notu    text,
  ADD COLUMN IF NOT EXISTS modeller      text;

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_kaynak_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_kaynak_ck
  CHECK (kaynak IN ('HAFTALIK', 'GUNLUK'));

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_bicim_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_bicim_ck
  CHECK (bicim IN ('REELS', 'KARUSEL', 'TEK_GORSEL', 'STORY'));

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_uzman_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_uzman_ck
  CHECK (uzman_karari IS NULL OR uzman_karari IN ('GECER', 'DUZELT', 'INCELENMEDI'));

-- Günlük paket gün + sıra ile tekil: zamanlayıcı iki kez koşarsa aynı
-- günün ikinci paketi yazılmaz.
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_gunluk_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_gunluk_ck
  CHECK (kaynak <> 'GUNLUK' OR (gun IS NOT NULL AND sira BETWEEN 1 AND 5));
CREATE UNIQUE INDEX IF NOT EXISTS ig_plan_gun_sira_uq
  ON core.ig_gonderi_plani (gun, sira) WHERE kaynak = 'GUNLUK';

-- Model kademesi: metin yayına gidecek materyale dönüşüyor.
INSERT INTO core.model_kademe (is_anahtari, kademe, gerekce, risk, atayan) VALUES
  ('ig_gunluk', 'muhakeme',
   'Günlük Instagram paketi: yazılan kanca ve caption onaydan sonra yayına gidiyor; uzman incelemesi de karar besliyor.',
   'MUSTERIYE', 'sahip-30.10.2026')
ON CONFLICT (is_anahtari) DO NOTHING;

-- Company Memory (ai_reader) yalnız karar özetini okur: İçerik Direktörü,
-- sohbet ve ekip üyeleri için. Caption/görsel sütunları BİLEREK kapalı.
GRANT SELECT (plan_id, uretim_at, kaynak, gun, sira, urun_slug, bicim, kanca,
              kanca_formulu, kanca_puani, denetim, uzman_karari, durum)
  ON core.ig_gonderi_plani TO ai_reader;

COMMIT;
