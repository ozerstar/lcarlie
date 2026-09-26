-- =====================================================================
-- 027 GERİ ALMA
--
-- ⚠️ `kanal` sütunu DÜŞÜRÜLMEZ. İçinde insan beyanı olabilir ve geri
--    alma sırasında veri silmek, geri almayı kayba çevirir. Sütun
--    kullanılmadan durur; zararsızdır.
-- =====================================================================
\set ON_ERROR_STOP on

BEGIN;

DROP VIEW IF EXISTS mart.ciro_kanal;
DROP VIEW IF EXISTS mart.elle_satis;

-- urun_dagitim 026'daki haline döner
CREATE OR REPLACE VIEW mart.urun_dagitim AS
WITH satilan AS (
    SELECT urun_adi, sum(adet)::numeric AS adet, count(*)::int AS satir
      FROM mart.siparis_kalem
     GROUP BY urun_adi
), bedelsiz AS (
    SELECT urun_adi,
           sum(COALESCE(adet, 0))::numeric AS adet,
           count(*)::int AS satir
      FROM core.gonderi_notu
     WHERE tur IN ('UGC', 'INFLUENCER', 'NUMUNE', 'HEDIYE')
     GROUP BY urun_adi
)
SELECT COALESCE(s.urun_adi, b.urun_adi) AS urun_adi,
       COALESCE(s.adet, 0)   AS satilan_adet,
       COALESCE(s.satir, 0)  AS satis_satiri,
       COALESCE(b.adet, 0)   AS bedelsiz_adet,
       COALESCE(b.satir, 0)  AS bedelsiz_satiri,
       COALESCE(s.adet, 0) + COALESCE(b.adet, 0) AS toplam_cikan
  FROM satilan s
  FULL OUTER JOIN bedelsiz b ON b.urun_adi = s.urun_adi;

COMMIT;
