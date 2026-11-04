-- =============================================================================
-- CR-017 PRODUCTION INSTRUMENTATION  -  OLCULEN YENI DURUM  (17.09.2026)
--
-- 🔴 URETIMDE YAPILAN DEGISIKLIK (tek, geri alinabilir, ayar):
--    Wix > Pazarlama Entegrasyonlari > Google Etiketi  ->  G-KCPFLRG2RV eklendi.
--    Onceki durum: yuva BOSTU; Wix ecommerce event'lerini yalniz Google Ads
--    etiketine (AW-17698757160) gonderiyordu, GA4 yalniz page_view aliyordu.
--
-- 🔴 OLCULEN SONUC (tarayici ag trafigi, degisiklik ONCESI/SONRASI):
--      ONCE : view_item -> AW-17698757160          (GA4'e GITMIYOR)
--      SONRA: view_item -> AW-17698757160 + G-KCPFLRG2RV   ✅
--    page_view sayisi DEGISMEDI -> cift sayim OLUSMADI.
--
-- 🔴 URUN BAGIMSIZ: bu bir AYARDIR, kod degil. Wix tum native urun
--    sayfalarinda ayni event'i uretir; yarin eklenen urun icin EK IS YOK.
--
-- 🔴 DUZELTILEN ONCEKI HATAM: CR-017 raporunda "native urun sayfasinda
--    view_item GA4'e gidiyor" yazmistim. YANLISTI - Google Ads'e gidiyordu.
--    Hata, collect isteginin `tid` parametresini okumamaktan kaynaklandi;
--    event adi dogru, HEDEF yanlis okunmustu.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) SAYFA BAZLI KAPSAMA  -  olculen yeni durum
-- ---------------------------------------------------------------------------
-- 🔴 SAYFA ROLU ile guncellenir, sayfa ADIYLA degil: yarin baska bir urunun
--    native sayfasi olculdugunde ayni kural gecerli olur.
UPDATE core.funnel_sayfa_kapsama k SET
  enstrumantasyon = 'MEASURED',
  olcum_kaniti = 'OLCULDU 17.09.2026 (Wix Google Etiketi''ne G-KCPFLRG2RV eklendikten SONRA): '
                 'en=view_item istegi tid=G-KCPFLRG2RV ile gozlendi. Degisiklik ONCESINDE '
                 'ayni event yalniz tid=AW-17698757160''a gidiyordu.',
  olcum_zamani = clock_timestamp()
 FROM core.sayfa_urun s
WHERE s.sayfa_yolu = k.sayfa
  AND k.adim_kod = 'PRODUCT_VIEW'
  AND s.sayfa_rolu = 'NATIVE_URUN'
  AND k.enstrumantasyon IS DISTINCT FROM 'MEASURED';

-- 🔴 OZEL LANDING HALA OLCULMUYOR - ve bu en yuksek is etkili acik.
--    Reklam trafigi bu sayfaya iniyor; Wix native entegrasyonu burada
--    view_item URETMIYOR cunku sayfa bir urun sayfasi DEGIL.
UPDATE core.funnel_sayfa_kapsama k SET
  enstrumantasyon = 'NOT_INSTRUMENTED',
  olcum_kaniti = 'OLCULDU 17.09.2026 (GA4 eklendikten SONRA da): ozel landing sayfasinda '
                 'yalniz page_view var, view_item YOK. Wix native entegrasyonu bu event''i '
                 'yalniz NATIVE URUN sayfalarinda uretir. '
                 '🔴 IS ETKISI: reklam trafigi buraya iniyor, yani en cok ziyaret alan '
                 'sayfada urun goruntuleme HALA olculmuyor.',
  olcum_zamani = clock_timestamp()
 FROM core.sayfa_urun s
WHERE s.sayfa_yolu = k.sayfa
  AND k.adim_kod = 'PRODUCT_VIEW'
  AND s.sayfa_rolu IN ('OZEL_LANDING','KAMPANYA_LANDING');

-- add_to_cart: degisiklikten SONRA da gonderilmiyor (yeniden olculdu)
UPDATE core.funnel_sayfa_kapsama SET
  olcum_kaniti = 'YENIDEN OLCULDU 17.09.2026, GA4 entegrasyonu eklendikten SONRA: '
                 'butona tiklandi, urun sepete eklendi, collect istegi sayisi DEGISMEDI '
                 '(12 -> 12). Wix native entegrasyonu add_to_cart URETMIYOR.',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'ADD_TO_CART';

