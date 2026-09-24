-- SAHA: üç kaynağı tek hedef listesinde birleştirir (sürüm 2)
--
-- Sürüm 1'den farkı:
--   * saha_bilgi ARTIK ÜÇ KAYNAĞA DA bağlanır. Önce yalnız OSM'ye
--     bağlıydı; sahada Overture kaydı hakkında öğrenilen telefon hiçbir
--     yere yazılamıyordu.
--   * Overture kategorisinden BRANŞ çıkarılır (core.saha_brans_esleme).
--   * Kopya grubu tek bir `grup` metnine indirildi; ziyaret sayısı artık
--     KAYDA değil GRUBA bağlanıyor (neden: saha-sema3.sql başlığı).
--
-- KAYNAKLAR VE NEDEN ÜÇÜ BİRDEN:
--   OSM       eczanede lider, koordinatı %100 güvenilir
--   OVERTURE  diğer her şeyde lider; güzellik salonu OSM'de HİÇ yok
--   ELLE      sahada görülüp haritada olmayan yerler
--
-- 🔴 KOPYA AYIKLAMA eşiğinin bedeli: 100 m içinde aynı adı taşıyan iki AYRI
-- işletme birleşir (zincir şubeleri). Daha dar eşikte aynı işletme iki kez
-- görünür ve saha elemanı aynı kapıyı iki kez çalar. İkincisi daha pahalı.
-- Adsız kayıt ASLA birleştirilmez.

BEGIN;

DROP VIEW IF EXISTS mart.saha_hedef;

