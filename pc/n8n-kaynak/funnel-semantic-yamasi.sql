-- =============================================================================
-- CR-017 SEMANTIC AUDIT YAMASI  (17.09.2026, Chief Architect)
--
-- 🔴 DUZELTILEN ANA HATA: TEK BIR GLOBAL `behavior` STATUSU, UC AYRI
--    GERCEGI EZIYORDU.
--
--      A) SITE SOURCE CONNECTION   -> GA4 sitede CALISIYOR (G-KCPFLRG2RV
--                                     canli, page_view gonderiyor)
--      B) GROWTH OS INGESTION      -> Data API credential YOK, ambara veri
--                                     AKMIYOR
--      C) EVENT-LEVEL INSTRUMENT.  -> adim ve SAYFA bazinda degisiyor
--
--    Onceki hali ucunu birden 'SOURCE_NOT_CONNECTED' yapiyordu. Bu YANLIS:
--    "GA4 bagli degil" ile "GA4 verisi bize gelmiyor" ayni sey degildir.
--    Birincisi bir kurulum eksigi, ikincisi bir ENTEGRASYON eksigidir ve
--    ikisi FARKLI ISI gerektirir. Ayrica sitede calisan bir olcumu
--    "bagli degil" diye kaydetmek, ileride "GA4 kuralim" gibi YANLIS BIR
--    ISE yonlendirirdi - oysa GA4 zaten kurulu.
--
-- 🔴 ARCHITECTURE REBUILD YOK. Mevcut source_authority semasi tek statuye
--    zorluyordu; ayri SATIRLAR ve kucuk bir sayfa-kapsama tablosuyla
--    ayristirildi.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0) DURUM SOZLUGU: ingestion blokajı icin yeni durum
-- ---------------------------------------------------------------------------
-- 🔴 'SOURCE_NOT_CONNECTED' bu durumu anlatmiyor: kaynak BAGLI (site uzerinde
--    calisiyor), bize AKTARIM bloke. Ayri bir kelime gerekiyor.
ALTER TABLE core.source_authority
  DROP CONSTRAINT IF EXISTS source_authority_current_connection_check;
ALTER TABLE core.source_authority
  ADD CONSTRAINT source_authority_current_connection_check
  CHECK (current_connection IN (
    'CONNECTED','PARTIAL','SOURCE_NOT_CONNECTED','NONE','UNKNOWN',
    'MANUAL_CONTROLLED_INPUT','OPTIONAL_RECONCILIATION_GAP',
    'BLOCKED_BY_EXTERNAL_CREDENTIAL'   -- kaynak calisiyor, AKTARIM bloke
  ));

-- ---------------------------------------------------------------------------
-- 1A) SITE SOURCE CONNECTION  -  GA4 sitede CALISIYOR
-- ---------------------------------------------------------------------------
INSERT INTO core.source_authority
  (alan, authority, mirror, freshness, current_connection, gap,
   dogrulama_zamani, dogrulama_yontemi, notlar)
VALUES
  ('behavior_site_tracking', 'GA4 (G-KCPFLRG2RV) + GTM-5XR5TQKP', 'tarayici', 'canli',
   'CONNECTED',
   'GA4 SITEDE CALISIYOR ve OLCULDU (17.09.2026, tarayici ag trafigi): '
   'G-KCPFLRG2RV yapilandirilmis, page_view gonderiyor, _ga_KCPFLRG2RV cerezi olusuyor, '
   'GTM-5XR5TQKP her sayfada (checkout dahil) yukleniyor, Consent Mode kurulu. '
   'BU SATIR AMBAR AKISINI OLCMEZ - onun icin behavior satirina bakilir. '
   'Event bazinda kapsama ise adima ve SAYFAYA gore degisir; '
   'core.funnel_adim ve core.funnel_sayfa_kapsama''ya bakilir.',
   clock_timestamp(),
   'performance resource timing (/g/collect istekleri) + GTM container okumasi',
   'Site tarafi kurulum EKSIK DEGIL. Eksik olan ecommerce event enstrumantasyonu '
   've Growth OS aktarimi - ikisi ayri satirda.')
