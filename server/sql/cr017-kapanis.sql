-- =============================================================================
-- CR-017  ·  KAPANIS  -  CLOSED_BASELINE  (17.09.2026)
--
-- GTM Surum 4: "CR-017 GA4 duplicate removal - add_to_cart"
--   Degistirildi: CR017-GA4_Event-Istisna-DirectTagDuplikeleri (regex)
--   ^(page_view|view_item|gtm\.dom)$  ->  ^(page_view|view_item|gtm\.dom|add_to_cart)$
--   DOKUNULMADI: paylasilan Custom_Event tetikleyicisi · Pixel_Template · GA4_Config
--   Etiket silinmedi/duraklatilmadi · purchase block listesine EKLENMEDI
--   ROLLBACK: Surum 3'e don, veya regex'ten add_to_cart'i cikar.
--
-- ALTYAPI FAZI KAPANIYOR. Kalan event acıklari YENI TUR ACILMADAN durum olarak
-- kaydedilir. Sonraki ana faz: AGENCY / GROWTH OPERATING SYSTEM.
-- =============================================================================

BEGIN;

INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES

-- ---------------------------------------------------------------------------
-- 1) SON DUZELTME VE PRODUCTION DOGRULAMASI
-- ---------------------------------------------------------------------------
  ('cr017_gtm_surum_4', 'YAYINLANDI_DOGRULANDI',
   '17.09.2026 02:34 yayinlandi. GTM Surum 4 · 3 etiket / 3 tetikleyici / 17 degisken. '
   'Tek degisiklik: istisna tetikleyicisinin regex''ine add_to_cart eklendi. '
   'GEREKCE (production''da olculmustu): add_to_cart''in IKI bagimsiz ureticisi vardi - '
   'Wix dogrudan Google Etiketi ve GTM GA4_Event. Istisna, GTM kopyasini engeller; '
   'Wix native hit kalir. '
   'PREVIEW: GA4 hedefine Urunu Goruntuleme x1, Alisveris Sepetine Ekleme x1, gtm.dom yok; '
   'GA4_Event add_to_cart''ta da ateslenmedi; Pixel_Template 3->5 ateslendi. '
   'PRODUCTION AG OLCUMU (preview disi sekme, gtm.js onbellegi tazelenerek): '
   '  _s=1 view_item   WIX = 1 ✅ '
   '  _s=2 page_view   WIX = 1 ✅ (sayfa yuklemesi) '
   '  _s=3 add_to_cart WIX = 1 ✅ (GTM kopyasi YOK) '
   '  _s=4 page_view   WIX     (side-cart sanal sayfa goruntulemesi, GTM kopyasi DEGIL) '
   '  gtm.dom = 0 ✅ '
   'GTM kaynakli hicbir GA4 hit''i kalmadi.'),

  ('cr017_meta_regresyon_surum4', 'BROWSER_TARAFI_TEMIZ_CAPI_NOT_VERIFIED',
   'Surum 4 sonrasi production olcumu, Surum 3 olcumuyle BIREBIR AYNI: '
   'fbq = function ✅ · connect.facebook.net/en_US/fbevents.js 1 ✅ · '
   'connect.facebook.net/signals/config/<pixel> 1 ✅ · '
   'lcarlie.shop/_serverless/analytics-reporter/facebook/event 5 istek ✅ '
   '(Wix first-party CAPI relay''i). Preview''da Pixel_Template add_to_cart''ta atesleniyor. '
   '🔴 CAPI SUNUCU TARAFI SONUCU OLCULEMEDI -> NOT_VERIFIED. Calisiyor VARSAYILMIYOR.'),

-- ---------------------------------------------------------------------------
-- 2) DUPLICATE BAYRAGI
-- ---------------------------------------------------------------------------
  ('cr017_raw_browser_duplicate_risk', 'FALSE_DOGRULANAN_KAPSAM',
   'RAW_BROWSER_DUPLICATE_RISK = FALSE · 17.09.2026 production dogrulamasi ile. '
   'DOGRULANAN KAPSAM (native urun sayfasi, G-KCPFLRG2RV): '
   '  page_view 2->1 · view_item 2->1 · add_to_cart 2->1 · gtm.dom 1->0. '
   'KAPSAM DISI (bayrak bunlar icin gecerli DEGIL): '
   '  purchase -> NOT_VERIFIED (hic olculmedi, dokunulmadi) '
   '  ozel landing koprü yolundaki add_to_cart -> NOT_VERIFIED '
   '  view_cart / begin_checkout -> zaten GA4''e gitmiyor, duplicate sorusu yok. '
   '🔴 BU BAYRAK FUNNEL_READY VEYA ROAS_READY ANLAMINA GELMEZ. '
   '🔴 GA4''un sunucu tarafinda tekillestirme yapip yapmadigi hala dogrulanmadi '
   '(GA4 property erisimi yok) - ancak tarayicidan artik TEK hit cikiyor, yani '
   'sunucu tarafi tekillestirmeye IHTIYAC KALMADI.'),