CREATE VIEW mart.saha_hedef AS
WITH hepsi AS (
  -- OSM
  SELECT ('osm:' || p.osm_tur || ':' || p.osm_id) AS hedef_anahtari,
         'OSM'::text AS kaynak,
         p.osm_tur, p.osm_id, NULL::bigint AS nokta_id, NULL::text AS overture_id,
         COALESCE(b.ad, p.ad) AS ad, p.tur,
         COALESCE(b.brans, p.brans_tahmin) AS brans,
         CASE WHEN b.brans IS NOT NULL THEN 'BEYAN'
              WHEN p.brans_tahmin IS NOT NULL THEN 'TAHMIN' ELSE 'YOK' END AS brans_kaynagi,
         NULL::text AS kategori,
         COALESCE(b.telefon, p.telefon) AS telefon,
         COALESCE(b.eposta, p.eposta) AS eposta,
         p.website, NULL::text AS sosyal, p.adres, p.ilce, p.enlem, p.boylam,
         b.ilgili_kisi, b.notlar, COALESCE(b.hedef_disi, false) AS hedef_disi,
         NULL::numeric AS guven, p.ilk_gorulme, p.son_gorulme, p.kayip_at
    FROM raw.osm_poi p
    LEFT JOIN core.saha_bilgi b
           ON b.hedef_anahtari = 'osm:' || p.osm_tur || ':' || p.osm_id
  UNION ALL
  -- OVERTURE
  SELECT ('ovt:' || o.overture_id), 'OVERTURE',
         NULL::text, NULL::bigint, NULL::bigint, o.overture_id,
         COALESCE(b.ad, o.ad), o.tur,
         COALESCE(b.brans, m.brans),
         CASE WHEN b.brans IS NOT NULL THEN 'BEYAN'
              WHEN m.brans IS NOT NULL THEN 'CIKARIM' ELSE 'YOK' END,
         o.kategori,
         COALESCE(b.telefon, o.telefon), COALESCE(b.eposta, o.eposta),
         o.website, o.sosyal, o.adres, o.ilce, o.enlem, o.boylam,
         b.ilgili_kisi, b.notlar, COALESCE(b.hedef_disi, false),
         o.guven, o.ilk_gorulme, o.son_gorulme, o.kayip_at
    FROM raw.overture_poi o
    LEFT JOIN core.saha_bilgi b ON b.hedef_anahtari = 'ovt:' || o.overture_id
    LEFT JOIN core.saha_brans_esleme m ON m.kategori = o.kategori
  UNION ALL
  -- ELLE
  SELECT ('elle:' || e.nokta_id), 'ELLE',
         NULL::text, NULL::bigint, e.nokta_id, NULL::text,
         COALESCE(b.ad, e.ad), e.tur, COALESCE(b.brans, e.brans),
         CASE WHEN COALESCE(b.brans, e.brans) IS NOT NULL THEN 'BEYAN' ELSE 'YOK' END,
         NULL::text, COALESCE(b.telefon, e.telefon), COALESCE(b.eposta, e.eposta),
         e.website, NULL::text, e.adres, e.ilce, e.enlem, e.boylam,
         COALESCE(b.ilgili_kisi, e.ilgili_kisi), COALESCE(b.notlar, e.notlar),
         COALESCE(b.hedef_disi, e.hedef_disi, false),
         NULL::numeric, e.eklendi, e.eklendi, NULL::timestamptz
    FROM core.saha_elle_nokta e
    LEFT JOIN core.saha_bilgi b ON b.hedef_anahtari = 'elle:' || e.nokta_id
),
puanli AS (
  SELECT h.*,
         -- Zenginlik: dolu alan sayısı. Elle eklenen kayıt her zaman kazanır
         -- çünkü orada bir insan bakmıştır.
         (CASE WHEN kaynak = 'ELLE' THEN 100 ELSE 0 END
          + (telefon IS NOT NULL)::int * 3
          + (eposta  IS NOT NULL)::int * 3
          + (adres   IS NOT NULL)::int * 2
          + (website IS NOT NULL)::int
          + (brans   IS NOT NULL)::int * 2
          + (ilce    IS NOT NULL)::int) AS zenginlik,
         -- Kopya grubu: normalize ad + 3 ondalık koordinat (≈100 m).
         -- Adı ya da koordinatı olmayan kayıt KENDİ BAŞINA bir gruptur.
         CASE WHEN ad IS NULL OR btrim(ad) = '' OR enlem IS NULL OR boylam IS NULL
              THEN hedef_anahtari
              ELSE lower(regexp_replace(ad, '[^[:alnum:]]', '', 'g'))
                   || '@' || round(enlem::numeric, 3)
                   || ',' || round(boylam::numeric, 3) END AS grup
    FROM hepsi h
),
-- Ziyaret GRUBA bağlanır: aynı işletmenin OSM kaydına gidildiyse, tazeleme
-- sonrası Overture kaydı öne geçse bile "gidildi" görünür.
ziyaret AS (
  SELECT g.grup,
         count(*) AS ziyaret_sayisi,
         max(z.ziyaret_at) AS son_ziyaret,
         (array_agg(z.sonuc ORDER BY z.ziyaret_at DESC))[1] AS son_sonuc
    FROM core.saha_ziyaret z
    JOIN (SELECT DISTINCT hedef_anahtari, grup FROM puanli) g
      ON g.hedef_anahtari = z.hedef_anahtari
   GROUP BY g.grup
)
SELECT DISTINCT ON (p.grup)
       p.hedef_anahtari, p.kaynak, p.osm_tur, p.osm_id, p.nokta_id, p.overture_id,
       p.ad, p.tur, p.brans, p.brans_kaynagi, p.kategori, p.telefon, p.eposta,
       p.website, p.sosyal, p.adres, p.ilce, p.enlem, p.boylam, p.ilgili_kisi,
       p.notlar, p.hedef_disi, p.guven, p.ilk_gorulme, p.son_gorulme, p.kayip_at,
       p.zenginlik, p.grup,
       COALESCE(z.ziyaret_sayisi, 0) AS ziyaret_sayisi,
       z.son_ziyaret, z.son_sonuc
  FROM puanli p
  LEFT JOIN ziyaret z ON z.grup = p.grup
 ORDER BY p.grup, p.zenginlik DESC;

COMMIT;
