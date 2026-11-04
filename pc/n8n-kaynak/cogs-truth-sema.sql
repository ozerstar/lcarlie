-- =============================================================================
-- L'CARLIE - COGS / UNIT ECONOMICS TRUTH LAYER
--
-- TEMEL SORU: "Bir siparis gercekten bize ne kazandirdi?"
--
-- 🔴 IKI METRIK, ASLA TEK SAYI:
--      ORDER_CONTRIBUTION_PRE_MARKETING    -> siparisin kendi ekonomisi
--      COMMERCIAL_CONTRIBUTION_AFTER_MEDIA -> reklam dahil ticari sonuc
--    Ikincisi siparis grain'inde HESAPLANMAZ. CR-011'de olculdu: konusma-siparis
--    eslesmesi 0/259, yani order-level deterministik reklam maliyeti atamasi YOK.
--    Bu yuzden siparis satirinda reklam maliyeti alani HIC ACILMIYOR.
--
-- 🔴 UNKNOWN != 0 TL.  Bilinmeyen bir maliyeti sifir saymak pozitif marj
--    URETMEKTIR. Katki "bilinen bilesenlerden" hesaplanir, eksiklerin ADI yazilir.
--
-- 🔴 NOT_YET_KNOWN != UNKNOWN.  Biri zamanla kendiliginden kapanir (tahsilat
--    gerceklesince COD komisyonu belli olur), digeri ancak biri is yaparsa.
--
-- 🔴🔴 SINIR (BOUND) SEMANTIGI - 17.09.2026 Chief Architect semantic audit:
--    Ilk surumde bu rakama "ALT SINIR" dedim. YANLISTI ve matematigi kontrol
--    edince cikti:
--      - Cozulmemis MALIYETLER katkiyi yalniz DUSURUR      (yon: asagi)
--      - Ama COGS'un KDV tabani da cozulmemis: 400 TL KDV DAHIL ise gercek
--        COGS 333,33'tur, yani maliyet DUSER ve katki ARTAR (yon: yukari)
--        Olculdu (son 30 gun): bu duzeltme katkiyi 800,00 TL ARTIRABILIR.
--    Iki yonlu belirsizlik varken "alt sinir" demek YANLIS KESINLIKTIR.
--    Bu yuzden varsayilan ad NOTR: KNOWN_COMPONENT_CONTRIBUTION.
--    UST SINIR ayrica ve ACIKCA hesaplanir (bkz. en_iyi_olasi_katki):
--      ust_sinir = bilinen_katki + COGS_KDV_lehte_duzeltmesi
--    cunku diger tum cozulmemis bilesenler yalniz maliyettir (>= 0).
--
-- 🔴 YENIDEN KURULMAYAN SEYLER (minimum-diff):
--      core.urun_maliyet + core.maliyet_bul()  -> effective-dated COGS, AYNEN
--      mart.siparis_kalem · mart.gonderi · mart.siparis · core.ayar
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) URUN DISI MALIYET BILESENLERI  -  effective-dated + kanit metadatasi
-- ---------------------------------------------------------------------------
-- 🔴 NEDEN AYRI TABLO: core.urun_maliyet URUN bazlidir. Paketleme, odeme
--    komisyonu, kanal komisyonu urun bazli DEGIL - siparis ya da tutar
--    bazlidir. Ayni tabloya sokulsaydi urun_id'ye sahte deger yazmak gerekirdi.
CREATE TABLE IF NOT EXISTS core.maliyet_bileseni (
  bilesen_id        bigserial PRIMARY KEY,
  bilesen           text NOT NULL,
  uygulama          text NOT NULL CHECK (uygulama IN ('SIPARIS_SABIT','BIRIM_SABIT','CIRO_YUZDE')),
  deger             numeric,               -- NULL = bilinmiyor (0 DEGIL)
  para_birimi       text NOT NULL DEFAULT 'TRY',
  -- 🔴 KDV TABANI ACIKCA TASINIR. "400 TL" tek basina eksik bilgidir.
  kdv_tabani        text NOT NULL DEFAULT 'BILINMIYOR'
                    CHECK (kdv_tabani IN ('KDV_HARIC','KDV_DAHIL','BILINMIYOR','YOK')),
  kanit_sinifi      text NOT NULL
                    CHECK (kanit_sinifi IN ('MEASURED','BUSINESS_INPUT','DERIVED',
                                            'ESTIMATED','UNKNOWN','NOT_YET_KNOWN',
                                            'UNKNOWN_BUSINESS_INPUT_REQUIRED')),
  kapsam            text NOT NULL,
  kaynak            text NOT NULL,
  gerekce           text,
  gecerli_baslangic timestamptz NOT NULL DEFAULT '2026-01-01',
  gecerli_bitis     timestamptz,
  son_dogrulama     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- ---------------------------------------------------------------------------
-- MIGRATION: `zorunlu boolean` -> `kritiklik text`   (rerun-safe, additive)
-- ---------------------------------------------------------------------------
-- 🔴 NEDEN DEGISTI (17.09.2026, semantic audit): ilk surumde `zorunlu` vardi
--    ve sinirlari TERS cizilmisti - paketleme zorunlu (INCOMPLETE yapardi),
--    kanal komisyonu zorunlu degil (PARTIAL birakirdi). Locked design bunun
--    TERSINI soyluyor:
--      CRITICAL  -> urun COGS · odeme/COD komisyonu · giden kargo ·
--                   kanal komisyonu · iade/iade etkisi     -> INCOMPLETE
--      SECONDARY -> paketleme · numune/tester              -> PARTIAL
-- 🔴 KEYFI PARASAL ESIK YOK. Tamlik BILESEN BAZLIDIR. "Materyal esigi" bir
--    is girdisi ya da blocker DEGILDIR; ileride istege bagli politika olabilir.
DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='core' AND table_name='maliyet_bileseni'
                    AND column_name='kritiklik') THEN
    ALTER TABLE core.maliyet_bileseni
      ADD COLUMN kritiklik text NOT NULL DEFAULT 'CRITICAL';
    ALTER TABLE core.maliyet_bileseni
      ADD CONSTRAINT maliyet_bileseni_kritiklik_check
      CHECK (kritiklik IN ('CRITICAL','SECONDARY'));
  END IF;
  -- 🔴 KATKI YONU (17.09.2026, Chief Architect kalici regresyon kurali).
  --    Yeni bir cozulmemis bilesen eklendiginde, YONU TANIMLANMADAN
  --    katki/sinir hesabina SESSIZCE girmemeli ve mevcut katki_ust_siniri
  --    kanitini sessizce GECERSIZ KILMAMALI.
  --    Varsayilan bilerek 'BILINMIYOR': yeni bir satir beyan edilmeden
  --    eklenirse mutabakat KIRMIZI yanar, sessizce gecmez.
  --      AZALTIR  -> maliyet (>= 0). Katkiyi yalniz DUSURUR; ust sinira girmez.
  --      ARTIRIR  -> katkiyi YUKARI tasiyabilir. UST SINIRA DAHIL EDILMEK
  --                  ZORUNDADIR, yoksa ust sinir OLDUGUNDAN DUSUK kalir.
  --      BILINMIYOR -> yon beyan edilmemis. Sinir kaniti URETILEMEZ.
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='core' AND table_name='maliyet_bileseni'
                    AND column_name='katki_yonu') THEN
    ALTER TABLE core.maliyet_bileseni
      ADD COLUMN katki_yonu text NOT NULL DEFAULT 'BILINMIYOR';
    ALTER TABLE core.maliyet_bileseni
      ADD CONSTRAINT maliyet_bileseni_katki_yonu_check
      CHECK (katki_yonu IN ('AZALTIR','ARTIRIR','BILINMIYOR'));
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='core' AND table_name='maliyet_bileseni'
                AND column_name='zorunlu') THEN
    -- bilesen_bul() bu kolonu donduruyordu; once fonksiyon dusurulur.
    DROP FUNCTION IF EXISTS core.bilesen_bul(text, timestamptz);
    ALTER TABLE core.maliyet_bileseni DROP COLUMN zorunlu;
  END IF;
