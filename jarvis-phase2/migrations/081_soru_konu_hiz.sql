-- 081 · mart.soru_konu HIZ (26.11.2026)
--
-- AJANLAR sayfasi 12-16 sn'de aciliyordu. Ekip panosu bu gorunumu iki kez
-- okuyor (customer_voice + mart.kreatif_hipotez icinden). Eski tanim her
-- gelen mesaj x her konu x her kalip icin core.tr_norm(metin)'i YENIDEN
-- hesapliyordu: ~37 bin dongu, ~1,4 sn (EXPLAIN ANALYZE, 26.11).
--
-- Yeni tanim normalize metni mesaj basina BIR KEZ hesaplar (MATERIALIZED
-- CTE) ve ayni LIKE karsilastirmasini o kolonda yapar. Kolonlar, tipleri,
-- siralari, kaliplar, sorgu_surumu ve sonuc AYNI -- yalniz hesaplama
-- sirasi degisti. CREATE OR REPLACE yetkileri (ai_reader kolon izinleri
-- dahil) ve bagimli mart.kreatif_hipotez'i korur.
--
-- Geri donus: deploy/geri-donus/081_soru_konu_eski.sql (eski tanim aynen).
BEGIN;
CREATE OR REPLACE VIEW mart.soru_konu AS
 WITH kalip AS (
         SELECT t.konu,
            t.kaliplar,
            t.aciklama
           FROM ( VALUES ('ICERIK'::text,ARRAY['icindeki'::text, 'icinde ne'::text, 'icerik'::text, 'formul'::text],'Urunun icinde ne var'::text), ('FIYAT'::text,ARRAY['fiyat'::text, 'ne kadar'::text, 'kac para'::text, 'ucret'::text],'Fiyat'::text), ('SIPARIS_YOLU'::text,ARRAY['siparis'::text, 'nasil alin'::text, 'nereden al'::text],'Nasil siparis verilir'::text), ('ETKI_FAYDA'::text,ARRAY['ne ise'::text, 'fayda'::text, 'etki'::text, 'ise yar'::text],'Ne ise yarar / faydasi'::text), ('KULLANIM'::text,ARRAY['nasil kullan'::text, 'nereye'::text, 'ne kadar sur'::text, 'gunde'::text],'Nasil kullanilir'::text), ('GUVENLIK'::text,ARRAY['yan etki'::text, 'alerj'::text, 'zararl'::text, 'guvenl'::text],'Yan etki / guvenlik'::text), ('SELAMLAMA'::text,ARRAY['merhaba'::text, 'selam'::text, 'tesekkur'::text, 'sagol'::text],'Selamlasma / tesekkur'::text)) t(konu, kaliplar, aciklama)
        ), gelen AS MATERIALIZED (
         SELECT m.konusma_id,
            m.metin,
            core.tr_norm(m.metin) AS norm
           FROM lcarlie.mesaj m
          WHERE m.yon = 'gelen'::text
        ), esles AS (
         SELECT k.konu,
            k.aciklama,
            g.konusma_id,
            g.metin
           FROM gelen g
             JOIN kalip k ON (EXISTS ( SELECT 1
                   FROM unnest(k.kaliplar) p(p)
                  WHERE g.norm ~~ (('%'::text || p.p) || '%'::text)))
        ), toplam AS (
         SELECT count(*)::numeric AS konusma
           FROM lcarlie.konusma
        )
 SELECT e.konu,
    max(e.aciklama) AS aciklama,
    count(DISTINCT e.konusma_id) AS distinct_konusma,
    count(*) AS eslesen_mesaj,
    round(100.0 * count(DISTINCT e.konusma_id)::numeric / (( SELECT toplam.konusma
           FROM toplam))) AS konusma_yuzde,
    (array_agg(DISTINCT "left"(core.pii_maskele(btrim(e.metin)), 56)))[1:3] AS ornekler,
    'tr_norm + LIKE (her iki taraf normalize)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM esles e
  GROUP BY e.konu
UNION ALL
 SELECT 'DIGER'::text AS konu,
    'Hicbir konuya girmeyen musteri mesaji'::text AS aciklama,
    count(DISTINCT g.konusma_id) AS distinct_konusma,
    count(*) AS eslesen_mesaj,
    round(100.0 * count(DISTINCT g.konusma_id)::numeric / (( SELECT toplam.konusma
           FROM toplam))) AS konusma_yuzde,
    (array_agg(DISTINCT "left"(core.pii_maskele(btrim(g.metin)), 56)))[1:3] AS ornekler,
    'tr_norm + LIKE (her iki taraf normalize)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM gelen g
  WHERE btrim(g.metin) <> ''::text AND NOT (EXISTS ( SELECT 1
           FROM kalip k,
            LATERAL unnest(k.kaliplar) p(p)
          WHERE g.norm ~~ (('%'::text || p.p) || '%'::text)));
COMMIT;
