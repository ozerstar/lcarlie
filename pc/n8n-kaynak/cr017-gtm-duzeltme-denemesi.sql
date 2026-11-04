-- =============================================================================
-- CR-017  ·  GTM CIFT HIT DUZELTME DENEMESI  (17.09.2026)
--
-- SONUC: PUBLISH EDILMEDI. Canli GTM Surum 2 DEGISMEDI.
--        GTM calisma alani PRISTINE birakildi (0 degistirilen/0 eklenen/0 silinen).
--
-- Iki aday diff PREVIEW'da denendi, IKISI DE BASARISIZ - cunku cift sayimi
-- degil, add_to_cart'in TEK KAYNAGINI yok ediyorlar.
-- =============================================================================

BEGIN;

INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES

-- ---------------------------------------------------------------------------
-- 1) BAGIMLILIK DENETIMI  -  durma kosulu KARSILANMADI
-- ---------------------------------------------------------------------------
  ('cr017_pixel_bagimliligi', 'YOK_SADECE_PAYLASILAN_DEGISKEN',
   '17.09.2026 GTM Preview (Tag Assistant) ile DOGRULANDI. '
   'view_item olayinda: Tetiklenen = GA4_Event + Pixel_Template; Tetiklenmeyen = GA4_Config. '
   'Pixel_Template''in tetikleyicileri: DOM_Ready (eslesmedi) VEYA Custom_Event (eslesti). '
   'Engelleyici tetikleyici yok. KURULUM/TEMIZLEME ETIKETI (tag sequencing) BOLUMU YOK. '
   'Yani Pixel_Template, GA4 etiketlerinin firing''ine BAGIMLI DEGIL - ayni tetikleyiciyle '
   'BAGIMSIZ atesleniyor. '
   'Paylasilan olan yalnizca DEGISKENLER: Pixel_ID, FBEventName, Event_ID_Constant. '
   'Pixel_Template''te "Use GA4 dataLayer Integration = true" ayari da GA4 ETIKETLERINE degil, '
   'Wix''in push ettigi GA4 formatindaki dataLayer''a bagli (API cagrisi gozlendi: '
   'dataLayer.push({event:"view_item", ...}) - kaynagi Wix, GA4 etiketleri bu veriyi URETMIYOR, '
   'TUKETIYOR).'),

-- ---------------------------------------------------------------------------
-- 2) 🔴 ONCEKI DUZELTMEMDEKI HATA  -  add_to_cart'in GERCEK kaynagi
-- ---------------------------------------------------------------------------
  ('cr017_add_to_cart_gercek_kaynak', 'GTM_GA4_EVENT_ETIKETI',
   '🔴 BUGUN YAZDIGIM cr017-olcum-duzeltmesi.sql KISMEN YANLISTI. '
   'Orada "add_to_cart GA4''e ulasiyor, bunu Wix Google Etiketi degisikligim sagladi" '
   'anlamina gelen bir kayit birakmistim. PREVIEW OLCUMU BUNU CURUTTU. '
   'DENEY: GA4_Event duraklatildi, GA4_Config AKTIF birakildi. Preview''da gercek bir '
   'SEPETE EKLE tiklandi (Tag Assistant olay #13 = add_to_cart; Pixel_Template 3->5 '
   'atesledi, yani olay GERCEKTEN olustu). SONUC: GA4''e add_to_cart 0 HIT. '
   'Ayrica her iki GA4 etiketi de duraklatildiginda yine 0 HIT (Tag Assistant olay #39). '
   'CIKARIM: production''da GA4''e giden add_to_cart hit''lerinin kaynagi GTM''deki '
   'GA4_Event etiketidir; Wix''in dogrudan Google Etiketi add_to_cart''i GA4''e GONDERMIYOR. '
   'view_item ve page_view ise Wix tarafindan gonderiliyor (GA4 etiketleri duraklatiliyken '
   'de 1''er hit olarak gozlendi). '
   'ONCEKI ATIF HATAM: hit''leri `gtm` parametresine gore WIX/GTM diye ayirmistim; '
   'add_to_cart icin bu ayrim yaniltici cikti - o hit _ee=1 (event echo) isaretliydi, '
   'yani bagimsiz bir gonderim degil, GTM kaynakli olayin ikinci hedefe yankisiydi.'),

-- ---------------------------------------------------------------------------
-- 3) DENENEN IKI DIFF VE NEDEN BASARISIZ
-- ---------------------------------------------------------------------------
  ('cr017_denenen_diffler', 'IKISI_DE_BASARISIZ_PUBLISH_YOK',
   'DIFF A - GA4_Config + GA4_Event ikisi de DURAKLAT: '
   '  page_view 1 ✅ · view_item 1 ✅ · gtm.dom 0 ✅ · Meta Pixel calisiyor ✅ '
   '  ANCAK add_to_cart 0 ❌ (hedef 1). '
   'DIFF B - yalniz GA4_Event DURAKLAT, GA4_Config AKTIF: '
   '  page_view 1 ✅ · view_item 1 ✅ · gtm.dom 0 ✅ · Meta Pixel calisiyor ✅ '
   '  ANCAK add_to_cart yine 0 ❌. '
   'ORTAK NEDEN: add_to_cart''i GA4''e gonderen TEK bilesen GA4_Event etiketi. '
   'Duraklatmak cift sayimi degil, event''in KENDISINI yok ediyor. '
   'Bu yuzden PUBLISH EDILMEDI ve calisma alani degisiklikleri GERI ALINDI.'),

