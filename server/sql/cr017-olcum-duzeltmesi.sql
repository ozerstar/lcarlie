-- =============================================================================
-- CR-017  ·  OLCUM DUZELTMESI  (17.09.2026)
--
-- 🔴 BU YAMA ONCEKI RAPORUMDAKI BIR HATAYI DUZELTIYOR.
--
--    ONCEKI IDDIAM : "add_to_cart NOT_INSTRUMENTED - butona tiklandi, urun
--                     sepete eklendi, collect istegi 12 -> 12 degismedi."
--    GERCEK        : add_to_cart GA4'E GIDIYOR.
--
--    HATANIN KOKU  : o olcumu Wix Google Etiketi'ne G-KCPFLRG2RV eklenmeden
--                    ONCE yaptim. O anda add_to_cart tipki view_item gibi
--                    yalniz AW-17698757160'a gidiyordu. Ayari degistirdikten
--                    SONRA yalnizca view_item'i yeniden olctum, add_to_cart'i
--                    olcmedim ve eski sonucu tasidim.
--    DERS          : bir ayar degisikliginin etkisi, etkilenen TUM event'ler
--                    icin yeniden olculmeli; tek event dogrulanip digerlerine
--                    genellenmemeli.
--
-- 🔴 BUGUNKU OLCUM YONTEMI (canli site, www.lcarlie.shop):
--    performance.getEntriesByType('resource') icindeki /g/collect istekleri,
--    her istegin tid ve en parametreleri okunarak.
--
--    NATIVE URUN SAYFASI (/product-page/...) - SEPETE EKLE tiklandi:
--      tid=G-KCPFLRG2RV  en=view_item     ✅
--      tid=G-KCPFLRG2RV  en=add_to_cart   ✅   <-- onceden YOK sanilan
--      tid=G-KCPFLRG2RV  en=page_view     ✅
--    SEPET SAYFASI (/cart):
--      yalniz page_view  -> view_cart YOK  (yeniden olculdu, degismedi)
--    OZEL LANDING (/vireon):
--      yalniz page_view  -> view_item YOK  (yeniden olculdu, degismedi)
--
--    Test kalintisi temizlendi: sepete eklenen urun kaldirildi, sepet bos.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) ADD_TO_CART  -  adim seviyesi
-- ---------------------------------------------------------------------------
-- 🔴 NEDEN 'MEASURED' DEGIL DE 'PARTIAL':
--    Native urun sayfasinda KANITLANDI. Ama sitede sepete eklemenin IKINCI bir
--    yolu var: ozel landing sayfalari masterPage.js icindeki koprü uzerinden
--    cart.addProducts() cagiriyor (programatik). O yolun GA4 event uretip
--    uretmedigi OLCULMEDI. Kapsama sayfa rolune gore degisiyor -> PARTIAL.
--    PRODUCT_VIEW ile birebir ayni gerekce.
UPDATE core.funnel_adim SET
  enstrumantasyon = 'PARTIAL',
  olcum_kaniti = 'DUZELTILDI 17.09.2026. NATIVE urun sayfasinda GA4''e GONDERILIYOR: '
                 'SEPETE EKLE tiklandiginda tid=G-KCPFLRG2RV en=add_to_cart istegi '
                 'gozlendi (currency + items dolu). '
                 'ONCEKI "NOT_INSTRUMENTED" KAYDI YANLISTI: o olcum Wix Google '
                 'Etiketi''ne GA4 eklenmeden ONCE yapilmisti. '
                 '🔴 HALA OLCULMEDI: ozel landing sayfalarindaki koprü yolu '
                 '(cart.addProducts) bu event''i uretiyor mu - BILINMIYOR, '
                 'varsayilmadi.',
  olcum_yeri = 'sayfa rolune gore: NATIVE_URUN = MEASURED · OZEL/REKLAM LANDING = OLCULMEDI',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART';

