-- BAYİ FİYATI: satış fiyat listesinin tam hali
--
-- İlk sürümde tek bir `bayi_fiyat` sütunu vardı; sahibin listesi TEK FİYAT
-- DEĞİL, kademeli: PSF, %30 ve %40 iskonto (KDV hariç/dahil ayrı) ve
-- Trendyol fiyatı. Tek sütuna sıkıştırmak, sahada "hangi fiyat?" sorusunu
-- cevapsız bırakırdı.
--
-- 🔴 ÇELİŞKİLİ SATIR SAHAYA FİYAT VERMEZ. Listenin kendi iskonto mantığı
-- (PSF×0,70 / PSF×0,60 / PSF×1,15) her satıra uygulandı; dört hücre
-- tutmadı (MENTHALIS üç hücre, KINESIS+ bir hücre; en büyüğü %18,2).
-- Bu satırlarda basılı değer SAKLANIR ama `celiskili` işaretlenir ve
-- panel fiyat yerine "teyit gerekiyor" yazar. Yanlış fiyat vermek,
-- fiyat verememekten pahalıdır.

BEGIN;

ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS psf numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS isk30_haric numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS isk30_dahil numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS isk40_haric numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS isk40_dahil numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS trendyol numeric(12, 2);
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS barkod text;
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS celiskili boolean NOT NULL DEFAULT false;
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS celiski_notu text;
ALTER TABLE core.urun_bayi_fiyat ADD COLUMN IF NOT EXISTS kaynak text;

-- Eski tek-fiyat sütunu artık zorunlu değil: liste kademeli geliyor.
ALTER TABLE core.urun_bayi_fiyat ALTER COLUMN bayi_fiyat DROP NOT NULL;
ALTER TABLE core.urun_bayi_fiyat DROP CONSTRAINT IF EXISTS urun_bayi_fiyat_bayi_fiyat_check;

-- Çelişkili satır açıklamasız işaretlenemez: "neden" olmadan bir uyarı,
-- okuyanı bilgilendirmez, yalnız huzursuz eder.
ALTER TABLE core.urun_bayi_fiyat DROP CONSTRAINT IF EXISTS bayi_celiski_ck;
ALTER TABLE core.urun_bayi_fiyat ADD CONSTRAINT bayi_celiski_ck
  CHECK (NOT celiskili OR coalesce(btrim(celiski_notu), '') <> '');

-- Kampanya koşulları: fiyatın yanında konuşulan şeyler. Sahada
-- "70.000 TL üzeri stand desteği var" demek, fiyat kırmadan değer katar.
CREATE TABLE IF NOT EXISTS core.bayi_kampanya (
  sira      smallint PRIMARY KEY,
  baslik    text NOT NULL,
  kosul     text,
  gecerli   boolean NOT NULL DEFAULT true,
  kaynak    text,
  girildi   timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW mart.bayi_fiyat_gecerli AS
SELECT b.urun_slug, b.barkod, b.psf,
       -- Çelişkili satırda kademe fiyatı GÖSTERİLMEZ.
       CASE WHEN b.celiskili THEN NULL ELSE b.isk30_haric END AS isk30_haric,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk30_dahil END AS isk30_dahil,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk40_haric END AS isk40_haric,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk40_dahil END AS isk40_dahil,
       CASE WHEN b.celiskili THEN NULL ELSE b.trendyol END AS trendyol,
       b.celiskili, b.celiski_notu, b.kaynak, b.girildi
  FROM core.urun_bayi_fiyat b;

COMMIT;
