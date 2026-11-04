-- =============================================================================
-- L'CARLIE - META HESAP KAYDI ve IKI AYRI KAPSAMA OLCUSU  (16.09.2026)
--
-- 🔴 NEDEN AYRI DOSYA VE NEDEN ERKEN UYGULANIR:
--    mart.nakit_gunluk, mart.nakit_ozet, mart.gunluk_hazirlik ve mart-ajans
--    bu view'i okur. Bu yuzden onlardan ONCE kurulmali. Kaynak otoritesi
--    ve karar hafizasi duzeltmeleri ise EN SONA aittir (operating-truth-yamasi.sql),
--    cunku core-authority-guncelle.sql ve cr016/meta-kapsama yamalari
--    source_authority'yi sonradan yeniden yaziyor - erken yazilan duzeltme
--    sessizce EZILIRDI.
--
-- 🔴 DUZELTILEN VARSAYIM: "Meta kapsamasi 1/3, yani eksik veri."
--    Uc hesap BILINIYOR ama yalnizca BIRI operasyonda; digerlerinde reklam
--    yayinlanmiyor. Bu bir VERI KALITESI ACIGI degil, KAPSAM DISI birakmadir.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- BILINEN HESAPLAR ve OPERASYONEL DURUMLARI
-- ---------------------------------------------------------------------------
-- 🔴 raw.meta_hesap yalnizca ERISILEBILEN hesabi tutar (API'den ne okunduysa).
--    Erisilemeyen hesaplar orada YOK, dolayisiyla "3 hesap var" bilgisi hicbir
--    yerde yazili degildi: "/3" paydasi mart-nakit.sql ve mart-ajans.sql icine
--    SABIT KODLANMISTI. Sabit payda, hesap sayisi degistiginde sessizce yalan
--    soyler ve kimse fark etmez.
CREATE TABLE IF NOT EXISTS core.meta_hesap_kayit (
  hesap_id          text PRIMARY KEY,
  ad                text,
  -- ACTIVE            = reklam yayinlaniyor, paid-media operasyonunda
  -- INACTIVE_EXCLUDED = reklam yayinlanmiyor, kapsam disi (ACIKLIK DEGIL)
  operasyonel_durum text NOT NULL
    CHECK (operasyonel_durum IN ('ACTIVE','INACTIVE_EXCLUDED')),
  -- 🔴 Durumun NEREDEN geldigi yazilir. Sahip beyani da bir kaynaktir ama
  --    OLCUM DEGILDIR; ikisi ayni kutuya konmaz.
  durum_kaynagi     text NOT NULL,
  son_dogrulama     timestamptz NOT NULL DEFAULT clock_timestamp(),
  notlar            text
);

COMMENT ON TABLE core.meta_hesap_kayit IS
  'Bilinen Meta reklam hesaplari ve OPERASYONEL durumlari. Kapsama paydasi buradan turer, sabit kodlanmaz.';

INSERT INTO core.meta_hesap_kayit
  (hesap_id, ad, operasyonel_durum, durum_kaynagi, notlar) VALUES
  ('1301171572214198', 'Lcarlie Reklam Hesabi', 'ACTIVE',
   'OLCULDU: Graph API act_/insights - harcama satirlari okunuyor',
   'Tek aktif paid-media hesabi. META_ADS_TOKEN ile ad/adset/creative seviyesi cekiliyor.'),
  ('560782561026922', NULL, 'INACTIVE_EXCLUDED',
   'SAHIP BEYANI + Business Manager UI olcumu (16.09.2026)',
   'Reklam yayinlanmiyor; BM''de uc yilda hic kampanya gorulmedi. Sistem kullanicisina '
   'atanmamis (#200) - ancak bu VERI ACIGI DEGIL: okunacak harcama yok.'),
  ('1601342818221781', NULL, 'INACTIVE_EXCLUDED',
   'SAHIP BEYANI + Business Manager UI olcumu (16.09.2026)',
   'Reklam yayinlanmiyor; BM''de 1 Tem-16 Eyl 2026 harcamasi 0,00 TL. Sistem kullanicisina '
   'atanmamis (#200) - ancak bu VERI ACIGI DEGIL: okunacak harcama yok.')
ON CONFLICT (hesap_id) DO UPDATE
  SET ad                = coalesce(EXCLUDED.ad, core.meta_hesap_kayit.ad),
      operasyonel_durum = EXCLUDED.operasyonel_durum,
      durum_kaynagi     = EXCLUDED.durum_kaynagi,
      son_dogrulama     = clock_timestamp(),
      notlar            = EXCLUDED.notlar;

-- ---------------------------------------------------------------------------
-- IKI AYRI KAPSAMA
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.meta_kapsama CASCADE;

CREATE VIEW mart.meta_kapsama AS
WITH k AS (
  SELECT count(*)                                                      AS bilinen,
         count(*) FILTER (WHERE operasyonel_durum='ACTIVE')            AS aktif,
         count(*) FILTER (WHERE operasyonel_durum='INACTIVE_EXCLUDED') AS kapsam_disi
    FROM core.meta_hesap_kayit
), e AS (
  SELECT count(*)                                                      AS erisilen,
         count(*) FILTER (WHERE r.hesap_id IN
           (SELECT hesap_id FROM core.meta_hesap_kayit WHERE operasyonel_durum='ACTIVE'))
                                                                       AS erisilen_aktif
    FROM raw.meta_hesap r
)
SELECT
  k.bilinen, k.aktif, k.kapsam_disi, e.erisilen, e.erisilen_aktif,

  -- 🔴 BILINEN HESAP KAPSAMASI: envanter olcusu. Raporda GORUNUR ama
  --    Growth/Agency kararinin esasi DEGILDIR.
  format('%s/%s', e.erisilen, k.bilinen)                               AS bilinen_kapsama,

  -- 🔴 AKTIF OPERASYONEL KAPSAMA: karar metrigi budur. Payda AKTIF hesap
  --    sayisidir - bir hesap ACTIVE'e cevrilirse payda kendiliginden buyur
  --    ve erisim yoksa oran duser. Kod degisikligi GEREKMEZ.
  format('%s/%s', e.erisilen_aktif, k.aktif)                           AS aktif_kapsama,

  (e.erisilen_aktif >= k.aktif AND k.aktif > 0)                        AS aktif_tam,

  CASE
    WHEN k.aktif = 0                 THEN 'NO_ACTIVE_ACCOUNT'
    WHEN e.erisilen_aktif >= k.aktif THEN 'COMPLETE'
    ELSE 'PARTIAL'
  END                                                                  AS aktif_durum,

  -- 🔴 TERMINOLOJI KILIDI (Chief Architect, 16.09.2026).
  --    "Meta coverage %100" TEK BASINA YAZILMAZ. Yuzde, her zaman neyin
  --    yuzdesi oldugu ile birlikte gecer:
  --        Operational Meta Coverage: 100% (1/1 active known accounts)
  --    Sebep: business_management izni olmadigi icin hesap KESFI yapilamiyor.
  --    Dolayisiyla sistemin soyledigi sey su DEGIL:
  --        "Meta Business icindeki butun hesaplari otomatik kesfediyoruz"
  --    Soyledigi sey su:
  --        "registry'de BILINEN ve AKTIF olarak siniflandirilmis operasyonel
  --         hesaplarin %100'u kapsaniyor"
  --    Ciplak "%100", ikincisini birincisi gibi okutur.
  format('Operational Meta Coverage: %s%% (%s/%s active known accounts)',
         CASE WHEN k.aktif > 0
              THEN round(100.0 * e.erisilen_aktif / k.aktif)::text ELSE '—' END,
         e.erisilen_aktif, k.aktif)                                    AS etiket,

  -- 🔴 Bu cumle raporlarda AYNEN kullanilir ki ayni olgu uc yerde uc farkli
  --    sekilde anlatilmasin.
  CASE
    WHEN e.erisilen_aktif >= k.aktif AND k.aktif > 0 THEN
      format('Registry''de bilinen ve AKTIF siniflandirilmis operasyonel hesaplarin '
             'tamami kapsaniyor (%s/%s). Bilinen %s hesabin %s tanesi reklam yayinlamiyor '
             '(INACTIVE_EXCLUDED) - bu bir veri acigi DEGIL, kapsam disi birakmadir. '
             'DIKKAT: bu "Meta Business''teki tum hesaplari kesfediyoruz" DEMEK DEGILDIR - '
             'business_management izni yok, kesif elle yapilir (DISCOVERY_VISIBILITY_RISK).',
             e.erisilen_aktif, k.aktif, k.bilinen, k.kapsam_disi)
    ELSE
      format('AKTIF hesaplarin %s/%s tanesi okunabiliyor - EKSIK HARCAMA RISKI VAR.',
             e.erisilen_aktif, k.aktif)
  END                                                                  AS ifade,

  -- 🔴 KESIF RISKI GROWTH BLOCKER DEGILDIR (Chief Architect kilidi).
  --    business_management eksikligi bugun operasyonu ENGELLEMIYOR; yalnizca
  --    ileride yeni bir reklam hesabi acilirsa otomatik kesfedilemeyecegi
  --    anlamina geliyor. Bu bir OPS / elle kontrol riskidir, veri acigi degil.
  --    Blocker listesine konursa gercek blocker'lari (COGS, orneklem, atif)
  --    gurultuye bogar.
  'DISCOVERY_VISIBILITY_RISK'                                          AS kesif_riski,
  'OPS / elle kontrol - GROWTH BLOCKER DEGIL. business_management izni yok, '
  'hesap kesfi elle yapilir: yeni acilan bir reklam hesabi core.meta_hesap_kayit''a '
  'elle eklenmedikce kapsama paydasi eski kalir.'                      AS kesif_riski_aciklama
FROM k, e;

COMMENT ON VIEW mart.meta_kapsama IS
  'Iki ayri kapsama: bilinen hesap (envanter) ve AKTIF operasyonel (karar metrigi). Payda sabit kodlanmaz.';

COMMIT;