-- ---------------------------------------------------------------------------
-- 4) DOGRU MINIMUM DIFF  -  TASARLANDI, UYGULANMADI
-- ---------------------------------------------------------------------------
  ('cr017_dogru_minimum_diff', 'ISTISNA_TETIKLEYICI_ONERISI_UYGULANMADI',
   'Hedef: GA4_Event''i KORU (add_to_cart ve ileride purchase icin tek kaynak), ama '
   'Wix''in ZATEN GA4''e gonderdigi event''leri TEKRARLAMASINI engelle. '
   '🔴 DIKKAT - PAYLASILAN TETIKLEYICI TUZAGI: Custom_Event tetikleyicisi GA4_Event ile '
   'Pixel_Template ARASINDA PAYLASILIYOR. O tetikleyicinin kosulunu degistirmek '
   'META PIKSELINI BOZAR. Tetikleyici DUZENLENMEMELI. '
   'ONERILEN YOL: GA4_Event etiketine YALNIZ ONA AIT bir ISTISNA (blocking) tetikleyicisi '
   'eklenir; istisna sunlari kapsar: view_item · page_view · gtm.dom '
   '(Wix''in zaten gonderdikleri + cop event). Boylece GA4_Event yalniz Wix''in '
   'GONDERMEDIGI event''leri iletir. '
   'BEKLENEN SONUC: page_view 1 · view_item 1 · add_to_cart 1 · gtm.dom 0 · Meta bozulmaz. '
   'DOGRULANMASI GEREKEN: istisna tetikleyicisi GA4_Config''in send_page_view=true '
   'davranisini etkilemez; page_view''in tekil kaldigi ayrica olculmeli. '
   '🔴 UYGULANMADI - Chief Architect onayi bekliyor (tag DUZENLEME gerektiriyor, '
   'duraklatmadan daha buyuk bir diff).'),

-- ---------------------------------------------------------------------------
-- 5) ROLLBACK / GUVENLIK DURUMU
-- ---------------------------------------------------------------------------
  ('cr017_gtm_rollback_capasi', 'SURUM_2_CANLI_DEGISMEDI',
   'GTM canli surum: 2 (14.08.2026, 3 etiket / 2 tetikleyici / 11 degisken). '
   'Bu oturumda HIC publish yapilmadi; Surum 2 aynen canlida. '
   'Calisma alani degisiklikleri "Degisikligi iptal et" ile tek tek geri alindi; '
   'son durum: "Henuz degisiklik yapmadiniz" (0 degistirilen / 0 eklenen / 0 silinen). '
   'Test kalintisi: sepete eklenen urunler kaldirildi, sepet BOS. '
   'Wix tarafi: Google Etiketi ayarina DOKUNULMADI.')

ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 6) ADD_TO_CART KANITINI DUZELT  -  kaynak yanlis yazilmisti
-- ---------------------------------------------------------------------------
UPDATE core.funnel_sayfa_kapsama SET
  olcum_kaniti = 'OLCULDU 17.09.2026: native urun sayfasinda SEPETE EKLE sonrasi '
                 'tid=G-KCPFLRG2RV en=add_to_cart collect istegi gozlendi - event GA4''E ULASIYOR. '
                 '🔴 KAYNAK DUZELTILDI: bu hit''i Wix''in Google Etiketi DEGIL, GTM''deki '
                 'FB_CONVERSIONS_API-...-Web-Tag-GA4_Event etiketi uretiyor. '
                 'KANIT: preview''da o etiket duraklatildiginda (GA4_Config aktifken bile) '
                 'gercek bir sepete ekleme yapildi ve GA4''e 0 hit gitti. '
                 'Wix ayrica wixDevelopersAnalytics uzerinden AddToCart standart event''ini '
                 'gercek urun kimligiyle uretiyor (id, name, price, currency, quantity, sku) - '
                 'yani DOM kazima / ad eslestirme / slug tahmini GEREKMIYOR. '
                 '🔴 KIRILGANLIK: add_to_cart olcumu su an Meta CAPI sihirbazinin urettigi '
                 'bir GTM etiketine bagli; o etiket ayni zamanda view_item/page_view''i '
                 'CIFTLIYOR ve GA4''e gtm.dom cop event''i gonderiyor.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART' AND sayfa_rolu = 'NATIVE_URUN';

COMMIT;
