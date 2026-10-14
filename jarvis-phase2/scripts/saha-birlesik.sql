-- SAHA birleşik hedef listesi (sürüm 3)
--
-- 🔴 NEDEN MADDİLEŞTİRİLDİ. Panel her filtre kutusu işaretlendiğinde facet
-- sayılarını yeniden hesaplıyor. Görünüm ise 21 bin satırlık üç yönlü
-- UNION + DISTINCT ON'u her sorguda baştan kuruyordu: ölçülen süre
-- 1,78 saniye. Kutuya basıp iki saniye beklemek, filtreyi kullanılmaz
-- kılar.
--
-- Ayrım şu gözleme dayanıyor: KAYNAK VERİ AYDA BİR değişir (tarama),
-- ZİYARET gün içinde değişir. Bu yüzden kaynak maddileştirildi, ziyaret
-- canlı bağlandı. Ziyaret kaydı anında görünür; tarama sonrası
-- mart.saha_tazele() çağrılır.
--
-- İKİ KATMAN:
--   mart.saha_tum     kopya ayıklanmadan ÖNCE, ~21 bin satır.
--                     Ziyaret eşleşmesi buradan yapılır: elenen kopyaya
--                     gidilmişse de "gidildi" görünmeli.
--   mart.saha_kaynak  kopya ayıklanmış, ~18,8 bin satır.
--
-- mart.saha_hedef bu ikisinin üstünde ince bir görünümdür.

BEGIN;

DROP VIEW IF EXISTS mart.saha_hedef;
DROP MATERIALIZED VIEW IF EXISTS mart.saha_kaynak;
DROP MATERIALIZED VIEW IF EXISTS mart.saha_tum;

