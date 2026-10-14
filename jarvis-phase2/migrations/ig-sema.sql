-- INSTAGRAM GÖNDERİ PLANI
--
-- NEDEN TABLO: gönderi fikri üretilip sohbette kalırsa kaybolur. Burada
-- her paket DURUM taşır (ÖNERİ → ONAYLANDI → YAYINLANDI / REDDEDİLDİ) ve
-- DAYANAK taşır: hangi ölçüme bakılarak önerildi.
--
-- 🔴 CAPTION İÇİNDEKİ HER ÜRÜN CÜMLESİ AYIKLANMIŞTIR, UYDURULMAMIŞ.
-- Kaynak yayındaki Wix metninin mevzuat denetçisinden temiz geçen
-- cümleleridir -- kataloğun kullandığı havuzun aynısı. Kanca ve yapı
-- yazılır; İDDİA yazılmaz.
--
-- İTİRAZ ayrı sütun: "kreatif tarafıyla tartışılsın" isteği, her pakete
-- karşı argümanı ve ona karşı ölçülmüş kanıtı yazmak demek. Boş itiraz
-- tartışılmamış demektir ve o paket onaya çıkmaz.

BEGIN;

CREATE TABLE IF NOT EXISTS core.ig_gonderi_plani (
  plan_id     bigserial PRIMARY KEY,
  urun_slug   text NOT NULL,
  amac        text NOT NULL,          -- SATIS | TANITIM | B2B
  bicim       text NOT NULL,          -- REELS | KARUSEL | TEK_GORSEL
  kanca       text NOT NULL,
  caption     text NOT NULL,
  hashtagler  text[] NOT NULL DEFAULT '{}',
  gorsel_brief text NOT NULL,
  cta         text,
  cta_gerekce text,
  dayanak     text NOT NULL,          -- hangi ÖLÇÜME dayanıyor
  itiraz      text,                   -- kreatif tarafın karşı argümanı
  itiraza_yanit text,
  denetim     text NOT NULL,          -- TEMIZ | BULGULU
  denetim_notu text,
  durum       text NOT NULL DEFAULT 'ONERI',
  uretim_at   timestamptz NOT NULL DEFAULT now(),
  karar_at    timestamptz,
  karar_veren text
);

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_durum_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_durum_ck
  CHECK (durum IN ('ONERI', 'ONAYLANDI', 'REDDEDILDI', 'YAYINLANDI'));

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_amac_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_amac_ck
  CHECK (amac IN ('SATIS', 'TANITIM', 'B2B'));

ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_bicim_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_bicim_ck
  CHECK (bicim IN ('REELS', 'KARUSEL', 'TEK_GORSEL'));

-- 🔴 DENETİMDEN BULGULU GEÇEN PAKET ONAYLANAMAZ. Kuralı koda değil
-- şemaya yazıyoruz: panel ile veritabanı ayrı karar verirse biri
-- diğerini sessizce kabul eder.
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_onay_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_onay_ck
  CHECK (durum NOT IN ('ONAYLANDI', 'YAYINLANDI') OR denetim = 'TEMIZ');

-- İtirazı yanıtlanmamış paket de onaya çıkmaz: "tartışılsın" isteğinin
-- şemadaki karşılığı bu.
ALTER TABLE core.ig_gonderi_plani DROP CONSTRAINT IF EXISTS ig_plan_itiraz_ck;
ALTER TABLE core.ig_gonderi_plani ADD CONSTRAINT ig_plan_itiraz_ck
  CHECK (durum NOT IN ('ONAYLANDI', 'YAYINLANDI')
         OR coalesce(btrim(itiraza_yanit), '') <> '');

CREATE INDEX IF NOT EXISTS ig_plan_durum_idx ON core.ig_gonderi_plani (durum, uretim_at DESC);
CREATE INDEX IF NOT EXISTS ig_plan_urun_idx  ON core.ig_gonderi_plani (urun_slug);

COMMIT;
