-- =============================================================================
-- L'CARLIE - GUNLUK TICARI NABIZ / NAKIT KORKULUGU  (CR-013)
--
-- 🔴🔴 BU BIR ATIF / ROAS RAPORU DEGILDIR.
--    "Bu satisi su reklam getirdi" demez, diyemez. Attribution mantigi
--    CR-011'de olculdu ve KURULAMAZ oldugu kanitlandi; bu dosya ona
--    DOKUNMAZ. Burada olculen sey tek bir sey: BAGLI KAYNAKLARDAN
--    GORULEBILEN NAKIT VE MALIYET.
--
-- 🔴 NEDEN OLCUM KESIMINDEN BAGIMSIZ:
--    core.ayar.olcum_baslangici = 1 Ekim 2026 ve DEGISMEZ - o tarih temiz
--    atif penceresi icindir. Ama nakit 1 Ekim'i beklemez. 17.08-16.09
--    doneminde reklam harcamasi, olculebilen en yuksek ciroyu asmisti ve
--    bu hesap bir ay boyunca hicbir panelde GORUNMEDI - cunku her gorunum
--    kesim tarihine bagliydi. Susmasi gereken sey atifli ROAS'ti, nakit degil.
--
-- 🔴 EKSIK MALIYET **SIFIR SAYILMAZ**.  Odeme/COD komisyonu, basarisiz
--    teslimat bedeli ve numune URUN maliyeti bilinmiyor. Bunlar 0 kabul
--    edilip "kar" uretilmez; mart.nakit_veri_kalitesi'nde MISSING olarak
--    durur ve panel bunu gizlemez. Yani asagidaki katki rakamlari
--    GERCEKTEN OLDUGUNDAN IYIMSERDIR.
--
-- 🔴 META HARCAMASI BIR TABANDIR, tam deger degil: 3 reklam hesabinin
--    1'i okunuyor. Eksik hesaplar harcamayi yalniz ARTIRIR - bu yuzden
--    "harcama > ciro" sonucu eksik veriye ragmen GECERLIDIR.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.nakit_veri_kalitesi CASCADE;
DROP VIEW IF EXISTS mart.nakit_gunluk        CASCADE;
DROP FUNCTION IF EXISTS mart.nakit_ozet(int) CASCADE;