END $mig$;

CREATE UNIQUE INDEX IF NOT EXISTS maliyet_bileseni_acik_tek
  ON core.maliyet_bileseni (bilesen) WHERE gecerli_bitis IS NULL;

COMMENT ON TABLE core.maliyet_bileseni IS
  'Urun disi degisken maliyet bilesenleri. Effective-dated + kanit sinifli. deger NULL = bilinmiyor, 0 DEGIL.';

-- ---------------------------------------------------------------------------
-- 2) SEED  -  bilinmeyenler ACIKCA bilinmiyor olarak girer
-- ---------------------------------------------------------------------------
INSERT INTO core.maliyet_bileseni
  (bilesen, uygulama, deger, kdv_tabani, kanit_sinifi, kritiklik, kapsam, kaynak, gerekce)
SELECT * FROM (VALUES
  ('PAKETLEME', 'SIPARIS_SABIT', NULL::numeric, 'BILINMIYOR',
   'UNKNOWN_BUSINESS_INPUT_REQUIRED', 'SECONDARY', 'ORDER',
   'YOK - hicbir tabloda kaydi yok',
   'Kutu/dolgu/etiket/bant. SECONDARY: cozulmemesi ekonomiyi INCOMPLETE yapmaz '
   'ama eksik_bilesenler icinde ACIKCA gorunur ve katkiyi iyimser birakir.'),

  ('ODEME_KOMISYONU', 'CIRO_YUZDE', NULL, 'BILINMIYOR',
   'UNKNOWN_BUSINESS_INPUT_REQUIRED', 'CRITICAL', 'ORDER',
   'YOK - PayTR settlement bagli degil',
   'Online odeme komisyonu. CRITICAL: her tahsil edilmis sipariste MUTLAKA olusur '
   've tutari kucuk degildir. Beyan edilirse BUSINESS_INPUT olur, MEASURED OLMAZ.'),

  ('KANAL_KOMISYONU', 'CIRO_YUZDE', NULL, 'BILINMIYOR',
   'UNKNOWN_BUSINESS_INPUT_REQUIRED', 'CRITICAL', 'ORDER',
   'YOK - dogrulanmadi',
   'Kendi sitemiz oldugu icin 0 BEKLENIYOR ama DOGRULANMADI; beklenti olcum degildir. '
   'CRITICAL: 0 oldugu dogrulanana kadar katki oldugundan yuksek gorunur. '
   'Sahip 0 derse MEASURED 0 olarak girer ve bu bilesen kapanir.')
) AS v(bilesen, uygulama, deger, kdv_tabani, kanit_sinifi, kritiklik, kapsam, kaynak, gerekce)
WHERE NOT EXISTS (
  SELECT 1 FROM core.maliyet_bileseni m
   WHERE m.bilesen = v.bilesen AND m.gecerli_bitis IS NULL);