ON CONFLICT (alan) DO UPDATE SET
  authority=EXCLUDED.authority, current_connection=EXCLUDED.current_connection,
  gap=EXCLUDED.gap, dogrulama_zamani=clock_timestamp(),
  dogrulama_yontemi=EXCLUDED.dogrulama_yontemi, notlar=EXCLUDED.notlar;

-- ---------------------------------------------------------------------------
-- 1B) GROWTH OS INGESTION  -  credential bloke
-- ---------------------------------------------------------------------------
-- 🔴 `behavior` satiri ARTIK YALNIZ AKTARIMI olcer. Adi korunuyor cunku
--    mart.kanit_kalitesi ve raporlar bu alani okuyor - yeniden adlandirmak
--    calisan seyleri bozardi (minimum-diff).
UPDATE core.source_authority SET
  authority = 'GA4 Data API (Growth OS aktarimi)',
  current_connection = 'BLOCKED_BY_EXTERNAL_CREDENTIAL',
  gap = 'BU SATIR AKTARIMI OLCER, SITE KURULUMUNU DEGIL. '
        'GA4 sitede CALISIYOR (bkz. behavior_site_tracking = CONNECTED) ama '
        'Growth OS ambarina TEK SATIR gelmiyor: GA4 Data API credential YOK, '
        'property ID bilinmiyor, ETL yok. '
        '🔴 ONCEKI ETIKET DUZELTILDI: "SOURCE_NOT_CONNECTED" yaziyordu ve bu, '
        'sitede calisan bir olcumu "kurulmamis" gibi gosteriyordu - okuyan '
        '"GA4 kuralim" gibi YANLIS BIR ISE yonlendirilirdi. Dogru is: '
        'Data API yetkilendirmesi. '
        'EVENT BAZINDA KAPSAMA BU SATIRDAN OKUNMAZ; adim ve sayfa bazinda '
        'degisir (core.funnel_adim + core.funnel_sayfa_kapsama).',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = '.env taramasi (Google/GA4 anahtari yok) + raw.ga4_event bos'
WHERE alan = 'behavior';

-- ---------------------------------------------------------------------------
-- 1C) EVENT-LEVEL: SAYFA BAZINDA KAPSAMA
-- ---------------------------------------------------------------------------
-- 🔴 NEDEN AYRI TABLO: ayni event SAYFAYA GORE farkli davraniyor.
--    view_item native urun sayfasinda MEASURED, reklamlarin indigi
--    /vireon sayfasinda NOT_INSTRUMENTED. Tek bir "PARTIAL" etiketi bu
--    ayrimi GIZLIYORDU - oysa is acisindan kritik olan tam olarak
--    HANGI sayfada olculmedigi.
CREATE TABLE IF NOT EXISTS core.funnel_sayfa_kapsama (
  adim_kod        text NOT NULL REFERENCES core.funnel_adim(adim_kod),
  sayfa           text NOT NULL,
  sayfa_rolu      text NOT NULL,   -- REKLAM_LANDING / NATIVE_URUN / SEPET / ODEME
  enstrumantasyon text NOT NULL
                  CHECK (enstrumantasyon IN ('MEASURED','NOT_INSTRUMENTED','NOT_TESTED','UNKNOWN')),
  olcum_kaniti    text NOT NULL,
  olcum_zamani    timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (adim_kod, sayfa)
);

COMMENT ON TABLE core.funnel_sayfa_kapsama IS
  'Event kapsamasi SAYFA bazinda. Ayni event bir sayfada olculup digerinde olculmeyebilir.';

