-- idefix-kuru.sql — KURU CALISTIRMA. Hicbir sey yazmaz, yalniz karsilastirir.
-- Girdi: psql -v veri=<birlesik JSON dizisi>  (idefix-cek.sh verir)
-- TEMP tablo oturum sonunda kaybolur; BEGIN/COMMIT yok, yazma yok.

CREATE TEMP TABLE gelen AS
SELECT e->>'barcode'                                AS barkod,
       e->>'title'                                  AS ad,
       NULLIF(e->>'price','')::numeric              AS fiyat,
       NULLIF(e->>'inventoryQuantity','')::numeric  AS stok,
       e->>'status'                                 AS durum
  FROM jsonb_array_elements(:'veri'::jsonb) AS e
 WHERE coalesce(e->>'barcode','') <> '';

SELECT count(*) AS idefix_urun,
       count(*) FILTER (WHERE fiyat IS NULL OR fiyat <= 0) AS fiyati_yok,
       count(*) FILTER (WHERE stok IS NULL OR stok = 0)    AS stogu_sifir
  FROM gelen;

SELECT count(*) FILTER (WHERE w.urun_id IS NOT NULL) AS wix_eslesen,
       count(*) FILTER (WHERE w.urun_id IS NULL)     AS wix_eslesmeyen
  FROM gelen g LEFT JOIN raw.wix_urun w ON w.sku = g.barkod;

\echo '--- Wix fiyatiyla karsilastirma (barkodu eslesenler) ---'
SELECT left(coalesce(w.ad, g.ad), 26) AS urun,
       g.barkod,
       w.fiyat AS wix,
       g.fiyat AS idefix,
       CASE WHEN w.fiyat IS NULL OR w.fiyat = 0 OR g.fiyat IS NULL THEN NULL
            ELSE round((g.fiyat - w.fiyat) / w.fiyat * 100, 1) END AS fark_yuzde,
       g.stok,
       g.durum
  FROM gelen g JOIN raw.wix_urun w ON w.sku = g.barkod
 ORDER BY 5 DESC NULLS LAST;

\echo '--- Idefix te olup Wix te barkodu bulunmayanlar ---'
SELECT g.barkod, left(g.ad, 40) AS ad, g.fiyat, g.durum
  FROM gelen g LEFT JOIN raw.wix_urun w ON w.sku = g.barkod
 WHERE w.urun_id IS NULL
 ORDER BY 2;

\echo '--- Wix te olup Idefix te bulunmayanlar (eksik listeleme) ---'
SELECT w.sku AS barkod, left(w.ad, 40) AS ad, w.fiyat AS wix_fiyat
  FROM raw.wix_urun w
 WHERE w.sku IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM gelen g WHERE g.barkod = w.sku)
 ORDER BY 2;
