-- =============================================================================
-- L'CARLIE - RAW KATMANI DOGRULAMASI  (CR-004 Faz 1 kabul testleri)
--
-- 🔴 "Sorgu calisti" BASARI DEGILDIR. Her satir SUCCESS/PARTIAL/FAILED
--    dondurur ve beklenen deger ACIKCA yazilidir.
-- 🔴 PII ekrana basilmaz.
--
-- ⚠️ BU DOSYA BIR ANLIK GORUNTU TESTIDIR, SUREGELEN KONTROL DEGIL.
--    Beklenen degerler 16.09.2026 olcumune CAKILIDIR (37 siparis, 55 kalem,
--    49 gonderi, 82.073,50 TL). 38. siparis geldigi an bu testler FAILED der
--    ve bu YANLIS BIR ALARM olur. Her zaman kirmizi yanan test, bakilmayan
--    testtir - gercek bozulmayi da gizler.
--
--    SUREGELEN kontroller icin **mutabakat.sql** kullanilir: oradaki testler
--    ILISKISELDIR (kalem toplami = siparis toplami, PII = 0, yetim kayit = 0)
--    ve veri buyudukce dogru kalirlar. Gunluk hatta calisan odur.
--
--    Buradaki dosyanin isi: kesim oncesi dondurulmus veriyle bir kiyas noktasi
--    tutmak. Kesimden sonra beklenen degerler guncellenmeli ya da dosya
--    arsivlenmelidir.
-- =============================================================================
\pset footer off
\set ON_ERROR_STOP on

\echo '=== 1) SAYIMLAR (CR-001/CR-003 olcumleriyle karsilastirma) ==='
WITH s AS (
  SELECT (SELECT count(*) FROM raw.wix_order)      AS wix,
         (SELECT count(*) FROM raw.wix_order_item) AS kalem,
         (SELECT count(*) FROM raw.bk_shipment)    AS bk
)
SELECT * FROM (
  SELECT 'Wix siparis'      AS kontrol, wix::text   AS gercek, '37' AS beklenen,
         CASE WHEN wix=37   THEN 'SUCCESS' ELSE 'FAILED' END AS durum FROM s
  UNION ALL
  SELECT 'Wix kalem',        kalem::text, '55', CASE WHEN kalem=55 THEN 'SUCCESS' ELSE 'FAILED' END FROM s
  UNION ALL
  SELECT 'BasitKargo gonderi', bk::text,  '49', CASE WHEN bk=49    THEN 'SUCCESS' ELSE 'FAILED' END FROM s
) t;

\echo ''
\echo '=== 2) TUTARLAR (kaynakla birebir tutmali) ==='
-- 🔴 CR-001/CR-003'te gecen 72.223,50 rakami TUM siparislerin degil,
--    yalniz ODENMIS olanlarin toplamiydi. raw katmani ise iptal ve
--    odenmemis dahil HEPSINI tutar - dogru davranis budur. Bu testin
--    ilk surumu 82.073,50'i "FAILED" saydi; hata veride degil,
--    testin beklentisindeydi. Iki rakam da ayri ayri dogrulanir.
SELECT 'Wix TUM siparis toplami' AS kontrol,
       to_char(sum(toplam),'FM999999990.00') AS gercek, '82073.50' AS beklenen,
       CASE WHEN sum(toplam)=82073.50 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM raw.wix_order
UNION ALL
SELECT 'Wix ODENMIS toplami',
       to_char(sum(toplam),'FM999999990.00'), '72223.50',
       CASE WHEN sum(toplam)=72223.50 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.wix_order WHERE odeme_durumu='PAID'
UNION ALL
SELECT 'Wix ODENMEMIS toplami',
       to_char(sum(toplam),'FM999999990.00'), '9850.00',
       CASE WHEN sum(toplam)=9850.00 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.wix_order WHERE odeme_durumu<>'PAID'
UNION ALL
SELECT 'Kargo ucreti toplami',
       to_char(sum(kargo_ucreti),'FM999999990.00'), '7063.83',
       CASE WHEN sum(kargo_ucreti)=7063.83 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.bk_shipment;

