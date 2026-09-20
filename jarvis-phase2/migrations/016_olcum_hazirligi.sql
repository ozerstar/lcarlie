-- 016 — Dönüşüm ölçümü: engelleri adlandır, ara çözümü kur
--
-- DURUM (20.09.2026 ölçüldü)
-- Site GA4'e veri GÖNDERİYOR (G-KCPFLRG2RV; page_view, view_item,
-- add_to_cart tekil). Ama:
--   1. GA4 -> veritabanı çekimi HİÇ YAZILMADI (raw.yukleme_log'da ga4 yok)
--   2. Google kimlik bilgisi YOK (/etc/lcarlie altında Google dosyası yok)
--   3. Wix siparişlerinde ATIF VERİSİ YOK: 37/37 siparişte 0 utm, 0 fbclid,
--      0 gclid, 0 referrer; channelInfo yalnızca {"type":"WEB"}
--   4. Huninin karar adımları GA4'e gitmiyor: begin_checkout, view_cart yok;
--      purchase'ın durumu ölçülmedi
--
-- YANİ gerçek atıf (hangi reklam hangi siparişi getirdi) bugün KURULAMAZ.
-- mart.ga4_siparis_mutabakat zaten bunu bekliyor ve GA4_TARAFI_OLCULMEDI der.
--
-- BU MIGRATION NE YAPAR
-- a) mart.olcum_hazirligi -- her engeli adıyla, neyi engellediğiyle ve
--    çözümüyle listeler. Panel "GA4 akmıyor" demek yerine bunu gösterir.
-- b) mart.harcama_siparis_ortusmesi -- günlük harcama ile günlük sipariş
--    yan yana. ⚠ Bu ATIF DEĞİLDİR, örtüşmedir: aynı gün reklam harcanmış
--    ve sipariş gelmiş olması, siparişin o reklamdan geldiğini GÖSTERMEZ.
--    Sütun adları ve açıklama bunu açıkça söyler.
--
-- NEDEN YİNE DE DEĞERLİ
-- "Reklam harcadığımız günlerde sipariş geliyor mu" sorusu, atıf kadar
-- iyi olmasa da bugün cevaplanabilen tek sorudur. Hiç cevap vermemekten
-- iyidir -- yeter ki ne olmadığı yazılı olsun.

\set ON_ERROR_STOP on
BEGIN;

-- ------------------------------------------------- a) ölçüm hazırlığı
CREATE OR REPLACE VIEW mart.olcum_hazirligi AS
SELECT * FROM (VALUES
  (1, 'GA4 veri çekimi',
      'YOK',
      'GA4''ten veritabanına veri çeken istemci hiç yazılmadı. raw.yukleme_log''da ga4 kaydı yok.',
      'Reklamın satışa dönüp dönmediği bilinemiyor.',
      'GA4 Property ID (sayısal) + Google servis hesabı gerekir. Servis hesabına GA4 yönetiminden Görüntüleyici yetkisi verilmeli.',
      'SAHIP'),
  (2, 'Google kimlik bilgisi',
      'YOK',
      '/etc/lcarlie altında Google servis hesabı dosyası yok.',
      'GA4 Data API çağrılamıyor.',
      'Google Cloud''da servis hesabı açıp JSON anahtarı /etc/lcarlie/ga4.json olarak konmalı.',
      'SAHIP'),
  (3, 'Sipariş atıf verisi',
      'YOK',
      '37 siparişin 37''sinde utm/fbclid/gclid/referrer yok. channelInfo yalnız {"type":"WEB"}.',
      'Sipariş düzeyinde "hangi reklamdan geldi" sorusu Wix verisiyle cevaplanamaz.',
      'GA4 purchase olayındaki transaction_id, Wix sipariş numarasıyla eşleştirilecek. mart.ga4_siparis_mutabakat bunu bekliyor.',
      'GA4_GELINCE'),
  (4, 'Huni adımları',
      'EKSIK',
      'GA4''e page_view, view_item, add_to_cart gidiyor. begin_checkout ve view_cart GİTMİYOR. purchase''ın durumu ölçülmedi.',
      'Sepete ekleyip almayan ile hiç sepete eklemeyen ayırt edilemiyor; dönüşüm hunisi karar adımlarında kopuk.',
      'GTM''de begin_checkout ve view_cart tetikleyicileri kurulmalı; purchase''ın tekil gittiği ilk gerçek siparişte ölçülmeli.',
      'SITE'),
  (5, 'Özel landing ölçümü',
      'EKSIK',
      'Özel landing sayfalarında (/vireon gibi) view_item GA4''e gitmiyor; sepete ekleme postMessage köprüsünden geçiyor ve onCartChange ateşlenmiyor.',
      'Reklam trafiğinin indiği sayfalar sessizce ölçüm dışı kalıyor.',
      'wixDevelopersAnalytics köprüsü kullanılabilir — Özel Kod katmanından, site yayını gerektirmeden.',
      'SITE')
) AS t(sira, engel, durum, bulgu, neyi_engelliyor, cozum, kimde);

