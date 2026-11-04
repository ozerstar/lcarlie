-- =============================================================================
-- L'CARLIE - KIMLIK MANTIGI TESTI  (CR-003 madde 5 + 6)
--
-- 🔴 SENTETIK VERI. Tum kimlikler CR-002.5 standardina gore 'test-' onekli.
-- 🔴 Test kendi verisini SONUNDA TEMIZLER; gercek musteri verisine dokunmaz.
-- 🔴 Ayni betik iki kez calisir - IDEMPOTENCY boyle kanitlanir.
--
-- Senaryolar:
--   A  gecerli telefon (+90 bicimi) + e-posta            -> MATCHED
--   B  A ile AYNI telefon, FARKLI ham bicim (0XXX)       -> CONFLICT
--   C  9 haneli gecersiz telefon                          -> INVALID
--   D  telefon/e-posta yok, yalniz kaynak kimligi         -> UNKNOWN
--   E  A ile ayni e-posta, farkli telefon                 -> e-posta CONFLICT
-- =============================================================================
\set ON_ERROR_STOP on
\timing off

\echo '=== TEMIZLIK (onceki test kalintisi) ==='
DELETE FROM core.identity_conflict
 WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test','test-e@ornek.test');
DELETE FROM core.customer_identity WHERE source_customer_id LIKE 'test-%';
DELETE FROM core.customer c
 WHERE NOT EXISTS (SELECT 1 FROM core.customer_identity ci WHERE ci.customer_id = c.customer_id);

\echo ''
\echo '=== 1. GECIS ==='
SELECT 'A' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-A','+90 532 111 00 01','test-a@ornek.test');
SELECT 'B' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-B','0532 111 00 01','test-b@ornek.test');
SELECT 'C' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-C','532111000','test-c@ornek.test');
SELECT 'D' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-D',NULL,NULL);
SELECT 'E' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-E','+90 532 111 00 02','test-a@ornek.test');

\echo ''
\echo '=== 1. GECIS SONUCU ==='
SELECT ci.source_customer_id AS kaynak_musteri,
       c.identity_status,
       c.phone_normalized,
       c.email_normalized
  FROM core.customer c
  JOIN core.customer_identity ci
    ON ci.customer_id = c.customer_id AND ci.kimlik_tipi = 'wix_buyer_id'
 WHERE ci.source_customer_id LIKE 'test-%'
 ORDER BY 1;

\echo ''
\echo '=== HAM DEGER KORUNDU MU (normalize edilen ayri kolonda) ==='
SELECT source_customer_id, kimlik_tipi, deger_ham, COALESCE(deger_normal,'(NULL=invalid)') AS deger_normal, gecerli, match_confidence
  FROM core.customer_identity
 WHERE source_customer_id LIKE 'test-%' AND kimlik_tipi IN ('phone','email')
 ORDER BY 1,2;

\echo ''
\echo '=== CAKISMALAR ==='
SELECT kimlik_tipi, deger_normal, array_length(customer_ids,1) AS musteri_sayisi, durum,
       jsonb_array_length(kaynak_kayitlar) AS kaynak_kaydi
  FROM core.identity_conflict
 WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')
 ORDER BY 1,2;

