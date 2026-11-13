-- Jarvis ECZANELER sekmesi: eczane başına tek satır, yapılan her iş tarihiyle.
-- Sahip 13.11.2026: "Jarvis'te bir tabloda eczane listelerini koy, bilgilerini
-- koy, bu eczanelerle ilgili neler yapıldı tikli halde götürülsün."
--
-- Görünüm n8n sahibinin yetkisiyle çalışır; panel rolü (jarvis_web) YALNIZ bu
-- görünümü okur, ham tablolara (kaynak, etkileşim metni) erişmez.
BEGIN;
CREATE OR REPLACE VIEW mart.eczane_takip AS
WITH wa AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, durum, gonderildi, guncellendi, hata_kodu
  FROM core.eczane_gonderim WHERE kanal = 'whatsapp'
  ORDER BY hedef_id, gonderildi DESC
), et AS (
  SELECT hedef_id,
    max(zaman) FILTER (WHERE tur = 'GONDERILDI' AND ayrinti->>'kanal' = 'eposta'
                       AND coalesce(ayrinti->>'test','false') <> 'true') AS eposta_gonderildi,
    max(zaman) FILTER (WHERE tur = 'SAYFA')  AS sayfa_son,
    count(*)   FILTER (WHERE tur = 'SAYFA')  AS sayfa_sayisi,
    max(zaman) FILTER (WHERE tur = 'YANIT')  AS yanit_son,
    max(zaman) FILTER (WHERE tur = 'CIKIS')  AS cikis_zaman,
    max(zaman) AS son_islem
  FROM core.eczane_etkilesim GROUP BY hedef_id
), son_yanit AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, left(ayrinti->>'metin', 160) AS metin
  FROM core.eczane_etkilesim WHERE tur = 'YANIT'
  ORDER BY hedef_id, zaman DESC
), rv AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, baslangic, durum, yetkili, telefon AS yetkili_tel, ilgi
  FROM core.eczane_randevu WHERE durum <> 'IPTAL'
  ORDER BY hedef_id, baslangic DESC
), ep AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, eposta, dogrulama
  FROM core.eczane_eposta WHERE coalesce(dogrulama, '') <> 'GECERSIZ'
  ORDER BY hedef_id, (dogrulama = 'GECERLI') DESC NULLS LAST, id
), cep AS (
  SELECT DISTINCT ON (hedef_id) hedef_id, t AS cep
  FROM raw.eczane_kaynak, unnest(telefonlar) t
  WHERE hedef_id IS NOT NULL AND left(t, 1) = '5'
  ORDER BY hedef_id, kaynak
)
SELECT h.id, h.il, h.ilce, h.eczane, h.eczaci,
       right(regexp_replace(coalesce(h.telefon, ''), '\D', '', 'g'), 10) AS telefon,
       cep.cep, ep.eposta, ep.dogrulama AS eposta_dogrulama,
       ('AEO_TEMSILCI' = ANY (h.etiketler)) AS temsilci,
       h.son_nobet, h.durum, h.oncelik, h.enlem IS NOT NULL AS konumlu,
       wa.gonderildi AS wa_gonderildi, wa.durum AS wa_durum, wa.hata_kodu AS wa_hata,
       et.eposta_gonderildi, et.sayfa_son, coalesce(et.sayfa_sayisi, 0) AS sayfa_sayisi,
       et.yanit_son, son_yanit.metin AS yanit_metin, et.cikis_zaman,
       rv.baslangic AS randevu, rv.durum AS randevu_durum, rv.yetkili AS randevu_yetkili,
       rv.yetkili_tel AS randevu_tel, rv.ilgi AS randevu_ilgi,
       (rv.durum = 'YAPILDI' OR h.durum IN ('ZIYARET_EDILDI', 'MUSTERI')) AS ziyaret_edildi,
       (h.durum = 'MUSTERI') AS musteri,
       greatest(et.son_islem, wa.guncellendi, rv.baslangic) AS son_islem
FROM core.eczane_hedef h
LEFT JOIN wa ON wa.hedef_id = h.id
LEFT JOIN et ON et.hedef_id = h.id
LEFT JOIN son_yanit ON son_yanit.hedef_id = h.id
LEFT JOIN rv ON rv.hedef_id = h.id
LEFT JOIN ep ON ep.hedef_id = h.id
LEFT JOIN cep ON cep.hedef_id = h.id
WHERE h.durum <> 'GECERSIZ' AND NOT ('TEST' = ANY (h.etiketler));

COMMENT ON VIEW mart.eczane_takip IS
  'Eczane başına kampanya takibi (Jarvis ECZANELER). PII içerir: yalnız sahip paneli.';
GRANT USAGE ON SCHEMA mart TO jarvis_web;
GRANT SELECT ON mart.eczane_takip TO jarvis_web;
COMMIT;
