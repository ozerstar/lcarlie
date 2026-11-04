-- =============================================================================
-- CR-017 VELO OBSERVABILITY  -  DURUM KAYDI  (17.09.2026)
-- 🔴 KOD YAZILDI, DAGITILMADI. Iki karar bekliyor.
-- =============================================================================
BEGIN;

INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('cr017_velo_durum', 'YAZILDI_DAGITILMADI',
   'velo-masterPage-observability.js kaynak klasorde hazir. Kural taramasi gecti: '
   'urun literali 0, DOM selector 0, click scraping 0. Dagitim IKI KARARA bagli.'),

  ('cr017_velo_blocker_1', 'SITE_IKI_BRANCH',
   '🔴 Wix editoru acilirken "Choose a branch of LCARLIE" diyaloğu cikti: '
   'Original-Branch ve "Wix studio version" olmak uzere IKI BRANCH var. '
   'Hangisinin CANLI oldugu ve digerinde ne bekledigi BILINMIYOR. '
   'Yanlis branch''ten yayin, canli siteyi DEGISTIREBILIR. '
   'Bu, onayin kapsamadigi bir risk sinifidir ("mevcut calisan sistemi bozma '
   'ihtimali yuksek degisiklik"). Editor ACILMADI, iptal edildi, hicbir sey degismedi.'),

  ('cr017_velo_blocker_2', 'VELO_FRONTEND_CART_API_DOGRULANMADI',
   'Wix dokumantasyon araclari klasik Velo frontend referansini (wix-ecom-frontend '
   'cart-change olayi) indekslemiyor; API imzasi DOGRULANAMADI. '
   'KOD BU YUZDEN VARSAYMIYOR: runtime feature-detection ile bilinen adlar tek tek '
   'denenir, hicbiri yoksa add_to_cart SESSIZCE OLCULMEZ ve neden konsola yazilir. '
   'Yani eksik API sitede HATA URETMEZ - ama dogrulanana kadar add_to_cart''in '
   'calisacagi da GARANTI DEGILDIR.'),

  ('cr017_velo_purchase', 'BILEREK_UYGULANMADI',
   '🔴 purchase Velo tarafinda UYGULANMADI. Sebep CR-017 kurali: "Native Wix event '
   'varsa duplicate uretme." Wix''in purchase gonderip gondermedigi OLCULMEDI '
   '(gercek siparis gerektirir). Olcmeden eklemek GA4''te CIFT purchase ve cift '
   'transaction_id yaratir, mutabakati bozar. Once olculecek.'),

  ('cr017_velo_registry_gereksinimi', 'WIX_CMS_KOLEKSIYONU_GEREKLI',
   'Ozel landing view_item icin Wix CMS''te SayfaUrunKayit koleksiyonu gerekir '
   '(sayfaYolu · urunId · sayfaRolu). Postgres''teki core.sayfa_urun Velo''dan '
   'okunamaz. Koleksiyon yoksa kod ozel landing view_item URETMEZ - slug''a bakarak '
   'urun TAHMIN ETMEZ (CR-017 yasagi).')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

COMMIT;