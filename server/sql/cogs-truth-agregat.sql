-- =============================================================================
-- L'CARLIE - UNIT ECONOMICS AGREGAT + REKLAM SONRASI TICARI KATKI
--
-- 🔴 GRAIN AYRIMI BU DOSYANIN VAR OLMA SEBEBIDIR.
--    Siparis ekonomisi SIPARIS grain'indedir; reklam harcamasi GUN grain'inde
--    ve siparise INDIRILEMEZ. Ikisi ancak AGREGAT seviyede bir araya gelir.
--
-- 🔴🔴 IKI KAVRAM AYRI (17.09.2026, Chief Architect semantic audit):
--
--      EKONOMIK TAMLIK (completeness)
--        "Bu siparisin maliyetlerini biliyor muyuz?"
--        -> COMPLETE / PARTIAL / INCOMPLETE
--
--      TICARI YON (directional conclusion)
--        "Elimizdeki kanitla yonu soyleyebilir miyiz?"
--        -> NEGATIVE_PROVEN_BY_BOUND / POSITIVE_PROVEN_BY_BOUND / INDETERMINATE
--
--    Ikisi BIRBIRINI GEREKTIRMEZ. Ekonomi eksik olsa bile, cozulmemis
--    bilesenlerin YONU ve SINIRI biliniyorsa yon KANITLANABILIR:
--    cozulmemis bilesenlerin hepsi maliyettir (>= 0) ve katkiyi yalniz
--    DUSURUR; tek istisna COGS KDV tabanidir ve etkisi YUKARI ama SINIRLIDIR.
--    Yani UST SINIR hesaplanabiliyorsa ve ust sinir bile harcamanin altindaysa
--    sonuc NEGATIFTIR - eksik veriye RAGMEN.
--
--    Bu ayrim olmadan sistem iki hatadan birine duserdi:
--      (a) "veri tam degil, hicbir sey soyleyemem"  -> felc
--      (b) "katki pozitif gorunuyor"                -> yanlis kesinlik
--
-- 🔴 NEGATIVE_PROVEN_BY_BOUND, ECONOMICALLY_VALIDATED ANLAMINA GELMEZ.
--    Yon kanitlanmis olabilir ama tutar hala bilinmiyor.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.ticari_yasayabilirlik CASCADE;
DROP FUNCTION IF EXISTS mart.ekonomi_ozet(int) CASCADE;
DROP VIEW IF EXISTS mart.ekonomi_gunluk        CASCADE;

