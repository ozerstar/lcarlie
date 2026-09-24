-- SAHA ZİYARET SİSTEMİ — şema
--
-- Amaç: Ankara'daki eczane / klinik / diş / spor salonu noktalarını kendi
-- veri merkezimizde tutmak, bölge seçip rota planlamak, ziyaretleri ve
-- görüşme notlarını kaydetmek, sipariş çıkarsa ona bağlamak.
--
-- MİMARİ. Projenin mevcut raw → core → mart ayrımına uyar ve ayrımın
-- sebebi burada özellikle önemli:
--
--   raw.osm_poi     Dış kaynağın AYNASI. Ayda bir tazelenir, ÜZERİNE YAZILIR.
--                   Buraya insan eli değmez -- değseydi bir sonraki tarama
--                   sessizce siler ve kimse fark etmezdi.
--   core.saha_bilgi İNSAN BEYANI. Ziyarette öğrenilen telefon, düzeltilen ad,
--                   branş. Tazeleme buna DOKUNMAZ.
--   mart.saha_hedef İkisinin birleşimi + her alanın KAYNAĞI.
--
-- Bu, bu gece gönderi sınıflandırmasında kurduğumuz desenin aynısı:
-- beyan çıkarımı yener ama gizlemez.

BEGIN;

CREATE SCHEMA IF NOT EXISTS saha;

-- ---------------------------------------------------------------- raw
CREATE TABLE IF NOT EXISTS raw.osm_poi (
  osm_tur       text NOT NULL CHECK (osm_tur IN ('node', 'way', 'relation')),
  osm_id        bigint NOT NULL,
  ad            text,
  tur           text NOT NULL,
  enlem         double precision NOT NULL,
  boylam        double precision NOT NULL,
  telefon       text,
  eposta        text,
  website       text,
  adres         text,
  ilce          text,
  etiket        jsonb NOT NULL,
  -- İlk ve son görülme: ayda bir tarama YENİ yerleri böyle bulur.
  ilk_gorulme   timestamptz NOT NULL DEFAULT now(),
  son_gorulme   timestamptz NOT NULL DEFAULT now(),
  -- 🔴 OSM'den kalkan kayıt SİLİNMEZ. Silseydik "dükkan kapandı" ile
  -- "tarama o gün eksik döndü" ayırt edilemezdi; ziyaret geçmişi de
  -- öksüz kalırdı. Kaybolduğu tarih yazılır, karar insana bırakılır.
  kayip_at      timestamptz,
  PRIMARY KEY (osm_tur, osm_id)
);
CREATE INDEX IF NOT EXISTS osm_poi_tur_idx ON raw.osm_poi (tur);
CREATE INDEX IF NOT EXISTS osm_poi_konum_idx ON raw.osm_poi (enlem, boylam);

COMMENT ON TABLE raw.osm_poi IS
  'OpenStreetMap aynasi. Ayda bir tazelenir, insan eli degmez.';

-- --------------------------------------------------------------- core
CREATE TABLE IF NOT EXISTS core.saha_bilgi (
  osm_tur     text NOT NULL,
  osm_id      bigint NOT NULL,
  ad          text,
  brans       text,
  telefon     text,
  eposta      text,
  ilgili_kisi text,
  notlar      text,
  -- Ziyarete DEĞMEZ işareti: kapanmış, ilgilenmiyor, yanlış kayıt.
  hedef_disi  boolean NOT NULL DEFAULT false,
  giren       text NOT NULL,
  girildi     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (osm_tur, osm_id)
);

COMMENT ON TABLE core.saha_bilgi IS
  'Insan beyani. Tazeleme buna dokunmaz; mart.saha_hedef bunu OSM verisinin ustune koyar.';

CREATE TABLE IF NOT EXISTS core.saha_ziyaret (
  ziyaret_id  bigserial PRIMARY KEY,
  osm_tur     text NOT NULL,
  osm_id      bigint NOT NULL,
  ziyaret_at  timestamptz NOT NULL DEFAULT now(),
  giden       text NOT NULL,
  sonuc       text NOT NULL CHECK (sonuc IN (
                'GORUSULDU', 'KAPALI', 'YETKILI_YOK', 'ILGILENMEDI',
                'NUMUNE_BIRAKILDI', 'SIPARIS_SOZU', 'TEKRAR_GEL')),
  not_metni   text,
  -- Sipariş çıkarsa buraya yazılır: numune -> ziyaret -> siparis zinciri
  -- tek parca kalsin diye. Ayri bir "siparisler" adasi kurulmaz.
  siparis_ref text
);
CREATE INDEX IF NOT EXISTS saha_ziyaret_hedef_idx ON core.saha_ziyaret (osm_tur, osm_id, ziyaret_at DESC);

CREATE TABLE IF NOT EXISTS core.saha_rota (
  rota_id     bigserial PRIMARY KEY,
  ad          text NOT NULL,
  bolge       text,
  baslangic_enlem  double precision,
  baslangic_boylam double precision,
  baslangic_adi    text,
  olusturan   text NOT NULL,
  olusturuldu timestamptz NOT NULL DEFAULT now(),
  planlanan_gun date
);

CREATE TABLE IF NOT EXISTS core.saha_rota_durak (
  rota_id     bigint NOT NULL REFERENCES core.saha_rota(rota_id) ON DELETE CASCADE,
  sira        integer NOT NULL,
  osm_tur     text NOT NULL,
  osm_id      bigint NOT NULL,
  onceki_mesafe_m numeric,
  PRIMARY KEY (rota_id, sira)
);

-- --------------------------------------------------------------- mart
CREATE OR REPLACE VIEW mart.saha_hedef AS
 SELECT p.osm_tur,
        p.osm_id,
        -- Her alanda beyan ONCE gelir; hangisinin konustugu ayrica yazilir.
        COALESCE(b.ad, p.ad)           AS ad,
        p.tur,
        b.brans,
        COALESCE(b.telefon, p.telefon) AS telefon,
        COALESCE(b.eposta, p.eposta)   AS eposta,
        p.website,
        p.adres,
        p.ilce,
        p.enlem,
        p.boylam,
        b.ilgili_kisi,
        b.notlar,
        COALESCE(b.hedef_disi, false)  AS hedef_disi,
        CASE WHEN b.telefon IS NOT NULL THEN 'BEYAN'
             WHEN p.telefon IS NOT NULL THEN 'OSM'
             ELSE 'YOK' END            AS telefon_kaynagi,
        CASE WHEN b.eposta IS NOT NULL THEN 'BEYAN'
             WHEN p.eposta IS NOT NULL THEN 'OSM'
             ELSE 'YOK' END            AS eposta_kaynagi,
        p.ilk_gorulme,
        p.son_gorulme,
        p.kayip_at,
        z.ziyaret_sayisi,
        z.son_ziyaret,
        z.son_sonuc
   FROM raw.osm_poi p
   LEFT JOIN core.saha_bilgi b USING (osm_tur, osm_id)
   LEFT JOIN LATERAL (
        SELECT count(*) AS ziyaret_sayisi,
               max(ziyaret_at) AS son_ziyaret,
               (SELECT sonuc FROM core.saha_ziyaret z2
                 WHERE z2.osm_tur = p.osm_tur AND z2.osm_id = p.osm_id
                 ORDER BY ziyaret_at DESC LIMIT 1) AS son_sonuc
          FROM core.saha_ziyaret z1
         WHERE z1.osm_tur = p.osm_tur AND z1.osm_id = p.osm_id
   ) z ON true;

COMMIT;
