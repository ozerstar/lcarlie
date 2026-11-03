-- 071 — META_CAMPAIGN_CHANGE ve PRICE_CHANGE UYGULAMAYA AÇILIR (sahip kararı 03.11.2026)
--
-- KARAR
-- Özer Yıldız, Aşama 3 listesi için: "hepsini yap".
--
-- NE AÇILIR
-- execution_enabled = true; scripts/aksiyon-uygulayici.py bu iki türü
-- ONAYDAN SONRA uygular ve sonucu platformdan geri okuyarak doğrular.
--   META_CAMPAIGN_CHANGE  PAUSE/RESUME   günde en fazla 10
--   PRICE_CHANGE          Wix fiyatı     günde en fazla 5, tek adımda ≤ %30
--
-- NE DEĞİŞMİYOR -- KASITLI
-- 1. Onay kapısı aynen: her iş human_approver onayı + parmak izi ister.
--    Jarvis kendi önerisini onaylayamaz.
-- 2. risk_class ve approval_mode aynı kalır (009'daki tek kişi kararı dahil).
-- 3. Diğer türler (WIX_PUBLISH, WHATSAPP_SEND_TEMPLATE, DRAFT_CUSTOMER_REPLY)
--    KAPALI kalır; kendi uygulayıcıları yazılınca ayrı migration ile açılır.
--
-- ACİL DURDURMA
--   UPDATE core.ai_orchestrator_config SET config_value='false'
--    WHERE config_key='uygulayici_acik';
--
-- GERİ ALMA: migrations/rollback/071_meta_fiyat_uygulama_ROLLBACK.sql

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname='ai_claim_approved_action_tipli') THEN
    RAISE EXCEPTION '070 uygulanmamis: tipli kapma fonksiyonu yok';
  END IF;
END $$;

INSERT INTO core.ai_action_tavan(action_type, gunluk_adet, gunluk_tutar, not_metni) VALUES
  ('META_CAMPAIGN_CHANGE', 10, NULL,
   'PAUSE harcamayi durdurur; RESUME yeniden baslatir. Gunde en fazla 10 degisiklik.'),
  ('PRICE_CHANGE', 5, NULL,
   'Wix fiyati. Gunde en fazla 5 urun; tek adimda %30 ustu degisim uygulayicida reddedilir.')
ON CONFLICT (action_type) DO UPDATE
  SET gunluk_adet=EXCLUDED.gunluk_adet, gunluk_tutar=EXCLUDED.gunluk_tutar,
      not_metni=EXCLUDED.not_metni, guncelleme=clock_timestamp();

UPDATE core.ai_action_type SET execution_enabled = true
 WHERE action_type IN ('META_CAMPAIGN_CHANGE', 'PRICE_CHANGE');

COMMIT;
