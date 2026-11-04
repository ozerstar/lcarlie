-- =============================================================================
-- L'CARLIE - URUN BAGIMSIZLIK YAMASI  (CR-017 kapsam duzeltmesi, 17.09.2026)
--
-- 🔴 DUZELTILEN HATA: MIMARI VIREON'A GOMULMUSTU.
--    Iki ayri yerde urun/sayfa literal'i IS MANTIGINDAYDI:
--      1) FIYAT OTORITESI  -> core.ayar.vireon_* anahtarlari +
--                             mart.fiyat_gercegi icinde `ad ILIKE '%vireon%'`
--      2) FUNNEL KAPSAMASI -> '/vireon' ve '/product-page/vireon-for-men'
--                             view govdesine yazilmisti
--    Yarin FEMISIA / INTIMBLANC / HYDRAVIE eklendiginde ikisi de YENI KOD
--    gerektirirdi. Vireon yalnizca ILK KANIT ORNEGIDIR; sistem L'CARLIE
--    GENELI icindir.
--
-- 🔴 BASARI KOSULU: "Yarin yeni bir urun eklenirse, yeni SQL/view/funnel
--    mantigi YAZMADAN ayni modeli kullanabilir miyiz?" -> EVET olmali.
--    Bu yama iki registry kuruyor ve view'lari onlardan turetiyor:
--      core.urun_fiyat_gercegi  (urun basina fiyat gercegi)
--      core.sayfa_urun          (sayfa <-> urun haritasi, OTOMATIK dolar)
--
-- 🔴 VIREON DEGERLERI SILINMIYOR - registry'ye SATIR olarak tasiniyor.
--    Literal olmaktan cikip VERI oluyorlar. Discovery kaniti da korunuyor.
-- =============================================================================

BEGIN;