\echo ''
\echo '=== SAYIMLAR (1. gecis) ==='
CREATE TEMP TABLE gecis1 AS
SELECT (SELECT count(*) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS kimlik,
       (SELECT count(DISTINCT customer_id) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS musteri,
       (SELECT count(*) FROM core.identity_conflict
         WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma,
       (SELECT coalesce(sum(jsonb_array_length(kaynak_kayitlar)),0) FROM core.identity_conflict
         WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma_kaynak;
SELECT * FROM gecis1;

\echo ''
\echo '=== 2. GECIS (AYNI VERI TEKRAR) ==='
SELECT 'A' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-A','+90 532 111 00 01','test-a@ornek.test');
SELECT 'B' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-B','0532 111 00 01','test-b@ornek.test');
SELECT 'C' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-C','532111000','test-c@ornek.test');
SELECT 'D' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-D',NULL,NULL);
SELECT 'E' AS senaryo, * FROM core.kaynak_musteri_ekle('wix','wix_buyer_id','test-E','+90 532 111 00 02','test-a@ornek.test');

\echo ''
\echo '=== 2. GECIS SAYIMLARI ==='
CREATE TEMP TABLE gecis2 AS
SELECT (SELECT count(*) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS kimlik,
       (SELECT count(DISTINCT customer_id) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS musteri,
       (SELECT count(*) FROM core.identity_conflict
         WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma,
       (SELECT coalesce(sum(jsonb_array_length(kaynak_kayitlar)),0) FROM core.identity_conflict
         WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma_kaynak;
SELECT * FROM gecis2;

\echo ''
\echo '=== 3. GECIS (YAKINSAMA KONTROLU) ==='
-- 🔴 NEDEN UCUNCU GECIS?
--    1. gecisde A islenirken B henuz YOKTU - A cakisan taraf degildi.
--    2. gecisde B ve E var, dolayisiyla A da cakisan taraf oldu ve
--    cakismanin kaynak listesine A EKLENDI. Bu bir sisme degil, YENI BILGI.
--    Dogru soru "buyudu mu" degil, "YAKINSIYOR MU": sistem tum taraflari
--    gordukten sonra tekrar calistirildiginda HICBIR SEY degismemeli.
SELECT core.kaynak_musteri_ekle('wix','wix_buyer_id','test-A','+90 532 111 00 01','test-a@ornek.test') IS NOT NULL AS a;
SELECT core.kaynak_musteri_ekle('wix','wix_buyer_id','test-B','0532 111 00 01','test-b@ornek.test') IS NOT NULL AS b;
SELECT core.kaynak_musteri_ekle('wix','wix_buyer_id','test-C','532111000','test-c@ornek.test') IS NOT NULL AS c;
SELECT core.kaynak_musteri_ekle('wix','wix_buyer_id','test-D',NULL,NULL) IS NOT NULL AS d;
SELECT core.kaynak_musteri_ekle('wix','wix_buyer_id','test-E','+90 532 111 00 02','test-a@ornek.test') IS NOT NULL AS e;

\echo ''
\echo '=== IDEMPOTENCY KARARI ==='
WITH g3 AS (
  SELECT (SELECT count(*) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS kimlik,
         (SELECT count(DISTINCT customer_id) FROM core.customer_identity WHERE source_customer_id LIKE 'test-%') AS musteri,
         (SELECT count(*) FROM core.identity_conflict
           WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma,
         (SELECT coalesce(sum(jsonb_array_length(kaynak_kayitlar)),0) FROM core.identity_conflict
           WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test')) AS cakisma_kaynak
)
SELECT
  CASE WHEN g3.kimlik  = g1.kimlik  THEN 'SUCCESS' ELSE 'FAILED' END AS "duplicate kimlik uretmedi",
  CASE WHEN g3.musteri = g1.musteri THEN 'SUCCESS' ELSE 'FAILED' END AS "duplicate musteri uretmedi",
  CASE WHEN g3.cakisma = g1.cakisma AND g3.cakisma > 0 THEN 'SUCCESS'
       WHEN g3.cakisma = 0 THEN 'FAILED (cakisma kayboldu)'
       ELSE 'FAILED' END AS "cakisma korundu",
  CASE WHEN g3.cakisma_kaynak = g2.cakisma_kaynak THEN 'SUCCESS'
       ELSE 'FAILED (yakinsamadi)' END AS "2.=3. gecis (yakinsadi)",
  format('g1: kimlik=%s musteri=%s cakisma=%s kaynak=%s | g2: kaynak=%s | g3: kimlik=%s musteri=%s cakisma=%s kaynak=%s',
         g1.kimlik,g1.musteri,g1.cakisma,g1.cakisma_kaynak,g2.cakisma_kaynak,
         g3.kimlik,g3.musteri,g3.cakisma,g3.cakisma_kaynak) AS detay
FROM gecis1 g1, gecis2 g2, g3;

\echo ''
\echo '=== BEKLENEN SINIFLAR ==='
SELECT
  (SELECT count(*) FROM core.customer c JOIN core.customer_identity ci ON ci.customer_id=c.customer_id
     AND ci.kimlik_tipi='wix_buyer_id' WHERE ci.source_customer_id LIKE 'test-%'
     AND c.identity_status='CONFLICT') AS conflict_musteri,
  (SELECT count(*) FROM core.customer_identity
    WHERE source_customer_id LIKE 'test-%' AND kimlik_tipi='phone' AND NOT gecerli) AS invalid_telefon,
  (SELECT count(*) FROM core.customer_identity
    WHERE source_customer_id LIKE 'test-%' AND kimlik_tipi='phone' AND gecerli) AS gecerli_telefon,
  (SELECT count(*) FROM core.customer_identity
    WHERE source_customer_id='test-D') AS D_kimlik_sayisi;

\echo ''
\echo '=== TEMIZLIK ==='
DELETE FROM core.identity_conflict
 WHERE deger_normal IN ('+905321110001','+905321110002','test-a@ornek.test');
DELETE FROM core.customer_identity WHERE source_customer_id LIKE 'test-%';
DELETE FROM core.customer c
 WHERE NOT EXISTS (SELECT 1 FROM core.customer_identity ci WHERE ci.customer_id = c.customer_id);

SELECT (SELECT count(*) FROM core.customer)          AS kalan_musteri,
       (SELECT count(*) FROM core.customer_identity) AS kalan_kimlik,
       (SELECT count(*) FROM core.identity_conflict) AS kalan_cakisma;
