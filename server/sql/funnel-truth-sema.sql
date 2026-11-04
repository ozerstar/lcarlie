-- =============================================================================
-- L'CARLIE - GA4 / FUNNEL TRUTH LAYER  (CR-017)
--
-- AMAC "GA4 baglamak" DEGIL. Amac: kullanici davranisini ve ticari funnel'i,
--      "OLCULMEDI" ile "GERCEKTEN GERCEKLESMEDI" durumlarini birbirine
--      KARISTIRMADAN, kanita dayali ve mutabakat yapilabilir sekilde kurmak.
--
-- 🔴🔴 UC DURUM ASLA BIRBIRINE KARISMAZ:
--      OBSERVED      -> enstrumantasyon saglikli VE olay gorulduk
--      NOT_OBSERVED  -> enstrumantasyon saglikli AMA olay olmadi
--      NOT_MEASURED  -> enstrumantasyon YOK; olayin olup olmadigi BILINMIYOR
--    "add_to_cart = 0" ile "add_to_cart olculmuyor" AYNI SEY DEGILDIR.
--    Birincisi bir is bulgusudur, ikincisi bir olcum acigidir.
--
-- 🔴 GA4 ASLA: order authority · payment authority · revenue authority ·
--    realized revenue authority · contribution authority OLMAZ.
--    GA4 purchase, DAVRANIS GOZLEMIDIR; ticari siparis gercegi Wix/core'dadir.
--
-- 🔴 BU DOSYA HICBIR OLCUMU UYDURMAZ. Asagidaki kapsama degerleri
--    17.09.2026'da TARAYICIDA, AG TRAFIGI UZERINDEN olculdu (bkz. kanit
--    kolonu). Olculmeyen hicbir adim "calisiyor" diye isaretlenmedi.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0) SEMANTIK DUZELTME  -  behavior artik PARTIAL DEGIL
-- ---------------------------------------------------------------------------
-- 🔴 CR-017'nin ILK regresyon sozlesmesi.
--    'PARTIAL' = "kismen VERI mevcut" demektir. Davranis verisi ambarda
--    SIFIR satir. GTM'in sitede olmasi bir BEHAVIOR COVERAGE DEGILDIR -
--    o yalnizca bir kesif/kanit bulgusudur ve gap metninde durur.
--    Onceki hali okuyana "kismen davranis verimiz var" dedirtiyordu.
UPDATE core.source_authority SET
  current_connection = 'SOURCE_NOT_CONNECTED',
  gap = 'AMBARDA SIFIR DAVRANIS SATIRI VAR. GA4 Data API baglantisi YOK, '
        'credential YOK, ETL YOK. Onceki "PARTIAL" etiketi YANLISTI: PARTIAL '
        '"kismen veri mevcut" demektir, oysa tek satir bile akmiyor. '
        'KESIF BULGUSU (17.09.2026, tarayicida AG TRAFIGI ile olculdu): '
        'GTM-5XR5TQKP canli · GA4 G-KCPFLRG2RV YAPILANDIRILMIS ve page_view '
        'GONDERIYOR · Google Ads AW-17698757160 da yukleniyor · Meta pikseli '
        '2469140530193842 PageView gonderiyor · Consent Mode ozel banner ile '
        'kurulu (lcarLie_consent_update). '
        'YANI: tarayici tarafinda GA4 CALISIYOR ama VERI AMBARA GELMIYOR. '
        'Ikisi ayri sorundur; bu satir IKINCISINI olcer.',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = 'Tarayici ag trafigi olcumu (performance resource timing) + GTM container okumasi'
WHERE alan = 'behavior';

