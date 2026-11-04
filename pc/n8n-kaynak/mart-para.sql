-- =============================================================================
-- L'CARLIE - MART: PARANIN EKONOMIK STATUSU  (CR-012)
--
-- 🔴 NEDEN BU DOSYA VAR:
--    Mevcut ciro ayrimimiz (dogrulanmis / beyan_edilmis) VERIYE NE KADAR
--    GUVENDIGIMIZI olcuyordu. Olcmedigi sey: PARA NEREDE.
--    Bagimsiz denetim (16.09.2026) bunu en buyuk yapisal acik olarak
--    isaretledi: "Kapida odeme siparisini Wix'e elle girmen siparisin
--    VARLIGINI dogrular; bu henuz TAHSIL EDILMIS ciro degildir."
--
--    Turkiye'de kapida odemede teslim EDILEMEME ve IADE sessiz zarardir.
--    Kargo verisi elimizde duruyordu ama bu zincir hic kurulmamisti.
--
-- 🔴 ZINCIR (her asama AYRI, hicbiri digerini VARSAYMAZ):
--      siparis verildi -> kargolandi -> teslim edildi -> tahsil edildi
--                                                     -> iade
--    Bir asamanin gerceklesmesi bir sonrakini IMA ETMEZ. "Teslim edildi"
--    demek "para geldi" demek degildir (kapida odemede arada BasitKargo
--    aktarimi var); "kart odemesi basarili" demek de "settlement oldu"
--    demek degildir - PayTR API'sine baglanti YOK.
--
-- 🔴 KDV: bu dosyadaki NET kolonlar KDV HARICTIR. Tahsilat kolonlari
--    KDV DAHILDIR - cunku bankaya/kuryeye giren para KDV dahil tutardir.
--    Ikisi bilerek ayri adlandirildi, TOPLANMAZ.
--
-- 🔴 Olcum kesiminden onceki veri bu view'lara GIRMEZ.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.para_ozet   CASCADE;
DROP VIEW IF EXISTS mart.siparis_para CASCADE;

