-- =============================================================================
-- CR-017  ·  GTM ISTISNA TETIKLEYICISI  -  YAYINLANDI  (17.09.2026)
--
-- GTM Surum 3: "CR-017 GA4 duplicate browser hit removal"
--   Eklendi     : CR017-GA4_Event-Istisna-DirectTagDuplikeleri (Ozel Etkinlik)
--                 regex ^(page_view|view_item|gtm\.dom)$
--   Degistirildi: FB_CONVERSIONS_API-...-Web-Tag-GA4_Event  (istisna eklendi)
--   DOKUNULMADI : paylasilan Custom_Event tetikleyicisi · Pixel_Template ·
--                 GA4_Config · hicbir etiket silinmedi/duraklatilmadi
--   ROLLBACK    : Surumler ekranindan Surum 2'ye don, veya istisnayi kaldir.
-- =============================================================================

BEGIN;

INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES

  ('cr017_gtm_istisna_yayini', 'YAYINLANDI_SURUM_3',
   '17.09.2026 02:21 yayinlandi. GTM Surum 3 · 3 etiket / 3 tetikleyici / 17 degisken. '
   'ONCEKI CANLI SURUM 2 (rollback hedefi). '
   'ZORUNLU ON KONTROL YAPILDI - direct Wix/Google Tag page_view''i 5 sayfa tipinin '
   'HEPSINDE 1 kez gonderiyor (preview''da olculdu): ana sayfa · native urun sayfasi · '
   'ozel landing (/vireon) · sepet (/cart) · checkout. '
   'Hicbir sayfa tipinde direct page_view eksigi YOK -> global page_view engellemesi guvenli.'),

  ('cr017_production_dogrulama', 'KISMEN_BASARILI_3_4',
   'PRODUCTION AG OLCUMU (yayin sonrasi, preview DISI sekme, gtm.js onbellegi tazelenerek): '
   'ONCE -> SONRA  ·  native urun sayfasi, G-KCPFLRG2RV: '
   'page_view  2 -> 1  ✅ | '
   'view_item  2 -> 1  ✅ | '
   'gtm.dom    1 -> 0  ✅ | '
   'add_to_cart 2 -> 2 ❌ DEGISMEDI. '
   'Sayfa yuklemesinde tek page_view; add_to_cart sonrasi gelen ikinci page_view '
   'side-cart sanal sayfa goruntulemesidir (kaynak WIX, GTM kopyasi DEGIL) - '
   'bu degisiklikten once de vardi.'),

