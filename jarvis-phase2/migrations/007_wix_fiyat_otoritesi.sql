-- 007 — WIX FİYAT OTORİTESİ (sahip kararı, 20.09.2026)
--
-- KARAR
-- Özer Yıldız: "Wix otoriter olsun." Bu, mart.fiyat_gercegi görünümünün
-- bugünkü davranışının BİLEREK tersine çevrilmesidir.
--
-- ÖNCESİ
-- Görünüm, işletme beyanı yoksa fiyatı NULL bırakıyor ve şöyle diyordu:
--   "Wix vitrini ... TL gösteriyor ama bu bir GÖZLEMDİR, otorite değildir."
-- Ölçüldü (20.09.2026): 36 üründen 35'i BUSINESS_TRUTH_MISSING,
-- musteriye_soylenecek_fiyat 35'inde NULL, wix_satis ise 35'inde DOLU.
-- Sonuç: sistem hiçbir fiyat sorusunu cevaplayamıyordu ve yerel model
-- boşluğu uydurmayla dolduruyordu ("VIREON 1.200 TL").
--
-- SONRASI
-- İşletme beyanı yoksa ve Wix'te fiyat varsa, MÜŞTERİYE SÖYLENECEK FİYAT
-- Wix satış fiyatıdır.
--
-- KAYNAK İZİ KAYBEDİLMİYOR
-- Yeni sütun `fiyat_kaynagi` her satırda fiyatın nereden geldiğini söyler:
--   BEYAN  : işletme fiyat gerçeği beyan edilmiş (eski davranış)
--   WIX    : beyan yok, Wix vitrini otorite kabul edildi (yeni)
--   YOK    : ne beyan ne Wix fiyatı var
-- Böylece "bu fiyatı kim söyledi" sorusu her zaman cevaplanabilir kalır.
--
-- NE DEĞİŞMİYOR
-- PRICE_TRUTH_MISMATCH aynen duruyor. Bir üründe HEM beyan HEM Wix fiyatı
-- varsa ve tutmuyorsa sistem yine uyarır ve hiçbir tarafı otomatik
-- düzeltmez. Karar değişikliği yalnız BEYAN YOKKEN geçerli.
--
-- ÖDEME OTORİTESİ DEĞİŞMEDİ
-- CR-002.5 bulgusu yerinde: Wix, "para tahsil edildi mi" sorusunun otoritesi
-- DEĞİLDİR (siparişlerin %43'ü çevrim dışı, elle işaretlenmiş). Bu migration
-- yalnız FİYAT otoritesine dokunur, ödemeye DOKUNMAZ.
--
-- GERİ ALMA: migrations/rollback/007_wix_fiyat_otoritesi_ROLLBACK.sql

BEGIN;

CREATE OR REPLACE VIEW mart.fiyat_gercegi AS
WITH w AS (
  SELECT u.urun_id,
         u.ad,
         (u.ham #>> '{priceData,price}')::numeric           AS wix_liste,
         (u.ham #>> '{priceData,discountedPrice}')::numeric AS wix_satis,
         u.ham #>> '{visible}'                              AS wix_yayinda
  FROM raw.wix_urun u
)
SELECT
  f.urun_id,
  w.ad AS urun_adi,
  f.base_price,
  f.kampanya_fiyati,
  f.fiyat_durumu,
  f.kampanya_suresi,
  f.kampanya_kaynagi,
  f.kampanya_bitisi,
  f.karsilastirma_izni,
  w.wix_liste,
  w.wix_satis,
  w.wix_yayinda,
  CASE
    WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
    WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
    ELSE NULL::numeric
  END AS beklenen_satis,

  -- DEĞİŞTİ: beyan yoksa Wix satış fiyatı müşteriye söylenecek fiyattır.
  CASE
    WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
    WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
    ELSE w.wix_satis
  END AS musteriye_soylenecek_fiyat,

  -- DEĞİŞTİ: beyan yokken artık BUSINESS_TRUTH_MISSING değil.
  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN' AND w.wix_satis IS NOT NULL
      THEN 'WIX_AUTHORITATIVE'
    WHEN f.fiyat_durumu = 'UNKNOWN'
      THEN 'FIYAT_YOK'
    WHEN w.wix_satis IS NULL OR w.wix_liste IS NULL
      THEN 'WIX_OKUNAMADI'
    WHEN w.wix_satis IS DISTINCT FROM CASE
           WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
           ELSE f.base_price END
      OR w.wix_liste IS DISTINCT FROM f.base_price
      THEN 'PRICE_TRUTH_MISMATCH'
    ELSE 'MATCH'
  END AS durum,

  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN' AND w.wix_satis IS NOT NULL THEN
      format('%s: %s TL. Kaynak Wix vitrini. Isletme ayrica fiyat beyan '
             'etmedi; sahip karariyla (20.09.2026) Wix fiyat otoritesidir.',
             w.ad, w.wix_satis)
    WHEN f.fiyat_durumu = 'UNKNOWN' THEN
      format('%s: fiyat YOK. Ne isletme beyani ne Wix fiyati okunabildi.', w.ad)
    WHEN w.wix_satis IS DISTINCT FROM CASE
           WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
           ELSE f.base_price END
      OR w.wix_liste IS DISTINCT FROM f.base_price THEN
      format('PRICE_TRUTH_MISMATCH (%s). Isletme: base %s, %s fiyati %s. '
             'Wix vitrini: liste %s, satis %s. SISTEM HICBIR TARAFI OTOMATIK '
             'DUZELTMEZ - iki kaynak da doluysa insan karari gerekir.',
             w.ad, f.base_price, f.fiyat_durumu, f.kampanya_fiyati,
             w.wix_liste, w.wix_satis)
    ELSE format('MATCH (%s): isletme gercegi ile Wix vitrini ortusuyor.', w.ad)
  END AS aciklama,

  -- YENİ: fiyatın kaynağı her zaman görünür kalsın.
  CASE
    WHEN f.fiyat_durumu IN ('CAMPAIGN', 'NORMAL') THEN 'BEYAN'
    WHEN w.wix_satis IS NOT NULL                  THEN 'WIX'
    ELSE 'YOK'
  END AS fiyat_kaynagi

FROM core.urun_fiyat_gercegi f
JOIN w ON w.urun_id = f.urun_id;

COMMENT ON VIEW mart.fiyat_gercegi IS
  'Urun fiyati. Sahip karari 20.09.2026: isletme beyani yoksa Wix fiyat '
  'otoritesidir. fiyat_kaynagi sutunu BEYAN/WIX/YOK ayrimini korur. '
  'ODEME otoritesi DEGISMEDI -- Wix "tahsil edildi" otoritesi degildir.';

COMMIT;
