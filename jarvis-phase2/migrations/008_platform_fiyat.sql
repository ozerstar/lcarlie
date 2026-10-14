-- 008 — PLATFORM BAZLI FİYAT MATRİSİ (sahip kararı, 20.09.2026)
--
-- KARAR
-- Özer Yıldız: "Farklı platformlara farklı fiyat belirleyebilelim. Wix'te
-- 1000 TL, Trendyol'da 1200 yapabileyim. İstersem yüzdesel toplu müdahale,
-- istersem tek tek." Ve: "hepsi gene benim onayıma baksın."
--
-- NE KURULUYOR
-- 1. core.platform              -- hangi platformlar var, hangisine yazılabilir
-- 2. core.urun_platform_fiyat   -- ONAYLANMIŞ fiyat, ürün × platform, ZAMANA GÖRE VERSİYONLU
-- 3. mart.platform_fiyat_matrisi-- panelin okuyacağı ızgara
--
-- NE KURULMUYOR — VE NEDEN
-- Ayrı bir onay kuyruğu KURULMUYOR. core.ai_action_proposal /
-- ai_action_approval / ai_action_execution zaten var ve PRICE_CHANGE işlem
-- tipi tanımlı (risk CRITICAL). İkinci bir onay yolu açmak, tek onay
-- kapısı kuralını delerdi. Fiyat değişikliği -- ister Jarvis önersin ister
-- insan elle girsin -- O yoldan geçer.
--
-- VERSİYONLAMA CR-006 DESENİ
-- Fiyat zamana göre versiyonlanır (gecerli_baslangic / gecerli_bitis).
-- Üzerine yazılmaz: "geçen ay Trendyol'da kaça satıyorduk" sorusu
-- cevaplanabilir kalmalı. Açık satır bitis IS NULL ile bulunur.
--
-- UYGULAMA BU MIGRATION'DA AÇILMIYOR
-- core.ai_action_type.execution_enabled hâlâ false. Bu tablo yalnız
-- NİYETİ tutar: "Trendyol'da 1200 olsun". Dışarı yazma ayrı ve açık bir
-- karardır; burada yapılmaz.
--
-- GERİ ALMA: migrations/rollback/008_platform_fiyat_ROLLBACK.sql

BEGIN;

