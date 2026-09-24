-- SAHA: üç kaynağı tek hedef listesinde birleştirir
--
-- KAYNAKLAR VE NEDEN ÜÇÜ BİRDEN:
--   OSM       eczanede lider (1.799 / 886), koordinatı %100 güvenilir
--   OVERTURE  diğer her şeyde lider; güzellik salonu OSM'de HİÇ yok,
--             e-posta %36 (OSM'de %0,5), adres %96 (OSM'de %23)
--   ELLE      sahada görülüp haritada olmayan yerler
-- Biri diğerinin yerine geçmez; hangisinin daha zengin olduğu KAYITA göre
-- değişir, kaynağa göre değil.
--
-- 🔴 KOPYA AYIKLAMA. Aynı işletme iki kaynakta da olabilir. Gruplama:
-- normalize edilmiş ad + 3 ondalık koordinat (≈100 m). Grupta ZENGİNLİK
-- puanı yüksek olan kazanır -- yani dolu alan sayısı fazla olan.
--
-- Eşiğin bedeli AÇIKÇA söylenmeli: 100 m içinde aynı adı taşıyan iki AYRI
-- işletme birleşir (zincir şubeleri). Daha dar eşik seçseydik bu kez aynı
-- işletmenin iki kaydı ayrı görünürdü ve saha elemanı aynı kapıyı iki kez
-- çalardı. İkinci hata sahada daha pahalı.
--
-- Adsız kayıt ASLA birleştirilmez: adı olmayan iki nokta aynı yer olabilir
-- de olmayabilir de, ve bunu bilmiyoruz.

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
    LEFT JOIN core.saha_bilgi b USING (osm_tur, osm_id)
  UNION ALL
  -- OVERTURE
  SELECT ('ovt:' || o.overture_id), 'OVERTURE',
         NULL::text, NULL::bigint, NULL::bigint, o.overture_id,
         o.ad, o.tur, NULL::text, 'YOK', o.kategori,
         o.telefon, o.eposta, o.website, o.sosyal, o.adres, o.ilce,
         o.enlem, o.boylam, NULL::text, NULL::text, false,
         o.guven, o.ilk_gorulme, o.son_gorulme, o.kayip_at
    FROM raw.overture_poi o
  UNION ALL
  -- ELLE
  SELECT ('elle:' || e.nokta_id), 'ELLE',
         NULL::text, NULL::bigint, e.nokta_id, NULL::text,
         e.ad, e.tur, e.brans,
         CASE WHEN e.brans IS NOT NULL THEN 'BEYAN' ELSE 'YOK' END,
         NULL::text, e.telefon, e.eposta, e.website, NULL::text,
         e.adres, e.ilce, e.enlem, e.boylam, e.ilgili_kisi, e.notlar,
         e.hedef_disi, NULL::numeric, e.eklendi, e.eklendi, NULL::timestamptz
    FROM core.saha_elle_nokta e
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
         CASE WHEN ad IS NULL OR btrim(ad) = '' THEN NULL
              ELSE lower(regexp_replace(ad, '[^[:alnum:]]', '', 'g')) END AS ad_anahtar
    FROM hepsi h
)
SELECT DISTINCT ON (
         COALESCE(ad_anahtar, hedef_anahtari),
         CASE WHEN ad_anahtar IS NULL THEN NULL ELSE round(enlem::numeric, 3) END,
         CASE WHEN ad_anahtar IS NULL THEN NULL ELSE round(boylam::numeric, 3) END)
       hedef_anahtari, kaynak, osm_tur, osm_id, nokta_id, overture_id,
       ad, tur, brans, brans_kaynagi, kategori, telefon, eposta, website,
       sosyal, adres, ilce, enlem, boylam, ilgili_kisi, notlar, hedef_disi,
       guven, ilk_gorulme, son_gorulme, kayip_at, zenginlik,
       z.ziyaret_sayisi, z.son_ziyaret, z.son_sonuc
  FROM puanli p
  LEFT JOIN LATERAL (
       SELECT count(*) AS ziyaret_sayisi, max(ziyaret_at) AS son_ziyaret,
              (SELECT sonuc FROM core.saha_ziyaret s2
                WHERE (s2.osm_tur = p.osm_tur AND s2.osm_id = p.osm_id)
                   OR (s2.nokta_id = p.nokta_id AND p.nokta_id IS NOT NULL)
                ORDER BY ziyaret_at DESC LIMIT 1) AS son_sonuc
         FROM core.saha_ziyaret s1
        WHERE (s1.osm_tur = p.osm_tur AND s1.osm_id = p.osm_id)
           OR (s1.nokta_id = p.nokta_id AND p.nokta_id IS NOT NULL)) z ON true
 ORDER BY COALESCE(ad_anahtar, hedef_anahtari),
          CASE WHEN ad_anahtar IS NULL THEN NULL ELSE round(enlem::numeric, 3) END,
          CASE WHEN ad_anahtar IS NULL THEN NULL ELSE round(boylam::numeric, 3) END,
          zenginlik DESC;

COMMIT;