-- ---------------------------------------------------------------------------
-- 2) ADD_TO_CART  -  sayfa seviyesi
-- ---------------------------------------------------------------------------
-- 🔴 BU UPDATE'IN KOSULU BILEREK STATUYE BAKMIYOR.
--    Ilk surumunde "AND enstrumantasyon IS DISTINCT FROM 'MEASURED'" yazmistim ve
--    BU BIR HATAYDI: raw-uygula.sh zincirinde ga4-instrumentation-yamasi.sql BU
--    DOSYADAN ONCE calisip TUM ADD_TO_CART satirlarinin olcum_kaniti'ni eski
--    (yanlis) metinle eziyor. Statu zaten MEASURED oldugu icin benim UPDATE'im
--    atlaniyor ve ortaya "statu MEASURED ama kanit 'uretmiyor' diyor" celiskisi
--    cikiyordu. Kosul kaldirildi; UPDATE deger bazinda idempotent.
UPDATE core.funnel_sayfa_kapsama SET
  enstrumantasyon = 'MEASURED',
  olcum_kaniti = 'OLCULDU 17.09.2026: native urun sayfasinda SEPETE EKLE sonrasi '
                 'tid=G-KCPFLRG2RV en=add_to_cart collect istegi gozlendi. '
                 'Wix ayrica wixDevelopersAnalytics uzerinden AddToCart standart '
                 'event''ini GERCEK urun kimligiyle uretiyor '
                 '(id, name, price, currency, quantity, sku, variantId) - '
                 'yani DOM kazima / ad eslestirme / slug tahmini GEREKMIYOR.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART'
  AND sayfa_rolu = 'NATIVE_URUN';

-- 🔴 IKINCI SEPETE EKLEME YOLU AYRI BIR SATIR OLMALI.
--    Bu satir bilerek NOT_TESTED: "olculdu ve yok" DEGIL, "hic olculmedi".
--    NOT_INSTRUMENTED yazmak, olculmemis bir alani olculmus gibi gosterirdi.
INSERT INTO core.funnel_sayfa_kapsama (adim_kod, sayfa, sayfa_rolu, enstrumantasyon, olcum_kaniti)
SELECT 'ADD_TO_CART', k.sayfa, 'REKLAM_LANDING', 'NOT_TESTED',
       'OLCULMEDI 17.09.2026. Ozel landing sayfasi sepete eklemeyi masterPage.js '
       'icindeki postMessage koprüsü ile yapiyor: cart.addProducts(). '
       'Bu PROGRAMATIK bir ekleme; Wix''in native SEPETE EKLE butonu degil. '
       'Mevcut kod bu yolda syncCartCount()''u ELLE cagiriyor (masterPage.js:1145) - '
       'yani native cart olayinin bu yolda atesledigi KANITLI degil. '
       'Analytics AddToCart event''inin bu yolda uretilip uretilmedigi ise AYRI bir '
       'mekanizma ve OLCULMEDI: iframe icerigi cross-origin oldugu icin butona '
       'tarayici otomasyonuyla ulasilamadi. VARSAYILMADI.'
  FROM core.funnel_sayfa_kapsama k
 WHERE k.adim_kod = 'PRODUCT_VIEW' AND k.sayfa_rolu = 'REKLAM_LANDING'
   AND NOT EXISTS (SELECT 1 FROM core.funnel_sayfa_kapsama x
                    WHERE x.adim_kod = 'ADD_TO_CART' AND x.sayfa_rolu = 'REKLAM_LANDING');