\echo ''
\echo '=== 3) PII GERCEKTEN CIKARILDI MI (ham jsonb dahil) ==='
SELECT 'recipient.name kalmadi' AS kontrol,
       count(*) FILTER (WHERE ham#>>'{recipient,name}' IS NOT NULL)::text AS gercek, '0' AS beklenen,
       CASE WHEN count(*) FILTER (WHERE ham#>>'{recipient,name}' IS NOT NULL)=0
            THEN 'SUCCESS' ELSE 'FAILED' END AS durum FROM raw.bk_shipment
UNION ALL
SELECT 'recipient.phone kalmadi',
       count(*) FILTER (WHERE ham#>>'{recipient,phone}' IS NOT NULL)::text, '0',
       CASE WHEN count(*) FILTER (WHERE ham#>>'{recipient,phone}' IS NOT NULL)=0
            THEN 'SUCCESS' ELSE 'FAILED' END FROM raw.bk_shipment
UNION ALL
SELECT 'recipient.address kalmadi',
       count(*) FILTER (WHERE ham#>>'{recipient,address}' IS NOT NULL)::text, '0',
       CASE WHEN count(*) FILTER (WHERE ham#>>'{recipient,address}' IS NOT NULL)=0
            THEN 'SUCCESS' ELSE 'FAILED' END FROM raw.bk_shipment
UNION ALL
SELECT 'sender.phone kalmadi',
       count(*) FILTER (WHERE ham#>>'{sender,phone}' IS NOT NULL)::text, '0',
       CASE WHEN count(*) FILTER (WHERE ham#>>'{sender,phone}' IS NOT NULL)=0
            THEN 'SUCCESS' ELSE 'FAILED' END FROM raw.bk_shipment
UNION ALL
SELECT 'sehir korundu (analiz icin)',
       count(*) FILTER (WHERE sehir IS NOT NULL)::text, '>0',
       CASE WHEN count(*) FILTER (WHERE sehir IS NOT NULL)>0
            THEN 'SUCCESS' ELSE 'PARTIAL' END FROM raw.bk_shipment;

\echo ''
\echo '=== 4) BAGLANTI: foreignCode -> Wix siparis ==='
SELECT 'foreignCode dolu gonderi' AS kontrol, count(*)::text AS gercek, '9' AS beklenen,
       CASE WHEN count(*)=9 THEN 'SUCCESS' ELSE 'PARTIAL' END AS durum
  FROM raw.bk_shipment WHERE foreign_code IS NOT NULL
UNION ALL
SELECT 'Wix siparisiyle eslesen', count(*)::text, '9',
       CASE WHEN count(*)=9 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.bk_shipment b JOIN raw.wix_order w ON w.siparis_id = b.foreign_code
UNION ALL
SELECT 'eslesmeyen foreignCode (hayalet)', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.bk_shipment b
 WHERE b.foreign_code IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM raw.wix_order w WHERE w.siparis_id=b.foreign_code);

\echo ''
\echo '=== 5) ZAMAN DILIMI VARSAYIMI (+03) TESTI ==='
-- 🔴 BasitKargo tarihleri offset'siz gelir. "+03" varsayimi test edilir.
--    "BK >= Wix" TEK BASINA YETMEZ: tarihler aslinda UTC olsaydi fark
--    +3 saat cikar ve bu kosul YINE gecerdi. Ayirt edici olan sudur:
--    bagli 9 gonderi Wix entegrasyonuyla siparisin hemen ardindan
--    olusuyor, yani gercek fark DAKIKALAR mertebesinde olmali.
--      +03 dogruysa  -> fark ~0
--      UTC olsaydi   -> fark tam -3 saat (negatif)
--      +06 olsaydi   -> fark tam +3 saat
--    Bu yuzden esik |fark| < 2 saat.
SELECT 'bagli gonderi zaman farki < 2 saat' AS kontrol,
       count(*) FILTER (WHERE abs(extract(epoch FROM b.olusturma - w.olusturma)) < 7200)::text
         || '/' || count(*)::text AS gercek,
       'hepsi' AS beklenen,
       CASE WHEN count(*)=0 THEN 'NO_DATA'
            WHEN count(*) FILTER (WHERE abs(extract(epoch FROM b.olusturma - w.olusturma)) < 7200) = count(*)
                 THEN 'SUCCESS (+03 dogrulandi)'
            ELSE 'FAILED (+03 varsayimi yanlis)' END AS durum
  FROM raw.bk_shipment b JOIN raw.wix_order w ON w.siparis_id=b.foreign_code;

SELECT round(min(extract(epoch FROM b.olusturma - w.olusturma))/3600.0, 2) AS min_saat_fark,
       round(max(extract(epoch FROM b.olusturma - w.olusturma))/3600.0, 2) AS max_saat_fark,
       round(avg(extract(epoch FROM b.olusturma - w.olusturma))/3600.0, 2) AS ort_saat_fark
  FROM raw.bk_shipment b JOIN raw.wix_order w ON w.siparis_id=b.foreign_code;

\echo ''
\echo '=== 6) SATIS OLMAYAN KAYITLAR (mart bunlari disarida birakacak) ==='
SELECT 'INCOMING (iade) gonderi' AS kontrol, count(*)::text AS gercek
  FROM raw.bk_shipment WHERE yon = 'INCOMING'
UNION ALL
SELECT 'Wix iptal edilmis siparis', count(*)::text
  FROM raw.wix_order WHERE teslimat_durumu = 'CANCELED'
UNION ALL
SELECT 'Wix arsivlenmis siparis', count(*)::text
  FROM raw.wix_order WHERE arsivlendi
UNION ALL
SELECT 'Wix odenmemis siparis', count(*)::text
  FROM raw.wix_order WHERE odeme_durumu <> 'PAID';

\echo ''
\echo '=== 7) CIRO AYRIMI ONIZLEMESI (tek "revenue" sayisi URETILMEZ) ==='
SELECT odeme_yontemi,
       count(*) AS siparis,
       to_char(sum(toplam),'FM999999990.00') AS tutar,
       CASE WHEN odeme_yontemi='PayTR' THEN 'dogrulanmis (saglayici onayli)'
            ELSE 'beyan edilmis (elle isaretlenmis)' END AS ciro_sinifi
  FROM raw.wix_order
 WHERE odeme_durumu='PAID'
 GROUP BY odeme_yontemi ORDER BY 2 DESC;

\echo ''
\echo '=== 8) OLCUM KESIMI (1 Ekim 2026) ==='
SELECT 'kesim oncesi Wix siparis' AS kontrol, count(*)::text AS gercek
  FROM raw.wix_order WHERE olusturma < (SELECT deger::timestamptz FROM core.ayar WHERE anahtar='olcum_baslangici')
UNION ALL
SELECT 'kesim sonrasi Wix siparis', count(*)::text
  FROM raw.wix_order WHERE olusturma >= (SELECT deger::timestamptz FROM core.ayar WHERE anahtar='olcum_baslangici')
UNION ALL
SELECT 'kesim oncesi BK gonderi', count(*)::text
  FROM raw.bk_shipment WHERE olusturma < (SELECT deger::timestamptz FROM core.ayar WHERE anahtar='olcum_baslangici')
UNION ALL
SELECT 'kesim sonrasi BK gonderi', count(*)::text
  FROM raw.bk_shipment WHERE olusturma >= (SELECT deger::timestamptz FROM core.ayar WHERE anahtar='olcum_baslangici');

\echo ''
\echo '=== 9) "EK BILGI" ALANI - NUMUNE ISARETLEMESI HENUZ BOS ==='
-- 🔴 Sahip karari: numune/UGC gonderileri "NUMUNE-<tarih>" ile isaretlenecek.
--    Bugun BU ALAN 49/49 BOS. Yani kural 1 Ekim'den itibaren gecerli olacak;
--    gecmis gonderilerde numune ayrimi ISARETLE YAPILAMAZ.
SELECT 'ek_bilgi dolu gonderi' AS kontrol, count(*)::text AS gercek, '0 (henuz)' AS beklenen
  FROM raw.bk_shipment WHERE ek_bilgi IS NOT NULL
UNION ALL
SELECT 'foreignCode BOS + ek_bilgi BOS (alarm adayi)', count(*)::text, '40 (gecmis)'
  FROM raw.bk_shipment WHERE foreign_code IS NULL AND ek_bilgi IS NULL;

\echo ''
\echo '=== 10) SON YUKLEME GUNLUGU ==='
SELECT kaynak, durum, okunan, yazilan, guncellenen,
       to_char(bitis AT TIME ZONE 'Europe/Istanbul','DD.MM HH24:MI') AS bitis
  FROM raw.yukleme_log ORDER BY id DESC LIMIT 6;