-- ---------------------------------------------------------------------------
-- GUNLUK NABIZ
-- ---------------------------------------------------------------------------
CREATE VIEW mart.nakit_gunluk AS
WITH gunler AS (
  -- 🔴 Takvim ekseni UNION ile kurulur: harcama olan ama siparis olmayan
  --    gun de, siparis olan ama harcama olmayan gun de GORUNMELI.
  --    Yalniz siparis gunlerine bakmak, "harcama var satis yok" gunlerini
  --    tamamen gizlerdi - ki bu donemin en onemli olgusu tam olarak odur.
  SELECT (olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun FROM raw.wix_order
  UNION SELECT gun FROM raw.meta_harcama WHERE kampanya_id <> '_HESAP'
  UNION SELECT (olusturma AT TIME ZONE 'Europe/Istanbul')::date FROM raw.bk_shipment
), sip AS (
  SELECT (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         count(*)                                              AS siparis,
         sum(w.toplam)                                         AS brut_ciro,
         sum(w.toplam - w.kdv)                                 AS net_ciro,
         sum(w.toplam - w.kdv) FILTER (WHERE w.odeme_durumu = 'PAID')                  AS tahsil_beyan,
         sum(w.toplam - w.kdv) FILTER (WHERE w.odeme_durumu IS DISTINCT FROM 'PAID')   AS tahsil_edilmemis
    FROM raw.wix_order w
   WHERE w.teslimat_durumu IS DISTINCT FROM 'CANCELED'
   GROUP BY 1
), kal AS (
  -- COGS + maliyet kalitesi. 🔴 Kalite, CIRO AGIRLIKLI olcülur: bir urunun
  --    maliyeti olculmus olsa bile cironun kucuk bir kismiysa, o gunun
  --    maliyet bilgisi hala zayiftir.
  SELECT (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         sum(k.satir_maliyet)                                         AS cogs,
         sum(k.satir_ciro_net)                                        AS kalem_net,
         sum(k.satir_ciro_net) FILTER (WHERE mk.kalite = 'OLCULMUS')  AS kalem_net_olculmus,
         count(*)                                                     AS kalem,
         count(*) FILTER (WHERE k.maliyeti_biliniyor)                  AS kalem_maliyetli
    FROM mart.siparis_kalem k
    JOIN raw.wix_order w        ON w.siparis_id = k.siparis_id
    LEFT JOIN mart.maliyet_kalite mk ON mk.urun_id = k.urun_id
   WHERE k.ciro_sinifi <> 'IPTAL'
   GROUP BY 1
), krg AS (
  -- 🔴 SATIS kargosu ile NUMUNE kargosu AYRI: ilki satisin maliyeti,
  --    ikincisi pazarlama gideri. Toplanirsa hangi kalemin buyudugu gizlenir.
  SELECT (olusturma AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         sum(kargo_ucreti) FILTER (WHERE sinif IN ('SATIS','ELLE_SATIS'))          AS satis_kargosu,
         -- 🔴 YALNIZ ACIKCA ISARETLENMIS NUMUNE pazarlama gideridir.
         sum(kargo_ucreti) FILTER (WHERE sinif = 'NUMUNE')                         AS numune_kargosu,
         -- 🔴 UNKNOWN: sinifi bilinmeyen gonderi gideri. Para odendi ama
         --    satis mi numune mi BILINMIYOR - ayri kolonda durur.
         sum(kargo_ucreti) FILTER (WHERE sinif = 'UNKNOWN')                         AS bilinmeyen_kargo,
         sum(kargo_ucreti) FILTER (WHERE sinif = 'IADE')                           AS iade_kargosu,
         -- Wix'te kaydi OLMAYAN kapida odeme: ciro olarak Wix'e girmez.
         -- 🔴 net_ciro'ya EKLENMEZ, ayri kolonda durur (cift sayim olmasin).
         sum(cod_tutar) FILTER (WHERE sinif='ELLE_SATIS' AND cod_durum='TRANSFERRED')                  AS wixdisi_tahsil_kdvli,
         sum(cod_tutar) FILTER (WHERE sinif='ELLE_SATIS' AND cod_durum IS DISTINCT FROM 'TRANSFERRED') AS wixdisi_bekleyen_kdvli
    FROM mart.gonderi GROUP BY 1
), rek AS (
  SELECT gun, sum(harcama) AS harcama, sum(gosterim) AS gosterim, sum(link_tiklama) AS tiklama
    FROM raw.meta_harcama WHERE kampanya_id <> '_HESAP' GROUP BY 1
), hesap AS (
  SELECT count(*) AS okunan FROM raw.meta_hesap
)
SELECT
  g.gun,
  coalesce(s.siparis, 0)                                   AS siparis,
  coalesce(s.brut_ciro, 0)                                 AS brut_ciro,            -- KDV DAHIL
  coalesce(s.net_ciro, 0)                                  AS net_ciro,             -- KDV HARIC  <- ana referans
  coalesce(s.tahsil_beyan, 0)                              AS tahsil_beyan_edilen,
  coalesce(s.tahsil_edilmemis, 0)                          AS tahsil_edilmemis,
  -- 🔴 Wix disi tutarlar net_ciro'ya DAHIL DEGIL. KDV hariclestirme %20
  --    varsayimiyla yapilir cunku BasitKargo COD tutarinda KDV ayrimi YOK.
  round(coalesce(k.wixdisi_tahsil_kdvli, 0) / 1.2, 2)      AS wixdisi_tahsil_net,
  round(coalesce(k.wixdisi_bekleyen_kdvli, 0) / 1.2, 2)    AS wixdisi_bekleyen_net,

  round(coalesce(c.cogs, 0), 2)                            AS bilinen_cogs,
  -- 🔴 Kalite ETIKETI, sayi degil: "%96 kapsama" ile "hepsi tahmin" ayni
  --    seye benziyordu; CR-012'de ayrildi, burada da ayri durur.
  CASE
    WHEN c.kalem IS NULL OR c.kalem = 0                    THEN 'VERI_YOK'
    WHEN c.kalem_maliyetli < c.kalem                       THEN 'EKSIK'
    WHEN coalesce(c.kalem_net_olculmus,0) = 0              THEN 'TAHMIN'
    WHEN c.kalem_net_olculmus >= c.kalem_net * 0.5         THEN 'OLCULMUS'
    ELSE 'KARISIK'
  END                                                      AS cogs_kalite,
  round(100.0 * coalesce(c.kalem_net_olculmus,0) / nullif(c.kalem_net,0), 1) AS cogs_olculmus_yuzde,

  round(coalesce(k.satis_kargosu, 0), 2)                   AS satis_kargosu,
  round(coalesce(k.numune_kargosu, 0), 2)                  AS numune_kargosu,
  -- 🔴 UNKNOWN kargo KATKIDAN DUSULUR ama PAZARLAMA GIDERI SAYILMAZ.
  --    Iki ayri soru: (a) para gitti mi -> EVET, nakit gercek. (b) bu para
  --    pazarlama miydi -> BILINMIYOR. Sinifi bilmemek, gideri yok saymak
  --    icin gerekce degildir; yok sayarsak katki KENDILIGINDEN iyilesir.
  round(coalesce(k.bilinmeyen_kargo, 0), 2)                AS bilinmeyen_kargo,
  round(coalesce(k.iade_kargosu, 0), 2)                    AS iade_kargosu,

  round(coalesce(r.harcama, 0), 2)                         AS meta_harcama_gozlenen,
  (SELECT aktif_kapsama FROM mart.meta_kapsama)             AS meta_hesap_kapsamasi,
  coalesce(r.gosterim, 0)                                  AS gosterim,
  coalesce(r.tiklama, 0)                                   AS link_tiklama,

  -- 🔴 KATKI RAKAMLARI IYIMSERDIR: odeme/COD komisyonu, basarisiz teslimat
  --    ve numune URUN maliyeti bu hesaba GIREMIYOR (MISSING). Gercek katki
  --    asagidakilerden DUSUKTUR.
  round(coalesce(s.net_ciro,0) - coalesce(c.cogs,0)
        - coalesce(k.satis_kargosu,0) - coalesce(k.numune_kargosu,0)
        - coalesce(k.bilinmeyen_kargo,0), 2)                              AS reklam_oncesi_katki,
  round(coalesce(s.net_ciro,0) - coalesce(c.cogs,0)
        - coalesce(k.satis_kargosu,0) - coalesce(k.numune_kargosu,0)
        - coalesce(k.bilinmeyen_kargo,0)
        - coalesce(r.harcama,0), 2)                                       AS reklam_sonrasi_katki,

  round(coalesce(r.harcama,0) / nullif(s.siparis,0), 2)    AS siparis_basina_harcama,
  round(coalesce(s.net_ciro,0) / nullif(r.harcama,0), 2)   AS ciro_harcama_orani,

  -- =========================================================================
  -- NAKIT DURUMU - DETERMINISTIK, SIRALI
  -- =========================================================================
  -- 🔴 EKSIK VERI ASLA OTOMATIK 'HEALTHY' URETMEZ. Sira onemli: once
  --    "veri var mi", sonra kirmizi esikler, en sona yesil.
  CASE
    -- 1) Hicbir sinyal yok: ne harcama ne siparis. "Sorun yok" DEGIL, "bilinmiyor".
    WHEN coalesce(r.harcama,0) = 0 AND coalesce(s.siparis,0) = 0
      THEN 'INSUFFICIENT_DATA'
    -- 2) Gozlenen harcama net ciroyu asiyor.
    --    🔴 Bu sonuc EKSIK VERIYE RAGMEN gecerlidir: okunmayan 2 hesap
    --       harcamayi yalniz artirir, eksik maliyetler katkiyi yalniz azaltir.
    WHEN coalesce(r.harcama,0) > coalesce(s.net_ciro,0)
      THEN 'CRITICAL'
    -- 3) Harcama, reklam oncesi katkinin tamamini yiyor.
    WHEN coalesce(r.harcama,0) >= coalesce(s.net_ciro,0) - coalesce(c.cogs,0)
                                - coalesce(k.satis_kargosu,0) - coalesce(k.numune_kargosu,0)
                                - coalesce(k.bilinmeyen_kargo,0)
      THEN 'WATCH'
    -- 4) Reklam sonrasi pozitif AMA maliyet olculmemis -> yesil YAZILMAZ.
    WHEN coalesce(c.kalem_net_olculmus,0) < coalesce(c.kalem_net,0) * 0.5
      THEN 'WATCH'
    ELSE 'HEALTHY'
  END                                                      AS nakit_durum