-- ---------------------------------------------------------------------------
-- 🔴 ONCEKI TESPITIMIN DUZELTMESI
-- ---------------------------------------------------------------------------
  ('cr017_add_to_cart_gercek_kaynak', 'IKI_BAGIMSIZ_URETICI',
   '🔴 DUZELTILDI. Daha once "add_to_cart''i GA4''e gonderen TEK bilesen GTM GA4_Event '
   'etiketidir" yazmistim. YANLISTI. '
   'HATANIN KOKU: o sonucu GTM Preview oturumunda performance.getEntriesByType(''resource'') '
   'ile olcmustum; preview oturumunda add_to_cart BEACON''I bu API tarafindan YAKALANMIYOR. '
   'Tag Assistant''in GA4 hedef gorunumu ("Gonderilen Isabetler") ayni anda '
   '"Alisveris Sepetine Ekleme" isabetlerini GOSTERIYORDU - yani event aslinda gidiyordu. '
   'PRODUCTION OLCUMU (yayin sonrasi, preview disi) kesin tabloyu verdi: '
   '  _s=3 add_to_cart _ee=1  FB parametresi YOK   -> Wix DOGRUDAN Google Etiketi '
   '  _s=4 add_to_cart        FB parametresi VAR   -> GTM GA4_Event etiketi '
   'YANI add_to_cart''in IKI BAGIMSIZ URETICISI var ve bu yuzden hala CIFT. '
   'DERS: preview oturumunda resource-timing ile olculen "0 hit" sonucu KANIT DEGILDIR; '
   'olcum yonteminin o baglamda gecerli oldugu ayrica dogrulanmalidir.'),

  ('cr017_add_to_cart_kalan_cift', 'ACIK_KARAR_BEKLIYOR',
   '🔴 add_to_cart HALA 2 hit. Sebep: Wix dogrudan Google Etiketi ve GTM GA4_Event '
   'etiketi AYNI event''i bagimsiz olarak gonderiyor. '
   'COZUM (uygulanmadi): mevcut istisna tetikleyicisinin regex''ine add_to_cart eklenir -> '
   '^(page_view|view_item|gtm\\.dom|add_to_cart)$ . Bu tek satirlik bir degisiklik ve '
   'geride Wix''in gonderdigi TEK hit kalir. '
   '🔴 NEDEN KENDILIGIMDEN YAPMADIM: Chief Architect''in bu turdaki basari kriteri acikca '
   '"GA4_Event: add_to_cart FIRED" diyordu ve aday istisna listesi 3 event ile sinirliydi. '
   'O kriter, add_to_cart''in tek kaynaginin GA4_Event oldugu varsayimiyla yazilmisti; '
   'yeni kanit bu varsayimi curuttu. Karar Chief Architect''e aittir. '
   'DIKKAT: bu degisiklik yapilirsa add_to_cart''in GA4''e giden surumu Wix''inki olur ve '
   'GA4_Event''in tasidigi ek parametreler (event_id, x-fb-ck-*) o event''te GA4''e gitmez - '
   'Meta CAPI dedup''i ETKILENMEZ cunku onu Pixel_Template tasiyor.'),

  ('cr017_meta_regresyon', 'BROWSER_TARAFI_TEMIZ_CAPI_NOT_VERIFIED',
   'Yayin sonrasi production olcumu: '
   'fbq = function ✅ · connect.facebook.net/en_US/fbevents.js yuklendi ✅ · '
   'connect.facebook.net/signals/config/2469140530193842 yuklendi ✅ '
   '(optin_meta_enabled_capi parametresi mevcut) · '
   'www.lcarlie.shop/_serverless/analytics-reporter/facebook/event -> 5 istek ✅ '
   '(Wix first-party CAPI relay''i calisiyor). '
   'Preview''da Pixel_Template atesleme sayisi degisiklikten etkilenmedi. '
   '🔴 CAPI SUNUCU TARAFI SONUCU OLCULEMEDI -> NOT_VERIFIED. Calisiyor VARSAYILMIYOR.'),

  ('cr017_raw_browser_duplicate_risk', 'KISMI_FALSE_KAPSAMA_SINIRLI',
   '17.09.2026 yayin sonrasi production dogrulamasiyla guncellendi. '
   'DUPLICATE COZULDU (RAW_BROWSER_DUPLICATE_RISK = FALSE) yalniz su event''ler icin: '
   '  page_view · view_item · gtm.dom (gtm.dom artik hic uretilmiyor). '
   'DUPLICATE DEVAM EDIYOR (RAW_BROWSER_DUPLICATE_RISK = TRUE): '
   '  add_to_cart (2 hit) - bkz. cr017_add_to_cart_kalan_cift. '
   '  purchase - OLCULMEDI, dokunulmadi, block listesine EKLENMEDI; ilk gercek '
   '  siparise kadar NOT_VERIFIED. '
   '🔴 Bu bayragin FALSE olmasi FUNNEL_READY veya ROAS_READY anlamina GELMEZ. '
   'GA4 sunucu tarafinda tekillestirme yapip yapmadigi hala dogrulanmadi '
   '(GA4 property erisimi BLOCKED_BY_EXTERNAL_CREDENTIAL).')

ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- ADD_TO_CART kaniti: kaynak tablosu duzeltildi
-- ---------------------------------------------------------------------------
UPDATE core.funnel_sayfa_kapsama SET
  olcum_kaniti = 'OLCULDU 17.09.2026 (GTM Surum 3 yayini sonrasi, production): native urun '
                 'sayfasinda SEPETE EKLE sonrasi tid=G-KCPFLRG2RV en=add_to_cart GA4''e ULASIYOR. '
                 'KAYNAK (kesinlesti): IKI BAGIMSIZ URETICI - (1) Wix dogrudan Google Etiketi '
                 '(_ee=1, FB parametresi yok), (2) GTM GA4_Event etiketi (FB parametreli). '
                 'Bu nedenle add_to_cart hala GA4''e 2 hit olarak gidiyor. '
                 'Wix ayrica wixDevelopersAnalytics uzerinden AddToCart standart event''ini '
                 'gercek urun kimligiyle uretiyor - DOM kazima / ad eslestirme GEREKMIYOR. '
                 '🔴 CIFT SAYIM RISKI BU EVENT ICIN ACIK (bkz. cr017_add_to_cart_kalan_cift).',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART' AND sayfa_rolu = 'NATIVE_URUN';

COMMIT;