-- ---------------------------------------------------------------------------
-- Siparis basina para zinciri
-- ---------------------------------------------------------------------------
CREATE VIEW mart.siparis_para AS
WITH gnd AS (
  -- Bir siparişin gonderileri. Iade (INCOMING) AYRI sayilir.
  SELECT b.foreign_code                                   AS siparis_id,
         count(*) FILTER (WHERE b.yon IS DISTINCT FROM 'INCOMING') AS giden_gonderi,
         count(*) FILTER (WHERE b.yon = 'INCOMING')       AS iade_gonderi,
         -- 🔴 "Kargoya verildi" = kargoya_verilis DOLU. durum metnine
         --    guvenilmez: BasitKargo durum adlarini degistirebilir,
         --    zaman damgasi ise olgudur.
         count(*) FILTER (WHERE b.yon IS DISTINCT FROM 'INCOMING'
                            AND b.kargoya_verilis IS NOT NULL)     AS kargolanan,
         count(*) FILTER (WHERE b.yon IS DISTINCT FROM 'INCOMING'
                            AND b.teslim IS NOT NULL)              AS teslim_edilen,
         max(b.kargoya_verilis)                           AS kargoya_verilis,
         max(b.teslim)                                    AS teslim,
         bool_or(b.cod_var)                               AS cod_var,
         sum(b.cod_tutar) FILTER (WHERE b.cod_durum='TRANSFERRED')        AS cod_tahsil,
         sum(b.cod_tutar) FILTER (WHERE b.cod_durum IS DISTINCT FROM 'TRANSFERRED'
                                    AND b.cod_var)                       AS cod_bekleyen,
         coalesce(sum(b.kargo_ucreti),0)                  AS kargo_gideri
    FROM raw.bk_shipment b
   WHERE b.foreign_code IS NOT NULL
   GROUP BY 1
)
SELECT s.siparis_id,
       s.siparis_no,
       s.gun,
       s.olusturma,
       s.ciro_sinifi,
       s.odeme_yontemi,
       s.toplam                                   AS tutar_kdv_dahil,
       s.toplam_kdv_haric                         AS tutar_net,
       s.kdv,

       -- --- ZINCIRIN ASAMALARI -------------------------------------------
       -- 🔴 Her biri UC DEGERLI: true / false / NULL(bilinmiyor).
       --    Gonderi kaydi hic yoksa "kargolanmadi" DEMEYIZ - bilmiyoruz.
       (g.siparis_id IS NOT NULL)                 AS gonderi_kaydi_var,
       CASE WHEN g.siparis_id IS NULL THEN NULL
            ELSE g.kargolanan > 0 END             AS kargolandi,
       CASE WHEN g.siparis_id IS NULL THEN NULL
            ELSE g.teslim_edilen > 0 END          AS teslim_edildi,
       CASE WHEN g.siparis_id IS NULL THEN NULL
            ELSE g.iade_gonderi > 0 END           AS iade_var,
       g.kargoya_verilis,
       g.teslim,

       -- --- PARA -----------------------------------------------------------
       -- 🔴 TAHSIL EDILDI SAYILMA KURALI - iki ayri yol:
       --    (a) Kart/PayTR: Wix 'PAID' diyor. Bu PayTR'nin DEGIL Wix'in
       --        beyanidir (core.source_authority'de yazili). Settlement
       --        dogrulamasi YOK - o yuzden adi "tahsil" degil "odeme_onayli".
       --    (b) Kapida odeme: BasitKargo cod_durum='TRANSFERRED' diyor,
       --        yani para BasitKargo'dan bize AKTARILDI. Bu daha guclu bir
       --        kanittir ama yine banka ekstresiyle karsilastirilmadi.
       CASE WHEN s.ciro_sinifi='DOGRULANMIS' THEN s.toplam END      AS odeme_onayli_kdv_dahil,
       coalesce(g.cod_tahsil, 0)                                    AS cod_tahsil_edilen,
       coalesce(g.cod_bekleyen, 0)                                  AS cod_bekleyen,

       -- 🔴 TESLIM EDILMIS NET SATIS: marj hesabinin dogru paydasi.
       --    Teslim edilmemis sipariş ciro sayilabilir ama KARLILIK hesabinda
       --    henuz gerceklesmemistir - kapida odemede iade riski burada.
       CASE WHEN g.teslim_edilen > 0 AND coalesce(g.iade_gonderi,0) = 0
            THEN s.toplam_kdv_haric END                             AS teslim_net_satis,

       coalesce(g.kargo_gideri, 0)                                  AS kargo_gideri,
       s.olcumde
  FROM mart.siparis s
  LEFT JOIN gnd g ON g.siparis_id = s.siparis_id;

COMMENT ON VIEW mart.siparis_para IS
  'Siparis basina para zinciri: kargolandi -> teslim -> tahsil -> iade. '
  'NET kolonlar KDV haric, tahsilat kolonlari KDV dahil. TOPLANMAZLAR.';

-- ---------------------------------------------------------------------------
-- Gunluk para ozeti
-- ---------------------------------------------------------------------------
CREATE VIEW mart.para_ozet AS
SELECT gun,
       count(*)                                                  AS siparis,
       count(*) FILTER (WHERE kargolandi)                        AS kargolandi,
       count(*) FILTER (WHERE teslim_edildi)                     AS teslim_edildi,
       count(*) FILTER (WHERE iade_var)                          AS iadeli,
       -- 🔴 "Gonderi kaydi yok" AYRI SAYILIR, "kargolanmadi" ile karistirilmaz.
       count(*) FILTER (WHERE NOT gonderi_kaydi_var)             AS gonderi_kaydi_yok,
       coalesce(sum(tutar_kdv_dahil),0)                          AS tutar_kdv_dahil,
       coalesce(sum(tutar_net),0)                                AS tutar_net,
       coalesce(sum(kdv),0)                                      AS kdv,
       coalesce(sum(odeme_onayli_kdv_dahil),0)                   AS odeme_onayli,
       coalesce(sum(cod_tahsil_edilen),0)                        AS cod_tahsil,
       coalesce(sum(cod_bekleyen),0)                             AS cod_bekleyen,
       coalesce(sum(teslim_net_satis),0)                         AS teslim_net_satis,
       coalesce(sum(kargo_gideri),0)                             AS kargo_gideri
  FROM mart.siparis_para
 WHERE olcumde
 GROUP BY gun
 ORDER BY gun;

COMMENT ON VIEW mart.para_ozet IS
  'Gunluk para durumu. teslim_net_satis marj hesabinin dogru paydasidir.';

COMMIT;