-- 🔴 Dunku satirlarin kritikligi locked design'a hizalanir (rerun-safe).
UPDATE core.maliyet_bileseni SET kritiklik = 'SECONDARY'
 WHERE bilesen = 'PAKETLEME' AND gecerli_bitis IS NULL AND kritiklik <> 'SECONDARY';
UPDATE core.maliyet_bileseni SET kritiklik = 'CRITICAL'
 WHERE bilesen IN ('ODEME_KOMISYONU','KANAL_KOMISYONU')
   AND gecerli_bitis IS NULL AND kritiklik <> 'CRITICAL';

-- 🔴 Mevcut uc bilesenin YONU acikca beyan edilir: ucu de MALIYETTIR,
--    yani katkiyi yalniz DUSURUR ve ust sinira GIRMEZ. Bu beyan olmadan
--    katki_ust_siniri kaniti gecerli degildir.
UPDATE core.maliyet_bileseni SET katki_yonu = 'AZALTIR'
 WHERE bilesen IN ('PAKETLEME','ODEME_KOMISYONU','KANAL_KOMISYONU')
   AND gecerli_bitis IS NULL AND katki_yonu <> 'AZALTIR';

-- ---------------------------------------------------------------------------
-- 3) BILESEN OKUYUCU  -  tarihe gore gecerli surum
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS core.bilesen_bul(text, timestamptz);
CREATE FUNCTION core.bilesen_bul(p_bilesen text, p_tarih timestamptz)
RETURNS TABLE (deger numeric, uygulama text, kanit_sinifi text, kritiklik text)
LANGUAGE sql STABLE AS $$
  SELECT m.deger, m.uygulama, m.kanit_sinifi, m.kritiklik
    FROM core.maliyet_bileseni m
   WHERE m.bilesen = p_bilesen
     AND m.gecerli_baslangic <= p_tarih
     AND (m.gecerli_bitis IS NULL OR m.gecerli_bitis > p_tarih)
   ORDER BY m.gecerli_baslangic DESC
   LIMIT 1;
$$;

COMMENT ON FUNCTION core.bilesen_bul(text, timestamptz) IS
  'Siparis TARIHINDE gecerli olan bilesen surumunu dondurur - bugunku degil.';