-- 🔴 INSERT TEK BASINA YETMEZ. Satir bir kez olustuktan sonra yukaridaki
--    NOT EXISTS onu korur, AMA ga4-instrumentation-yamasi.sql her apply'da
--    "WHERE adim_kod='ADD_TO_CART'" ile TUM satirlarin olcum_kaniti'ni eziyor.
--    Bu yuzden kanit AYRICA ve KOSULSUZ yazilir (deger bazinda idempotent).
UPDATE core.funnel_sayfa_kapsama SET
  enstrumantasyon = 'NOT_TESTED',
  olcum_kaniti = 'OLCULMEDI 17.09.2026. Ozel landing sayfasi sepete eklemeyi masterPage.js '
                 'icindeki postMessage koprüsü ile yapiyor: cart.addProducts(). '
                 'Bu PROGRAMATIK bir ekleme; Wix''in native SEPETE EKLE butonu degil. '
                 'Mevcut kod bu yolda syncCartCount()''u ELLE cagiriyor (masterPage.js:1145) - '
                 'yani native cart olayinin bu yolda atesledigi KANITLI degil. '
                 'Analytics AddToCart event''inin bu yolda uretilip uretilmedigi ise AYRI bir '
                 'mekanizma ve OLCULMEDI: iframe icerigi cross-origin oldugu icin butona '
                 'tarayici otomasyonuyla ulasilamadi. VARSAYILMADI.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART' AND sayfa_rolu = 'REKLAM_LANDING';

-- ---------------------------------------------------------------------------
-- 3) VIEW_CART  -  yeniden olculdu, DEGISMEDI
-- ---------------------------------------------------------------------------
-- Statu ayni kaliyor ama kanit tazeleniyor: bu sefer GA4 eklendikten SONRA olculdu.
UPDATE core.funnel_sayfa_kapsama SET
  olcum_kaniti = 'YENIDEN OLCULDU 17.09.2026, GA4 entegrasyonu eklendikten SONRA: '
                 '/cart sayfasinda GA4''e giden tek event page_view. view_cart YOK. '
                 'Yani bu, add_to_cart gibi "ayar eksikligi" degil - Wix native '
                 'entegrasyonu view_cart''i hic uretmiyor.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'VIEW_CART';

UPDATE core.funnel_adim SET
  olcum_kaniti = 'YENIDEN OLCULDU 17.09.2026 (GA4 eklendikten SONRA): /cart sayfasinda '
                 'yalniz page_view. view_cart uretilmiyor.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'VIEW_CART';

-- ---------------------------------------------------------------------------
-- 4) YENI OLCULEN RISK  -  GA4 CIFT HIT
-- ---------------------------------------------------------------------------
-- 🔴 ONCEKI RAPORUMDA "cift sayim olusmadi" DEDIM. O ifade yalniz page_view
--    sayisina bakiyordu ve FAZLA GENISTI. Bugunku olcum daha derin:
--
--    Ayni kullanici eylemi icin ayni tid'ye IKI collect istegi gidiyor:
--      view_item    -> _s=2 (_ee=1) ve _s=3
--      add_to_cart  -> _s=6 (_ee=1) ve _s=7
--      page_view    -> _s=4 (_ee=1) ve _s=5
--    Ayni sid, ayni _p; farkli _s sira numarasi -> GA4 istemcisi bunlari IKI
--    AYRI hit olarak siraladi.
--
--    Sayfada UC yukleyici birden var:
--      G-KCPFLRG2RV (dogrudan) · AW-17698757160 · GTM-5XR5TQKP
--
--    HIPOTEZ (KANITLANMADI): G-KCPFLRG2RV hem Wix Google Etiketi yuvasindan
--    hem GTM container'indan config ediliyor olabilir; gtag ayni event'i her
--    config icin bir kez gonderir.
--
--    NE BILINMIYOR: GA4'un sunucu tarafinda bunlari tekillestirip
--    tekillestirmedigi. Bunu ancak GA4 property erisimi (DebugView/Realtime)
--    ile dogrulayabilirim ve o erisim BLOCKED_BY_EXTERNAL_CREDENTIAL.
--
--    Bu yuzden: RISK olarak kayda geciyorum, "cift sayim var" DEMIYORUM.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('cr017_ga4_cift_hit_riski', 'OLCULDU_AGDA_DOGRULANMADI_GA4DE',
   '17.09.2026 olcumu: ayni eylem icin ayni GA4 tid''sine iki collect istegi gidiyor '
   '(view_item, add_to_cart, page_view). Ayni sid/_p, farkli _s; ilkinde _ee=1. '
   'Sayfada uc yukleyici var: G-KCPFLRG2RV (dogrudan), AW-17698757160, GTM-5XR5TQKP. '
   'HIPOTEZ: GA4 olcum kimligi hem Wix Google Etiketi yuvasindan hem GTM''den config '
   'ediliyor olabilir. KANITLANMADI. '
   'DOGRULAMA YOLU: (1) GTM-5XR5TQKP icinde G-KCPFLRG2RV''ye ait GA4 Configuration/Event '
   'tag''i var mi bakilacak; (2) GA4 DebugView''da tek eylemin 1 mi 2 mi event urettigi '
   'gorulecek - bu GA4 property erisimi gerektirir. '
   '🔴 ONEMLI: bu risk cozulmeden GA4''e YENI event kaynagi EKLENMEMELI - aksi halde '
   'cift sayimin ustune ucuncu bir kaynak binebilir. '
   '🔴 ONCEKI RAPORUMDAKI "cift sayim olusmadi" IFADESI DUZELTILDI: o ifade yalniz '
   'page_view SAYISINA bakiyordu, hit sira numaralarina bakmiyordu.'),