CREATE MATERIALIZED VIEW mart.saha_tum AS
WITH hepsi AS (
  -- OSM
  SELECT ('osm:' || p.osm_tur || ':' || p.osm_id) AS hedef_anahtari,
         'OSM'::text AS kaynak,
         p.osm_tur, p.osm_id, NULL::bigint AS nokta_id, NULL::text AS overture_id,
         p.ad, p.tur, p.brans_tahmin AS brans,
         CASE WHEN p.brans_tahmin IS NOT NULL THEN 'TAHMIN' ELSE 'YOK' END AS brans_kaynagi,
         NULL::text AS kategori, p.telefon, p.eposta,
         p.website, NULL::text AS sosyal, p.adres, p.ilce AS ilce_ham,
         p.enlem, p.boylam, NULL::text AS ilgili_kisi, NULL::text AS notlar,
         NULL::numeric AS guven, p.ilk_gorulme, p.son_gorulme, p.kayip_at
    FROM raw.osm_poi p
  UNION ALL
  -- OVERTURE
  SELECT ('ovt:' || o.overture_id), 'OVERTURE',
         NULL::text, NULL::bigint, NULL::bigint, o.overture_id,
         o.ad, o.tur, m.brans,
         CASE WHEN m.brans IS NOT NULL THEN 'CIKARIM' ELSE 'YOK' END,
         o.kategori, o.telefon, o.eposta,
         o.website, o.sosyal, o.adres, o.ilce,
         o.enlem, o.boylam, NULL::text, NULL::text,
         o.guven, o.ilk_gorulme, o.son_gorulme, o.kayip_at
    FROM raw.overture_poi o
    LEFT JOIN core.saha_brans_esleme m ON m.kategori = o.kategori
  UNION ALL
  -- ELLE
  SELECT ('elle:' || e.nokta_id), 'ELLE',
         NULL::text, NULL::bigint, e.nokta_id, NULL::text,
         e.ad, e.tur, e.brans,
         CASE WHEN e.brans IS NOT NULL THEN 'BEYAN' ELSE 'YOK' END,
         NULL::text, e.telefon, e.eposta,
         e.website, NULL::text, e.adres, e.ilce, e.enlem, e.boylam,
         e.ilgili_kisi, e.notlar,
         NULL::numeric, e.eklendi, e.eklendi, NULL::timestamptz
    FROM core.saha_elle_nokta e
)
SELECT h.hedef_anahtari, h.kaynak, h.osm_tur, h.osm_id, h.nokta_id, h.overture_id,
       h.ad, h.tur, h.brans, h.brans_kaynagi, h.kategori, h.telefon, h.eposta,
       h.website, h.sosyal, h.adres, h.enlem, h.boylam, h.ilgili_kisi, h.notlar,
       h.guven, h.ilk_gorulme, h.son_gorulme, h.kayip_at,

       -- Aksansız arama anahtarı: 'dis' yazan 'Diş'i bulsun.
       core.tr_anahtar(h.ad) AS ad_ara,

       -- İLÇE. Ham değer SAKLANIR; normalleştirilmiş olan ayrı sütunda.
       -- 'Çankaya' / 'ÇANKAYA' / 'Cankaya' / 'çankaya' tek seçeneğe iner.
       h.ilce_ham,
       CASE WHEN e.cesit IN ('ILCE', 'SEMT') THEN e.ilce END AS ilce,
       CASE WHEN e.cesit = 'ILCE'   THEN 'BEYAN'
            WHEN e.cesit = 'SEMT'   THEN 'SEMTTEN'      -- semt ilçesine bağlandı
            WHEN e.cesit = 'IL'     THEN 'IL_YAZILMIS'  -- 'Ankara' ilçe değil
            WHEN e.cesit = 'IL_DISI' THEN 'BASKA_IL'    -- kaynak veri hatası
            WHEN h.ilce_ham IS NOT NULL THEN 'TANINMADI'
            ELSE 'YOK' END AS ilce_kaynagi,

       -- Kalıptan gelen eleme. İnsan beyanı (core.saha_bilgi) bunu
       -- mart.saha_hedef katmanında YENER -- biri "bu hedeftir" dediyse
       -- desen onu geri eleyemez.
       (d.neden IS NOT NULL) AS kalip_disi,
       d.neden AS kalip_neden,

       (CASE WHEN h.kaynak = 'ELLE' THEN 100 ELSE 0 END
        + (h.telefon IS NOT NULL)::int * 3
        + (h.eposta  IS NOT NULL)::int * 3
        + (h.adres   IS NOT NULL)::int * 2
        + (h.website IS NOT NULL)::int
        + (h.brans   IS NOT NULL)::int * 2
        + (h.ilce_ham IS NOT NULL)::int) AS zenginlik,

       -- Kopya grubu: normalize ad + 3 ondalık koordinat (≈100 m).
       -- Adı ya da koordinatı olmayan kayıt KENDİ BAŞINA bir gruptur:
       -- adsız iki nokta aynı yer olabilir de olmayabilir de, bilmiyoruz.
       CASE WHEN core.tr_anahtar(h.ad) IS NULL
                 OR h.enlem IS NULL OR h.boylam IS NULL
            THEN h.hedef_anahtari
            ELSE replace(core.tr_anahtar(h.ad), ' ', '')
                 || '@' || round(h.enlem::numeric, 3)
                 || ',' || round(h.boylam::numeric, 3) END AS grup
  FROM hepsi h
  LEFT JOIN LATERAL (
       -- Ham ilçe 'Çukurambar/Çankaya' ya da 'Söğütözü, Yenimahalle' gibi
       -- birleşik gelebiliyor. Önce tamamı, sonra kelimeleri denenir;
       -- gerçek ilçe adı semte tercih edilir.
       SELECT s.ilce, s.cesit
         FROM (SELECT core.tr_anahtar(h.ilce_ham) AS kelime
               UNION ALL
               SELECT unnest(string_to_array(core.tr_anahtar(h.ilce_ham), ' '))) t
         JOIN core.saha_ilce_esleme s ON s.ham = t.kelime
        ORDER BY CASE s.cesit WHEN 'ILCE' THEN 1 WHEN 'SEMT' THEN 2
                              WHEN 'IL' THEN 3 ELSE 4 END
        LIMIT 1) e ON true
  LEFT JOIN LATERAL (
       SELECT k.neden FROM core.saha_disla_kalip k
        WHERE core.tr_anahtar(h.ad) ~ k.kalip LIMIT 1) d ON true;

CREATE UNIQUE INDEX saha_tum_anahtar_idx ON mart.saha_tum (hedef_anahtari);
CREATE INDEX saha_tum_grup_idx ON mart.saha_tum (grup);