INSERT INTO core.funnel_sayfa_kapsama (adim_kod, sayfa, sayfa_rolu, enstrumantasyon, olcum_kaniti)
SELECT * FROM (VALUES
  ('LANDING','/vireon','REKLAM_LANDING','MEASURED',
   'en=page_view gozlendi'),
  ('LANDING','/product-page/vireon-for-men','NATIVE_URUN','MEASURED',
   'en=page_view gozlendi'),
  ('LANDING','/cart','SEPET','MEASURED','en=page_view gozlendi'),
  ('LANDING','/checkout','ODEME','MEASURED','en=page_view + scroll gozlendi'),

  -- 🔴 IS ACISINDAN EN KRITIK SATIR: reklamlarin indigi sayfa olculmuyor.
  ('PRODUCT_VIEW','/vireon','REKLAM_LANDING','NOT_INSTRUMENTED',
   '🔴 Reklam trafiginin indigi sayfada view_item YOK - yalniz page_view gozlendi. '
   'Yani reklamdan gelen kullanicinin urun gormesi OLCULMUYOR.'),
  ('PRODUCT_VIEW','/product-page/vireon-for-men','NATIVE_URUN','MEASURED',
   'en=view_item gozlendi (Wix native urun sayfasi enstrumante)'),

  ('ADD_TO_CART','/product-page/vireon-for-men','NATIVE_URUN','NOT_INSTRUMENTED',
   'Butona tiklandi, urun sepete GERCEKTEN eklendi (sepette 1.200,00 TL gorundu); '
   'yeni GA4 istegi OLUSMADI (6 -> 6).'),
  ('VIEW_CART','/cart','SEPET','NOT_INSTRUMENTED',
   'Sepet sayfasinda yalniz page_view; view_cart YOK.'),
  ('BEGIN_CHECKOUT','/checkout','ODEME','NOT_INSTRUMENTED',
   'Odeme sayfasinda yalniz page_view + scroll; begin_checkout YOK. '
   'Ayni alan adi ve ayni GTM container -> teknik engel YOK.'),
  ('PURCHASE','/checkout','ODEME','NOT_TESTED',
   'Gercek siparis gerektirdigi icin OLCULMEDI ve UYDURULMADI.')
) AS v(adim_kod, sayfa, sayfa_rolu, enstrumantasyon, olcum_kaniti)
WHERE NOT EXISTS (
  SELECT 1 FROM core.funnel_sayfa_kapsama k
   WHERE k.adim_kod = v.adim_kod AND k.sayfa = v.sayfa);

-- ---------------------------------------------------------------------------
-- 2) META CLAIM DARALTILDI
-- ---------------------------------------------------------------------------
-- 🔴 ASIRI GENELLEME DUZELTILDI. Tarayicida yalniz PageView gozlendi;
--    bundan "Meta'nin optimizasyon sinyali yalniz PageView" SONUCU CIKMAZ.
--    Cunku olculmeyen baska kanallar var: Conversions API (server-side),
--    Wix<->Meta native entegrasyonu, Ads Manager event source.
--    Bunlari GORMEDIM - yoklugunu de kanitlamadim.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('meta_browser_pixel_event_coverage', 'PAGEVIEW_ONLY_OBSERVED',
   'OLCULDU (17.09.2026 tarayici): Meta pikseli 2469140530193842 yalniz PageView '
   'gonderdi; ViewContent/AddToCart GOZLENMEDI. Bu YALNIZCA tarayici pikseli icin gecerlidir.'),
  ('meta_total_optimization_signal', 'NOT_VERIFIED',
   '🔴 DOGRULANMADI. Meta''nin TOPLAM optimizasyon sinyali tarayici pikselinden ibaret '
   'olmayabilir: Conversions API (server-side), Wix-Meta native entegrasyonu ve Ads '
   'Manager event source''lari OLCULMEDI. '
   'ONCEKI IFADE GERI CEKILDI: "Meta''nin optimizasyon sinyali de sayfa goruntulemeyle '
   'sinirli" - bu bir SONUC degil, olculmemis bir alana yapilmis CIKARIMDI. '
   'Dogrulama yolu: Ads Manager > Events Manager > veri kaynaklari.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

UPDATE core.ayar SET
  aciklama = '17.09.2026 tarayici olcumu: piksel yukleniyor ve PageView gonderiyor. '
             'Event kapsamasi icin meta_browser_pixel_event_coverage, toplam sinyal icin '
             'meta_total_optimization_signal (NOT_VERIFIED) satirlarina bakilir.'
WHERE anahtar = 'kesif_meta_pixel_id';

-- ---------------------------------------------------------------------------
-- 3) GOOGLE ADS ETIKETI  -  hipotez, blocker DEGIL
-- ---------------------------------------------------------------------------
-- 🔴 "Etiket var" ile "aktif hesap var", "harcama var", "nakit eksik"
--    ARASINDA UC AYRI SICRAMA var ve hicbiri olculmedi.
--    Onceki kayit "harcama varsa nakit tablosu EKSIKTIR" diyordu - bu bir
--    kosullu ifade olsa da bir BLOCKER gibi okunuyordu.
UPDATE core.ayar SET
  deger = 'DISCOVERED_UNREGISTERED_GOOGLE_ADS_TAG',
  aciklama = 'AW-17698757160 GTM container''inda bulundu ve sayfada yukleniyor '
             '(17.09.2026 olcumu). SISTEMDE KAYITLI DEGILDI. '
             '🔴 BU BIR BLOCKER DEGILDIR ve su anda bir bulgu bile degil, '
             'bir ARASTIRMA HIPOTEZIDIR: '
             'etiketin varligi != aktif Google Ads hesabi != guncel harcama != eksik nakit. '
             'Uc sicrama da OLCULMEDI. '
             'DOGRULAMA SIRASI: (1) hesap erisimi var mi, (2) hesapta aktif kampanya '
             'var mi, (3) harcama var mi. Ucu de dogrulanirsa nakit tablosu gozden '
             'gecirilir; o zamana kadar nakit rakamlari EKSIK SAYILMAZ.'
