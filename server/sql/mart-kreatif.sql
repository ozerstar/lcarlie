-- =============================================================================
-- L'CARLIE - KREATIF PERFORMANS  (CR-016 corrective patch)
--
-- 🔴 UC SINYAL KATMANI BIRBIRINE KARISTIRILMAZ:
--
--    1) ATTENTION            - CTR, CPC. Dikkat olcer. SATIS DEGIL.
--    2) META_CONVERSION      - Meta'nin RAPORLADIGI event'ler.
--                              Meta'nin IDDIASIDIR, dogrulanmis satis DEGIL.
--    3) COMMERCIAL_CONFIRM   - Wix/siparis tarafinda dogrulanan bag.
--                              ATIF YOK -> bugun NOT_AVAILABLE.
--
-- 🔴 "KAZANAN REKLAM" ILAN EDILMEZ.  Yuksek CTR alip satisi dogrulanmayan
--    reklam icin sonuc "YUKSEK DIKKAT SINYALI"dir. CTR satis degildir.
--
-- 🔴 KAPSAMA 1/3 hesap. Bu view TUM reklamlari degil, GORULEN reklamlari
--    gosterir ve bunu her satirda yazar.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.kreatif_karar   CASCADE;
DROP VIEW IF EXISTS mart.reklam_performans CASCADE;

-- ---------------------------------------------------------------------------
-- AD PERFORMANSI - 7 / 14 / 30 gun
-- ---------------------------------------------------------------------------
CREATE VIEW mart.reklam_performans AS
WITH p AS (
  SELECT r.ad_id, r.ad_adi, r.kampanya_adi, r.adset_adi, w.pencere,
         sum(r.harcama)                                   AS harcama,
         sum(r.gosterim)                                  AS gosterim,
         sum(r.erisim)                                    AS erisim,
         sum(r.tiklama)                                   AS tiklama,
         sum(r.link_tiklama)                              AS link_tiklama,
         -- 🔴 CTR/CPC SATIR ORTALAMASI ALINMAZ, YENIDEN HESAPLANIR.
         --    Gunluk ctr degerlerinin ortalamasi, gun hacimleri farkliysa
         --    YANLIS cikar (basit ortalama tuzagi).
         round(100.0*sum(r.tiklama)/nullif(sum(r.gosterim),0), 2)   AS ctr_yuzde,
         round(sum(r.harcama)/nullif(sum(r.tiklama),0), 2)          AS cpc,
         round(1000.0*sum(r.harcama)/nullif(sum(r.gosterim),0), 2)  AS cpm,
         -- Meta'nin raporladigi event'ler (IDDIA)
         sum((SELECT coalesce(sum((e->>'value')::numeric),0)
                FROM jsonb_array_elements(coalesce(r.eylemler,'[]'::jsonb)) e
               WHERE e->>'action_type' LIKE '%purchase%'))          AS meta_satis_iddiasi,
         sum((SELECT coalesce(sum((e->>'value')::numeric),0)
                FROM jsonb_array_elements(coalesce(r.eylem_degerleri,'[]'::jsonb)) e
               WHERE e->>'action_type' LIKE '%purchase%'))          AS meta_gelir_iddiasi,
         sum((SELECT coalesce(sum((e->>'value')::numeric),0)
                FROM jsonb_array_elements(coalesce(r.eylemler,'[]'::jsonb)) e
               WHERE e->>'action_type' = 'landing_page_view'))      AS sayfa_goruntuleme
    FROM raw.meta_reklam r
    CROSS JOIN (VALUES (7),(14),(30)) AS w(pencere)
   WHERE r.gun > current_date - w.pencere
   GROUP BY r.ad_id, r.ad_adi, r.kampanya_adi, r.adset_adi, w.pencere
)
SELECT p.pencere, p.ad_id, p.ad_adi, p.kampanya_adi, p.adset_adi,
       round(p.harcama,2) AS harcama, p.gosterim, p.erisim,
       p.tiklama, p.link_tiklama, p.ctr_yuzde, p.cpc, p.cpm,
       k.baslik, k.govde, k.cta, k.nesne_tipi, k.etkin_durum,
       -- ===== KATMAN 1: DIKKAT =====
       CASE WHEN p.gosterim < 1000 THEN 'YETERSIZ_ORNEKLEM'
            WHEN p.ctr_yuzde >= 8  THEN 'YUKSEK_DIKKAT'
            WHEN p.ctr_yuzde >= 4  THEN 'ORTA_DIKKAT'
            ELSE 'DUSUK_DIKKAT' END                       AS attention,
       -- ===== KATMAN 2: META'NIN IDDIASI =====
       p.meta_satis_iddiasi, p.meta_gelir_iddiasi, p.sayfa_goruntuleme,
       CASE WHEN p.meta_satis_iddiasi > 0 THEN 'META_SATIS_IDDIA_EDIYOR'
            WHEN p.sayfa_goruntuleme > 0  THEN 'YALNIZ_SAYFA_GORUNTULEME'
            ELSE 'META_DONUSUM_YOK' END                   AS meta_conversion_signal,
       -- ===== KATMAN 3: TICARI DOGRULAMA =====
       -- 🔴 ATIF YOK (CR-011: ad eslesmesi 0/259). Wix siparisiyle reklam
       --    arasinda dogrulanabilir bag KURULAMIYOR. Sabit NOT_AVAILABLE;
       --    ileride atif kurulursa burasi gercek degere doner.
       'NOT_AVAILABLE'::text                              AS commercial_confirmation,
       '1/3 hesap'::text                                  AS kapsama
  FROM p LEFT JOIN raw.meta_kreatif k ON k.ad_id = p.ad_id;

