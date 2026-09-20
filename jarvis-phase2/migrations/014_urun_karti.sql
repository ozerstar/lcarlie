-- 014 — mart.urun_karti: bir ürün hakkında bilinen her şey, tek satırda
--
-- NEDEN
-- "HYDRAVIE nedir" sorusuna yalnız fiyat dönüyordu. Oysa sistemde çok
-- daha fazlası var: hangi platformlarda yayında, stok ne, kaç satmış,
-- marjı ne, kaç görseli var, iki platform arasında kaç alan farklı.
-- Hepsi ayrı görünümlerde duruyordu ve hiçbiri tek soruda birleşmiyordu.
--
-- TEK SATIR, ÇÜNKÜ CEVAP TEK CÜMLE OLACAK
-- Sohbet katmanı bunu okuyup insan diline çevirir. Satır başına bir ürün
-- olması, o çevirinin JOIN yapmasını gerektirmez.
--
-- EKSİK VERİ GİZLENMEZ
-- Satmamış ürünün satış alanları NULL kalır, 0 YAZILMAZ: "hiç satmadı"
-- ile "veri yok" ayrı şeylerdir ve cevap bu ayrımı koruyabilmeli.

\set ON_ERROR_STOP on
BEGIN;

CREATE OR REPLACE VIEW mart.urun_karti AS
WITH satis AS (
  SELECT urun_id, adet, ciro, ciro_net, brut_marj, brut_marj_yuzde, kalem
  FROM mart.urun_karlilik
),
fark AS (
  SELECT urun_id,
         count(*) FILTER (WHERE durum = 'FARKLI')          AS farkli_alan,
         count(*) FILTER (WHERE durum = 'YALNIZ_WIX')      AS yalniz_wix,
         count(*) FILTER (WHERE durum = 'YALNIZ_TRENDYOL') AS yalniz_trendyol
  FROM mart.urun_alan_karsilastirma GROUP BY urun_id
),
platform AS (
  SELECT urun_id,
         count(*) FILTER (WHERE platform_fiyati IS NOT NULL)  AS platform_sayisi,
         min(marj_yuzde) FILTER (WHERE marj_yuzde IS NOT NULL) AS en_dusuk_marj,
         string_agg(platform_adi || ': ' || to_char(gecerli_fiyat, 'FM999G999D00') || ' TL',
                    ' · ' ORDER BY platform_kod)
           FILTER (WHERE gecerli_fiyat IS NOT NULL)          AS fiyat_ozeti
  FROM mart.platform_fiyat_matrisi
  WHERE platform_aktif
  GROUP BY urun_id
)
SELECT
  w.urun_id,
  w.ad                                        AS urun_adi,
  w.ham ->> 'sku'                             AS sku,
  -- Aciklamadan HTML temizlenir; cevap metni olarak kullanilabilsin.
  btrim(regexp_replace(COALESCE(w.ham ->> 'description', ''),
                       '<[^>]*>', ' ', 'g'))  AS aciklama_duz,
  (w.ham #>> '{priceData,discountedPrice}')::numeric AS wix_satis,
  (w.ham #>> '{priceData,price}')::numeric           AS wix_liste,
  (w.ham #>> '{stock,quantity}')::int                AS wix_stok,
  (w.ham ->> 'visible') = 'true'                     AS wix_yayinda,
  mart.dizi_uzunluk(w.ham #> '{media,items}')        AS wix_gorsel,
  t.barkod IS NOT NULL                               AS trendyolda_var,
  (t.ham #>> '{fiyat,salePrice}')::numeric           AS trendyol_satis,
  (t.ham #>> '{fiyat,quantity}')::int                AS trendyol_stok,
  m.maliyet                                          AS birim_maliyet,
  m.kaynak                                           AS maliyet_kaynagi,
  s.adet                                             AS satilan_adet,
  s.ciro                                             AS ciro,
  s.brut_marj_yuzde                                  AS satis_marj_yuzde,
  p.platform_sayisi,
  p.fiyat_ozeti,
  p.en_dusuk_marj,
  f.farkli_alan,
  f.yalniz_wix,
  f.yalniz_trendyol
FROM raw.wix_urun w
LEFT JOIN raw.trendyol_urun t ON t.barkod = w.ham ->> 'sku'
LEFT JOIN (SELECT urun_id, maliyet, kaynak FROM core.urun_maliyet
           WHERE gecerli_bitis IS NULL) m ON m.urun_id = w.urun_id
LEFT JOIN satis s    ON s.urun_id = w.urun_id
LEFT JOIN fark f     ON f.urun_id = w.urun_id
LEFT JOIN platform p ON p.urun_id = w.urun_id;

COMMENT ON VIEW mart.urun_karti IS
  'Bir urun hakkinda bilinen her sey, tek satirda: fiyat, stok, platform, '
  'satis, marj, alan farklari. Satmamis urunun satis alanlari NULL kalir '
  '-- "hic satmadi" ile "veri yok" ayri seylerdir.';

GRANT SELECT ON mart.urun_karti TO ai_reader;

COMMIT;
