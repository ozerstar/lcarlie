-- =============================================================================
-- L'CARLIE - STOK TEK OKUMA YUZU  (K2, sahip 15.11.2026 "bagla")
--
-- Uc sayi uc farkli sey soyluyordu:
--   Wix stok alani      : 36/36 sabit 250 (GERCEK DEGIL - kimse saymadi)
--   Trendyol stok       : 999 (ilan acik kalsin diye)
--   core.stok_sayim     : INSAN beyani/sayimi, URUN ADIYLA (productId yok)
--   finans merkezi      : uretilen - satilan (fatura/kanal satisi)
--
-- core.stok_guncel = son insan sayimi - sayimdan SONRA tum kanallardaki satis
--   (mart.satis_kalem_tum: wix + trendyol + idefix + n11 + hb + elle, iptal haric)
--   - sayimdan sonra panelden girilen bedelsiz cikis (UGC/INFLUENCER/NUMUNE/HEDIYE).
-- Kaynak ve tarih her satirda yazar; digerleri YANINDA durur, karsilastirilir.
--
-- 🔴 HICBIR YERE STOK YAZILMAZ. Wix/pazaryerine yazmak sahibin karari;
--    oneri_stok yalniz liste. (stok_sayim'a da makine yazamaz: human_approver.)
-- 🔴 Urun adi -> productId: core.urun_id_ad() (Turkce harf cevirisi + en uzun kod).
--    Eslesmeyen sayim satiri SESSIZCE dusmez: core.stok_tutarsizlik'ta listelenir.
-- =============================================================================
BEGIN;

CREATE OR REPLACE VIEW core.stok_guncel AS
WITH sayim AS (
  SELECT DISTINCT ON (core.urun_id_ad(s.urun_adi))
         core.urun_id_ad(s.urun_adi) AS urun_id, s.sayim_id, s.urun_adi, s.adet, s.nerede,
         s.giren, s.sayim_zamani, s.not_metni
    FROM core.stok_sayim s
   WHERE core.urun_id_ad(s.urun_adi) IS NOT NULL
   ORDER BY core.urun_id_ad(s.urun_adi), s.sayim_zamani DESC, s.sayim_id DESC
), satis AS (
  SELECT y.urun_id,
         sum(k.adet)                                            AS adet,
         sum(k.adet) FILTER (WHERE k.kanal = 'wix')             AS wix,
         sum(k.adet) FILTER (WHERE k.kanal NOT IN ('wix','elle')) AS pazaryeri,
         sum(k.adet) FILTER (WHERE k.kanal = 'elle')            AS elle
    FROM sayim y
    JOIN mart.satis_kalem_tum k ON k.urun_id = y.urun_id AND k.olusturma > y.sayim_zamani
   WHERE k.ciro_sinifi <> 'IPTAL'
   GROUP BY y.urun_id
), bedelsiz AS (
  SELECT y.urun_id, sum(coalesce(n.adet, 1)) AS adet
    FROM sayim y
    JOIN core.gonderi_notu n ON core.urun_id_ad(n.urun_adi) = y.urun_id AND n.girildi > y.sayim_zamani
   WHERE n.tur IN ('UGC','INFLUENCER','NUMUNE','HEDIYE')
   GROUP BY y.urun_id
), finans AS (
  SELECT DISTINCT ON (a.finans_ad) a.finans_ad, a.uretilen, a.satilan, a.olcum_at
    FROM core.finans_maliyet_anlik a ORDER BY a.finans_ad, a.olcum_at DESC
), h AS (
  SELECT k.urun_id, k.urun_kod, k.finans_ad, k.barkod, k.pazaryeri_barkod,
         y.adet AS sayim_adet, y.sayim_zamani, y.giren AS sayim_giren, y.nerede AS sayim_yeri,
         CASE WHEN y.sayim_id IS NULL THEN NULL
              WHEN y.nerede ILIKE 'SAHIP BEYANI%' OR y.not_metni ILIKE '%fiziksel sayim yapilmadi%'
              THEN 'SAHIP_BEYANI' ELSE 'FIZIKSEL_SAYIM' END       AS sayim_turu,
         EXTRACT(day FROM now() - y.sayim_zamani)::int            AS sayim_gun_gecti,
         coalesce(s.adet, 0)      AS sayim_sonrasi_satis,
         coalesce(s.wix, 0)       AS sayim_sonrasi_wix,
         coalesce(s.pazaryeri, 0) AS sayim_sonrasi_pazaryeri,
         coalesce(s.elle, 0)      AS sayim_sonrasi_elle,
         coalesce(b.adet, 0)      AS sayim_sonrasi_bedelsiz,
         CASE WHEN y.sayim_id IS NOT NULL
              THEN y.adet - coalesce(s.adet, 0) - coalesce(b.adet, 0) END AS hesaplanan_stok,
         f.uretilen AS finans_uretilen, f.satilan AS finans_satilan,
         f.uretilen - f.satilan AS finans_stok, f.olcum_at AS finans_olcum_at,
         nullif(w.ham #>> '{stock,quantity}', '')::numeric AS wix_stok,
         nullif(t.ham #>> '{fiyat,quantity}', '')::numeric AS trendyol_stok
    FROM core.urun_kimlik k
    LEFT JOIN sayim y    ON y.urun_id = k.urun_id
    LEFT JOIN satis s    ON s.urun_id = k.urun_id
    LEFT JOIN bedelsiz b ON b.urun_id = k.urun_id
    LEFT JOIN finans f   ON f.finans_ad = k.finans_ad
    LEFT JOIN raw.wix_urun w      ON w.urun_id = k.urun_id
    LEFT JOIN raw.trendyol_urun t ON t.barkod = k.pazaryeri_barkod
)
SELECT h.*,
       CASE WHEN h.hesaplanan_stok IS NOT NULL
            THEN format('core.stok_sayim %s (%s, %s) - sonraki satis (mart.satis_kalem_tum) - bedelsiz (core.gonderi_notu)',
                        h.sayim_turu, to_char(h.sayim_zamani AT TIME ZONE 'Europe/Istanbul', 'DD.MM.YYYY'), h.sayim_giren)
            ELSE 'SAYIM_YOK - stok bilinmiyor' END            AS kaynak,
       greatest(h.hesaplanan_stok, 0)                       AS oneri_stok,   -- YAZILMAZ, liste
       array_remove(ARRAY[
         CASE WHEN h.sayim_adet IS NULL THEN 'SAYIM_YOK' END,
         CASE WHEN h.sayim_turu = 'SAHIP_BEYANI' THEN 'SAYIM_SAHIP_BEYANI(fiziksel sayim degil)' END,
         CASE WHEN h.sayim_gun_gecti > 14 THEN format('SAYIM_ESKI(%s gun)', h.sayim_gun_gecti) END,
         CASE WHEN h.hesaplanan_stok < 0 THEN 'HESAP_NEGATIF' END,
         CASE WHEN h.finans_stok IS NOT NULL AND h.hesaplanan_stok IS NOT NULL
               AND abs(h.finans_stok - h.hesaplanan_stok) > 10
              THEN format('FINANS_FARKLI(uretilen-satilan %s)', round(h.finans_stok)) END,
         CASE WHEN h.wix_stok IS DISTINCT FROM h.hesaplanan_stok AND h.hesaplanan_stok IS NOT NULL
              THEN format('WIX_FARKLI(%s)', round(h.wix_stok)) END,
         CASE WHEN h.trendyol_stok IS NOT NULL AND h.hesaplanan_stok IS NOT NULL
               AND h.trendyol_stok <> h.hesaplanan_stok
              THEN format('TRENDYOL_FARKLI(%s)', round(h.trendyol_stok)) END
       ], NULL)                                             AS tutarsizliklar
  FROM h;

COMMENT ON VIEW core.stok_guncel IS
  'K2 15.11.2026: TEK stok okuma yuzu. hesaplanan_stok = son insan sayimi - sayimdan sonraki tum kanal satislari - bedelsiz cikis. Wix 250 / Trendyol 999 / finans uretilen-satilan yaninda, karsilastirma tutarsizliklar sutununda. Hicbir yere yazilmaz.';

CREATE OR REPLACE VIEW core.stok_tutarsizlik AS
SELECT g.urun_kod, x.bulgu, g.hesaplanan_stok, g.wix_stok, g.trendyol_stok, g.finans_stok,
       g.sayim_zamani, g.kaynak
  FROM core.stok_guncel g, unnest(g.tutarsizliklar) x(bulgu)
UNION ALL
SELECT s.urun_adi, 'SAYIM_ADI_ESLESMEDI(urun kimligine baglanamadi)', NULL, NULL, NULL, NULL, s.sayim_zamani,
       'core.stok_sayim #' || s.sayim_id
  FROM core.stok_sayim s
 WHERE core.urun_id_ad(s.urun_adi) IS NULL
UNION ALL
SELECT array_to_string(g.urun_adlari, ' + '), 'SAYIM_SONRASI_BEDELSIZ_GONDERI_URUNU_BILINMIYOR(' || g.sinif || ')',
       NULL, NULL, NULL, NULL, g.olusturma, 'mart.gonderi ' || g.gonderi_id
  FROM mart.gonderi g
 WHERE g.sinif IN ('NUMUNE','UNKNOWN')
   AND g.olusturma > (SELECT min(sayim_zamani) FROM core.stok_sayim);

COMMENT ON VIEW core.stok_tutarsizlik IS
  'K2: stok tutarsizliklari - urun basina bulgu + eslesmeyen sayim satiri + sayimdan sonra urunu bilinmeyen bedelsiz gonderi (stoktan dusulemedi).';

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jarvis_web') THEN
    GRANT SELECT ON core.stok_guncel, core.stok_tutarsizlik TO jarvis_web;
    GRANT SELECT ON core.stok_sayim, core.finans_maliyet_anlik TO jarvis_web;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_reader') THEN
    GRANT SELECT ON core.stok_guncel, core.stok_tutarsizlik TO ai_reader;
  END IF;
END $$;

COMMIT;
