-- 009 — PRICE_CHANGE TEK KİŞİ ONAYI (sahip kararı, 20.09.2026)
--
-- KARAR
-- Özer Yıldız: "Tek kişi onaylayacak."
--
-- ÖNCESİ
-- PRICE_CHANGE.approval_mode = 'TWO_PERSON'. İki ayrı kişinin onayı
-- gerekiyordu. İşletmede fiyat kararını veren tek kişi olduğu için bu
-- kapı pratikte hiç geçilemezdi -- yani özellik kapalıydı.
--
-- SONRASI
-- approval_mode = 'ONE_PERSON'. Fiyat değişikliği tek onayla geçer.
--
-- NE DEĞİŞMİYOR -- BUNLAR KASITLI
-- 1. risk_class CRITICAL kalır. Kayıt, denetim ve geri alma yolu aynen sürer.
-- 2. execution_enabled false kalır. Onay ayrı şey, DIŞARIYA YAZMA ayrı şey.
--    Bu migration yalnız onay sayısını değiştirir; platforma yazmayı AÇMAZ.
-- 3. Kendi önerisini onaylayamama kuralı aynen geçerlidir. Tek kişi demek,
--    "Jarvis kendi önerisini onaylasın" demek DEĞİLDİR -- onaylayan insandır.
--
-- NEDEN AYRI MIGRATION
-- Yönetişim değişikliği veri değişikliğinden ayrı tutulur ki geri alınırken
-- fiyat matrisi bozulmasın.
--
-- GERİ ALMA: migrations/rollback/009_tek_kisi_onay_ROLLBACK.sql

BEGIN;

-- Beklenen durumda mıyız? Değilsek durur, sessizce farklı bir şey yapmayız.
DO $$
DECLARE mevcut text;
BEGIN
  SELECT approval_mode INTO mevcut
  FROM core.ai_action_type WHERE action_type = 'PRICE_CHANGE';
  IF mevcut IS NULL THEN
    RAISE EXCEPTION 'PRICE_CHANGE islem tipi yok -- beklenmeyen sema';
  END IF;
  IF mevcut <> 'TWO_PERSON' THEN
    RAISE EXCEPTION 'PRICE_CHANGE.approval_mode beklenen TWO_PERSON degil, % -- migration daha once uygulanmis olabilir', mevcut;
  END IF;
END $$;

UPDATE core.ai_action_type
SET approval_mode = 'ONE_PERSON',
    description   = 'Fiyat degisikligi onerisi. Sahip karari 20.09.2026: tek '
                    'kisi onayi yeterli. Uygulama (execution) hala KAPALI.'
WHERE action_type = 'PRICE_CHANGE';

-- Doğrula: onay tek kişiye düştü ama uygulama HÂLÂ kapalı olmalı.
DO $$
DECLARE m text; e boolean;
BEGIN
  SELECT approval_mode, execution_enabled INTO m, e
  FROM core.ai_action_type WHERE action_type = 'PRICE_CHANGE';
  IF m <> 'ONE_PERSON' THEN
    RAISE EXCEPTION 'approval_mode guncellenmedi: %', m;
  END IF;
  IF e THEN
    RAISE EXCEPTION 'execution_enabled ACILMIS -- bu migration disariya yazmayi ACMAMALI';
  END IF;
END $$;

COMMIT;
