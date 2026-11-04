-- =============================================================================
-- L'CARLIE - FUNNEL SAGLIK · ORAN · MUTABAKAT  (CR-017 mart katmani)
--
-- 🔴 TEK BIR "GA4 calisiyor" BOOLEAN'I URETILMEZ. Her adim kendi sagligini
--    tasir: page_view MEASURED iken add_to_cart NOT_INSTRUMENTED olabilir.
--
-- 🔴 ORAN YALNIZ PAYDA GUVENILIRKEN HESAPLANIR. add_to_cart olculmuyorsa
--    "ATC orani %0" DENMEZ -> NOT_MEASURABLE.
--
-- 🔴 GA4 TICARI OTORITE DEGILDIR. purchase mutabakati iki tarafi AYRI sayar;
--    GA4 tarafi bos olsa bile Wix tarafi gercektir ve tersi ASLA dogru degildir.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.funnel_orani          CASCADE;
DROP VIEW IF EXISTS mart.ga4_siparis_mutabakat CASCADE;
DROP VIEW IF EXISTS mart.funnel_saglik         CASCADE;

-- ---------------------------------------------------------------------------
-- ADIM SAGLIGI  -  enstrumantasyon + veri akisi AYRI iki boyut
-- ---------------------------------------------------------------------------
CREATE VIEW mart.funnel_saglik AS
WITH veri AS (
  SELECT f.adim_kod,
         count(e.ga4_event_id)                                      AS event_satiri,
         max(e.event_timestamp)                                     AS son_event,
         count(*) FILTER (WHERE e.kanit_durumu = 'CONSENT_LIMITED')  AS consent_kisitli
    FROM core.funnel_adim f
    LEFT JOIN raw.ga4_event e ON e.event_name = f.ga4_event_adi
   GROUP BY f.adim_kod
)
SELECT
  f.sira, f.adim_kod, f.ad, f.ga4_event_adi,
  f.enstrumantasyon,
  v.event_satiri,
  v.son_event,

  -- 🔴 IKI AYRI SORU, IKI AYRI CEVAP:
  --    (1) Bu adim OLCULEBILIR mi?      -> enstrumantasyon
  --    (2) Veri ambara GELIYOR mu?      -> veri_akisi
  --    Ikisi karistirilirsa "enstrumantasyon var ama ETL yok" durumu
  --    "enstrumantasyon yok" gibi okunur ve YANLIS ISE yonlendirir.
  CASE
    WHEN v.event_satiri > 0                        THEN 'AKIYOR'
    WHEN f.enstrumantasyon = 'NOT_INSTRUMENTED'    THEN 'ENSTRUMANTASYON_YOK'
    WHEN f.enstrumantasyon = 'NOT_TESTED'          THEN 'TEST_EDILMEDI'
    ELSE 'ETL_YOK'
  END                                                              AS veri_akisi,

  -- 🔴 UC DURUM MODELI - CR-017'nin kalbi.
  --    NOT_OBSERVED yalnizca enstrumantasyon SAGLIKLI ve veri AKARKEN
  --    verilebilir. Aksi halde NOT_MEASURED'dir.
  CASE
    WHEN v.event_satiri > 0                                        THEN 'OBSERVED'
    WHEN f.enstrumantasyon = 'MEASURED'
         AND EXISTS (SELECT 1 FROM raw.ga4_event)                  THEN 'NOT_OBSERVED'
    ELSE 'NOT_MEASURED'
  END                                                              AS gozlem_durumu,

  -- Panel/brief icin tek cumle
  CASE
    WHEN v.event_satiri > 0 THEN
      format('%s satir gozlendi (son: %s)', v.event_satiri,
             to_char(v.son_event AT TIME ZONE 'Europe/Istanbul','DD.MM HH24:MI'))
    WHEN f.enstrumantasyon = 'NOT_INSTRUMENTED' THEN
      'ENSTRUMANTASYON YOK - olay gerceklesse bile olculmez. "0" YAZILAMAZ.'
    WHEN f.enstrumantasyon = 'NOT_TESTED' THEN
      'TEST EDILMEDI - dogrulamak gercek siparis gerektirir (insan onayi).'
    WHEN f.enstrumantasyon IN ('MEASURED','PARTIAL') THEN
      'Tarayicida event GONDERILIYOR ama ambara AKMIYOR (GA4 Data API bagli degil).'
    ELSE 'Durum bilinmiyor.'
  END                                                              AS ifade,
  f.olcum_kaniti, f.olcum_yeri, f.notlar
