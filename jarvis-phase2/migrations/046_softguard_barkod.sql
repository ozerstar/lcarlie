-- 046 — SOFTGUARD barkodu duzeltiliyor (sahip karari 22.10.2026)
--
-- KARAR
-- Ozer: "8684869609608 Softguard / barkodu buguardinki sabit kalsin tum
-- platformlarda ayrica duzelt."
--   BUGUARD  = 8684869609301  (DEGISMEZ, tum platformlarda sabit)
--   SOFTGUARD = 8684869609608 (yeni)
--
-- KAYNAK ONCE DUZELTILDI
-- Wix urun 2abdb739-3675-3c6b-a312-2283a12e395b SKU'su API ile 8684869609608
-- yapildi ve geri okunarak dogrulandi; `urun-yukle.py` ile raw.wix_urun
-- tazelendi. Bu gocun isi, Wix'ten TUREMEYEN iki core tablosunu hizalamak.
--
-- 🔴 SIPARIS GECMISINE DOKUNULMAZ
-- raw.wix_order_item ve mart.siparis_kalem icinde 8684869609301 tasiyan satir
-- BUGUARD satisidir -- barkodu zaten dogru. Olsaydi bile degistirilmezdi:
-- siparis kaydi o gunku gercegi tutar, katalog duzeltmesi geriye yurutulmez.

\set ON_ERROR_STOP on
BEGIN;

-- 1) Bayi fiyat listesi: softguard satirina yeni barkod, celiski kaldirilir
UPDATE core.urun_bayi_fiyat
   SET barkod = '8684869609608',
       barkod_celiskili = false,
       barkod_notu = 'Barkod 22.10.2026 sahip karariyla ayrildi: SOFTGUARD '
                     '8684869609608, BUGUARD 8684869609301. Kaynak (Wix) duzeltildi.'
 WHERE urun_slug = 'softguard' AND barkod = '8684869609301';

-- 2) BUGUARD satirinda barkod ayni kalir, yalniz celiski notu kapanir
UPDATE core.urun_bayi_fiyat
   SET barkod_celiskili = false,
       barkod_notu = 'Barkod 22.10.2026 sahip karariyla sabitlendi: BUGUARD '
                     '8684869609301 (degismez). SOFTGUARD 8684869609608 oldu.'
 WHERE urun_slug = 'buguard' AND barkod = '8684869609301';

-- 3) SEO tablosu: softguard satirinin sku'su
UPDATE core.urun_seo
   SET sku = '8684869609608', guncelleme = now()
 WHERE urun_id = '2abdb739-3675-3c6b-a312-2283a12e395b'
   AND sku = '8684869609301';

-- Dogrulama: ayni barkodu iki urun tasiyor mu?
SELECT 'core.urun_bayi_fiyat' AS tablo, barkod, count(*) AS urun
  FROM core.urun_bayi_fiyat WHERE barkod IN ('8684869609301','8684869609608')
 GROUP BY 1,2
UNION ALL
SELECT 'core.urun_seo', sku, count(*)
  FROM core.urun_seo WHERE sku IN ('8684869609301','8684869609608')
 GROUP BY 1,2
UNION ALL
SELECT 'raw.wix_urun', sku, count(*)
  FROM raw.wix_urun WHERE sku IN ('8684869609301','8684869609608')
 GROUP BY 1,2
 ORDER BY 1,2;

COMMIT;