COMMENT ON VIEW mart.olcum_hazirligi IS
  'Donusum olcumunu engelleyen maddeler. kimde sutunu isin kimde oldugunu '
  'soyler: SAHIP (kimlik bilgisi), SITE (GTM/Velo), GA4_GELINCE (veri akinca).';

-- --------------------------------- b) örtüşme (ATIF DEĞİL)
CREATE OR REPLACE VIEW mart.harcama_siparis_ortusmesi AS
WITH gunler AS (
  SELECT gun FROM raw.meta_harcama
  UNION
  SELECT olusturma::date FROM mart.siparis
),
h AS (
  SELECT gun, sum(harcama) AS harcama, sum(gosterim) AS gosterim,
         sum(link_tiklama) AS link_tiklama
  FROM raw.meta_harcama GROUP BY gun
),
s AS (
  SELECT olusturma::date AS gun, count(*) AS siparis,
         sum(toplam - kdv) FILTER (
           WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')) AS net_ciro
  FROM mart.siparis GROUP BY 1
)
SELECT g.gun,
       COALESCE(h.harcama, 0)      AS harcama,
       h.gosterim,
       h.link_tiklama,
       COALESCE(s.siparis, 0)      AS siparis,
       s.net_ciro,
       -- ⚠ ATIF DEGIL. Ayni gun reklam harcanmasi ve siparis gelmesi,
       -- siparisin o reklamdan geldigini GOSTERMEZ. Sutun adi bunu
       -- hatirlatsin diye "ortusme" denildi.
       CASE
         WHEN COALESCE(h.harcama, 0) > 0 AND COALESCE(s.siparis, 0) > 0
           THEN 'HARCAMA_VE_SIPARIS'
         WHEN COALESCE(h.harcama, 0) > 0 THEN 'YALNIZ_HARCAMA'
         WHEN COALESCE(s.siparis, 0) > 0 THEN 'YALNIZ_SIPARIS'
         ELSE 'IKISI_DE_YOK'
       END AS ortusme
FROM gunler g
LEFT JOIN h ON h.gun = g.gun
LEFT JOIN s ON s.gun = g.gun
ORDER BY g.gun;

COMMENT ON VIEW mart.harcama_siparis_ortusmesi IS
  '⚠ ATIF DEGILDIR. Gunluk harcama ile gunluk siparisin yan yana '
  'gorunumudur. Ayni gun reklam harcanip siparis gelmesi, siparisin o '
  'reklamdan geldigini KANITLAMAZ -- gercek atif icin GA4 purchase '
  'transaction_id eslestirmesi gerekir (bkz. mart.ga4_siparis_mutabakat).';

GRANT SELECT ON mart.olcum_hazirligi             TO ai_reader;
GRANT SELECT ON mart.harcama_siparis_ortusmesi   TO ai_reader;

COMMIT;