-- ---------------------------------------------------------------------------
-- 4) SIPARIS EKONOMISI
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.ekonomi_veri_kalitesi CASCADE;
DROP VIEW IF EXISTS mart.siparis_ekonomi       CASCADE;

CREATE VIEW mart.siparis_ekonomi AS
WITH kalem AS (
  SELECT k.siparis_id,
         sum(k.satir_ciro_net)                            AS net_ciro,
         sum(k.satir_maliyet)                             AS cogs,
         count(*) FILTER (WHERE NOT k.maliyeti_biliniyor) AS cogs_eksik_kalem
    FROM mart.siparis_kalem k GROUP BY k.siparis_id
), kargo AS (
  -- 🔴 KARGO SIPARISE ANCAK DETERMINISTIK BAG VARSA YAZILIR (foreignCode).
  --    Bag yoksa UNKNOWN'dur; ortalama kargo bedeli DAGITILMAZ.
  -- 🔴 toplam_maliyet kullanilir: extraFee zaten shipmentFee'nin ICINDE
  --    (olculdu, fark 0,00). Ikisi ayrica toplanirsa CIFT SAYIM olur.
  SELECT g.siparis_id,
         sum(g.toplam_maliyet) AS kargo_maliyet,
         sum(g.cod_komisyon)   AS cod_komisyon,
         count(*) FILTER (WHERE g.cod_komisyon_sinifi = 'NOT_YET_KNOWN') AS cod_bekleyen,
         count(*) FILTER (WHERE g.cod_komisyon_sinifi = 'UNKNOWN')       AS cod_bilinmeyen
    FROM mart.gonderi g WHERE g.siparis_id IS NOT NULL GROUP BY g.siparis_id
), b AS (
  SELECT s.siparis_id, s.olusturma, s.ciro_sinifi, s.olcumde,
         s.teslimat_durumu, s.odeme_durumu,
         k.net_ciro,
         -- 29.09.2026 · COGS KDV TABANI COZULDU: sahip beyani KDV_DAHIL.
         --   Ciro tarafi KDV HARIC olculuyor (net_ciro_kdv_haric). Maliyeti
         --   KDV DAHIL birakmak iki tarafi FARKLI tabanda karsilastirmak
         --   olurdu ve katkiyi sistematik olarak DUSUK gosterirdi.
         --
         -- 🔴 Ayari YAZMAK tek basina YETMIYORDU (olculdu 29.09.2026):
         --   eski kod yalnizca 'taban cozulmemisse yukari duzeltme IHTIMALI
         --   var' diyordu. Taban beyan edilince ihtimali sifirliyor ama
         --   maliyeti DUSURMUYORDU: dogru cevabi girmek ust siniri
         --   40.158 -> 36.425 TL'ye DUSURUYORDU. KDV_DAHIL dali eklendi.
         CASE WHEN (SELECT deger FROM core.ayar
                     WHERE anahtar = 'maliyet_kdv_tabani') = 'KDV_DAHIL'
              THEN round(k.cogs / 1.2, 2)
              ELSE k.cogs END                          AS cogs,
         k.cogs_eksik_kalem,
         kg.kargo_maliyet, kg.cod_komisyon, kg.cod_bekleyen, kg.cod_bilinmeyen,
         (kg.siparis_id IS NOT NULL) AS kargo_bagli,
         (SELECT deger     FROM core.bilesen_bul('PAKETLEME',       s.olusturma)) AS paketleme,
         (SELECT kritiklik FROM core.bilesen_bul('PAKETLEME',       s.olusturma)) AS paketleme_kritiklik,
         (SELECT deger     FROM core.bilesen_bul('ODEME_KOMISYONU', s.olusturma)) AS odeme_yuzde,
         (SELECT kritiklik FROM core.bilesen_bul('ODEME_KOMISYONU', s.olusturma)) AS odeme_kritiklik,
         (SELECT deger     FROM core.bilesen_bul('KANAL_KOMISYONU', s.olusturma)) AS kanal_yuzde,
         (SELECT kritiklik FROM core.bilesen_bul('KANAL_KOMISYONU', s.olusturma)) AS kanal_kritiklik,
         (SELECT deger FROM core.ayar WHERE anahtar='maliyet_kdv_tabani')         AS cogs_kdv_tabani,
         -- 29.09.2026 · Sahip beyani: 400 TL birim maliyet KARGOYU DA kapsiyor.
         --   Boyle oldugunda olculen kargo ucretini katkidan AYRICA dusmek
         --   ayni gideri IKI KEZ saymaktir (olculen tutar: 32 sipariste
         --   1.075,54 TL). Ayar yoksa eski davranis korunur.
         (SELECT deger FROM core.ayar WHERE anahtar='maliyet_kargo_dahil')        AS cogs_kargo_dahil
    FROM mart.siparis s
    LEFT JOIN kalem k  ON k.siparis_id  = s.siparis_id
    LEFT JOIN kargo kg ON kg.siparis_id = s.siparis_id
), h AS (
  SELECT b.*,
    -- Bilinen bilesenlerden hesaplanan katki
    (coalesce(b.net_ciro,0) - coalesce(b.cogs,0)
     - CASE WHEN b.cogs_kargo_dahil = 'EVET' THEN 0
            ELSE coalesce(b.kargo_maliyet,0) END
     - coalesce(b.cod_komisyon,0)
     - coalesce(b.paketleme,0)
     - coalesce(coalesce(b.net_ciro,0) * b.odeme_yuzde / 100.0, 0)
     - coalesce(coalesce(b.net_ciro,0) * b.kanal_yuzde / 100.0, 0)) AS katki,
    -- 🔴 COGS KDV TABANI COZULMEMISSE katki YUKARI da hareket edebilir.
    --    400 TL KDV DAHIL ise gercek COGS 400/1,2'dir -> maliyet duser.
    --    Bu, katkiyi ARTIRABILECEK TEK cozulmemis bilesendir; digerlerinin
    --    hepsi maliyettir (>= 0) ve yalniz DUSURUR.
    CASE WHEN b.cogs_kdv_tabani IS NULL AND b.cogs IS NOT NULL
         THEN round(b.cogs - b.cogs / 1.2, 2) ELSE 0 END AS cogs_kdv_lehte_duzeltme,
    -- Kritik / ikincil cozulmemis bilesenler AYRI listelenir
    array_remove(ARRAY[
      CASE WHEN b.cogs IS NULL OR b.cogs_eksik_kalem > 0 THEN 'urun_cogs' END,
      CASE WHEN NOT b.kargo_bagli
            AND coalesce(b.cogs_kargo_dahil,'HAYIR') <> 'EVET'
           THEN 'giden_kargo(siparis-gonderi bagi yok)' END,
      CASE WHEN coalesce(b.cod_bilinmeyen,0) > 0         THEN 'cod_komisyonu(UNKNOWN)' END,
      CASE WHEN b.odeme_yuzde IS NULL AND b.odeme_kritiklik='CRITICAL' THEN 'odeme_komisyonu' END,
      CASE WHEN b.kanal_yuzde IS NULL AND b.kanal_kritiklik='CRITICAL' THEN 'kanal_komisyonu' END,
      CASE WHEN b.teslimat_durumu = 'CANCELED'           THEN 'iade_ekonomisi(UNKNOWN)' END
    ], NULL) AS kritik_eksik,
    array_remove(ARRAY[
      CASE WHEN b.paketleme IS NULL AND b.paketleme_kritiklik='SECONDARY' THEN 'paketleme' END,
      CASE WHEN coalesce(b.cod_bekleyen,0) > 0 THEN 'cod_komisyonu(NOT_YET_KNOWN)' END,
      CASE WHEN b.cogs_kdv_tabani IS NULL      THEN 'cogs_kdv_tabani(yon: katkiyi ARTIRABILIR)' END
    ], NULL) AS ikincil_eksik
  FROM b
)
SELECT
  h.siparis_id, h.olusturma, h.ciro_sinifi, h.olcumde,
  h.teslimat_durumu, h.odeme_durumu,

  round(coalesce(h.net_ciro,0), 2)                        AS net_ciro_kdv_haric,
  CASE
    WHEN h.ciro_sinifi = 'IPTAL'                          THEN 'IPTAL'
    WHEN h.ciro_sinifi = 'ODENMEDI'                       THEN 'BOOKED_NOT_REALIZED'
    WHEN h.ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS') THEN 'REALIZED'
    ELSE 'BILINMIYOR'
  END                                                     AS gelir_durumu,
  0::numeric                                              AS kargo_geliri,

  round(h.cogs, 2)                                        AS cogs,
  round(h.kargo_maliyet, 2)                               AS kargo_maliyet,
  round(h.cod_komisyon, 2)                                AS cod_komisyon,
  h.paketleme                                             AS paketleme,
  CASE WHEN h.odeme_yuzde IS NOT NULL
       THEN round(coalesce(h.net_ciro,0) * h.odeme_yuzde / 100.0, 2) END AS odeme_komisyonu,
  CASE WHEN h.kanal_yuzde IS NOT NULL
       THEN round(coalesce(h.net_ciro,0) * h.kanal_yuzde / 100.0, 2) END AS kanal_komisyonu,

  -- ===== KNOWN_COMPONENT_CONTRIBUTION =====
  -- 🔴 ADI BILEREK NOTR. "Alt sinir" DEGILDIR: cozulmemis COGS KDV tabani
  --    katkiyi YUKARI da tasiyabilir. Yon iddiasi yalniz asagidaki
  --    en_iyi_olasi_katki ile ve ACIKCA yapilir.
  round(h.katki, 2)                                       AS bilinen_bilesen_katkisi,
  h.cogs_kdv_lehte_duzeltme                               AS cogs_kdv_lehte_duzeltme,

  -- ===== KANITLANABILIR UST SINIR =====
  -- 🔴 Tum cozulmemis bilesenler maliyettir (>= 0) ve katkiyi yalniz DUSURUR;
  --    TEK istisna COGS KDV tabanidir ve etkisi YUKARI ve SINIRLIDIR.
  --    Dolayisiyla gercek katki SU DEGERI ASAMAZ.
  round(h.katki + h.cogs_kdv_lehte_duzeltme, 2)           AS en_iyi_olasi_katki,

  h.kritik_eksik                                          AS kritik_eksik,
  h.ikincil_eksik                                         AS ikincil_eksik,
  (h.kritik_eksik || h.ikincil_eksik)                     AS eksik_bilesenler,

  -- ===== TAMLIK  (bilesen bazli, parasal esik YOK) =====
  CASE
    WHEN cardinality(h.kritik_eksik)  > 0 THEN 'INCOMPLETE'
    WHEN cardinality(h.ikincil_eksik) > 0 THEN 'PARTIAL'
    ELSE 'COMPLETE'
  END                                                     AS tamlik,

  -- ===== EKONOMIK OLARAK DOGRULANMIS =====
  -- 🔴 YALNIZ hicbir KRITIK bilesen eksik degilse. Ikincil eksik varsa
  --    ekonomi "dogrulanmis" sayilir ama katki IYIMSER kalir - bu ayrim
  --    ikincil_eksik listesinde gorunur.
  (cardinality(h.kritik_eksik) = 0)                       AS ekonomik_dogrulanmis,

  CASE WHEN h.cogs IS NULL THEN 'UNKNOWN'
       ELSE coalesce((SELECT CASE WHEN bool_and(mk.kalite='OLCULMUS') THEN 'MEASURED'
                                  ELSE 'BUSINESS_INPUT' END
                        FROM mart.siparis_kalem k2
                        JOIN mart.maliyet_kalite mk ON mk.urun_id = k2.urun_id
                       WHERE k2.siparis_id = h.siparis_id), 'UNKNOWN')
  END                                                     AS cogs_kanit_sinifi