CREATE MATERIALIZED VIEW mart.saha_kaynak AS
SELECT DISTINCT ON (grup) * FROM mart.saha_tum
 ORDER BY grup, zenginlik DESC, hedef_anahtari;

CREATE UNIQUE INDEX saha_kaynak_grup_idx    ON mart.saha_kaynak (grup);
CREATE UNIQUE INDEX saha_kaynak_anahtar_idx ON mart.saha_kaynak (hedef_anahtari);
CREATE INDEX saha_kaynak_tur_idx   ON mart.saha_kaynak (tur);
CREATE INDEX saha_kaynak_ilce_idx  ON mart.saha_kaynak (ilce);
CREATE INDEX saha_kaynak_brans_idx ON mart.saha_kaynak (brans);
CREATE INDEX saha_kaynak_ara_idx   ON mart.saha_kaynak (ad_ara);
CREATE INDEX saha_kaynak_konum_idx ON mart.saha_kaynak (enlem, boylam);

-- ÜST KATMAN: sahada girilen bilgi ve ziyaret CANLI bağlanır.
--
-- 🔴 NEDEN MADDİLEŞTİRİLMEDİ. Bunlar maddileştirilmiş katmanda olsaydı,
-- sahada bir telefon düzeltmek ya da "bu hedef değil" demek 21 bin satırı
-- yeniden kurmayı gerektirirdi -- kaydın ekranda görünmesi saniyeler
-- sürerdi. Kaynak veri ayda bir değişir, bunlar gün içinde; ayrıldılar.
CREATE VIEW mart.saha_hedef AS
SELECT k.hedef_anahtari, k.kaynak, k.osm_tur, k.osm_id, k.nokta_id,
       k.overture_id, k.grup, k.kategori, k.website, k.sosyal, k.adres,
       k.enlem, k.boylam, k.guven, k.ilk_gorulme, k.son_gorulme, k.kayip_at,
       k.zenginlik, k.ilce, k.ilce_ham, k.ilce_kaynagi,

       -- Beyan çıkarımı YENER ama gizlemez: hangisi olduğu ekranda görünür.
       COALESCE(b.ad, k.ad) AS ad,
       k.tur,
       COALESCE(b.brans, k.brans) AS brans,
       CASE WHEN b.brans IS NOT NULL THEN 'BEYAN' ELSE k.brans_kaynagi END
         AS brans_kaynagi,
       COALESCE(b.telefon, k.telefon) AS telefon,
       COALESCE(b.eposta, k.eposta) AS eposta,
       COALESCE(b.ilgili_kisi, k.ilgili_kisi) AS ilgili_kisi,
       COALESCE(b.notlar, k.notlar) AS notlar,
       COALESCE(core.tr_anahtar(b.ad), k.ad_ara) AS ad_ara,

       -- İnsan beyanı kalıbı yener: biri "bu hedeftir" dediyse desen onu
       -- geri eleyemez; "hedef değil" dediyse desen gerekmez.
       COALESCE(b.hedef_disi, k.kalip_disi) AS hedef_disi,
       CASE WHEN b.hedef_disi IS TRUE  THEN 'elle işaretlendi'
            WHEN b.hedef_disi IS FALSE THEN NULL
            ELSE k.kalip_neden END AS hedef_disi_neden,

       COALESCE(z.ziyaret_sayisi, 0) AS ziyaret_sayisi,
       z.son_ziyaret, z.son_sonuc
  FROM mart.saha_kaynak k
  LEFT JOIN core.saha_bilgi b ON b.hedef_anahtari = k.hedef_anahtari
  LEFT JOIN LATERAL (
       -- Ziyaret GRUBA bağlanır: aynı işletmenin elenen kopyasına
       -- gidilmişse de "gidildi" görünmeli.
       SELECT count(*) AS ziyaret_sayisi,
              max(v.ziyaret_at) AS son_ziyaret,
              (array_agg(v.sonuc ORDER BY v.ziyaret_at DESC))[1] AS son_sonuc
         FROM core.saha_ziyaret v
         JOIN mart.saha_tum t ON t.hedef_anahtari = v.hedef_anahtari
        WHERE t.grup = k.grup) z ON true;

COMMIT;