-- ---------------------------------------------------------------------------
-- 3) KALAN EVENT ACIKLARI  -  gercek statuleriyle, YENI TUR ACILMADAN
-- ---------------------------------------------------------------------------
  ('cr017_kalan_acik_view_cart', 'NOT_MEASURED',
   'view_cart · /cart sayfasinda GA4''e giden tek event page_view. view_cart URETILMIYOR. '
   'Olculdu 17.09.2026 (GA4 entegrasyonu eklendikten SONRA yeniden). '
   'Wix native entegrasyonunun kapsami disinda. Yeni altyapi turu ACILMADI.'),

  ('cr017_kalan_acik_begin_checkout', 'NOT_MEASURED',
   'begin_checkout · odeme sayfasinda GA4''e giden tek event page_view. '
   'Checkout sayfasi 17.09.2026''da acildi ve olculdu (veri girilmedi, siparis olusturulmadi): '
   'yalniz page_view = 1. begin_checkout URETILMIYOR. Yeni altyapi turu ACILMADI.'),

  ('cr017_kalan_acik_landing_view_item', 'NOT_MEASURED',
   'Ozel landing (/vireon) · view_item URETILMIYOR; yalniz page_view = 1 (17.09.2026 olcumu). '
   'Wix native entegrasyonu view_item''i yalniz NATIVE urun sayfalarinda uretir. '
   '🔴 IS ETKISI: reklam trafigi bu sayfaya iniyor, yani en cok ziyaret alan sayfada '
   'urun goruntuleme olculmuyor. Yeni altyapi turu ACILMADI - durum olarak kayitli.'),

  ('cr017_kalan_acik_landing_add_to_cart', 'NOT_VERIFIED',
   'Ozel landing koprü yolu (masterPage.js -> cart.addProducts) icin add_to_cart '
   'GA4''e gidiyor mu - OLCULMEDI. iframe icerigi cross-origin oldugu icin butona '
   'tarayici otomasyonuyla ulasilamadi. VARSAYILMADI. Yeni tur ACILMADI.'),

  ('cr017_kalan_acik_purchase', 'NOT_VERIFIED',
   'purchase · DOKUNULMADI. Istisna/block listesine EKLENMEDI. Test siparisi URETILMEDI. '
   'GTM''de purchase''a ozel etiket yok; ancak GA4_Event''in Etkinlik Adi {{Event}} dinamik '
   've transaction_id/value parametreleri tanimli oldugu icin dataLayer''a purchase duserse '
   'GA4''e iletebilir - bu durumda Wix dogrudan etiketiyle CIFT olusabilir. '
   '🔴 ILK GERCEK SIPARISTE OLCULECEK: hangi yol purchase gonderiyor, kac hit, '
   'transaction_id var mi. O ana kadar NOT_VERIFIED.'),

  ('cr017_kalan_acik_ga4_ingestion', 'BLOCKED_BY_EXTERNAL_CREDENTIAL',
   'GA4 Data API ingestion · raw.ga4_event HALA 0 satir. GA4 Property ID + Data API '
   'service account dis girdisi bekleniyor. Site tarafinda event akiyor olmasi '
   'ambara veri geldigi ANLAMINA GELMEZ - iki ayri boyut, ikisi de kendi statusunu tasir.'),

-- ---------------------------------------------------------------------------
-- 4) CR-017 KAPANIS
-- ---------------------------------------------------------------------------
  ('cr017_durum', 'CLOSED_BASELINE',
   'CR-017 KAPANDI · 17.09.2026. ALTYAPI FAZI KAPANIYOR. '
   'BASELINE ICERIGI: '
   '(1) GA4 tarayici tarafinda TEKIL hit - page_view/view_item/add_to_cart 1''er, gtm.dom 0 '
   '(GTM Surum 4, production''da dogrulandi). '
   '(2) Meta Pixel/CAPI yapisi korundu - paylasilan tetikleyici ve Pixel_Template hic '
   'degistirilmedi; browser tarafi regresyonsuz, CAPI sunucu tarafi NOT_VERIFIED. '
   '(3) Funnel semantigi: NOT_MEASURED != 0 · OBSERVED/NOT_OBSERVED/NOT_MEASURED ayrimi · '
   'GA4 ticari otorite DEGIL · is mantiginda urun/sayfa literali yok. '
   '(4) COGS frozen baseline (NEGATIVE_PROVEN_BY_BOUND) KORUNDU. '
   '🔴 CLOSED_BASELINE, FULLY_OPERATIONAL DEMEK DEGILDIR: kalan event acıklari '
   'cr017_kalan_acik_* anahtarlarinda gercek statuleriyle durmaktadir. '
   '🔴 FUNNEL_READY = FALSE · ROAS kapisi ACILMADI. '
   'SONRAKI ANA FAZ: AGENCY / GROWTH OPERATING SYSTEM.'),

  ('cr017_validation', 'PRODUCTION_VERIFIED_BROWSER_SIDE',
   '17.09.2026. Tarayici tarafi olcum production''da DOGRULANDI (tekil hit). '
   'Ambara ilk gercek GA4 verisi akip reconciliation turu gorulmeden funnel truth '
   'FULLY VALIDATED SAYILMAZ - bu, GA4 Data API dis girdisine baglidir.')

ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 5) ADD_TO_CART kaniti: artik TEKIL
-- ---------------------------------------------------------------------------
-- 🔴 enstrumantasyon MEASURED kaliyor; adim seviyesi PARTIAL kaliyor cunku ozel
--    landing koprü yolu HALA olculmedi. Tekillesme kapsama genisletmez.
UPDATE core.funnel_sayfa_kapsama SET
  olcum_kaniti = 'OLCULDU 17.09.2026 (GTM Surum 4 sonrasi, production): native urun sayfasinda '
                 'SEPETE EKLE sonrasi tid=G-KCPFLRG2RV en=add_to_cart TEK hit olarak gidiyor. '
                 'ONCE 2 hit vardi (Wix dogrudan Google Etiketi + GTM GA4_Event); GTM kopyasi '
                 'istisna tetikleyicisiyle engellendi, Wix native hit kaldi. '
                 'Wix ayrica wixDevelopersAnalytics uzerinden AddToCart standart event''ini '
                 'gercek urun kimligiyle uretiyor - DOM kazima / ad eslestirme GEREKMIYOR. '
                 '🔴 Ozel landing koprü yolu (cart.addProducts) icin AYRI ve OLCULMEDI.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART' AND sayfa_rolu = 'NATIVE_URUN';

COMMIT;
