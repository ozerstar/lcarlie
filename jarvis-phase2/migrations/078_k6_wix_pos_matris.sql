-- 078 · K6 (sahip 15.11.2026 "bagla"): Wix POS %5 platform fiyat matrisine yansir.
--
-- Once: core.platform wix komisyon_yuzde = 0 -> Wix marji POS'u dusmuyordu (~%5 iyimser).
-- Sonra: Wix'in komisyonu TEK KAYNAKTAN okunur: core.maliyet_bileseni POS_KOMISYONU
--   (sahip beyani 14.10.2026, kanit BUSINESS_INPUT). core.platform.komisyon_yuzde'ye
--   KOPYA yazilmaz (iki yer ayrisirdi - bag. haritasi K6).
-- 🔴 Beyan "havale ve kapida odemeye uygulanmaz" diyor; matris tek fiyat satiri oldugu
--    icin muhafazakar davranir (hepsi kartla odenmis gibi). Gercek siparis bazinda
--    yalniz PayTR'a uygulanir: mart.satis_kalem_tum / mart.siparis_ekonomi.
-- Geri alma: rollback/078_k6_wix_pos_matris.sql (bir onceki tanim).
BEGIN;
CREATE OR REPLACE VIEW mart.platform_fiyat_matrisi AS
 WITH acik AS (
         SELECT urun_platform_fiyat.urun_id,
            urun_platform_fiyat.platform_kod,
            urun_platform_fiyat.fiyat,
            urun_platform_fiyat.yontem,
            urun_platform_fiyat.gerekce,
            urun_platform_fiyat.gecerli_baslangic,
            urun_platform_fiyat.kaydeden
           FROM core.urun_platform_fiyat
          WHERE urun_platform_fiyat.gecerli_bitis IS NULL
        ), maliyet AS (
         SELECT urun_maliyet.urun_id,
            urun_maliyet.maliyet,
            urun_maliyet.kaynak,
            urun_maliyet.gerekce
           FROM core.urun_maliyet
          WHERE urun_maliyet.gecerli_bitis IS NULL
        ), temel AS (
         SELECT g.urun_id,
            g.urun_adi,
            p.kod AS platform_kod,
            p.ad AS platform_adi,
            p.aktif AS platform_aktif,
            p.yazma_izni,
            p.kdv_yuzde,
            p.kargo_bedeli,
            COALESCE(k.komisyon_yuzde,
                     CASE WHEN p.kod = 'wix' THEN (SELECT m.deger FROM core.maliyet_bileseni m
                                                     WHERE m.bilesen = 'POS_KOMISYONU' AND m.gecerli_bitis IS NULL
                                                     ORDER BY m.gecerli_baslangic DESC LIMIT 1)
                          ELSE p.komisyon_yuzde END) AS komisyon_yuzde,
            k.komisyon_yuzde IS NOT NULL AS komisyon_istisnasi,
            g.musteriye_soylenecek_fiyat AS referans_fiyat,
            g.fiyat_kaynagi AS referans_kaynagi,
            a.fiyat AS platform_fiyati,
            a.yontem,
            a.gerekce,
            a.gecerli_baslangic,
            a.kaydeden,
            COALESCE(a.fiyat, g.musteriye_soylenecek_fiyat) AS gecerli_fiyat,
            m.maliyet AS birim_maliyet,
            m.kaynak AS maliyet_kaynagi,
            m.gerekce AS maliyet_gerekcesi
           FROM mart.fiyat_gercegi g
             CROSS JOIN core.platform p
             LEFT JOIN acik a ON a.urun_id = g.urun_id AND a.platform_kod = p.kod
             LEFT JOIN core.urun_platform_komisyon k ON k.urun_id = g.urun_id AND k.platform_kod = p.kod
             LEFT JOIN maliyet m ON m.urun_id = g.urun_id
        )
 SELECT urun_id,
    urun_adi,
    platform_kod,
    platform_adi,
    platform_aktif,
    yazma_izni,
    kdv_yuzde,
    kargo_bedeli,
    komisyon_yuzde,
    komisyon_istisnasi,
    referans_fiyat,
    referans_kaynagi,
    platform_fiyati,
    yontem,
    gerekce,
    gecerli_baslangic,
    kaydeden,
    gecerli_fiyat,
    birim_maliyet,
    maliyet_kaynagi,
    maliyet_gerekcesi,
        CASE
            WHEN platform_fiyati IS NULL THEN 'REFERANS'::text
            WHEN referans_fiyat IS NULL THEN 'REFERANS_YOK'::text
            WHEN platform_fiyati > referans_fiyat THEN 'YUKSEK'::text
            WHEN platform_fiyati < referans_fiyat THEN 'DUSUK'::text
            ELSE 'AYNI'::text
        END AS fark_durumu,
        CASE
            WHEN platform_fiyati IS NULL OR referans_fiyat IS NULL OR referans_fiyat = 0::numeric THEN NULL::numeric
            ELSE round((platform_fiyati / referans_fiyat - 1::numeric) * 100::numeric, 1)
        END AS fark_yuzde,
    round(gecerli_fiyat * komisyon_yuzde / 100.0, 2) AS komisyon_tutari,
    round((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0), 2) AS net_kdvsiz,
    round((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0) - birim_maliyet, 2) AS marj,
        CASE
            WHEN gecerli_fiyat IS NULL OR komisyon_yuzde IS NULL OR birim_maliyet IS NULL THEN NULL::numeric
            ELSE round(100.0 * ((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0) - birim_maliyet) / NULLIF((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0), 0::numeric), 1)
        END AS marj_yuzde,
        CASE
            WHEN gecerli_fiyat IS NULL THEN 'FIYAT_YOK'::text
            WHEN komisyon_yuzde IS NULL THEN 'KOMISYON_YOK'::text
            WHEN birim_maliyet IS NULL THEN 'MALIYET_YOK'::text
            WHEN ((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0) - birim_maliyet) < 0::numeric THEN 'ZARAR'::text
            WHEN (100.0 * ((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0) - birim_maliyet) / NULLIF((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0), 0::numeric)) < 10::numeric THEN 'KRITIK'::text
            WHEN (100.0 * ((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0) - birim_maliyet) / NULLIF((gecerli_fiyat * (1::numeric - komisyon_yuzde / 100.0) - kargo_bedeli) / (1::numeric + kdv_yuzde / 100.0), 0::numeric)) < 25::numeric THEN 'DUSUK'::text
            ELSE 'OK'::text
        END AS marj_uyari
   FROM temel t;
;
COMMENT ON VIEW mart.platform_fiyat_matrisi IS 'Urun x platform fiyat/komisyon/marj. Wix komisyonu = core.maliyet_bileseni POS_KOMISYONU (078, K6 15.11.2026; muhafazakar: tum siparis kartli varsayilir).';
COMMIT;