FROM h;

COMMENT ON VIEW mart.siparis_ekonomi IS
  'Siparis basina ekonomi. bilinen_bilesen_katkisi bir SINIR IDDIASI DEGILDIR; '
  'kanitlanabilir ust sinir en_iyi_olasi_katki kolonundadir. Reklam maliyeti BU GRAIN''DE YOKTUR.';

-- ---------------------------------------------------------------------------
-- 5) VERI KALITESI
-- ---------------------------------------------------------------------------
CREATE VIEW mart.ekonomi_veri_kalitesi AS
SELECT m.bilesen AS kalem, m.kanit_sinifi AS durum,
       CASE WHEN m.deger IS NULL
            THEN format('[%s] deger BILINMIYOR (%s) - 0 TL SAYILMIYOR. %s',
                        m.kritiklik, m.kaynak, m.gerekce)
            ELSE format('[%s] %s %s (%s)', m.kritiklik, m.deger, m.uygulama, m.kdv_tabani)
       END AS aciklama,
       CASE WHEN m.deger IS NULL AND m.kritiklik='CRITICAL' THEN 'siparis ekonomisi INCOMPLETE'
            WHEN m.deger IS NULL THEN 'ekonomi PARTIAL - katki IYIMSER'
            ELSE 'hesaba giriyor' END AS etki
  FROM core.maliyet_bileseni m WHERE m.gecerli_bitis IS NULL
