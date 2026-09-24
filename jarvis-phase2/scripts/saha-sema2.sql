-- SAHA v2: elle eklenen noktalar, ziyaret fotoğrafı, birleşik hedef görünümü
--
-- 🔴 ELLE EKLENEN NOKTA OSM AYNASINA KONULAMAZ. `raw.osm_poi` ayda bir
-- OpenStreetMap'ten tazeleniyor ve o taramada görünmeyen her kayıt
-- `kayip_at` ile işaretleniyor. Elle eklenen bir nokta OSM'de olmadığı için
-- ilk taramada kaybolmuş sayılırdı. Bu yüzden ayrı tablo ve birleşik görünüm.

BEGIN;

-- Elle eklenen hedefler. Sahada görülen ama haritada olmayan yerler.
CREATE TABLE IF NOT EXISTS core.saha_elle_nokta (
  nokta_id    bigserial PRIMARY KEY,
  ad          text NOT NULL,
  tur         text NOT NULL,
  brans       text,
  enlem       double precision NOT NULL,
  boylam      double precision NOT NULL,
  telefon     text,
  eposta      text,
  website     text,
  adres       text,
  ilce        text,
  ilgili_kisi text,
  notlar      text,
  hedef_disi  boolean NOT NULL DEFAULT false,
  -- Konumun nereden geldiği: telefonun GPS'i mi, haritadan tıklama mı,
  -- elle mi yazıldı. Sonradan "bu koordinat güvenilir mi" diye sorulacak.
  konum_kaynagi text NOT NULL DEFAULT 'ELLE'
                CHECK (konum_kaynagi IN ('GPS', 'HARITA', 'ELLE')),
  konum_dogruluk_m numeric,
  ekleyen     text NOT NULL,
  eklendi     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saha_elle_konum_idx ON core.saha_elle_nokta (enlem, boylam);

-- Ziyaret fotoğrafı: gidildiğinin kanıtı.
-- Dosya diske yazılır, veritabanında yalnız yol ve özet durur -- binlerce
-- fotoğrafı tabloya gömmek yedek boyutunu ve sorgu hızını bozar.
CREATE TABLE IF NOT EXISTS core.saha_ziyaret_foto (
  foto_id     bigserial PRIMARY KEY,
  ziyaret_id  bigint NOT NULL REFERENCES core.saha_ziyaret(ziyaret_id) ON DELETE CASCADE,
  dosya_yolu  text NOT NULL,
  bayt        integer NOT NULL,
  -- Fotoğrafın çekildiği yer, varsa. Ziyaretin konumuyla karşılaştırmak
  -- "gerçekten orada mıydı" sorusunu ölçülebilir kılar.
  enlem       double precision,
  boylam      double precision,
  eklendi     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saha_foto_ziyaret_idx ON core.saha_ziyaret_foto (ziyaret_id);

-- Ziyaretin yapıldığı konum (telefonun GPS'i). Ziyaret kaydına eklenir.
ALTER TABLE core.saha_ziyaret ADD COLUMN IF NOT EXISTS enlem double precision;
ALTER TABLE core.saha_ziyaret ADD COLUMN IF NOT EXISTS boylam double precision;
ALTER TABLE core.saha_ziyaret ADD COLUMN IF NOT EXISTS konum_dogruluk_m numeric;

-- Elle eklenen noktalar için de ziyaret kaydı tutulabilmeli.
ALTER TABLE core.saha_ziyaret ADD COLUMN IF NOT EXISTS nokta_id bigint;
ALTER TABLE core.saha_ziyaret ALTER COLUMN osm_tur DROP NOT NULL;
ALTER TABLE core.saha_ziyaret ALTER COLUMN osm_id DROP NOT NULL;

-- Birleşik hedef görünümü: OSM + elle eklenenler tek listede.
-- `hedef_anahtari` ikisini tek bir kimlikle adresler; panel ve rota motoru
-- kaynağın hangisi olduğunu bilmek zorunda kalmaz.
CREATE OR REPLACE VIEW mart.saha_hedef AS
 SELECT ('osm:' || p.osm_tur || ':' || p.osm_id)     AS hedef_anahtari,
        'OSM'::text                                   AS kaynak,
        p.osm_tur, p.osm_id, NULL::bigint             AS nokta_id,
        COALESCE(b.ad, p.ad)                          AS ad,
        p.tur,
        COALESCE(b.brans, p.brans_tahmin)             AS brans,
        CASE WHEN b.brans IS NOT NULL THEN 'BEYAN'
             WHEN p.brans_tahmin IS NOT NULL THEN 'TAHMIN'
             ELSE 'YOK' END                           AS brans_kaynagi,
        COALESCE(b.telefon, p.telefon)                AS telefon,
        COALESCE(b.eposta, p.eposta)                  AS eposta,
        p.website, p.adres, p.ilce, p.enlem, p.boylam,
        b.ilgili_kisi, b.notlar,
        COALESCE(b.hedef_disi, false)                 AS hedef_disi,
        p.ilk_gorulme, p.son_gorulme, p.kayip_at,
        z.ziyaret_sayisi, z.son_ziyaret, z.son_sonuc
   FROM raw.osm_poi p
   LEFT JOIN core.saha_bilgi b USING (osm_tur, osm_id)
   LEFT JOIN LATERAL (
        SELECT count(*) AS ziyaret_sayisi, max(ziyaret_at) AS son_ziyaret,
               (SELECT sonuc FROM core.saha_ziyaret z2
                 WHERE z2.osm_tur = p.osm_tur AND z2.osm_id = p.osm_id
                 ORDER BY ziyaret_at DESC LIMIT 1) AS son_sonuc
          FROM core.saha_ziyaret z1
         WHERE z1.osm_tur = p.osm_tur AND z1.osm_id = p.osm_id) z ON true
 UNION ALL
 SELECT ('elle:' || e.nokta_id)                       AS hedef_anahtari,
        'ELLE'::text                                   AS kaynak,
        NULL::text, NULL::bigint, e.nokta_id,
        e.ad, e.tur, e.brans,
        CASE WHEN e.brans IS NOT NULL THEN 'BEYAN' ELSE 'YOK' END,
        e.telefon, e.eposta, e.website, e.adres, e.ilce, e.enlem, e.boylam,
        e.ilgili_kisi, e.notlar, e.hedef_disi,
        e.eklendi, e.eklendi, NULL::timestamptz,
        z.ziyaret_sayisi, z.son_ziyaret, z.son_sonuc
   FROM core.saha_elle_nokta e
   LEFT JOIN LATERAL (
        SELECT count(*) AS ziyaret_sayisi, max(ziyaret_at) AS son_ziyaret,
               (SELECT sonuc FROM core.saha_ziyaret z2
                 WHERE z2.nokta_id = e.nokta_id
                 ORDER BY ziyaret_at DESC LIMIT 1) AS son_sonuc
          FROM core.saha_ziyaret z1
         WHERE z1.nokta_id = e.nokta_id) z ON true;

COMMIT;
