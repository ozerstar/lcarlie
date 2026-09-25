-- BAYİ FİYATI 2: fiyat çelişkisi ile barkod çelişkisi AYRI ŞEYLER
--
-- 🔴 TEK BAYRAK İKİ İŞİ BİRDEN GÖRÜYORDU. `celiskili` hem "bu satırın
-- fiyatı tutmuyor" hem "bu satırın barkodu tutmuyor" için kullanılmıştı.
-- Sonuç ölçüldü: OPTYWAVE'in FİYATLARI doğruydu, yalnız barkodu
-- şüpheliydi; ama mart.bayi_fiyat_gecerli onun da kademe fiyatlarını
-- NULL döndürüyordu. Yani sahada barkod belirsizliği yüzünden fiyat
-- söylenemiyordu. Barkod belirsizliği depoyu ilgilendirir, fiyatı değil.
--
-- Bundan sonra:
--   celiskili        → YALNIZ fiyat çelişkisi. Kademe fiyatını gizler.
--   barkod_celiskili → barkod şüphesi. Fiyatı GİZLEMEZ, uyarı olarak durur.

BEGIN;

ALTER TABLE core.urun_bayi_fiyat
  ADD COLUMN IF NOT EXISTS barkod_celiskili boolean NOT NULL DEFAULT false;
ALTER TABLE core.urun_bayi_fiyat
  ADD COLUMN IF NOT EXISTS barkod_notu text;

-- Aynı kural burada da: gerekçesiz uyarı, okuyanı yalnız huzursuz eder.
ALTER TABLE core.urun_bayi_fiyat DROP CONSTRAINT IF EXISTS bayi_barkod_celiski_ck;
ALTER TABLE core.urun_bayi_fiyat ADD CONSTRAINT bayi_barkod_celiski_ck
  CHECK (NOT barkod_celiskili OR coalesce(btrim(barkod_notu), '') <> '');

-- Fiyat nereden geliyor: basılı listeden mi, hesaptan mı? Sahada
-- "bu fiyat kesin mi" sorusu sorulduğunda cevabı olsun.
ALTER TABLE core.urun_bayi_fiyat
  ADD COLUMN IF NOT EXISTS psf_kaynagi text;

-- Sütun SIRASI değişiyor (psf_kaynagi ekleniyor): CREATE OR REPLACE bunu
-- yapamaz, önce düşürmek gerekir. Başka nesne bu görünüme bağlı değil --
-- pg_depend ile bakıldı, bağımlı görünüm yok.
DROP VIEW IF EXISTS mart.bayi_fiyat_gecerli;

CREATE VIEW mart.bayi_fiyat_gecerli AS
SELECT b.urun_slug, b.barkod, b.psf, b.psf_kaynagi,
       -- Kademe fiyatını YALNIZ fiyat çelişkisi gizler.
       CASE WHEN b.celiskili THEN NULL ELSE b.isk30_haric END AS isk30_haric,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk30_dahil END AS isk30_dahil,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk40_haric END AS isk40_haric,
       CASE WHEN b.celiskili THEN NULL ELSE b.isk40_dahil END AS isk40_dahil,
       CASE WHEN b.celiskili THEN NULL ELSE b.trendyol END AS trendyol,
       b.celiskili, b.celiski_notu,
       b.barkod_celiskili, b.barkod_notu,
       b.kaynak, b.girildi
  FROM core.urun_bayi_fiyat b;

COMMIT;