WHERE anahtar = 'kesif_google_ads_etiketi';

-- ---------------------------------------------------------------------------
-- 4) CR-017 DURUMU  -  IMPLEMENTATION_COMPLETE, FULLY_LOCKED DEGIL
-- ---------------------------------------------------------------------------
-- 🔴 Pipeline GERCEK GA4 verisiyle en az BIR ingestion + reconciliation turu
--    gormeden "fully validated" sayilamaz. Bugun raw.ga4_event BOS; view'lar
--    sentetik veriyle sinandi ama URETIM VERISIYLE calismadi.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('cr017_durum', 'IMPLEMENTATION_COMPLETE',
   'Sema, event sozlesmesi, kapsama modeli, mutabakat ve testler KURULDU ve gecti. '
   'ANCAK: FULLY_LOCKED / FULLY_OPERATIONAL DEGIL.'),
  ('cr017_ga4_ingestion', 'BLOCKED_BY_EXTERNAL_CREDENTIAL',
   'GA4 Data API credential ve property ID yok. Uydurulmadi.'),
  ('cr017_validation', 'PENDING_FIRST_REAL_INGESTION',
   '🔴 Funnel truth katmani GERCEK GA4 verisiyle en az bir ingestion + reconciliation '
   'turu gormeden FULLY VALIDATED sayilmaz. Bugunku testler SENTETIK veriyle '
   '(rollback''li) yapildi; uretim verisiyle calismadi.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 5) TEST / INTERNAL TRAFIK AYRIMI  -  yok, GAP olarak kaydedilir
-- ---------------------------------------------------------------------------
-- 🔴 FILTRE UYDURULMADI. Bugun boyle bir ayrim YOK.
--    Growth OS tarafinda kirlenme YOK cunku raw.ga4_event BOS - test
--    trafigi ambara hic girmedi. Ama GA4 PROPERTY'sinde bugunku discovery
--    oturumu KAYITLIDIR ve ileride veri cekilirse iceri gelir.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('test_trafik_ayrimi', 'YOK',
   '🔴 Internal/test/bot trafik ayrimi KURULU DEGIL ve filtre UYDURULMADI. '
   'BUGUNKU DURUM: Growth OS behavioral metrikleri KIRLENMEDI cunku raw.ga4_event '
   'BOS - discovery sirasindaki test page_view/add-to-cart ambara HIC girmedi. '
   'ANCAK GA4 property''sinde bu oturum KAYITLIDIR (17.09.2026, 1 oturum, '
   'yaklasik 6 page_view + 1 view_item + 1 sepete ekleme). Data API baglandiginda '
   'bu trafik de gelecektir. '
   'ONERI (uygulanmadi): GA4''te internal traffic IP filtresi ya da debug_mode '
   'isaretleyicisi - ikisi de GA4 panelinde insan islemi gerektirir.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 6) KAPSAMA MATRISI  -  her boyut KENDI statusunu tasir
-- ---------------------------------------------------------------------------
-- 🔴 TEK BIR "GA4 calisiyor mu" CEVABI YOK ve olmayacak. Asagidaki her satir
--    ayri bir soruya cevap verir; biri digerini EZMEZ.
DROP VIEW IF EXISTS mart.davranis_kapsama_matrisi CASCADE;

CREATE VIEW mart.davranis_kapsama_matrisi AS
SELECT 1 AS sira, 'SITE GA4 CONNECTION' AS boyut,
       (SELECT current_connection FROM core.source_authority WHERE alan='behavior_site_tracking') AS durum,
       'GA4 G-KCPFLRG2RV sitede canli, page_view gonderiyor (olculdu)' AS kanit
UNION ALL
SELECT 2, 'GROWTH OS GA4 INGESTION',
       (SELECT current_connection FROM core.source_authority WHERE alan='behavior'),
       format('raw.ga4_event: %s satir · Data API credential: YOK',
              (SELECT count(*) FROM raw.ga4_event))
UNION ALL
SELECT 3, 'PAGE_VIEW COVERAGE',
       (SELECT CASE WHEN bool_and(enstrumantasyon='MEASURED') THEN 'MEASURED'
                    WHEN bool_or(enstrumantasyon='MEASURED')  THEN 'PARTIAL'
                    ELSE 'NOT_INSTRUMENTED' END
          FROM core.funnel_sayfa_kapsama WHERE adim_kod='LANDING'),
       (SELECT format('%s/%s sayfada olculdu',
                      count(*) FILTER (WHERE enstrumantasyon='MEASURED'), count(*))
          FROM core.funnel_sayfa_kapsama WHERE adim_kod='LANDING')
UNION ALL
SELECT 4, 'VIEW_ITEM COVERAGE — /vireon (reklam landing)',
       (SELECT enstrumantasyon FROM core.funnel_sayfa_kapsama
         WHERE adim_kod='PRODUCT_VIEW' AND sayfa='/vireon'),
       'Reklam trafiginin indigi sayfa - view_item GOZLENMEDI'
UNION ALL
SELECT 5, 'VIEW_ITEM COVERAGE — native product page',
       (SELECT enstrumantasyon FROM core.funnel_sayfa_kapsama
         WHERE adim_kod='PRODUCT_VIEW' AND sayfa='/product-page/vireon-for-men'),
       'Wix native urun sayfasinda view_item GOZLENDI'
UNION ALL
SELECT 6, 'ADD_TO_CART COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='ADD_TO_CART'),
       'Tiklandi, urun sepete eklendi, GA4 istegi OLUSMADI'
UNION ALL
SELECT 7, 'BEGIN_CHECKOUT COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='BEGIN_CHECKOUT'),
       'Ayni alan adi + ayni GTM container -> teknik engel YOK, enstrumantasyon yok'
UNION ALL
SELECT 8, 'PURCHASE COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='PURCHASE'),
       'Gercek siparis gerektirir - OLCULMEDI, tahmin de URETILMEDI'
UNION ALL
SELECT 9, 'PURCHASE↔WIX RECONCILIATION',
       (SELECT durum FROM mart.ga4_siparis_mutabakat),
       (SELECT format('GA4 %s / Wix %s · eslesen %s · GA4_ONLY %s · WIX_ONLY %s',
                      ga4_purchase_sayisi, wix_siparis_sayisi, eslesen, ga4_only, wix_only)
          FROM mart.ga4_siparis_mutabakat)
UNION ALL
SELECT 10, 'META BROWSER PIXEL EVENT COVERAGE',
       (SELECT deger FROM core.ayar WHERE anahtar='meta_browser_pixel_event_coverage'),
       'Yalniz tarayici pikseli icin gecerli'
UNION ALL
SELECT 11, 'META TOTAL OPTIMIZATION SIGNAL',
       (SELECT deger FROM core.ayar WHERE anahtar='meta_total_optimization_signal'),
       'CAPI / server-side / native entegrasyon OLCULMEDI'
UNION ALL
SELECT 12, 'GOOGLE ADS TAG',
       (SELECT deger FROM core.ayar WHERE anahtar='kesif_google_ads_etiketi'),
       'Etiket bulundu; hesap/harcama DOGRULANMADI - blocker DEGIL'
ORDER BY 1;

COMMENT ON VIEW mart.davranis_kapsama_matrisi IS
  'Davranis olcumunun HER BOYUTU ayri statu tasir. Tek bir global "GA4 calisiyor" cevabi YOKTUR.';

COMMIT;