FROM core.funnel_adim f
JOIN veri v ON v.adim_kod = f.adim_kod
ORDER BY f.sira;

COMMENT ON VIEW mart.funnel_saglik IS
  'Adim bazli funnel sagligi. ENSTRUMANTASYON ile VERI AKISI ayri boyutlar. NOT_MEASURED != 0.';

-- ---------------------------------------------------------------------------
-- FUNNEL ORANLARI  -  payda guvenilir degilse SAYI URETILMEZ
-- ---------------------------------------------------------------------------
CREATE VIEW mart.funnel_orani AS
WITH a AS (SELECT adim_kod, sira, ad, enstrumantasyon, event_satiri, gozlem_durumu FROM mart.funnel_saglik),
ciftler AS (
  SELECT u.adim_kod AS ust_kod, u.ad AS ust_ad, u.event_satiri AS ust_sayi,
         u.gozlem_durumu AS ust_durum, u.enstrumantasyon AS ust_ens,
         a.adim_kod AS alt_kod, a.ad AS alt_ad, a.event_satiri AS alt_sayi,
         a.gozlem_durumu AS alt_durum, a.enstrumantasyon AS alt_ens
    FROM a u JOIN a ON a.sira = u.sira + 1
)
SELECT
  ust_kod, ust_ad, alt_kod, alt_ad,

  -- 🔴 ORAN YALNIZ IKI ADIM DA GOZLENEBILIYORSA HESAPLANIR.
  --    Payda gozlenmiyorsa oran matematiksel olarak TANIMSIZDIR;
  --    0 ya da %100 yazmak UYDURMAKTIR.
  CASE WHEN ust_durum = 'OBSERVED' AND alt_durum = 'OBSERVED' AND ust_sayi > 0
       THEN round(100.0 * alt_sayi / ust_sayi, 1) END              AS oran_yuzde,

  CASE
    WHEN ust_durum = 'OBSERVED' AND alt_durum = 'OBSERVED' AND ust_sayi > 0
      THEN 'HESAPLANDI'
    ELSE 'NOT_MEASURABLE'
  END                                                              AS oran_durumu,

  -- 🔴 DROP-OFF da ayni kurala tabidir: iki komsu adim da olculebilir
  --    degilse "dusus yok" ya da "%100 dusus" DENMEZ.
  CASE
    WHEN ust_durum = 'OBSERVED' AND alt_durum = 'OBSERVED' AND ust_sayi > 0
      THEN round(100.0 * (ust_sayi - alt_sayi) / ust_sayi, 1)
  END                                                              AS dusus_yuzde,

  CASE
    WHEN ust_durum = 'OBSERVED' AND alt_durum = 'OBSERVED' AND ust_sayi > 0
      THEN format('%s -> %s: %s%%', ust_ad, alt_ad, round(100.0*alt_sayi/ust_sayi,1))
    WHEN alt_ens = 'NOT_INSTRUMENTED' THEN
      format('NOT_MEASURABLE - "%s" enstrumantasyonu YOK. Oran 0 DEGIL, BILINMIYOR.', alt_ad)
    WHEN ust_ens = 'NOT_INSTRUMENTED' THEN
      format('NOT_MEASURABLE - payda "%s" olculmuyor.', ust_ad)
    ELSE 'NOT_MEASURABLE - veri ambara akmiyor (GA4 Data API bagli degil).'
  END                                                              AS ifade
FROM ciftler ORDER BY ust_kod;

COMMENT ON VIEW mart.funnel_orani IS
  'Funnel gecis oranlari. Payda GOZLENEBILIR degilse oran URETILMEZ -> NOT_MEASURABLE.';