-- ---------------------------------------------------------------------------
-- 2) ADIM SEVIYESI  -  PRODUCT_VIEW artik GA4'e akiyor (sayfaya gore)
-- ---------------------------------------------------------------------------
UPDATE core.funnel_adim SET
  enstrumantasyon = 'PARTIAL',
  olcum_kaniti = 'NATIVE urun sayfalarinda GA4''e GONDERILIYOR (17.09.2026 uretim '
                 'degisikligi sonrasi olculdu). OZEL LANDING sayfalarinda HALA YOK. '
                 'Kapsama sayfa ROLUNE gore degisir -> PARTIAL.',
  olcum_yeri = 'sayfa rolune gore: NATIVE_URUN = MEASURED · OZEL_LANDING = NOT_INSTRUMENTED',
  olcum_zamani = clock_timestamp()
WHERE adim_kod = 'PRODUCT_VIEW';

-- ---------------------------------------------------------------------------
-- 3) SITE KURULUM OTORITESI  -  GA4 artik ecommerce de aliyor
-- ---------------------------------------------------------------------------
UPDATE core.source_authority SET
  gap = 'GA4 SITEDE CALISIYOR ve ECOMMERCE EVENT DE ALIYOR (17.09.2026 uretim degisikligi). '
        'YAPILAN: Wix > Pazarlama Entegrasyonlari > Google Etiketi''ne G-KCPFLRG2RV eklendi. '
        'ONCE: Wix ecommerce event''lerini yalniz AW-17698757160''a gonderiyordu, GA4 sadece '
        'page_view aliyordu. SONRA: view_item GA4''e de gidiyor (olculdu). '
        'page_view sayisi DEGISMEDI - cift sayim olusmadi. '
        'HALA EKSIK (olculdu): add_to_cart · view_cart · begin_checkout uretilmiyor; '
        'purchase test edilmedi; ozel landing sayfalarinda view_item yok. '
        'Bunlar Wix native entegrasyonunun KAPSAMI DISINDA - Velo/GTM isi gerektirir.',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = 'Tarayici ag trafigi: collect isteklerinin tid parametresi, degisiklik oncesi/sonrasi'
WHERE alan = 'behavior_site_tracking';

-- ---------------------------------------------------------------------------
-- 4) URETIM DEGISIKLIGI KAYDI  -  geri alma yolu dahil
-- ---------------------------------------------------------------------------
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('cr017_uretim_degisikligi_1', 'WIX_GOOGLE_TAG_GA4_EKLENDI',
   '17.09.2026 · Wix > Pazarlama Entegrasyonlari > Google Etiketi > G-KCPFLRG2RV eklendi. '
   'ETKI (olculdu): GA4 artik native urun sayfalarinda view_item aliyor; TUM urunler icin '
   'gecerli, kod YOK. page_view cift sayimi OLUSMADI. '
   'GERI ALMA: ayni ekrandan etiket kaldirilir - tek adim, kod degisikligi yok. '
   'DOKUNULMAYAN: GTM container, Meta pikseli, Google Ads etiketi, reklam/kampanya/fiyat.'),
  ('cr017_kalan_enstrumantasyon', 'VELO_VEYA_GTM_GEREKIYOR',
   'Wix native entegrasyonunun URETMEDIGI event''ler (17.09.2026 olcumu): '
   'add_to_cart · view_cart · begin_checkout · ozel landing''de view_item. '
   'Bunlar icin iki yol var: (a) Velo (wix-ecom-frontend olaylari -> dataLayer) - '
   'urun bagimsiz ve saglam ama SITE YAYINI gerektirir; (b) GTM DOM/click tetikleyicisi - '
   'yayin gerektirmez ama urun verisini DOM''dan kazimak zorunda kalir ve bu, CR-017''nin '
   'yasakladigi turden KIRILGAN/SAYFA-YAPISINA-GOMULU bir cozumdur. '
   '🔴 ONERI: (a). Site yayini "mevcut calisan sistemi bozma ihtimali" tasidigi icin '
   'AYRI ONAY bekleniyor.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

COMMIT;
