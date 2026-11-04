-- idefix-yaz.sql — Idefix cekimini veritabanina yazar.
-- Girdi: psql -v veri=<birlesik JSON dizisi>  (idefix-cek.sh --yaz verir)
--
-- YAZDIGI YERLER (hepsi BIZIM veritabani; Idefix'e yazma YOK):
--   raw.idefix_urun               ayna, barkod uzerine upsert
--   core.urun_platform_fiyat      yontem='PLATFORM' gozlem, zamana gore versiyonlu
--   core.platform                 idefix satiri aktif=true (yazma_izni DEGISMEZ)
--
-- DOKUNMADIGI YER: core.urun_platform_komisyon. Idefix komisyon bildirmiyor.

\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE gelen AS
SELECT e->>'barcode'                                AS barkod,
       e->>'stockCode'                              AS stok_kodu,
       NULLIF(e->>'reference','')::bigint           AS referans,
       e->>'title'                                  AS ad,
       e->>'status'                                 AS durum,
       NULLIF(e->>'price','')::numeric              AS fiyat,
       NULLIF(e->>'inventoryQuantity','')::numeric  AS stok,
       coalesce(e->'ham', e)                        AS ham
  FROM jsonb_array_elements(:'veri'::jsonb) AS e
 WHERE coalesce(e->>'barcode','') <> '';

-- Ayna: ustune yazilir, SILINMEZ -- kismi cekim aynayi bosaltmasin.
INSERT INTO raw.idefix_urun (barkod, stok_kodu, referans, ad, durum, ham, cekildi)
SELECT barkod, stok_kodu, referans, ad, durum, ham, now() FROM gelen
    ON CONFLICT (barkod) DO UPDATE
   SET stok_kodu = EXCLUDED.stok_kodu,
       referans  = EXCLUDED.referans,
       ad        = EXCLUDED.ad,
       durum     = EXCLUDED.durum,
       ham       = EXCLUDED.ham,
       cekildi   = EXCLUDED.cekildi;

-- Fiyat gozlemi YALNIZ Wix barkoduyla eslesen urunler icin.
CREATE TEMP TABLE esles AS
SELECT w.urun_id, g.fiyat
  FROM gelen g JOIN raw.wix_urun w ON w.sku = g.barkod
 WHERE g.fiyat IS NOT NULL AND g.fiyat > 0;

-- 1. adim: fiyati DEGISMIS acik satiri kapat (IS DISTINCT FROM -- CR-008).
UPDATE core.urun_platform_fiyat f
   SET gecerli_bitis = now()
  FROM esles e
 WHERE f.urun_id = e.urun_id
   AND f.platform_kod = 'idefix'
   AND f.gecerli_bitis IS NULL
   AND f.fiyat IS DISTINCT FROM e.fiyat;

-- 2. adim: acik satiri olmayana yeni gozlem yaz.
-- AYRI statement olmak ZORUNDA: ayni statement icinde NOT EXISTS, yukarida
-- kapatilan satirlari hala acik gorur ve hicbir sey eklenmez.
INSERT INTO core.urun_platform_fiyat
       (urun_id, platform_kod, fiyat, yontem, gerekce, kaydeden)
SELECT e.urun_id, 'idefix', e.fiyat, 'PLATFORM',
       'Idefix pim/catalog inventory/list cekimi', 'idefix-cek.sh'
  FROM esles e
 WHERE NOT EXISTS (SELECT 1 FROM core.urun_platform_fiyat f
                    WHERE f.urun_id = e.urun_id
                      AND f.platform_kod = 'idefix'
                      AND f.gecerli_bitis IS NULL);

-- aktif=true: hesap artik API ile okunabiliyor. yazma_izni'ne DOKUNULMAZ.
UPDATE core.platform SET aktif = true, guncelleme = now() WHERE kod = 'idefix';

SELECT (SELECT count(*) FROM raw.idefix_urun) AS ayna_satir,
       (SELECT count(*) FROM esles)           AS eslesen,
       (SELECT count(*) FROM core.urun_platform_fiyat
         WHERE platform_kod = 'idefix' AND gecerli_bitis IS NULL) AS acik_gozlem;

COMMIT;
