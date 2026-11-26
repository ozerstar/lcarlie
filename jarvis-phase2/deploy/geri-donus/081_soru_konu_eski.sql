-- 081 geri donus: mart.soru_konu eski tanimi (26.11.2026 oncesi, aynen)
BEGIN;
CREATE OR REPLACE VIEW mart.soru_konu AS
 WITH kalip AS (
         SELECT t.konu,
            t.kaliplar,
            t.aciklama
           FROM ( VALUES ('ICERIK'::text,ARRAY['icindeki'::text, 'icinde ne'::text, 'icerik'::text, 'formul'::text],'Urunun icinde ne var'::text), ('FIYAT'::text,ARRAY['fiyat'::text, 'ne kadar'::text, 'kac para'::text, 'ucret'::text],'Fiyat'::text), ('SIPARIS_YOLU'::text,ARRAY['siparis'::text, 'nasil alin'::text, 'nereden al'::text],'Nasil siparis verilir'::text), ('ETKI_FAYDA'::text,ARRAY['ne ise'::text, 'fayda'::text, 'etki'::text, 'ise yar'::text],'Ne ise yarar / faydasi'::text), ('KULLANIM'::text,ARRAY['nasil kullan'::text, 'nereye'::text, 'ne kadar sur'::text, 'gunde'::text],'Nasil kullanilir'::text), ('GUVENLIK'::text,ARRAY['yan etki'::text, 'alerj'::text, 'zararl'::text, 'guvenl'::text],'Yan etki / guvenlik'::text), ('SELAMLAMA'::text,ARRAY['merhaba'::text, 'selam'::text, 'tesekkur'::text, 'sagol'::text],'Selamlasma / tesekkur'::text)) t(konu, kaliplar, aciklama)
        ), esles AS (
         SELECT k.konu,
            k.aciklama,
            m.konusma_id,
            m.metin
           FROM lcarlie.mesaj m
             JOIN kalip k ON (EXISTS ( SELECT 1
                   FROM unnest(k.kaliplar) p(p)
                  WHERE core.tr_norm(m.metin) ~~ (('%'::text || p.p) || '%'::text)))
          WHERE m.yon = 'gelen'::text
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
    count(DISTINCT m.konusma_id) AS distinct_konusma,
    count(*) AS eslesen_mesaj,
    round(100.0 * count(DISTINCT m.konusma_id)::numeric / (( SELECT toplam.konusma
           FROM toplam))) AS konusma_yuzde,
    (array_agg(DISTINCT "left"(core.pii_maskele(btrim(m.metin)), 56)))[1:3] AS ornekler,
    'tr_norm + LIKE (her iki taraf normalize)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM lcarlie.mesaj m
  WHERE m.yon = 'gelen'::text AND btrim(m.metin) <> ''::text AND NOT (EXISTS ( SELECT 1
           FROM kalip k,
            LATERAL unnest(k.kaliplar) p(p)
          WHERE core.tr_norm(m.metin) ~~ (('%'::text || p.p) || '%'::text)));
COMMIT;