-- ===========================================================================
-- 1) URUN BASINA FIYAT GERCEGI  (core.ayar.vireon_* yerine)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS core.urun_fiyat_gercegi (
  urun_id            text PRIMARY KEY,
  base_price         numeric,
  kampanya_fiyati    numeric,
  fiyat_durumu       text NOT NULL DEFAULT 'NORMAL'
                     CHECK (fiyat_durumu IN ('NORMAL','CAMPAIGN','UNKNOWN')),
  kampanya_suresi    text,
  kampanya_kaynagi   text,
  kampanya_bitisi    text,
  -- 🔴 Karsilastirmali fiyat izni URUN BAZINDADIR: bir urunun gecmis fiyat
  --    kaniti varken digerininki olmayabilir.
  karsilastirma_izni text NOT NULL DEFAULT 'HAYIR'
                     CHECK (karsilastirma_izni IN ('EVET','HAYIR')),
  gerekce            text,
  guncelleme         timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE core.urun_fiyat_gercegi IS
  'ISLETME fiyat gercegi, URUN BASINA. Wix vitrini otorite DEGILDIR - karsilastirma mart.fiyat_gercegi''nde.';

-- 🔴 GOC: core.ayar.vireon_* -> registry satiri.
--    urun_id LITERAL DEGIL, katalogdan deterministik bulunuyor.
INSERT INTO core.urun_fiyat_gercegi
  (urun_id, base_price, kampanya_fiyati, fiyat_durumu, kampanya_suresi,
   kampanya_kaynagi, kampanya_bitisi, karsilastirma_izni, gerekce)
SELECT u.urun_id,
       (SELECT deger FROM core.ayar WHERE anahtar='vireon_base_price')::numeric,
       (SELECT deger FROM core.ayar WHERE anahtar='vireon_current_selling_price')::numeric,
       coalesce((SELECT deger FROM core.ayar WHERE anahtar='vireon_price_state'),'UNKNOWN'),
       (SELECT deger FROM core.ayar WHERE anahtar='vireon_campaign_duration'),
       (SELECT deger FROM core.ayar WHERE anahtar='vireon_campaign_source'),
       (SELECT deger FROM core.ayar WHERE anahtar='vireon_campaign_end'),
       coalesce((SELECT deger FROM core.ayar WHERE anahtar='vireon_comparative_claim_allowed'),'HAYIR'),
       'core.ayar.vireon_* anahtarlarindan tasindi (17.09.2026 urun bagimsizlik yamasi). '
       'Sahip dogrulamasi: base 2400, kampanya 1200, 10 gunluk gecici kampanya, '
       'bitis tarihi Wix''te YOK -> OWNER_INPUT_REQUIRED.'
  FROM raw.wix_urun u
 WHERE u.ad ILIKE '%vireon%'          -- <- GOC SORGUSU, is mantigi DEGIL
   AND EXISTS (SELECT 1 FROM core.ayar WHERE anahtar='vireon_base_price')
ON CONFLICT (urun_id) DO NOTHING;

-- 🔴 DIGER TUM URUNLER icin de satir acilir: fiyat gercegi BILINMIYOR olarak
--    DURUR. Bos birakilsaydi "fiyati bilinen tek urun Vireon" gibi bir
--    sessizlik olurdu; simdi 36 urunun 35'inin fiyat gercegi ACIKCA eksik.
INSERT INTO core.urun_fiyat_gercegi (urun_id, fiyat_durumu, gerekce)
SELECT u.urun_id, 'UNKNOWN',
       'Isletme fiyat gercegi BEYAN EDILMEDI. Wix vitrini bir GOZLEMDIR, otorite degildir; '
       'base price / kampanya durumu sahip beyani gerektirir.'
  FROM raw.wix_urun u
 WHERE NOT EXISTS (SELECT 1 FROM core.urun_fiyat_gercegi f WHERE f.urun_id = u.urun_id);

-- ===========================================================================
-- 2) SAYFA <-> URUN HARITASI  (funnel icin, OTOMATIK dolar)
-- ===========================================================================
-- 🔴 YENI URUN EKLENDIGINDE KOD YAZILMAZ: native urun sayfalari Wix
--    katalogundan (productPageUrl) KENDILIGINDEN turer. Yalnizca OZEL
--    landing sayfalari elle eslenir - cunku onlar Wix'te urunle bagli degil.
CREATE TABLE IF NOT EXISTS core.sayfa_urun (
  sayfa_yolu   text PRIMARY KEY,
  urun_id      text,                 -- NULL = urun-disi sayfa (sepet/odeme/anasayfa)
  sayfa_rolu   text NOT NULL
               CHECK (sayfa_rolu IN ('NATIVE_URUN','OZEL_LANDING','KAMPANYA_LANDING',
                                     'KATEGORI','ANASAYFA','SEPET','ODEME','ICERIK','DIGER')),
  kaynak       text NOT NULL,        -- OTOMATIK_WIX / ELLE
  notlar       text,
  guncelleme   timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE core.sayfa_urun IS
  'Sayfa <-> urun haritasi. Native urun sayfalari Wix katalogundan OTOMATIK turer; ozel landing''ler elle eslenir.';

-- 2a) NATIVE URUN SAYFALARI - tum katalogdan otomatik
INSERT INTO core.sayfa_urun (sayfa_yolu, urun_id, sayfa_rolu, kaynak, notlar)
SELECT u.ham#>>'{productPageUrl,path}', u.urun_id, 'NATIVE_URUN', 'OTOMATIK_WIX',
       'Wix katalogundan turetildi - yeni urun eklendiginde kendiliginden gelir.'
  FROM raw.wix_urun u
 WHERE u.ham#>>'{productPageUrl,path}' IS NOT NULL
ON CONFLICT (sayfa_yolu) DO UPDATE
  SET urun_id = EXCLUDED.urun_id, sayfa_rolu = EXCLUDED.sayfa_rolu,
      kaynak = EXCLUDED.kaynak, guncelleme = clock_timestamp();

-- 2b) URUN-DISI SAYFALAR
INSERT INTO core.sayfa_urun (sayfa_yolu, urun_id, sayfa_rolu, kaynak, notlar) VALUES
  ('/cart',     NULL, 'SEPET',    'ELLE', 'Urun-disi akis sayfasi'),
  ('/checkout', NULL, 'ODEME',    'ELLE', 'Urun-disi akis sayfasi'),
  ('/',         NULL, 'ANASAYFA', 'ELLE', 'Urun-disi akis sayfasi')
ON CONFLICT (sayfa_yolu) DO NOTHING;

-- 2c) OZEL LANDING SAYFALARI
-- 🔴 Bunlar Wix'te urunle BAGLI DEGIL, o yuzden elle eslenir. Yeni bir
--    landing acildiginda BURAYA BIR SATIR eklenir - view/SQL degismez.
--    Bugun bilinen tek ornek Vireon'unki; digerleri geldiginde ayni desen.
INSERT INTO core.sayfa_urun (sayfa_yolu, urun_id, sayfa_rolu, kaynak, notlar)
SELECT '/vireon', u.urun_id, 'OZEL_LANDING', 'ELLE',
       'Reklam trafiginin indigi ozel landing. Wix urun sayfasi DEGIL, o yuzden '
       'katalogdan turetilemez ve elle eslenmistir.'
  FROM raw.wix_urun u WHERE u.ad ILIKE '%vireon%'