UNION ALL
SELECT 'Urun COGS kalitesi',
       CASE WHEN (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS') > 0
            THEN 'PARTIAL' ELSE 'BUSINESS_INPUT' END,
       format('%s urunun %s''i sahip beyani, olculmus %s',
              (SELECT count(*) FROM mart.maliyet_kalite),
              (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='TAHMIN'),
              (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS')),
       'katki OLDUGUNDAN IYIMSER olabilir'
UNION ALL
-- 🔴 KDV tabani belirsizligi AYRI bir satir: etkisi digerlerinin TERSI YONDE.
SELECT 'COGS KDV tabani',
       CASE WHEN (SELECT deger FROM core.ayar WHERE anahtar='maliyet_kdv_tabani') IS NULL
            THEN 'UNKNOWN_BUSINESS_INPUT_REQUIRED' ELSE 'BUSINESS_INPUT' END,
       format('400 TL beyaninin KDV dahil mi haric mi oldugu TEYIT EDILMEDI. '
              'KDV DAHIL ise gercek COGS 333,33''tur ve katki ARTAR. '
              'Etki (son 30 gun, gerceklesmis): %s TL',
              (SELECT to_char(coalesce(sum(cogs_kdv_lehte_duzeltme),0),'FM999990.00')
                 FROM mart.siparis_ekonomi
                WHERE gelir_durumu='REALIZED'
                  AND (olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date-30)),
       'katkiyi ARTIRABILIR - diger eksiklerin TERSI yon'
UNION ALL
SELECT 'Kargo-siparis bagi',
       CASE WHEN (SELECT count(*) FROM mart.gonderi WHERE siparis_id IS NOT NULL) =
                 (SELECT count(*) FROM mart.gonderi) THEN 'MEASURED' ELSE 'PARTIAL' END,
       format('%s siparisin kargosu deterministik bagli (%s gonderinin %s''inde foreignCode var). '
              'Bagsiz sipariste kargo UNKNOWN - ortalama DAGITILMIYOR.',
              (SELECT count(DISTINCT siparis_id) FROM mart.gonderi WHERE siparis_id IS NOT NULL),
              (SELECT count(*) FROM mart.gonderi),
              (SELECT count(*) FROM mart.gonderi WHERE siparis_id IS NOT NULL)),
       'bagsiz siparisler INCOMPLETE (CRITICAL)'
UNION ALL
SELECT 'COD komisyonu', 'PARTIAL',
       format('%s kapida odemeli gonderinin %s''inde komisyon OLCULDU; %s''i tahsilat bekliyor',
              (SELECT count(*) FROM mart.gonderi WHERE cod_var),
              (SELECT count(*) FROM mart.gonderi WHERE cod_komisyon_sinifi='MEASURED'),
              (SELECT count(*) FROM mart.gonderi WHERE cod_komisyon_sinifi='NOT_YET_KNOWN')),
       'NOT_YET_KNOWN zamanla kendiliginden kapanir (SECONDARY)'
UNION ALL
SELECT 'Numune/tester urun maliyeti', 'UNKNOWN',
       format('%s gonderinin urun maliyeti BAGLANAMIYOR: BasitKargo''da productId YOK. '
              'Ad eslesmesi yalniz ONERI uretebilir, otoriter baglama YAPILMAZ.',
              (SELECT count(*) FROM mart.gonderi WHERE sinif IN ('NUMUNE','UNKNOWN'))),
       'hicbir siparise yazilmiyor'
UNION ALL
SELECT 'Iade/refund ekonomisi', 'UNKNOWN',
       format('%s iptal siparis, %s iade gonderisi. Iade TUTARI, kismi iade, geri kazanilan '
              'stok ve geri kazanilamayan komisyon AYRISTIRILAMIYOR - kayit yapisi YOK.',
              (SELECT count(*) FROM raw.wix_order WHERE teslimat_durumu='CANCELED'),
              (SELECT count(*) FROM mart.gonderi WHERE sinif='IADE')),
       'iptal siparisler INCOMPLETE (CRITICAL)';

COMMENT ON VIEW mart.ekonomi_veri_kalitesi IS
  'Ekonomi katmaninda neyin bilinmedigi. UNKNOWN degerler 0 TL DEGILDIR. KDV tabani TERS yonde etki eder.';

COMMIT;
