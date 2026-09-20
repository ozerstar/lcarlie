-- 013 — mart.urun_alan_karsilastirma: değiştirilebilir her alan, iki platformda
--
-- AMAÇ
-- Panelde "e-ticaret" başlığı altında bir ürünün DEĞİŞTİRİLEBİLİR tüm
-- bilgilerine tek yerden erişmek. Bu görünüm ürün × alan şeklinde
-- düzleştirir: her satır bir alanın Wix'teki ve Trendyol'daki değeridir.
--
-- NEDEN DÜZLEŞTİRİLDİ
-- Panel ızgarası satır bekler. Alanları sütun yapmak, platform veya alan
-- eklendiğinde şemayı değiştirmeyi gerektirirdi; satır yapmak gerektirmez.
--
-- YAZILABİLİRLİK BİLGİSİ DE TAŞINIR
-- `yazilabilir` sütunu o alanın ilgili platformda API ile değiştirilip
-- değiştirilemeyeceğini söyler. Kaynak: Lonca UpdateContentInput /
-- UpdateVariantInput / PriceInventoryUpdate tipleri ve Wix ürün kaydı.
-- Panel, değiştirilemeyen bir alanı düzenlenebilir göstermemeli.
--
-- AÇIKLAMA KARŞILAŞTIRMASI
-- İki tarafta da HTML. Birebir eşleşme neredeyse hiç olmaz; bu yüzden
-- uzunluk da taşınır ve `durum` FARKLI der. Bu DOĞRUDUR: iki platformda
-- iki ayrı metin var ve bunu bilmek gerekir.

\set ON_ERROR_STOP on
BEGIN;

-- Dizi sayimi TIP KONTROLLU olmali. Wix'te media bir dizi DEGIL, icinde
-- items dizisi olan bir NESNE; ciplak jsonb_array_length "cannot get
-- array length of a non-array" ile patliyordu. Kuru calistirma yakaladi.
CREATE OR REPLACE FUNCTION mart.dizi_uzunluk(j jsonb) RETURNS int
LANGUAGE sql IMMUTABLE AS $fn$
  SELECT CASE WHEN jsonb_typeof(j) = 'array'
              THEN jsonb_array_length(j) ELSE 0 END;
$fn$;
COMMENT ON FUNCTION mart.dizi_uzunluk(jsonb) IS
  'Dizi degilse 0 doner. Ciplak jsonb_array_length nesneye carpinca hata verir.';

CREATE OR REPLACE VIEW mart.urun_alan_karsilastirma AS
WITH w AS (
  SELECT urun_id,
         ad,
         ham ->> 'sku'                                   AS sku,
         ham ->> 'name'                                  AS w_ad,
         ham ->> 'description'                           AS w_aciklama,
         (ham #>> '{priceData,discountedPrice}')::numeric AS w_satis,
         (ham #>> '{priceData,price}')::numeric           AS w_liste,
         (ham #>> '{stock,quantity}')                    AS w_stok,
         ham ->> 'visible'                               AS w_yayinda,
         ham ->> 'ribbon'                                AS w_rozet,
         ham #>> '{seoData,tags}'                        AS w_seo,
         ham ->> 'slug'                                  AS w_slug,
         mart.dizi_uzunluk(ham #> '{media,items}') AS w_gorsel
  FROM raw.wix_urun
),
t AS (
  SELECT barkod,
         content_id,
         ham ->> 'title'                                  AS t_ad,
         ham ->> 'description'                            AS t_aciklama,
         (ham #>> '{fiyat,salePrice}')::numeric           AS t_satis,
         (ham #>> '{fiyat,listPrice}')::numeric           AS t_liste,
         ham #>> '{fiyat,quantity}'                       AS t_stok,
         ham #>> '{variant,onSale}'                       AS t_yayinda,
         ham #>> '{variant,vatRate}'                      AS t_kdv,
         ham #>> '{category,name}'                        AS t_kategori,
         mart.dizi_uzunluk(ham -> 'images')       AS t_gorsel,
         mart.dizi_uzunluk(ham -> 'attributes')   AS t_ozellik
  FROM raw.trendyol_urun
),
birlesik AS (
  -- w.* zaten sku ve ad tasiyor; ayrica secmek "ambiguous" hatasi verir.
  -- Kuru calistirma bunu yakaladi.
  SELECT w.*, t.*
  FROM w LEFT JOIN t ON t.barkod = w.sku
)
SELECT urun_id, ad AS urun_adi, sku, content_id, sira, alan, grup,
       wix_deger, trendyol_deger,
       wix_yazilabilir, trendyol_yazilabilir,
       CASE
         WHEN wix_deger IS NULL AND trendyol_deger IS NULL THEN 'IKISINDE_DE_YOK'
         WHEN trendyol_deger IS NULL THEN 'YALNIZ_WIX'
         WHEN wix_deger IS NULL      THEN 'YALNIZ_TRENDYOL'
         WHEN btrim(wix_deger) = btrim(trendyol_deger) THEN 'AYNI'
         ELSE 'FARKLI'
       END AS durum
FROM birlesik,
LATERAL (VALUES
  ( 1, 'Ürün adı',        'temel',   w_ad,                    t_ad,               true,  true),
  ( 2, 'Açıklama',        'temel',   w_aciklama,              t_aciklama,         true,  true),
  ( 3, 'Satış fiyatı',    'fiyat',   w_satis::text,           t_satis::text,      true,  true),
  ( 4, 'Liste fiyatı',    'fiyat',   w_liste::text,           t_liste::text,      true,  true),
  ( 5, 'Stok',            'stok',    w_stok,                  t_stok,             true,  true),
  ( 6, 'Yayında',         'durum',   w_yayinda,               t_yayinda,          true,  true),
  ( 7, 'Görsel sayısı',   'medya',   w_gorsel::text,          t_gorsel::text,     true,  true),
  ( 8, 'Barkod / SKU',    'kimlik',  sku,                     barkod,             true,  true),
  ( 9, 'KDV oranı',       'fiyat',   NULL,                    t_kdv,              false, true),
  (10, 'Kategori',        'temel',   NULL,                    t_kategori,         false, false),
  (11, 'Özellik sayısı',  'medya',   NULL,                    t_ozellik::text,    false, true),
  (12, 'Rozet',           'vitrin',  w_rozet,                 NULL,               true,  false),
  (13, 'SEO etiketleri',  'vitrin',  w_seo,                   NULL,               true,  false),
  (14, 'URL adı (slug)',  'vitrin',  w_slug,                  NULL,               true,  false)
) AS f(sira, alan, grup, wix_deger, trendyol_deger, wix_yazilabilir, trendyol_yazilabilir);

COMMENT ON VIEW mart.urun_alan_karsilastirma IS
  'Urun x alan: her degistirilebilir alanin Wix ve Trendyol degeri yan yana. '
  'yazilabilir sutunlari o alanin API ile degistirilip degistirilemeyecegini '
  'soyler -- panel degistirilemeyen alani duzenlenebilir gostermemeli. '
  'Aciklama alani iki tarafta da HTML; FARKLI cikmasi beklenen ve dogru '
  'sonuctur.';

GRANT SELECT ON mart.urun_alan_karsilastirma TO ai_reader;

COMMIT;