-- ---------------------------------------------------------------------------
-- PURCHASE MUTABAKATI  -  GA4 gozlemi vs Wix ticari gercegi
-- ---------------------------------------------------------------------------
-- 🔴 IKI TARAF AYRI SAYILIR ve GA4 ASLA otorite degildir.
--    GA4_ONLY bir "kayip siparis" DEGIL, bir TRACKING ANOMALISIDIR.
--    WIX_ONLY ise gercek siparistir ve GA4'un onu kacirmis olmasi
--    ciroyu DEGISTIRMEZ.
CREATE VIEW mart.ga4_siparis_mutabakat AS
WITH ga4 AS (
  SELECT count(*)                                              AS purchase_event,
         count(*) FILTER (WHERE transaction_id IS NOT NULL)     AS islem_kimlikli,
         count(*) FILTER (WHERE transaction_id IS NULL)         AS islem_kimliksiz,
         count(DISTINCT transaction_id)                         AS tekil_islem,
         coalesce(sum(value),0)                                 AS gozlenen_deger
    FROM raw.ga4_event WHERE event_name = 'purchase'
), wix AS (
  SELECT count(*)                                              AS siparis,
         count(*) FILTER (WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')) AS gerceklesmis,
         coalesce(sum(toplam - kdv) FILTER (WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),0) AS net_ciro
    FROM mart.siparis
), es AS (
  -- 🔴 DETERMINISTIK JOIN: GA4 transaction_id <-> Wix siparis_id / siparis_no.
  --    Fuzzy eslestirme YAPILMAZ (CR-016 kurali: uncertain match zorla
  --    birlestirilmez). Eslesmeyenler ayri sayilir.
  SELECT count(*) FILTER (WHERE w.siparis_id IS NOT NULL)        AS eslesen,
         count(*) FILTER (WHERE w.siparis_id IS NULL)            AS ga4_only
    FROM (SELECT DISTINCT transaction_id FROM raw.ga4_event
           WHERE event_name='purchase' AND transaction_id IS NOT NULL) g
    LEFT JOIN mart.siparis w
      ON w.siparis_id = g.transaction_id OR w.siparis_no::text = g.transaction_id
)
SELECT
  ga4.purchase_event                                     AS ga4_purchase_sayisi,
  ga4.tekil_islem                                        AS ga4_tekil_islem,
  ga4.islem_kimliksiz                                    AS ga4_islem_kimliksiz,
  round(ga4.gozlenen_deger,2)                            AS ga4_gozlenen_deger,
  wix.siparis                                            AS wix_siparis_sayisi,
  wix.gerceklesmis                                       AS wix_gerceklesmis,
  round(wix.net_ciro,2)                                  AS wix_net_ciro,
  es.eslesen                                             AS eslesen,
  es.ga4_only                                            AS ga4_only,
  (wix.siparis - es.eslesen)                             AS wix_only,

  -- 🔴 DUPLICATE KORUMASI: raw'da unique index var; burada ayrica olculur.
  (ga4.islem_kimlikli - ga4.tekil_islem)                 AS duplicate_islem,

  CASE
    WHEN ga4.purchase_event = 0 AND wix.siparis > 0 THEN 'GA4_TARAFI_OLCULMEDI'
    WHEN ga4.purchase_event = 0 AND wix.siparis = 0 THEN 'VERI_YOK'
    WHEN es.ga4_only > 0 OR (wix.siparis - es.eslesen) > 0 THEN 'AYRISMA_VAR'
    ELSE 'MUTABIK'
  END                                                    AS durum,

  CASE
    WHEN ga4.purchase_event = 0 AND wix.siparis > 0 THEN
      format('GA4 tarafinda 0 purchase event''i var, Wix tarafinda %s siparis. '
             'Bu "siparis yok" DEMEK DEGILDIR - GA4 Data API bagli degil ve '
             'purchase enstrumantasyonu TEST EDILMEDI. Ticari gercek Wix''tedir '
             've %s TL net ciro DEGISMEZ.', wix.siparis, round(wix.net_ciro,2))
    WHEN es.ga4_only > 0 THEN
      format('%s GA4 purchase''i Wix siparisiyle ESLESMIYOR - tracking anomalisi. '
             'Bu bir ciro kaydi DEGILDIR.', es.ga4_only)
    ELSE 'Iki taraf mutabik.'
  END                                                    AS ifade
FROM ga4, wix, es;

COMMENT ON VIEW mart.ga4_siparis_mutabakat IS
  'GA4 purchase gozlemi ile Wix ticari siparisi AYRI sayilir. GA4 ciro otoritesi DEGILDIR.';

COMMIT;
