-- GROWTH-005 OKUMA SORGUSU · SALT OKUNUR · 17.09.2026 (v2 - kati CORRECT kurali)
-- raw-uygula.sh zincirine EKLENMEDI, cron'a BAGLANMADI.
-- KATI KURAL: CORRECT yalnizca notlar->>'g5_saved_reply' 'VERIFIED' ile basliyorsa sayilir.
-- Metin benzerligi CORRECT DEGILDIR -> UNKNOWN_SOURCE olarak raporlanir.
-- Calistirma:
--   docker exec -i lcarlie-postgres psql -U n8n -d n8n -f - < /opt/lcarlie/sql/growth005-okuma.sql
\pset pager off
\set kesim '2026-09-17 03:30:00+03'

WITH n AS (
  SELECT konusma_id, zaman, yon, metin,
         translate(lower(metin), chr(305)||chr(351)||chr(231)||chr(287)||chr(252)||chr(246)||chr(304)||chr(350)||chr(199)||chr(286)||chr(220)||chr(214),'iscguoiscguo') t,
         (metin ~* 'bir reklama yan.t verdi') AS gurultu
  FROM lcarlie.mesaj WHERE length(trim(metin))>0),
cohort AS (
  SELECT id AS konusma_id, sonuc, siparis_no, notlar
  FROM lcarlie.konusma WHERE ilk_mesaj >= :'kesim'::timestamptz),
niyet AS (
  SELECT DISTINCT ON (c.konusma_id) c.konusma_id, c.sonuc, c.siparis_no, c.notlar, m.zaman AS niyet_an,
    CASE WHEN m.t ~ 'nasil siparis|siparis nasil|siparis ver|nasil alabil|nereden alabil|nereden al|nasil alir|almak istiyorum' THEN 'HOW_TO_ORDER'
         WHEN m.t ~ 'icindekiler|icerik|icinde ne|nasil kullan' THEN 'INGREDIENTS'
         ELSE 'PRICE' END AS intent
  FROM cohort c JOIN n m ON m.konusma_id=c.konusma_id AND m.yon='gelen'
  WHERE m.t ~ 'nasil siparis|siparis nasil|siparis ver|nasil alabil|nereden alabil|nereden al|nasil alir|almak istiyorum|fiyat|kac para|kac tl|ne kadar|ucret|icindekiler|icerik|icinde ne|nasil kullan'
  ORDER BY c.konusma_id, m.zaman),
cv AS (
  SELECT ni.*,
    (SELECT g.metin FROM n g WHERE g.konusma_id=ni.konusma_id AND g.yon='giden' AND NOT g.gurultu AND g.zaman>ni.niyet_an ORDER BY g.zaman LIMIT 1) AS cevap_metin,
    (SELECT g.zaman FROM n g WHERE g.konusma_id=ni.konusma_id AND g.yon='giden' AND NOT g.gurultu AND g.zaman>ni.niyet_an ORDER BY g.zaman LIMIT 1) AS reply_ts
  FROM niyet ni),
tam AS (
  SELECT cv.*,
    -- KAYNAK: yalnizca insan tarafindan dogrulanmis Saved Reply kullanimi CORRECT sayilir
    CASE WHEN cv.notlar->>'g5_saved_reply' LIKE 'VERIFIED%' THEN 'CORRECT_VERIFIED_MANUAL_MANUAL'
         WHEN cv.cevap_metin IS NULL THEN 'CEVAP_YOK'
         WHEN cv.cevap_metin ILIKE '%VIREON50%' THEN 'DEAD_COUPON'
         WHEN cv.cevap_metin ~ '2[.,]?400' AND cv.cevap_metin !~ '1[.,]?200' THEN 'WRONG_PRICE'
         -- asagidakiler METIN BENZERLIGI; kaynak dogrulanamaz -> CORRECT DEGIL
         WHEN cv.cevap_metin ILIKE '%buradan sipari%verebilirsin%'
           OR cv.cevap_metin ILIKE '%Epimedium, L-Arginin, Tribulus ve Damiana ekstreleri%'
           OR cv.cevap_metin ILIKE '%1.200 TL. U%cretsiz kargo%' THEN 'UNKNOWN_SOURCE_sablona_benzer'
         WHEN cv.cevap_metin ~ '1[.,]?200' AND cv.cevap_metin ILIKE '%lcarlie.shop%' THEN 'UNKNOWN_SOURCE_esdeger'
         WHEN cv.cevap_metin ~ '1[.,]?200' OR cv.cevap_metin ILIKE '%lcarlie.shop%' THEN 'INCOMPLETE'
         ELSE 'DOES_NOT_ANSWER' END AS kaynak_sinifi,
    (SELECT x.metin FROM n x WHERE x.konusma_id=cv.konusma_id AND x.yon='gelen' AND x.zaman>cv.reply_ts ORDER BY x.zaman LIMIT 1) AS sonraki_gelen,
    (SELECT translate(lower(x.metin), chr(305)||chr(351)||chr(231)||chr(287)||chr(252)||chr(246)||chr(304)||chr(350)||chr(199)||chr(286)||chr(220)||chr(214),'iscguoiscguo')
       FROM n x WHERE x.konusma_id=cv.konusma_id AND x.yon='gelen' AND x.zaman>cv.reply_ts ORDER BY x.zaman LIMIT 1) AS sonraki_t
  FROM cv)
SELECT
  count(*) AS cohort_n,
  count(*) FILTER (WHERE kaynak_sinifi='CORRECT_VERIFIED_MANUAL_MANUAL') AS correct_DOGRULANMIS,
  count(*) FILTER (WHERE kaynak_sinifi LIKE 'UNKNOWN_SOURCE%') AS unknown_source_metin_benzer,
  count(*) FILTER (WHERE sonraki_gelen IS NOT NULL) AS cevap_sonrasi_tekrar_mesaj,
  count(*) FILTER (WHERE sonraki_t ~ 'kapida|odeme|havale|iban|kart|taksit|kargo|teslimat|gizli|almak istiyorum|siparis ver|adresim|gonderin') AS ticari_yonlu_ikinci_soru,
  count(*) FILTER (WHERE intent='HOW_TO_ORDER') AS how_to_order_n,
  count(*) FILTER (WHERE intent='HOW_TO_ORDER' AND sonraki_gelen IS NOT NULL) AS how_to_order_ilerledi,
  count(*) FILTER (WHERE sonraki_gelen IS NULL) AS no_further_reply,
  count(*) FILTER (WHERE siparis_no IS NOT NULL) AS deterministik_satis,
  count(*) FILTER (WHERE siparis_no IS NULL) AS not_attributable
FROM tam;
