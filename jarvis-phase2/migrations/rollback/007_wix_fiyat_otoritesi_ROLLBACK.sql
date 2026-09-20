-- 007 GERİ ALMA — Wix fiyat otoritesi kararını iptal eder.
--
-- Görünümü 20.09.2026 öncesine döndürür: işletme beyanı yoksa fiyat NULL
-- kalır, durum BUSINESS_TRUTH_MISSING olur, Wix yalnız gözlem sayılır.
-- `fiyat_kaynagi` sütunu kaldırılır (CREATE OR REPLACE sütun düşüremez,
-- bu yüzden görünüm DROP edilip yeniden kurulur).

BEGIN;

DROP VIEW mart.fiyat_gercegi;

CREATE VIEW mart.fiyat_gercegi AS
WITH w AS (
  SELECT u.urun_id,
         u.ad,
         (u.ham #>> '{priceData,price}')::numeric           AS wix_liste,
         (u.ham #>> '{priceData,discountedPrice}')::numeric AS wix_satis,
         u.ham #>> '{visible}'                              AS wix_yayinda
  FROM raw.wix_urun u
)
SELECT
  f.urun_id, w.ad AS urun_adi, f.base_price, f.kampanya_fiyati,
  f.fiyat_durumu, f.kampanya_suresi, f.kampanya_kaynagi, f.kampanya_bitisi,
  f.karsilastirma_izni, w.wix_liste, w.wix_satis, w.wix_yayinda,
  CASE WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
       WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
       ELSE NULL::numeric END AS beklenen_satis,
  CASE WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
       WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
       ELSE NULL::numeric END AS musteriye_soylenecek_fiyat,
  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN' THEN 'BUSINESS_TRUTH_MISSING'
    WHEN w.wix_satis IS NULL OR w.wix_liste IS NULL THEN 'WIX_OKUNAMADI'
    WHEN w.wix_satis IS DISTINCT FROM CASE
           WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
           ELSE f.base_price END
      OR w.wix_liste IS DISTINCT FROM f.base_price THEN 'PRICE_TRUTH_MISMATCH'
    ELSE 'MATCH'
  END AS durum,
  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN' THEN
      format('%s: isletme fiyat gercegi BEYAN EDILMEDI. Wix vitrini %s TL '
             'gosteriyor ama bu bir GOZLEMDIR, otorite degildir. Musteriye '
             'fiyat soylenecekse once base price ve kampanya durumu beyan '
             'edilmeli.', w.ad, w.wix_satis)
    WHEN w.wix_satis IS DISTINCT FROM CASE
           WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
           ELSE f.base_price END
      OR w.wix_liste IS DISTINCT FROM f.base_price THEN
      format('PRICE_TRUTH_MISMATCH (%s). Isletme: base %s, %s fiyati %s. '
             'Wix vitrini: liste %s, satis %s. SISTEM HICBIR TARAFI OTOMATIK '
             'DUZELTMEZ - Wix otorite DEGILDIR. Insan karari gerekir.',
             w.ad, f.base_price, f.fiyat_durumu, f.kampanya_fiyati,
             w.wix_liste, w.wix_satis)
    ELSE format('MATCH (%s): isletme gercegi ile Wix vitrini ortusuyor.', w.ad)
  END AS aciklama
FROM core.urun_fiyat_gercegi f
JOIN w ON w.urun_id = f.urun_id;

COMMIT;
