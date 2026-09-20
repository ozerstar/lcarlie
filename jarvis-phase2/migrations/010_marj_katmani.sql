-- 010 — MARJ KATMANI (komisyon + KDV + maliyet)
--
-- NEDEN
-- Panelde toplu yüzde indirimi yapılacak. İndirimin ürünü zarara sokup
-- sokmadığı ONAYA GİTMEDEN ÖNCE görünmeli. Gerçek veriden örnek:
--   BABYSOFT  630 TL satış · 400 TL maliyet · %23,8 marj
--   Trendyol'da %20 indirim -> 504 TL, komisyon düşünce maliyetin altına iner.
--
-- KDV ÖLÇÜLDÜ, VARSAYILMADI
-- 37 siparişin tamamında kdv/toplam = %16,7 -> KDV oranı %20.
-- (CR-012'de KDV yanlış ele alınınca marj %24,6 şişik çıkmıştı.)
--
-- KOMİSYON ORANLARI BİLEREK BOŞ
-- Trendyol'da komisyon kategoriye göre %10-25 arasında değişir. Buraya
-- "ortalama %20" yazmak uydurma olurdu ve tam da bu sistemin engellemek
-- için kurulduğu şey budur. Oranlar NULL başlar; girilene kadar görünüm
-- KOMISYON_YOK der ve marj hesaplamaz.
--
-- MALİYET ZATEN YAKLAŞIK -- VE BU GİZLENMİYOR
-- core.urun_maliyet'teki 400 TL sahip beyanı ve kendi gerekçesi şöyle diyor:
-- "tum urunler icin ORTALAMA 400 TL. GERCEK URUN MALIYETI DEGIL".
-- Görünüm bunu `maliyet_kaynagi` sütununda taşır ki panel marjı kesin
-- bir sayı gibi göstermesin.
--
-- HESAP
--   komisyon_tutari = satis_fiyati * komisyon% / 100   (KDV dahil fiyat uzerinden)
--   net_kdvsiz      = (satis_fiyati - komisyon_tutari) / (1 + kdv%/100)
--   marj            = net_kdvsiz - birim_maliyet
--
-- GERİ ALMA: migrations/rollback/010_marj_katmani_ROLLBACK.sql

BEGIN;

ALTER TABLE core.platform
  ADD COLUMN IF NOT EXISTS komisyon_yuzde numeric CHECK (komisyon_yuzde >= 0 AND komisyon_yuzde < 100),
  ADD COLUMN IF NOT EXISTS kdv_yuzde      numeric NOT NULL DEFAULT 20 CHECK (kdv_yuzde >= 0),
  ADD COLUMN IF NOT EXISTS kargo_bedeli   numeric NOT NULL DEFAULT 0  CHECK (kargo_bedeli >= 0);

COMMENT ON COLUMN core.platform.komisyon_yuzde IS
  'Platform komisyonu. NULL = GIRILMEDI. Uydurma oran yazilmaz; girilene '
  'kadar marj hesaplanmaz.';
COMMENT ON COLUMN core.platform.kdv_yuzde IS
  'KDV orani. Varsayilan 20 -- 37 siparisin tamaminda olculdu (20.09.2026).';

-- Wix'te platform komisyonu yok; odeme saglayici komisyonu ayri konudur.
UPDATE core.platform SET komisyon_yuzde = 0
WHERE kod = 'wix' AND komisyon_yuzde IS NULL;

-- ------------------------------------------- urun bazli komisyon istisnasi
-- Trendyol komisyonu KATEGORIYE gore degisir. Tek bir platform orani her
-- urune uymaz; istisna gerekir.
CREATE TABLE IF NOT EXISTS core.urun_platform_komisyon (
  urun_id        text    NOT NULL,
  platform_kod   text    NOT NULL REFERENCES core.platform(kod),
  komisyon_yuzde numeric NOT NULL CHECK (komisyon_yuzde >= 0 AND komisyon_yuzde < 100),
  gerekce        text,
  kaydeden       text    NOT NULL,
  guncelleme     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (urun_id, platform_kod)
);

COMMENT ON TABLE core.urun_platform_komisyon IS
  'Urun bazli komisyon istisnasi. Platform genel oranini gecersiz kilar.';

-- --------------------------------------------------------- panel gorunumu
-- CREATE OR REPLACE sutun SIRASINI degistiremez; yeni sutunlar ortaya
-- girdigi icin gorunum dusurulup yeniden kurulur. Kuru calistirma bunu
-- yakaladi. Bagimlisi olmadigi once dogrulanir -- varsa DROP sessizce
-- calismaz, hata verir (CASCADE KULLANILMAZ).
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n
  FROM pg_depend d
  JOIN pg_rewrite r ON r.oid = d.objid
  JOIN pg_class c   ON c.oid = r.ev_class
  WHERE d.refobjid = 'mart.platform_fiyat_matrisi'::regclass
    AND c.relname <> 'platform_fiyat_matrisi';
  IF n > 0 THEN
    RAISE EXCEPTION 'gorunumun % bagimlisi var -- elle bakilmali', n;
  END IF;
END $$;

DROP VIEW IF EXISTS mart.platform_fiyat_matrisi;

CREATE VIEW mart.platform_fiyat_matrisi AS
WITH acik AS (
  SELECT urun_id, platform_kod, fiyat, yontem, gerekce,
         gecerli_baslangic, kaydeden
  FROM core.urun_platform_fiyat
  WHERE gecerli_bitis IS NULL
),
maliyet AS (
  SELECT urun_id, maliyet, kaynak, gerekce
  FROM core.urun_maliyet
  WHERE gecerli_bitis IS NULL
),
temel AS (
  SELECT
    g.urun_id, g.urun_adi,
    p.kod AS platform_kod, p.ad AS platform_adi,
    p.aktif AS platform_aktif, p.yazma_izni, p.kdv_yuzde, p.kargo_bedeli,
    COALESCE(k.komisyon_yuzde, p.komisyon_yuzde) AS komisyon_yuzde,
    k.komisyon_yuzde IS NOT NULL                 AS komisyon_istisnasi,
    g.musteriye_soylenecek_fiyat AS referans_fiyat,
    g.fiyat_kaynagi              AS referans_kaynagi,
    a.fiyat AS platform_fiyati, a.yontem, a.gerekce,
    a.gecerli_baslangic, a.kaydeden,
    COALESCE(a.fiyat, g.musteriye_soylenecek_fiyat) AS gecerli_fiyat,
    m.maliyet AS birim_maliyet,
    m.kaynak  AS maliyet_kaynagi,
    m.gerekce AS maliyet_gerekcesi
  FROM mart.fiyat_gercegi g
  CROSS JOIN core.platform p
  LEFT JOIN acik    a ON a.urun_id = g.urun_id AND a.platform_kod = p.kod
  LEFT JOIN core.urun_platform_komisyon k
                      ON k.urun_id = g.urun_id AND k.platform_kod = p.kod
  LEFT JOIN maliyet m ON m.urun_id = g.urun_id
)
SELECT
  t.*,
  CASE
    WHEN t.platform_fiyati IS NULL THEN 'REFERANS'
    WHEN t.referans_fiyat IS NULL  THEN 'REFERANS_YOK'
    WHEN t.platform_fiyati > t.referans_fiyat THEN 'YUKSEK'
    WHEN t.platform_fiyati < t.referans_fiyat THEN 'DUSUK'
    ELSE 'AYNI'
  END AS fark_durumu,
  CASE
    WHEN t.platform_fiyati IS NULL OR t.referans_fiyat IS NULL
         OR t.referans_fiyat = 0 THEN NULL
    ELSE round((t.platform_fiyati / t.referans_fiyat - 1) * 100, 1)
  END AS fark_yuzde,

  -- Komisyon tutari: KDV DAHIL satis fiyati uzerinden.
  round(t.gecerli_fiyat * t.komisyon_yuzde / 100.0, 2) AS komisyon_tutari,
  -- Elimize gecen, KDV'siz.
  round((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
        / (1 + t.kdv_yuzde / 100.0), 2)                AS net_kdvsiz,
  round((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
        / (1 + t.kdv_yuzde / 100.0) - t.birim_maliyet, 2) AS marj,
  CASE
    WHEN t.gecerli_fiyat IS NULL OR t.komisyon_yuzde IS NULL
         OR t.birim_maliyet IS NULL THEN NULL
    ELSE round(100.0
      * ((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
         / (1 + t.kdv_yuzde / 100.0) - t.birim_maliyet)
      / NULLIF((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
               / (1 + t.kdv_yuzde / 100.0), 0), 1)
  END AS marj_yuzde,

  -- Panelin renk verecegi alan. Esikler kasten muhafazakar.
  CASE
    WHEN t.gecerli_fiyat IS NULL   THEN 'FIYAT_YOK'
    WHEN t.komisyon_yuzde IS NULL  THEN 'KOMISYON_YOK'
    WHEN t.birim_maliyet IS NULL   THEN 'MALIYET_YOK'
    WHEN (t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
         / (1 + t.kdv_yuzde / 100.0) - t.birim_maliyet < 0      THEN 'ZARAR'
    WHEN 100.0 * ((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
                  / (1 + t.kdv_yuzde / 100.0) - t.birim_maliyet)
         / NULLIF((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
                  / (1 + t.kdv_yuzde / 100.0), 0) < 10          THEN 'KRITIK'
    WHEN 100.0 * ((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
                  / (1 + t.kdv_yuzde / 100.0) - t.birim_maliyet)
         / NULLIF((t.gecerli_fiyat * (1 - t.komisyon_yuzde / 100.0) - t.kargo_bedeli)
                  / (1 + t.kdv_yuzde / 100.0), 0) < 25          THEN 'DUSUK'
    ELSE 'OK'
  END AS marj_uyari
FROM temel t;

COMMENT ON VIEW mart.platform_fiyat_matrisi IS
  'Panel izgarasi: urun x platform, marj dahil. marj_uyari ZARAR/KRITIK/DUSUK/OK '
  'veya neyin eksik oldugunu soyler (KOMISYON_YOK / MALIYET_YOK / FIYAT_YOK). '
  'maliyet_kaynagi sutunu maliyetin BEYAN mi olctum mu oldugunu tasir -- '
  'bugunku 400 TL sahip beyanidir, gercek urun maliyeti degildir.';

GRANT SELECT ON mart.platform_fiyat_matrisi   TO ai_reader;
GRANT SELECT ON core.urun_platform_komisyon   TO ai_reader;

COMMIT;