-- ---------------------------------------------------------------------------
-- 1) EVENT CONTRACT  -  kanonik davranis olayi sozlesmesi
-- ---------------------------------------------------------------------------
-- 🔴 GA4 Data API henuz bagli DEGIL. Bu tablo BOS kalacak ve bos olmasi
--    KANITTIR: mart.funnel_saglik hicbir adimi "olculuyor" gostermez.
--    Alan listesi GA4 Data API'nin GERCEK alanlarina gore secildi; GA4'te
--    karsiligi olmayan alan UYDURULMADI.
CREATE TABLE IF NOT EXISTS raw.ga4_event (
  ga4_event_id     bigserial PRIMARY KEY,
  -- kimlik / zaman
  event_name       text        NOT NULL,
  event_timestamp  timestamptz NOT NULL,
  event_date       date        NOT NULL,
  user_pseudo_id   text,                 -- GA4 anonim kimlik
  session_id       text,                 -- ga_session_id
  -- sayfa
  page_location    text,
  page_path        text,
  -- trafik kaynagi
  source           text,
  medium           text,
  campaign         text,
  content          text,
  term             text,
  -- e-ticaret (yalniz ilgili event'lerde dolar)
  transaction_id   text,
  currency         text,
  value            numeric,
  item_id          text,
  item_name        text,
  quantity         numeric,
  -- 🔴 KANIT DURUMU her satirda tasinir; sonradan yorum yapilmaz.
  kanit_durumu     text NOT NULL DEFAULT 'OBSERVED'
                   CHECK (kanit_durumu IN ('OBSERVED','CONSENT_LIMITED','SAMPLED','SUSPECT')),
  ham              jsonb,
  cekim_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- 🔴 IDEMPOTENCY / DUPLICATE KORUMASI.
--    Ayni event ikinci kez cekilirse tekrar YAZILMAZ. purchase icin
--    transaction_id ayrica tekillestirilir (asagida).
-- 🔴 transaction_id TEKILLIK ANAHTARINA DAHIL (17.09.2026 duyarlilik
--    sinamasinda bulundu). Ilk surumde anahtar
--    (event_name, event_timestamp, user_pseudo_id, session_id, item_id) idi.
--    GA4 ayni saniyede, user_pseudo_id/session_id tasimayan IKI FARKLI
--    purchase dondurdugunde bu anahtar CAKISIYOR ve ikinci gercek islem
--    ETL'i patlatarak iceri alinamiyordu. Yani tekillik korumasi, ayirt
--    edici alani disarida biraktigi icin GERCEK VERIYI ENGELLIYORDU.
DROP INDEX IF EXISTS raw.ga4_event_tekil;
CREATE UNIQUE INDEX IF NOT EXISTS ga4_event_tekil
  ON raw.ga4_event (event_name, event_timestamp, coalesce(user_pseudo_id,''),
                    coalesce(session_id,''), coalesce(item_id,''),
                    coalesce(transaction_id,''));

-- 🔴 BIR purchase, BIR transaction_id. Ayni transaction_id iki kez gelirse
--    bu index patlar - "duplicate purchase" sessizce ciroyu iki katina
--    cikaramaz. transaction_id NULL olan purchase'lar bu korumanin
--    DISINDADIR ve mart tarafinda ayrica isaretlenir.
CREATE UNIQUE INDEX IF NOT EXISTS ga4_purchase_tekil
  ON raw.ga4_event (transaction_id)
  WHERE event_name = 'purchase' AND transaction_id IS NOT NULL;

COMMENT ON TABLE raw.ga4_event IS
  'GA4 Data API gozlemsel event aynasi. BOS OLMASI KANITTIR: baglanti yoksa hicbir adim olculuyor sayilmaz.';

-- ---------------------------------------------------------------------------
-- 2) FUNNEL ADIM KAPSAMASI  -  OLCULEN enstrumantasyon durumu
-- ---------------------------------------------------------------------------
-- 🔴 BU TABLONUN VAR OLMA SEBEBI: "event ambarda yok" iki farkli seyin
--    sonucu olabilir - (a) enstrumantasyon yok, (b) ETL yok. Ikisi ayri
--    is gerektirir. Bu tablo (a)'yi TARAYICI OLCUMUYLE kaydeder; (b)
--    raw.ga4_event'in bosluguyla zaten gorunur.
CREATE TABLE IF NOT EXISTS core.funnel_adim (
  adim_kod        text PRIMARY KEY,
  sira            int  NOT NULL,
  ad              text NOT NULL,
  ga4_event_adi   text,
  -- Enstrumantasyon durumu (TARAYICIDA OLCULDU)
  enstrumantasyon text NOT NULL
                  CHECK (enstrumantasyon IN ('MEASURED','NOT_INSTRUMENTED',
                                             'PARTIAL','DEGRADED','UNKNOWN','NOT_TESTED')),
  -- Hangi sayfada olculdu ve NE GORULDU
  olcum_yeri      text,
  olcum_kaniti    text NOT NULL,
  olcum_zamani    timestamptz NOT NULL DEFAULT clock_timestamp(),
  olcum_yontemi   text NOT NULL,
  notlar          text
);

COMMENT ON TABLE core.funnel_adim IS
  'Funnel adimlarinin ENSTRUMANTASYON durumu. Tarayici ag trafigiyle olculdu; varsayim yok.';

-- ---------------------------------------------------------------------------
-- 3) OLCULEN DURUM  (17.09.2026 tarayici olcumu)
-- ---------------------------------------------------------------------------
INSERT INTO core.funnel_adim
  (adim_kod, sira, ad, ga4_event_adi, enstrumantasyon, olcum_yeri, olcum_kaniti, olcum_yontemi, notlar)