-- ---------------------------------------------------------------- platform
CREATE TABLE IF NOT EXISTS core.platform (
  kod           text PRIMARY KEY,
  ad            text        NOT NULL,
  aktif         boolean     NOT NULL DEFAULT false,
  -- Jarvis bu platforma YAZABILIR mi? Satici hesabi ve API anahtari
  -- olmadan true yapilmaz. Varsayilan kapali.
  yazma_izni    boolean     NOT NULL DEFAULT false,
  -- Fiyatin otoritesi bu platformun kendisi mi (Wix icin evet, 007 karari).
  fiyat_otoritesi boolean   NOT NULL DEFAULT false,
  not_          text,
  guncelleme    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.platform IS
  'Satis platformlari. yazma_izni, satici hesabi + API anahtari dogrulanmadan '
  'true YAPILMAZ.';

INSERT INTO core.platform (kod, ad, aktif, yazma_izni, fiyat_otoritesi, not_) VALUES
  ('wix',         'Wix (lcarlie.shop)', true,  false, true,
   'Fiyat otoritesi -- sahip karari 20.09.2026 (migration 007).'),
  ('trendyol',    'Trendyol',           false, false, false,
   'Satici hesabi VAR; API anahtari bekleniyor.'),
  ('hepsiburada', 'Hepsiburada',        false, false, false,
   'Satici hesabi VAR; API anahtari bekleniyor.'),
  ('n11',         'N11',                false, false, false,
   'Satici hesabi VAR; API anahtari bekleniyor.'),
  ('idefix',      'Idefix',             false, false, false,
   'Satici hesabi DOGRULANMADI.')
ON CONFLICT (kod) DO NOTHING;

-- ------------------------------------------------- urun x platform fiyat
CREATE TABLE IF NOT EXISTS core.urun_platform_fiyat (
  id                bigserial PRIMARY KEY,
  urun_id           text        NOT NULL,
  platform_kod      text        NOT NULL REFERENCES core.platform(kod),
  fiyat             numeric     NOT NULL CHECK (fiyat > 0),
  para_birimi       text        NOT NULL DEFAULT 'TRY',
  -- Bu fiyat nasil belirlendi? Denetimde ilk sorulan sey.
  --   MANUEL      : insan tek tek girdi
  --   TOPLU_YUZDE : yuzdesel toplu islem uretti
  --   TOPLU_SABIT : sabit tutar toplu islem uretti
  --   PLATFORM    : platformdan okundu (gozlem)
  yontem            text        NOT NULL
                    CHECK (yontem IN ('MANUEL','TOPLU_YUZDE','TOPLU_SABIT','PLATFORM')),
  -- Toplu islemde ayni partiye ait satirlar bu id ile birlikte geri alinir.
  toplu_islem_id    uuid,
  -- Hangi onay bu fiyati gecerli kildi. NULL = henuz onaydan gecmemis
  -- (yalniz PLATFORM gozlemi icin kabul edilir).
  onay_action_id    text,
  gerekce           text,
  -- CR-006 deseni: uzerine yazilmaz, versiyonlanir.
  gecerli_baslangic timestamptz NOT NULL DEFAULT now(),
  gecerli_bitis     timestamptz,
  kaydeden          text        NOT NULL,
  kayit_zamani      timestamptz NOT NULL DEFAULT now()
);

-- Bir urunun bir platformda AYNI ANDA tek acik fiyati olur.
CREATE UNIQUE INDEX IF NOT EXISTS urun_platform_fiyat_acik
  ON core.urun_platform_fiyat (urun_id, platform_kod)
  WHERE gecerli_bitis IS NULL;

CREATE INDEX IF NOT EXISTS urun_platform_fiyat_toplu
  ON core.urun_platform_fiyat (toplu_islem_id)
  WHERE toplu_islem_id IS NOT NULL;

COMMENT ON TABLE core.urun_platform_fiyat IS
  'Urun x platform fiyati, zamana gore versiyonlu. Acik satir: gecerli_bitis '
  'IS NULL. Bu tablo NIYETI tutar; platforma yazma ayri ve acik bir karardir.';

-- --------------------------------------------------------- panel gorunumu
CREATE OR REPLACE VIEW mart.platform_fiyat_matrisi AS
WITH acik AS (
  SELECT urun_id, platform_kod, fiyat, yontem, gerekce,
         gecerli_baslangic, kaydeden
  FROM core.urun_platform_fiyat
  WHERE gecerli_bitis IS NULL
)
SELECT
  g.urun_id,
  g.urun_adi,
  p.kod                       AS platform_kod,
  p.ad                        AS platform_adi,
  p.aktif                     AS platform_aktif,
  p.yazma_izni,
  -- Referans fiyat: 007 karariyla Wix otorite.
  g.musteriye_soylenecek_fiyat AS referans_fiyat,
  g.fiyat_kaynagi             AS referans_kaynagi,
  a.fiyat                     AS platform_fiyati,
  a.yontem,
  a.gerekce,
  a.gecerli_baslangic,
  a.kaydeden,
  -- Platform fiyati belirlenmemisse referans gecerlidir.
  COALESCE(a.fiyat, g.musteriye_soylenecek_fiyat) AS gecerli_fiyat,
  CASE
    WHEN a.fiyat IS NULL THEN 'REFERANS'
    WHEN g.musteriye_soylenecek_fiyat IS NULL THEN 'REFERANS_YOK'
    WHEN a.fiyat > g.musteriye_soylenecek_fiyat THEN 'YUKSEK'
    WHEN a.fiyat < g.musteriye_soylenecek_fiyat THEN 'DUSUK'
    ELSE 'AYNI'
  END AS fark_durumu,
  CASE
    WHEN a.fiyat IS NULL OR g.musteriye_soylenecek_fiyat IS NULL
         OR g.musteriye_soylenecek_fiyat = 0 THEN NULL
    ELSE round((a.fiyat / g.musteriye_soylenecek_fiyat - 1) * 100, 1)
  END AS fark_yuzde
FROM mart.fiyat_gercegi g
CROSS JOIN core.platform p
LEFT JOIN acik a ON a.urun_id = g.urun_id AND a.platform_kod = p.kod;

COMMENT ON VIEW mart.platform_fiyat_matrisi IS
  'Panel izgarasi: urun x platform. Platform fiyati girilmemisse referans '
  '(Wix) fiyati gecerlidir; fark_durumu REFERANS der.';

GRANT SELECT ON mart.platform_fiyat_matrisi TO ai_reader;
GRANT SELECT ON core.platform               TO ai_reader;

COMMIT;