ON CONFLICT (sayfa_yolu) DO UPDATE
  SET urun_id = EXCLUDED.urun_id, sayfa_rolu = EXCLUDED.sayfa_rolu,
      notlar = EXCLUDED.notlar, guncelleme = clock_timestamp();

-- 2d) funnel kapsamasina URUN bagi
ALTER TABLE core.funnel_sayfa_kapsama
  ADD COLUMN IF NOT EXISTS urun_id text;

UPDATE core.funnel_sayfa_kapsama k
   SET urun_id = s.urun_id
  FROM core.sayfa_urun s
 WHERE s.sayfa_yolu = k.sayfa AND k.urun_id IS DISTINCT FROM s.urun_id;

-- ===========================================================================
-- 3) FIYAT GERCEGI  -  URUN BAGIMSIZ
-- ===========================================================================
DROP VIEW IF EXISTS mart.fiyat_gercegi CASCADE;

CREATE VIEW mart.fiyat_gercegi AS
WITH w AS (
  -- 🔴 DETERMINISTIK JOIN: urun_id uzerinden. Urun ADI ile eslestirme YOK.
  SELECT u.urun_id, u.ad,
         (u.ham#>>'{priceData,price}')::numeric           AS wix_liste,
         (u.ham#>>'{priceData,discountedPrice}')::numeric AS wix_satis,
         (u.ham#>>'{visible}')                            AS wix_yayinda
    FROM raw.wix_urun u
)
SELECT
  f.urun_id, w.ad AS urun_adi,
  f.base_price, f.kampanya_fiyati, f.fiyat_durumu,
  f.kampanya_suresi, f.kampanya_kaynagi, f.kampanya_bitisi, f.karsilastirma_izni,
  w.wix_liste, w.wix_satis, w.wix_yayinda,

  CASE WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
       WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
  END                                                    AS beklenen_satis,

  -- 🔴 OTORITE SIRASI: musteriye soylenecek fiyat ISLETME gercegindendir.
  --    Isletme gercegi BEYAN EDILMEMISSE fiyat UYDURULMAZ -> NULL.
  CASE WHEN f.fiyat_durumu = 'CAMPAIGN' THEN f.kampanya_fiyati
       WHEN f.fiyat_durumu = 'NORMAL'   THEN f.base_price
  END                                                    AS musteriye_soylenecek_fiyat,

  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN'                      THEN 'BUSINESS_TRUTH_MISSING'
    WHEN w.wix_satis IS NULL OR w.wix_liste IS NULL      THEN 'WIX_OKUNAMADI'
    WHEN w.wix_satis IS DISTINCT FROM
         (CASE WHEN f.fiyat_durumu='CAMPAIGN' THEN f.kampanya_fiyati ELSE f.base_price END)
      OR w.wix_liste IS DISTINCT FROM f.base_price       THEN 'PRICE_TRUTH_MISMATCH'
    ELSE 'MATCH'
  END                                                    AS durum,

  CASE
    WHEN f.fiyat_durumu = 'UNKNOWN' THEN
      format('%s: isletme fiyat gercegi BEYAN EDILMEDI. Wix vitrini %s TL gosteriyor ama '
             'bu bir GOZLEMDIR, otorite degildir. Musteriye fiyat soylenecekse once '
             'base price ve kampanya durumu beyan edilmeli.', w.ad, w.wix_satis)
    WHEN w.wix_satis IS DISTINCT FROM
         (CASE WHEN f.fiyat_durumu='CAMPAIGN' THEN f.kampanya_fiyati ELSE f.base_price END)
      OR w.wix_liste IS DISTINCT FROM f.base_price THEN
      format('🔴 PRICE_TRUTH_MISMATCH (%s). Isletme: base %s, %s fiyati %s. '
             'Wix vitrini: liste %s, satis %s. SISTEM HICBIR TARAFI OTOMATIK DUZELTMEZ - '
             'Wix otorite DEGILDIR. Insan karari gerekir.',
             w.ad, f.base_price, f.fiyat_durumu, f.kampanya_fiyati, w.wix_liste, w.wix_satis)
    ELSE format('MATCH (%s): isletme gercegi ile Wix vitrini ortusuyor.', w.ad)
  END                                                    AS aciklama
FROM core.urun_fiyat_gercegi f
JOIN w ON w.urun_id = f.urun_id;

COMMENT ON VIEW mart.fiyat_gercegi IS
  'URUN BASINA isletme fiyat gercegi vs Wix vitrini. Wix otorite DEGILDIR. Urun-bagimsiz.';

-- ===========================================================================
-- 4) FUNNEL KAPSAMA MATRISI  -  URUN x SAYFA x EVENT
-- ===========================================================================
DROP VIEW IF EXISTS mart.funnel_kapsama_matrisi CASCADE;

CREATE VIEW mart.funnel_kapsama_matrisi AS
SELECT
  s.sayfa_yolu, s.sayfa_rolu, s.urun_id,
  u.ad                                                   AS urun_adi,
  f.adim_kod, f.sira AS adim_sira, f.ad AS adim_adi, f.ga4_event_adi,
  -- 🔴 Sayfa bazinda olculmus kapsama VARSA o, yoksa adim geneli.
  --    Olculmemis sayfa "calisiyor" SAYILMAZ -> NOT_TESTED.
  coalesce(k.enstrumantasyon, 'NOT_TESTED')              AS enstrumantasyon,
  coalesce(k.olcum_kaniti, 'Bu sayfada OLCULMEDI - kapsama BILINMIYOR.') AS olcum_kaniti,
  (k.adim_kod IS NOT NULL)                               AS olculdu
FROM core.sayfa_urun s
CROSS JOIN core.funnel_adim f
LEFT JOIN core.funnel_sayfa_kapsama k
       ON k.sayfa = s.sayfa_yolu AND k.adim_kod = f.adim_kod
LEFT JOIN raw.wix_urun u ON u.urun_id = s.urun_id
-- Urun-disi sayfalarda urun event'leri anlamsiz: yalniz LANDING gosterilir.
WHERE s.urun_id IS NOT NULL OR f.adim_kod IN ('LANDING','VIEW_CART','BEGIN_CHECKOUT','PURCHASE')
ORDER BY u.ad NULLS FIRST, s.sayfa_rolu, f.sira;

COMMENT ON VIEW mart.funnel_kapsama_matrisi IS
  'URUN x SAYFA x EVENT kapsama matrisi. Yeni urun/landing eklenince KOD YAZILMADAN buyur.';

-- ===========================================================================
-- 5) DAVRANIS KAPSAMA MATRISI  -  literal sayfa adi YOK
-- ===========================================================================
DROP VIEW IF EXISTS mart.davranis_kapsama_matrisi CASCADE;

CREATE VIEW mart.davranis_kapsama_matrisi AS
SELECT 1 AS sira, 'SITE GA4 CONNECTION' AS boyut,
       (SELECT current_connection FROM core.source_authority WHERE alan='behavior_site_tracking') AS durum,
       'GA4 sitede canli, page_view gonderiyor (olculdu)' AS kanit
UNION ALL
SELECT 2, 'GROWTH OS GA4 INGESTION',
       (SELECT current_connection FROM core.source_authority WHERE alan='behavior'),
       format('raw.ga4_event: %s satir · Data API credential: YOK',
              (SELECT count(*) FROM raw.ga4_event))
UNION ALL
SELECT 3, 'PAGE_VIEW COVERAGE',
       (SELECT CASE WHEN count(*) FILTER (WHERE enstrumantasyon='MEASURED') = count(*) THEN 'MEASURED'
                    WHEN count(*) FILTER (WHERE enstrumantasyon='MEASURED') > 0 THEN 'PARTIAL'
                    ELSE 'NOT_MEASURED' END
          FROM core.funnel_sayfa_kapsama WHERE adim_kod='LANDING'),
       (SELECT format('%s/%s OLCULEN sayfada page_view gozlendi (toplam kayitli sayfa: %s)',
                      count(*) FILTER (WHERE enstrumantasyon='MEASURED'), count(*),
                      (SELECT count(*) FROM core.sayfa_urun))
          FROM core.funnel_sayfa_kapsama WHERE adim_kod='LANDING')
UNION ALL
-- 🔴 SAYFA ROLUNE gore, literal sayfa adiyla DEGIL.
SELECT 4, 'VIEW_ITEM COVERAGE — ozel landing (reklam trafigi)',
       (SELECT coalesce(string_agg(DISTINCT k.enstrumantasyon,'/'),'NOT_TESTED')
          FROM core.funnel_sayfa_kapsama k JOIN core.sayfa_urun s ON s.sayfa_yolu=k.sayfa
         WHERE k.adim_kod='PRODUCT_VIEW' AND s.sayfa_rolu IN ('OZEL_LANDING','KAMPANYA_LANDING')),
       (SELECT format('%s ozel landing kayitli, %s tanesi olculdu',
                      (SELECT count(*) FROM core.sayfa_urun WHERE sayfa_rolu IN ('OZEL_LANDING','KAMPANYA_LANDING')),
                      count(*))
          FROM core.funnel_sayfa_kapsama k JOIN core.sayfa_urun s ON s.sayfa_yolu=k.sayfa
         WHERE k.adim_kod='PRODUCT_VIEW' AND s.sayfa_rolu IN ('OZEL_LANDING','KAMPANYA_LANDING'))
UNION ALL
SELECT 5, 'VIEW_ITEM COVERAGE — native urun sayfasi',
       (SELECT coalesce(string_agg(DISTINCT k.enstrumantasyon,'/'),'NOT_TESTED')
          FROM core.funnel_sayfa_kapsama k JOIN core.sayfa_urun s ON s.sayfa_yolu=k.sayfa
         WHERE k.adim_kod='PRODUCT_VIEW' AND s.sayfa_rolu='NATIVE_URUN'),
       (SELECT format('%s native urun sayfasi kayitli, %s tanesi olculdu - '
                      'kalanlar NOT_TESTED (kapsama varsayilmiyor)',
                      (SELECT count(*) FROM core.sayfa_urun WHERE sayfa_rolu='NATIVE_URUN'),
                      count(*))
          FROM core.funnel_sayfa_kapsama k JOIN core.sayfa_urun s ON s.sayfa_yolu=k.sayfa
         WHERE k.adim_kod='PRODUCT_VIEW' AND s.sayfa_rolu='NATIVE_URUN')
UNION ALL
SELECT 6, 'ADD_TO_CART COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='ADD_TO_CART'),
       'Tiklandi, urun sepete eklendi, GA4 istegi OLUSMADI'
UNION ALL
SELECT 7, 'BEGIN_CHECKOUT COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='BEGIN_CHECKOUT'),
       'Ayni alan adi + ayni GTM container -> teknik engel YOK'
UNION ALL
SELECT 8, 'PURCHASE COVERAGE',
       (SELECT enstrumantasyon FROM core.funnel_adim WHERE adim_kod='PURCHASE'),
       'Gercek siparis gerektirir - OLCULMEDI, tahmin URETILMEDI'
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
UNION ALL
-- 🔴 URUN KAPSAMASI: kac urunun funnel'i olculdu.
SELECT 13, 'URUN KAPSAMASI (funnel olcumu)',
       (SELECT CASE WHEN count(DISTINCT urun_id) FILTER (WHERE olculdu) = 0 THEN 'NOT_TESTED'
                    WHEN count(DISTINCT urun_id) FILTER (WHERE olculdu)
                         < (SELECT count(*) FROM raw.wix_urun) THEN 'PARTIAL'
                    ELSE 'MEASURED' END
          FROM mart.funnel_kapsama_matrisi WHERE urun_id IS NOT NULL),
       (SELECT format('%s/%s urunun funnel''i OLCULDU. Kalanlar NOT_TESTED - '
                      'kapsamalari VARSAYILMIYOR.',
                      count(DISTINCT urun_id) FILTER (WHERE olculdu),
                      (SELECT count(*) FROM raw.wix_urun))
          FROM mart.funnel_kapsama_matrisi WHERE urun_id IS NOT NULL)
UNION ALL
SELECT 14, 'FIYAT GERCEGI KAPSAMASI',
       (SELECT CASE WHEN count(*) FILTER (WHERE fiyat_durumu='UNKNOWN') = 0 THEN 'MEASURED'
                    WHEN count(*) FILTER (WHERE fiyat_durumu<>'UNKNOWN') > 0 THEN 'PARTIAL'
                    ELSE 'NOT_MEASURED' END FROM core.urun_fiyat_gercegi),
       (SELECT format('%s/%s urunun isletme fiyat gercegi beyan edilmis',
                      count(*) FILTER (WHERE fiyat_durumu<>'UNKNOWN'), count(*))
          FROM core.urun_fiyat_gercegi)
ORDER BY 1;

COMMENT ON VIEW mart.davranis_kapsama_matrisi IS
  'Davranis olcumunun her boyutu ayri statu tasir. Sayfa ROLUNE gore turer - literal sayfa adi YOK.';

COMMIT;