-- ---------------------------------------------------------------------------
-- GUNLUK EKONOMI
-- ---------------------------------------------------------------------------
CREATE VIEW mart.ekonomi_gunluk AS
WITH gunler AS (
  SELECT (olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun FROM raw.wix_order
  UNION SELECT gun FROM raw.meta_harcama WHERE kampanya_id <> '_HESAP'
), sip AS (
  SELECT (e.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         count(*)                                           AS siparis,
         count(*) FILTER (WHERE e.gelir_durumu = 'REALIZED') AS gerceklesmis,
         count(*) FILTER (WHERE e.tamlik = 'COMPLETE')       AS tam,
         count(*) FILTER (WHERE e.tamlik = 'PARTIAL')        AS kismi,
         count(*) FILTER (WHERE e.tamlik = 'INCOMPLETE')     AS eksik,
         sum(e.net_ciro_kdv_haric)      FILTER (WHERE e.gelir_durumu='REALIZED') AS net_ciro,
         sum(e.bilinen_bilesen_katkisi) FILTER (WHERE e.gelir_durumu='REALIZED') AS bilinen_katki,
         -- 🔴 KANITLANABILIR UST SINIR: gercek katki bunu ASAMAZ.
         sum(e.en_iyi_olasi_katki)      FILTER (WHERE e.gelir_durumu='REALIZED') AS ust_sinir,
         sum(e.bilinen_bilesen_katkisi) FILTER (WHERE e.ekonomik_dogrulanmis
                                            AND e.gelir_durumu='REALIZED')       AS dogrulanmis_katki
    FROM mart.siparis_ekonomi e GROUP BY 1
), rek AS (
  SELECT gun, sum(harcama) AS harcama FROM raw.meta_harcama
   WHERE kampanya_id <> '_HESAP' GROUP BY 1
)
SELECT
  g.gun,
  coalesce(s.siparis,0)                             AS siparis,
  coalesce(s.gerceklesmis,0)                        AS gerceklesmis_siparis,
  coalesce(s.tam,0)                                 AS ekonomi_tam,
  coalesce(s.kismi,0)                               AS ekonomi_kismi,
  coalesce(s.eksik,0)                               AS ekonomi_eksik,
  round(coalesce(s.net_ciro,0),2)                   AS net_ciro,

  -- 🔴 AD NOTR: bu bir kar rakami DEGIL, bilinen bilesenlerden hesaplanmis
  --    bir ara degerdir. Yon iddiasi ust_sinir kolonuyla yapilir.
  round(coalesce(s.bilinen_katki,0),2)              AS bilinen_bilesen_katkisi,
  round(coalesce(s.ust_sinir,0),2)                  AS katki_ust_siniri,
  round(coalesce(s.dogrulanmis_katki,0),2)          AS dogrulanmis_katki,
  round(coalesce(r.harcama,0),2)                    AS reklam_harcamasi,

  round(coalesce(s.bilinen_katki,0) - coalesce(r.harcama,0), 2)
                                                    AS reklam_sonrasi_katki,
  -- 🔴 EN IYI OLASI SONUC: ust sinir bile harcamayi karsilamiyorsa yon KANITLI.
  round(coalesce(s.ust_sinir,0) - coalesce(r.harcama,0), 2)
                                                    AS reklam_sonrasi_ust_sinir,

  CASE WHEN coalesce(s.siparis,0) = 0 THEN NULL
       ELSE round(100.0 * s.tam / s.siparis, 1) END AS ekonomi_tamlik_yuzde,

  CASE
    WHEN coalesce(s.siparis,0) = 0 AND coalesce(r.harcama,0) = 0 THEN 'VERI_YOK'
    WHEN coalesce(s.siparis,0) = 0                               THEN 'HARCAMA_VAR_SIPARIS_YOK'
    WHEN coalesce(s.tam,0) = 0                                   THEN 'EKONOMI_OLCULEMEDI'
    WHEN s.tam < s.siparis                                       THEN 'EKONOMI_KISMI'
    ELSE 'EKONOMI_TAM'
  END                                               AS ekonomi_durumu
FROM gunler g
LEFT JOIN sip s ON s.gun = g.gun
LEFT JOIN rek r ON r.gun = g.gun
ORDER BY g.gun DESC;

COMMENT ON VIEW mart.ekonomi_gunluk IS
  'Gunluk birim ekonomisi + reklam. bilinen_bilesen_katkisi SINIR IDDIASI DEGILDIR; '
  'kanitlanabilir sinir katki_ust_siniri kolonundadir. Reklam siparise dagitilmaz.';

-- ---------------------------------------------------------------------------
-- PENCERE OZETI
-- ---------------------------------------------------------------------------
CREATE FUNCTION mart.ekonomi_ozet(p_gun int)
RETURNS TABLE (
  gun_sayisi int, baslangic date, bitis date,
  siparis bigint, gerceklesmis bigint,
  ekonomi_tam bigint, ekonomi_kismi bigint, ekonomi_eksik bigint,
  net_ciro numeric, bilinen_bilesen_katkisi numeric, katki_ust_siniri numeric,
  dogrulanmis_katki numeric, reklam_harcamasi numeric,
  reklam_sonrasi_katki numeric, reklam_sonrasi_ust_sinir numeric,
  ekonomi_tamlik_yuzde numeric, eksik_bilesenler text, ekonomi_durumu text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_bas date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date - p_gun;
        v_bit date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
BEGIN
  RETURN QUERY
  WITH p AS (SELECT * FROM mart.ekonomi_gunluk n WHERE n.gun > v_bas AND n.gun <= v_bit),
  t AS (
    SELECT sum(p.siparis) s, sum(p.gerceklesmis_siparis) g,
           sum(p.ekonomi_tam) tam, sum(p.ekonomi_kismi) kis, sum(p.ekonomi_eksik) eks,
           sum(p.net_ciro) nc, sum(p.bilinen_bilesen_katkisi) bk,
           sum(p.katki_ust_siniri) us, sum(p.dogrulanmis_katki) dk,
           sum(p.reklam_harcamasi) rh
      FROM p
  ), e AS (
    SELECT string_agg(DISTINCT x, ', ') AS liste
      FROM mart.siparis_ekonomi se, unnest(se.eksik_bilesenler) AS x
     WHERE (se.olusturma AT TIME ZONE 'Europe/Istanbul')::date > v_bas
       AND (se.olusturma AT TIME ZONE 'Europe/Istanbul')::date <= v_bit
  )
  SELECT p_gun, v_bas + 1, v_bit,
         coalesce(t.s,0)::bigint, coalesce(t.g,0)::bigint,
         coalesce(t.tam,0)::bigint, coalesce(t.kis,0)::bigint, coalesce(t.eks,0)::bigint,
         round(coalesce(t.nc,0),2), round(coalesce(t.bk,0),2), round(coalesce(t.us,0),2),
         round(coalesce(t.dk,0),2), round(coalesce(t.rh,0),2),
         round(coalesce(t.bk,0) - coalesce(t.rh,0),2),
         round(coalesce(t.us,0) - coalesce(t.rh,0),2),
         CASE WHEN coalesce(t.s,0)=0 THEN NULL ELSE round(100.0*t.tam/t.s,1) END,
         coalesce(e.liste,'(yok)'),
         CASE
           WHEN coalesce(t.s,0)=0 AND coalesce(t.rh,0)=0 THEN 'VERI_YOK'
           WHEN coalesce(t.tam,0)=0                      THEN 'EKONOMI_OLCULEMEDI'
           WHEN t.tam < t.s                              THEN 'EKONOMI_KISMI'
           ELSE 'EKONOMI_TAM'
         END
    FROM t, e;
END $$;

COMMENT ON FUNCTION mart.ekonomi_ozet(int) IS
  'Son N gunun birim ekonomisi. Tamlik ve TICARI YON ayri kavramlardir.';

-- ---------------------------------------------------------------------------
-- TICARI YASAYABILIRLIK  -  tamlik ILE yon AYRI
-- ---------------------------------------------------------------------------
CREATE VIEW mart.ticari_yasayabilirlik AS
WITH o AS (SELECT * FROM mart.ekonomi_ozet(30))
SELECT
  o.siparis, o.ekonomi_tam, o.ekonomi_tamlik_yuzde,
  o.bilinen_bilesen_katkisi, o.katki_ust_siniri, o.dogrulanmis_katki,
  o.reklam_harcamasi, o.reklam_sonrasi_katki, o.reklam_sonrasi_ust_sinir,
  o.eksik_bilesenler,

  -- ===== 1) EKONOMIK TAMLIK =====
  (o.ekonomi_tam > 0)                                     AS olculebiliyor,
  o.ekonomi_durumu                                        AS ekonomik_tamlik,

  -- 🔴 ECONOMICALLY_VALIDATED: tutar guvenilir mi. Yon kanitindan AYRIDIR.
  (o.ekonomi_tam > 0 AND o.ekonomi_tamlik_yuzde >= 80)    AS ekonomik_dogrulanmis,

  -- ===== 2) TICARI YON  (tamliktan BAGIMSIZ) =====
  -- 🔴 Ust sinir bile harcamayi karsilamiyorsa sonuc NEGATIFTIR - eksik
  --    veriye RAGMEN. Cunku cozulmemis her bilesen katkiyi yalniz DUSURUR
  --    (tek yukari yonlu bilesen COGS KDV tabanidir ve ust sinira ZATEN
  --    dahil edilmistir).
  CASE
    WHEN o.siparis = 0                            THEN 'NO_DATA'
    WHEN o.reklam_sonrasi_ust_sinir < 0           THEN 'NEGATIVE_PROVEN_BY_BOUND'
    WHEN o.reklam_sonrasi_katki > 0
     AND o.ekonomi_tamlik_yuzde >= 80             THEN 'POSITIVE_PROVEN_BY_BOUND'
    ELSE 'INDETERMINATE'
  END                                                     AS ticari_yon,

  -- ===== 3) SCALE KAPISI =====
  -- 🔴 Hem yon POZITIF KANITLI hem ekonomi yeterince tam olmali.
  --    NEGATIVE_PROVEN_BY_BOUND scale'i acmaz - kapatir.
  (o.ekonomi_tam > 0 AND o.siparis >= 10
   AND o.ekonomi_tamlik_yuzde >= 80
   AND o.reklam_sonrasi_ust_sinir > 0)                    AS scale_konusulabilir,

  CASE
    WHEN o.siparis = 0 THEN 'Son 30 gunde siparis YOK - ticari yon soylenemez.'
    WHEN o.reklam_sonrasi_ust_sinir < 0 THEN
      format('TICARI YON: NEGATIF ve KANITLI. Ekonomi TAM DEGIL (%s/%s siparis tam) ama '
             'yon yine de soylenebilir: cozulmemis bilesenlerin hepsi maliyettir ve katkiyi '
             'yalniz DUSURUR; tek yukari yonlu bilesen (COGS KDV tabani) ust sinira dahildir. '
             'EN IYI OLASI katki %s TL, reklam %s TL -> en iyi durumda bile %s TL. '
             'Eksik bilesenler: %s. '
             '🔴 Bu ECONOMICALLY_VALIDATED DEGILDIR: yon kanitli, TUTAR hala bilinmiyor.',
             o.ekonomi_tam, o.siparis, o.katki_ust_siniri, o.reklam_harcamasi,
             o.reklam_sonrasi_ust_sinir, o.eksik_bilesenler)
    WHEN o.ekonomi_tam = 0 THEN
      format('TICARI YON: BELIRSIZ. Ekonomisi TAM olan siparis YOK (%s siparisin %s''i eksik) '
             've ust sinir harcamanin ustunde - yani eksikler cozulunce sonuc pozitif de '
             'cikabilir negatif de. Eksik bilesenler: %s',
             o.siparis, o.ekonomi_eksik, o.eksik_bilesenler)
    ELSE
      format('Ekonomi %%%s tam. Bilinen katki %s TL, ust sinir %s TL, reklam %s TL.',
             o.ekonomi_tamlik_yuzde, o.bilinen_bilesen_katkisi,
             o.katki_ust_siniri, o.reklam_harcamasi)
  END                                                     AS ifade,

  -- ===== 4) ORDER ECONOMICS COMPLETE != AD PROFITABILITY =====
  -- 🔴 Chief Architect semantic audit (17.09.2026). Bir siparisin ekonomisi
  --    TAM olsa bile "reklam para kazandirdi mi" sorusu CEVAPLANMAZ:
  --    order-level deterministik reklam atamasi HALA YOK (CR-011, eslesme 0/259).
  --    Tam ekonomi su soruyu cevaplar: "bu siparis kendi basina ne kazandirdi".
  --    Reklamla karsilastirma ancak AGREGAT ve KARMA (blended) olur; hangi
  --    reklamin hangi siparisi getirdigi bilinmez ve bilinmeden de
  --    "su reklam karli" DENEMEZ.
  'BLENDED_ONLY: Bu yon KARMA (blended) bir karsilastirmadir. Siparis ekonomisi '
  'TAM olsa bile reklam-basina karlilik CEVAPLANMAZ - order-level atif YOK '
  '(CR-011, ad eslesmesi 0/259). Kampanya/adset/ad bazli karlilik iddiasi URETILEMEZ.'
                                                          AS atif_uyarisi
FROM o;

COMMENT ON VIEW mart.ticari_yasayabilirlik IS
  'EKONOMIK TAMLIK ile TICARI YON AYRI kavramlardir. NEGATIVE_PROVEN_BY_BOUND, '
  'ECONOMICALLY_VALIDATED anlamina GELMEZ: yon kanitli olabilir, tutar bilinmiyor olabilir.';

COMMIT;
