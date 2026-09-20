-- 017 — Reklam öncesi / sonrası dönem kıyası (016'nın düzeltmesi)
--
-- NEDEN GEREKLİ: 016'DAKİ GÜNLÜK ÖRTÜŞME YANILTIYOR
-- mart.harcama_siparis_ortusmesi "29 gün harcama var, 0 sipariş" diyor ve
-- bu, reklamın işe yaramadığı izlenimi veriyor. YANLIŞ okuma:
--   · Bu işletme ayda ~4–9 sipariş alıyor. Reklam olsun olmasın günlerin
--     çoğunda zaten sipariş YOK. Günlük eşleşme aramak, seyrek bir olayı
--     günlük çözünürlükte aramaktır.
--   · "Sipariş var, harcama yok" günlerinin çoğu reklamlar HİÇ BAŞLAMADAN
--     önceki aylar (Şubat–Temmuz). Kıyas edilen şeyler aynı dönemde değil.
--   · Reklam görüp bir hafta sonra alan müşteri, günlük örtüşmede görünmez.
--
-- DOĞRU BİRİM: DÖNEM, GÜN DEĞİL
-- Bu görünüm reklam öncesi ve reklam dönemini AYLIK HIZ olarak kıyaslar.
--
-- ⚠ YİNE DE ATIF DEĞİL, NEDENSELLİK DE DEĞİL
-- Aynı dönemde başka şeyler de değişti (yeni ürünler, sezon, Trendyol).
-- Örnek çok küçük: reklam döneminde 14 sipariş. 14 sipariş üzerinden
-- "reklam işe yarıyor" demek istatistiksel olarak dayanaksızdır.
-- Görünüm bu uyarıyı SÜTUN OLARAK taşır ki okuyan atlamasın.

\set ON_ERROR_STOP on
BEGIN;

CREATE OR REPLACE VIEW mart.reklam_donem_kiyasi AS
WITH sinir AS (
  SELECT min(gun) AS reklam_baslangic, max(gun) AS reklam_bitis
  FROM raw.meta_harcama
),
donem AS (
  SELECT
    CASE WHEN s.olusturma::date < b.reklam_baslangic
         THEN 'REKLAM_ONCESI' ELSE 'REKLAM_DONEMI' END AS donem,
    s.*
  FROM mart.siparis s CROSS JOIN sinir b
),
ozet AS (
  SELECT d.donem,
         count(*)                                   AS siparis,
         round(sum(d.toplam - d.kdv)::numeric, 2)   AS net_ciro,
         min(d.olusturma::date)                     AS ilk_gun,
         max(d.olusturma::date)                     AS son_gun
  FROM donem d GROUP BY d.donem
)
SELECT
  o.donem,
  o.ilk_gun, o.son_gun,
  (o.son_gun - o.ilk_gun + 1)                       AS gun_sayisi,
  round((o.son_gun - o.ilk_gun + 1) / 30.0, 1)      AS ay_sayisi,
  o.siparis,
  o.net_ciro,
  round(o.siparis / NULLIF((o.son_gun - o.ilk_gun + 1) / 30.0, 0), 1)
                                                    AS aylik_siparis,
  round(o.net_ciro / NULLIF((o.son_gun - o.ilk_gun + 1) / 30.0, 0), 0)
                                                    AS aylik_ciro,
  CASE WHEN o.donem = 'REKLAM_DONEMI'
       THEN (SELECT round(sum(harcama)::numeric, 2) FROM raw.meta_harcama)
       ELSE 0 END                                   AS reklam_harcamasi,
  -- Uyari SUTUN olarak tasinir: ozet okuyan da gorsun.
  CASE
    WHEN o.siparis < 30 THEN
      'ORNEK KUCUK (' || o.siparis || ' siparis) -- bu sayilardan '
      || 'nedensellik cikarilamaz'
    ELSE 'ornek yeterli'
  END                                               AS istatistik_uyarisi
FROM ozet o
ORDER BY o.donem DESC;

COMMENT ON VIEW mart.reklam_donem_kiyasi IS
  'Reklam oncesi ve reklam donemi AYLIK HIZ kiyasi. Gunluk ortusme '
  '(mart.harcama_siparis_ortusmesi) yaniltir cunku isletme ayda ~4-9 '
  'siparis aliyor; gunlerin cogunda reklam olsun olmasin siparis yoktur. '
  'BU GORUNUM DE ATIF VEYA NEDENSELLIK DEGILDIR -- ayni donemde baska '
  'seyler de degisti ve ornek cok kucuk.';

GRANT SELECT ON mart.reklam_donem_kiyasi TO ai_reader;

COMMENT ON VIEW mart.harcama_siparis_ortusmesi IS
  '⚠ ATIF DEGILDIR ve TEK BASINA YANILTIR. Gunluk cozunurlukte bakildiginda '
  '"harcama var siparis yok" gunleri cok gorunur; oysa isletme ayda ~4-9 '
  'siparis aliyor ve gunlerin cogunda zaten siparis yoktur. Donem kiyasi '
  'icin mart.reklam_donem_kiyasi kullanilmali.';

COMMIT;