SELECT * FROM (VALUES
  ('LANDING', 1, 'Oturum / iniş', 'page_view', 'MEASURED',
   '/vireon · /product-page/vireon-for-men · /cart · /checkout',
   'Dort sayfada da GA4 collect istegi en=page_view ile gozlendi. _ga ve '
   '_ga_KCPFLRG2RV cerezleri olusuyor.',
   'performance.getEntriesByType(resource) uzerinden /g/collect istekleri',
   'GA4 Enhanced Measurement aktif: scroll event''i de gozlendi.'),

  ('PRODUCT_VIEW', 2, 'Ürün görüntüleme', 'view_item', 'PARTIAL',
   '/product-page/vireon-for-men (VAR) · /vireon (YOK)',
   '🔴 NATIVE Wix urun sayfasinda en=view_item GONDERILIYOR. '
   'ANCAK reklamlarin gittigi OZEL LANDING sayfasinda (/vireon) YALNIZ '
   'page_view var, view_item YOK. Yani en cok trafik alan sayfa '
   'urun goruntuleme olarak SAYILMIYOR.',
   'Iki sayfada ayri ayri ag trafigi olcumu',
   'Kapsama sayfaya gore degisiyor -> PARTIAL. Reklam trafiginin cogu '
   'olculmeyen sayfaya iniyor olabilir; bu ayrica dogrulanmali.'),

  ('ADD_TO_CART', 3, 'Sepete ekleme', 'add_to_cart', 'NOT_INSTRUMENTED',
   '/product-page/vireon-for-men',
   '🔴 SEPETE EKLE butonuna TIKLANDI, urun sepete GERCEKTEN eklendi '
   '(sepet sayfasinda VIREON FOR MEN 1.200,00 TL gorundu) - buna ragmen '
   'HICBIR yeni GA4 collect istegi olusmadi. Yani olay gerceklesti, '
   'olcum gerceklesmedi.',
   'Gercek tiklama + sonrasinda collect istegi sayimi (6 -> 6, artis YOK)',
   'Bu adim icin "0 sepete ekleme" YAZILAMAZ: NOT_MEASURED''dir.'),

  ('VIEW_CART', 4, 'Sepet görüntüleme', 'view_cart', 'NOT_INSTRUMENTED',
   '/cart',
   'Sepet sayfasinda yalniz en=page_view gozlendi; view_cart YOK.',
   'Ag trafigi olcumu', NULL),

  ('BEGIN_CHECKOUT', 5, 'Ödeme adımına giriş', 'begin_checkout', 'NOT_INSTRUMENTED',
   '/checkout',
   'Odeme sayfasinda yalniz page_view ve scroll gozlendi; begin_checkout YOK. '
   '🔴 ONEMLI: checkout AYNI ALAN ADINDA (www.lcarlie.shop) ve AYNI GTM '
   'container''i yukluyor - yani iframe/cross-domain ENGELI YOK. '
   'Eksiklik teknik engelden degil, enstrumantasyon yoklugundan.',
   'Ag trafigi + document.domain + google_tag_manager container kontrolu',
   'Tek iframe www-lcarlie-shop.filesusr.com (Wix statik dosya sunucusu), '
   'odeme akisini engellemiyor.'),

  ('PURCHASE', 6, 'Satın alma', 'purchase', 'NOT_TESTED',
   '(test edilmedi)',
   '🔴 OLCULMEDI ve UYDURULMADI. purchase event''ini dogrulamak GERCEK bir '
   'siparis vermeyi gerektirir - bu para harcamaktir ve insan onayi ister. '
   'Diger adimlarin hicbirinde ecommerce event''i gorulmedigi icin '
   'purchase''in da calismama IHTIMALI yuksektir, ama bu bir TAHMINDIR, '
   'olcum degildir.',
   'Yapilmadi - kasitli',
   'Dogrulama yolu: gercek bir siparis sonrasi GA4 DebugView, ya da '
   'Wix''in kendi analytics raporu.')
) AS v(adim_kod, sira, ad, ga4_event_adi, enstrumantasyon, olcum_yeri, olcum_kaniti, olcum_yontemi, notlar)
WHERE NOT EXISTS (SELECT 1 FROM core.funnel_adim f WHERE f.adim_kod = v.adim_kod);