FROM gunler g
LEFT JOIN sip s ON s.gun = g.gun
LEFT JOIN kal c ON c.gun = g.gun
LEFT JOIN krg k ON k.gun = g.gun
LEFT JOIN rek r ON r.gun = g.gun
ORDER BY g.gun DESC;

COMMENT ON VIEW mart.nakit_gunluk IS
  'Gunluk ticari nabiz. OLCUM KESIMINDEN BAGIMSIZ. Atif/ROAS raporu DEGILDIR. '
  'Katki rakamlari iyimserdir: odeme komisyonu, basarisiz teslimat ve numune urun maliyeti MISSING.';

-- ---------------------------------------------------------------------------
-- PENCERE OZETI  (son N gun)
-- ---------------------------------------------------------------------------
-- 🔴 View degil FONKSIYON: 7 ve 30 gun icin iki ayri view tutmak, ayni
--    mantigin iki kopyasi demekti - projenin defalarca yasadigi bakim tuzagi.
CREATE FUNCTION mart.nakit_ozet(p_gun int)
RETURNS TABLE (
  gun_sayisi        int,
  baslangic         date,
  bitis             date,
  siparis           bigint,
  brut_ciro         numeric,
  net_ciro          numeric,
  tahsil_beyan      numeric,
  tahsil_edilmemis  numeric,
  wixdisi_tahsil    numeric,
  wixdisi_bekleyen  numeric,
  bilinen_cogs      numeric,
  cogs_olculmus_yuzde numeric,
  satis_kargosu     numeric,
  numune_kargosu    numeric,
  bilinmeyen_kargo  numeric,
  meta_harcama      numeric,
  meta_kapsama      text,
  reklam_oncesi     numeric,
  reklam_sonrasi    numeric,
  katki_yuzde       numeric,
  siparis_basina_harcama numeric,
  ciro_harcama_orani numeric,
  harcamali_satissiz_gun bigint,
  nakit_durum       text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_bas date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date - p_gun;
        v_bit date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
BEGIN
  RETURN QUERY
  WITH p AS (
    SELECT * FROM mart.nakit_gunluk n WHERE n.gun > v_bas AND n.gun <= v_bit
  ), t AS (
    SELECT sum(p.siparis)                 AS siparis,
           sum(p.brut_ciro)               AS brut_ciro,
           sum(p.net_ciro)                AS net_ciro,
           sum(p.tahsil_beyan_edilen)     AS tahsil_beyan,
           sum(p.tahsil_edilmemis)        AS tahsil_edilmemis,
           sum(p.wixdisi_tahsil_net)      AS wixdisi_tahsil,
           sum(p.wixdisi_bekleyen_net)    AS wixdisi_bekleyen,
           sum(p.bilinen_cogs)            AS cogs,
           sum(p.satis_kargosu)           AS satis_kargosu,
           sum(p.numune_kargosu)          AS numune_kargosu,
           sum(p.bilinmeyen_kargo)        AS bilinmeyen_kargo,
           sum(p.meta_harcama_gozlenen)   AS harcama,
           count(*) FILTER (WHERE p.meta_harcama_gozlenen > 0 AND p.siparis = 0) AS harcamali_satissiz
      FROM p
  )
  -- 🔴 sum(bigint) NUMERIC doner, bigint DEGIL. Acik cast olmadan
  --    "structure of query does not match function result type" hatasi verir.
  SELECT p_gun, v_bas + 1, v_bit,
         coalesce(t.siparis,0)::bigint, round(coalesce(t.brut_ciro,0),2), round(coalesce(t.net_ciro,0),2),
         round(coalesce(t.tahsil_beyan,0),2), round(coalesce(t.tahsil_edilmemis,0),2),
         round(coalesce(t.wixdisi_tahsil,0),2), round(coalesce(t.wixdisi_bekleyen,0),2),
         round(coalesce(t.cogs,0),2),
         -- 🔴 Pencere genelinde olculmus maliyet orani (ciro agirlikli)
         (SELECT round(100.0 * coalesce(sum(k.satir_ciro_net) FILTER (WHERE mk.kalite='OLCULMUS'),0)
                       / nullif(sum(k.satir_ciro_net),0), 1)
            FROM mart.siparis_kalem k
            JOIN raw.wix_order w ON w.siparis_id = k.siparis_id
            LEFT JOIN mart.maliyet_kalite mk ON mk.urun_id = k.urun_id
           WHERE (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date > v_bas
             AND (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date <= v_bit
             AND k.ciro_sinifi <> 'IPTAL'),
         round(coalesce(t.satis_kargosu,0),2), round(coalesce(t.numune_kargosu,0),2),
         round(coalesce(t.bilinmeyen_kargo,0),2),
         round(coalesce(t.harcama,0),2),
         (SELECT aktif_kapsama FROM mart.meta_kapsama),
         round(coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0),2),
         round(coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0)-coalesce(t.harcama,0),2),
         round(100.0 * (coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0))
               / nullif(t.net_ciro,0), 1),
         round(coalesce(t.harcama,0) / nullif(t.siparis,0), 2),
         round(coalesce(t.net_ciro,0) / nullif(t.harcama,0), 2),
         t.harcamali_satissiz::bigint,
         CASE
           WHEN coalesce(t.harcama,0) = 0 AND coalesce(t.siparis,0) = 0 THEN 'INSUFFICIENT_DATA'
           WHEN coalesce(t.harcama,0) > coalesce(t.net_ciro,0)          THEN 'CRITICAL'
           WHEN coalesce(t.harcama,0) >= coalesce(t.net_ciro,0)-coalesce(t.cogs,0)
                                        -coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
                                        -coalesce(t.bilinmeyen_kargo,0) THEN 'WATCH'
           ELSE 'WATCH'   -- 🔴 maliyet kalitesi olculmedigi surece HEALTHY uretilmez
         END
    FROM t;