COMMENT ON VIEW mart.reklam_performans IS
  'Ad bazinda 7/14/30 gun. UC SINYAL AYRI: attention / meta_conversion / commercial. '
  'CTR satis DEGILDIR; kazanan reklam ILAN EDILMEZ. Kapsama 1/3.';

-- ---------------------------------------------------------------------------
-- KREATIF KARAR SINYALI  (yorum degil, etiket)
-- ---------------------------------------------------------------------------
CREATE VIEW mart.kreatif_karar AS
SELECT pencere, ad_id, left(coalesce(ad_adi,'(adsiz)'),28) AS reklam,
       left(coalesce(kampanya_adi,''),26) AS kampanya,
       harcama, gosterim, tiklama, ctr_yuzde, cpc,
       attention, meta_conversion_signal, commercial_confirmation,
       -- 🔴 ETIKET, KARAR DEGIL.  "Kazanan" kelimesi bilerek yok.
       CASE
         WHEN attention = 'YETERSIZ_ORNEKLEM'                    THEN 'INSUFFICIENT_DATA'
         WHEN attention = 'YUKSEK_DIKKAT'
          AND meta_conversion_signal = 'META_SATIS_IDDIA_EDIYOR' THEN 'YUKSEK_DIKKAT_+_META_IDDIASI'
         WHEN attention = 'YUKSEK_DIKKAT'                        THEN 'YUKSEK_DIKKAT_SATIS_DOGRULANMADI'
         WHEN attention = 'DUSUK_DIKKAT' AND harcama > 500       THEN 'DUSUK_DIKKAT_HARCAMA_SURUYOR'
         ELSE 'IZLE' END                                         AS etiket,
       CASE
         WHEN attention = 'YETERSIZ_ORNEKLEM'
           THEN format('%s gosterim - 1000 altinda, oran yaniltici', gosterim)
         WHEN commercial_confirmation = 'NOT_AVAILABLE'
           THEN 'Ticari dogrulama YOK: atif kurulamiyor, bu reklamin satis getirip '
                'getirmedigi BILINMIYOR. CTR yalnizca dikkat olcer.'
         ELSE 'izleniyor' END                                    AS not_
  FROM mart.reklam_performans;

COMMENT ON VIEW mart.kreatif_karar IS
  'Kreatif etiketi - KARAR DEGIL. "Kazanan reklam" ifadesi bilerek yok; '
  'ticari dogrulama olmadan yuksek CTR yalniz DIKKAT sinyalidir.';

COMMIT;