-- 🔴 Rerun-safe: olcum yenilenirse etiket guncellenir, satir cogalmaz.
--
-- 🔴 25.09.2026 - IKI KUSUR DUZELTILDI.
--
-- (1) BLOK HICBIR SEY YAPMIYORDU. Eski hali `enstrumantasyon = v.enstrumantasyon`
--     yaziyordu ve `v`, core.funnel_adim'in KENDISIYDI (self-join). Yani satiri
--     kendi uzerine kopyaliyordu: WHERE kosulu tutsa bile etiket DEGISMIYORDU.
--     "Rerun-safe" diye yazilmis blok, yeniden olcum yapilsa onu uygulamazdi.
--     Artik deger x.ens'ten geliyor; digerleri (olcum_kaniti, olcum_yeri,
--     olcum_yontemi, notlar) BILEREK burada set EDILMIYOR -- onlar olcume ait
--     kanit metinleridir ve kendi yama dosyalarindan gelir, burada donmus bir
--     kopyalarini tutmak eski kaniti diriltmek olurdu.
--
-- (2) DEGERLER GUNCELLENDI. BEGIN_CHECKOUT ve PURCHASE, 17.09.2026'da GA4 Data
--     API ambara BAGLANMADAN once tarayici ag trafigiyle etiketlenmisti.
--     25.09.2026 olcumu (raw.ga4_event, ham->>'eventCount'):
--       begin_checkout  29 gunde 70 olay   -> olay ATILIYOR
--       purchase         9 gunde 10 olay   -> uretimde GOZLENDI, test gerekmiyor
--     Ikisi de PARTIAL: calisiyor ama EKSIK sayiyor (GA4, 01.08'den beri
--     Wix'teki 14 siparisin 8'ini yakaliyor, %57).
--     Kanit ve gerekce: sql/funnel-etiket-duzelt-20260925.sql
--
--     ⚠ Bu listeyi eski degerlere geri cevirmek, mutabakat.sql'in 23.
--     kontrolunu ("enstrumantasyonsuz adim OBSERVED olamaz") her gun FAILED'a
--     dusurur ve gunluk yanlis alarm e-postasini geri getirir.
UPDATE core.funnel_adim f SET
  enstrumantasyon = x.ens
FROM (VALUES
  -- ADD_TO_CART da 17.09 sonrasi duzeltilmisti (DB'de PARTIAL, 37 gunde 241
  -- olay). Bu listede eski degeriyle birakmak, BASKASININ duzeltmesini geri
  -- almak olurdu -- ilk yazisimda tam bunu yapiyordum, tek satirlik bir
  -- rollback denemesi yakaladi (UPDATE 1 dedi, 0 demeliydi).
  ('LANDING','MEASURED'), ('PRODUCT_VIEW','PARTIAL'), ('ADD_TO_CART','PARTIAL'),
  ('VIEW_CART','NOT_INSTRUMENTED'), ('BEGIN_CHECKOUT','PARTIAL'), ('PURCHASE','PARTIAL')
) AS x(kod, ens)
WHERE f.adim_kod = x.kod AND f.enstrumantasyon IS DISTINCT FROM x.ens;

-- ---------------------------------------------------------------------------
-- 4) EK KESIF BULGULARI  -  sisteme kayitli olmayan etiketler
-- ---------------------------------------------------------------------------
-- 🔴 Google Ads etiketi sistemde HIC KAYITLI DEGILDI. Kesifte bulundu.
--    Bu bir REKLAM HARCAMASI kaynagi olabilir ve Meta disinda bir kanal
--    demektir - nakit tablosu bugun yalniz Meta'yi biliyor.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('kesif_google_ads_etiketi', 'AW-17698757160',
   '🔴 17.09.2026 kesfi: GTM container''inda Google Ads donusum etiketi var ve '
   'sayfada yukleniyor. SISTEMDE KAYITLI DEGILDI. Google Ads hesabinda AKTIF '
   'harcama varsa nakit tablosu EKSIKTIR (bugun yalniz Meta okunuyor). '
   'DOGRULANMADI: harcama var mi yok mu olculmedi - insan teyidi gerekir.'),
  ('kesif_ga4_measurement_id', 'G-KCPFLRG2RV',
   '17.09.2026 tarayici olcumu: GA4 yapilandirilmis ve page_view gonderiyor.'),
  ('kesif_meta_pixel_id', '2469140530193842',
   '17.09.2026: Meta pikseli PageView gonderiyor. ViewContent/AddToCart GOZLENMEDI - '
   'yani Meta''nin optimizasyon sinyali de yalniz sayfa goruntulemeyle sinirli.'),
  ('kesif_consent_mode', 'OZEL_BANNER',
   'dataLayer''a lcarLie_consent_update push ediliyor (analytics_storage / ad_storage / '
   'ad_user_data / ad_personalization). Consent Mode KURULU. Onay verilmeden olcum '
   'kisitlanmasi TRACKING ARIZASI DEGILDIR - CONSENT_LIMITED olarak siniflanir.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

COMMIT;