END $$;

COMMENT ON FUNCTION mart.nakit_ozet(int) IS
  'Son N gunun nakit ozeti. HEALTHY yalniz olculmus maliyet varsa uretilir - bugun uretilemez.';

-- ---------------------------------------------------------------------------
-- VERI KALITESI - NEYIN BILINMEDIGI ACIKCA YAZILIR
-- ---------------------------------------------------------------------------
-- 🔴 Panel bunlari GIZLEMEZ. Eksik maliyet 0 sayilmadigi icin, katki
--    rakamlarinin ne kadar iyimser oldugu okuyana acikca soylenmeli.
CREATE VIEW mart.nakit_veri_kalitesi AS
SELECT 'COGS (urun maliyeti)'          AS kalem,
       CASE WHEN (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS') > 0
            THEN 'PARTIAL' ELSE 'TAHMIN' END AS durum,
       format('%s urunun %s''i SAHIP TAHMINI (ayni deger), olculmus: %s',
              (SELECT count(*) FROM mart.maliyet_kalite),
              (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='TAHMIN'),
              (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS')) AS aciklama,
       'katki OLDUGUNDAN IYIMSER olabilir'  AS etki
UNION ALL
SELECT 'COGS KDV tabani',
       CASE WHEN (SELECT deger FROM core.ayar WHERE anahtar='maliyet_kdv_tabani') IS NULL
            THEN 'MISSING' ELSE 'TANIMLI' END,
       'Beyan edilen maliyetin KDV dahil mi haric mi oldugu sorulmadi; KDV HARIC varsayiliyor',
       'marj yonu degismez, tutar degisir'
UNION ALL
SELECT 'Odeme komisyonu (PayTR)', 'MISSING',
       'PayTR API baglantisi yok; komisyon hicbir yerde olculmuyor',
       'gercek katki DAHA DUSUK'
UNION ALL
SELECT 'Kapida odeme komisyonu', 'MISSING',
       'BasitKargo toplam_maliyet ile kargo_ucreti farki ihmal edilebilir; COD komisyonu ayri gorunmuyor',
       'gercek katki DAHA DUSUK'
UNION ALL
SELECT 'Basarisiz teslimat maliyeti', 'MISSING',
       format('%s gonderi henuz teslim edilmedi; sonucu ve bedeli bilinmiyor',
              (SELECT count(*) FROM raw.bk_shipment WHERE yon='OUTGOING' AND teslim IS NULL)),
       'gercek katki DAHA DUSUK'
UNION ALL
SELECT 'Numune/UGC URUN maliyeti', 'MISSING',
       format('%s numune gonderisinin kargosu biliniyor ama icindeki urunun maliyeti yok (BasitKargo''da productId yok)',
              (SELECT count(*) FROM mart.gonderi WHERE sinif IN ('NUMUNE','UNKNOWN'))),
       'gercek katki DAHA DUSUK'
UNION ALL
-- 🔴 SINIFI BILINMEYEN GONDERI.  Daha once bunlar "kapida odeme yok +
--    Wix kaydi yok => numune" KURALIYLA numune sayiliyordu. O bir olcum
--    degil VARSAYIMDI: ayni desene havale/EFT satisi, hediye, barter, PR,
--    personel gonderisi de uyar. Varsayim kaldirildi; sinif artik UNKNOWN
--    ve bu satir kac gonderinin INSAN KARARI bekledigini soyler.
SELECT 'Gonderi sinifi (UNKNOWN)',
       CASE WHEN (SELECT count(*) FROM mart.gonderi WHERE sinif='UNKNOWN') = 0
            THEN 'TANIMLI' ELSE 'MISSING' END,
       format('%s gonderinin ne oldugu BILINMIYOR (acik isaret yok). Satis mi numune mi hediye mi ayirt edilemiyor; varsayimla numune sayilmiyor',
              (SELECT count(*) FROM mart.gonderi WHERE sinif='UNKNOWN')),
       'ne ciroya ne pazarlama giderine yazilir; kargosu katkidan DUSULUR'
UNION ALL
SELECT 'Meta hesap kapsamasi',
       (SELECT CASE WHEN aktif_tam THEN 'TANIMLI' ELSE 'PARTIAL' END FROM mart.meta_kapsama),
       (SELECT ifade FROM mart.meta_kapsama),
       (SELECT CASE WHEN aktif_tam THEN 'aktif hesaplarin tamami okunuyor - harcama TABAN degil TAM'
                    ELSE 'gercek harcama DAHA YUKSEK olabilir' END FROM mart.meta_kapsama)
UNION ALL
SELECT 'Meta harcamasi KDV tabani', 'MISSING',
       'Meta''nin bildirdigi harcamanin KDV dahil mi haric mi oldugu dogrulanmadi',
       'sinandi: KDV dahil varsayilsa bile harcama ciroyu asiyor'
UNION ALL
SELECT 'Stok', 'PARTIAL',
       format('%s urunun tamami sabit %s adet gorunuyor - gercek stok degil',
              (SELECT count(*) FROM raw.wix_urun),
              (SELECT max(stok_adet)::int FROM raw.wix_urun)),
       'nakit hesabina girmiyor'
UNION ALL
SELECT 'Cevrim disi odeme dogrulamasi', 'MISSING',
       format('%s siparis cevrim disi odendi isaretli; muhasebe/banka kaydiyla karsilastirilmiyor',
              (SELECT count(*) FROM raw.wix_order WHERE odeme_yontemi IS DISTINCT FROM 'PayTR' AND odeme_durumu='PAID')),
       'tahsil edilmis ciro DOGRULANMAMIS'
UNION ALL
SELECT 'Wix disi satis (WhatsApp/telefon)', 'PARTIAL',
       format('%s gonderi kapida odemeli ve Wix kaydi yok; ciro olarak net_ciro''ya EKLENMEZ',
              (SELECT count(*) FROM mart.gonderi WHERE sinif='ELLE_SATIS')),
       'gercek ciro biraz DAHA YUKSEK olabilir';

COMMENT ON VIEW mart.nakit_veri_kalitesi IS
  'Nakit gorunumunde neyin BILINMEDIGI. Eksik maliyetler 0 sayilmadi; katki rakamlari iyimser.';

COMMIT;