-- ---------------------------------------------------------------------------
-- 5) DOGRULANAN VELO API GERCEKLERI  (artik tahmin degil)
-- ---------------------------------------------------------------------------
  ('cr017_velo_api_dogrulandi', 'WIX_ECOM_FRONTEND_ONCARTCHANGE',
   '17.09.2026 editorde DOGRULANDI - feature-detection tahminine GEREK KALMADI. '
   'Bu sitede cozulen modul: wix-ecom-frontend (masterPage.js:6''da ZATEN import edilmis '
   've production''da calisiyor). npm kurulumu gerektiren @wix/site-ecom GEREKMIYOR. '
   'IMZA (resmi dokuman): onCartChange(handler) - handler PARAMETRE ALMAZ; sepet icerigi '
   'ayrica okunmalidir. '
   'KRITIK DOKUMAN NOTU: "Actions performed by any method other than refreshCart() do not '
   'trigger onCartChange()" -> programatik cart.addProducts() bu olayi ATESLEMEZ. '
   'Sepet frontend''den okunabiliyor: wix-stores-frontend cart.getCurrentCart() '
   '(masterPage.js:865''te zaten kullaniliyor) - backend web modulu GEREKMIYOR.'),

  ('cr017_masterpage_carpismasi', 'YAZDIGIM_DOSYA_URETIMI_SILECEKTI',
   '🔴 17.09.2026 - DAGITIM ONCESI YAKALANDI. velo-masterPage-observability.js dosyasini '
   'masterPage.js''e KURMAK uzereydim. masterPage.js BOS DEGIL: 1162 satir / 22.781 karakter '
   'canli production kodu (header, site ici arama, sepet sayaci, uye hesabi, '
   'ozel landing postMessage koprüsü). Uzerine yazmak bunlarin HEPSINI silecekti. '
   'Sitede ayrica /public/custom-elements/lcarlie-header.js 4.636 satir var. '
   'KURAL: Velo dosyasina yazmadan ONCE monaco model uzerinden mevcut icerik '
   'okunacak; "sayfa kodu bostur" VARSAYILMAYACAK.'),

  ('cr017_wix_analytics_koprusu', 'WIXDEVELOPERSANALYTICS_MEVCUT',
   '17.09.2026 canli sitede OLCULDU: window.wixDevelopersAnalytics var, '
   'anahtarlari {register, triggerEvent}, register(appName, handler) imzali. '
   'Gercek sayfa DOM''unda calisiyor; window.dataLayer ve gtag erisilebilir. '
   'Kaydedilen dinleyiciyle YAKALANAN event''ler: productPageLoaded, AddToCart, PageView. '
   'AddToCart alanlari: cartId, currency, id, quantity, name, sku, price, type, variantId. '
   'ANLAMI: Wix, gercek urun kimligiyle event uretiyor - urun bagimsiz, DOM kazimasiz. '
   'Bu koprü Ozel Kod (Custom Code) katmanindan erisilebilir ve SITE YAYINI GEREKTIRMEZ; '
   'Velo/masterPage.js hic degistirilmeden kullanilabilir. '
   '🔴 HENUZ KULLANILMADI: once cr017_ga4_cift_hit_riski cozulmeli.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 6) VELO DURUMU  -  is DAGITILMADI cunku GEREKSIZ CIKTI
-- ---------------------------------------------------------------------------
UPDATE core.ayar SET
  deger = 'DAGITILMADI_OLCUM_GEREKSIZ_KILDI',
  aciklama = '17.09.2026. Velo enstrumantasyonu DAGITILMADI. Sebep "yapilamadi" degil, '
             'OLCUM isin bir kismini GEREKSIZ kildi: add_to_cart zaten GA4''e ulasiyor '
             '(bkz. cr017_olcum_duzeltmesi). Kalan gercek aciklar icin de daha dusuk riskli '
             'bir yol bulundu: wixDevelopersAnalytics + Ozel Kod - site yayini gerektirmiyor, '
             'masterPage.js''e dokunmuyor. '
             'Ayrica yazdigim dosya oldugu gibi kurulsaydi 1162 satirlik uretim kodunu '
             'silecekti (bkz. cr017_masterpage_carpismasi).',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_velo_durum';

UPDATE core.ayar SET
  deger = 'COZULDU_PENDING_EDIT_YOK',
  aciklama = '17.09.2026 Site Gecmisi ile dogrulandi. Tum revizyonlar WIX EDITOR / '
             'Original-Branch. EN YENI KAYIT BIR YAYIN: 16 Eyl 2026 04:57 "Yayinlayan". '
             'Ondan SONRA hic "Kaydeden" satiri yok, 17 Eylul''e ait kayit yok. '
             'Yani kaydedilmis durum = yayinlanmis durum; bekleyen yayinlanmamis '
             'editor degisikligi YOK.',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_velo_blocker_1';

UPDATE core.ayar SET
  deger = 'COZULDU_API_DOGRULANDI',
  aciklama = '17.09.2026. Bkz. cr017_velo_api_dogrulandi. Runtime feature-detection '
             'fallback''i KALICI MIMARI YAPILMADI - gercek modul production kodundan '
             've resmi dokumandan dogrulandi.',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_velo_blocker_2';

-- ---------------------------------------------------------------------------
-- 7) URETIM DEGISIKLIGI KAYDI  -  etkisi bildirdigimden GENISMIS
-- ---------------------------------------------------------------------------
UPDATE core.ayar SET
  aciklama = aciklama || ' || DUZELTME 17.09.2026: bu ayarin etkisi raporladigimdan '
             'GENIS cikti. Yalniz view_item degil, add_to_cart da GA4''e bu degisiklikle '
             'akmaya basladi. Raporda eksik kalmasinin sebebi: degisiklikten sonra '
             'yalnizca view_item''i yeniden olcmus olmam.',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_uretim_degisikligi_1'
  AND aciklama NOT LIKE '%DUZELTME 17.09.2026: bu ayarin etkisi%';

UPDATE core.ayar SET
  deger = 'DARALDI_ADD_TO_CART_HARIC',
  aciklama = '17.09.2026 olcumu sonrasi DARALDI. Wix native entegrasyonunun URETMEDIGI '
             've hala eksik olan event''ler: view_cart · begin_checkout · ozel landing''de '
             'view_item · purchase (test edilmedi). '
             'add_to_cart BU LISTEDEN CIKARILDI - GA4''e ulastigi olculdu. '
             'Ozel landing koprü yolundaki add_to_cart ise AYRI ve OLCULMEDI.',
  guncelleme = clock_timestamp()
WHERE anahtar = 'cr017_kalan_enstrumantasyon';

COMMIT;
