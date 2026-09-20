-- 015 — mart.kreatif_performans: hangi SÖZ işe yarıyor
--
-- NEDEN
-- raw.meta_kreatif'te 63 reklam metninin KENDİSİ duruyor (başlık, gövde,
-- CTA, biçim) ve sistem bunlara hiç bakmıyordu. Reklam analizi iki
-- kampanya düzeyi sorgudan ibaretti. Oysa asıl soru şu: hangi cümle,
-- hangi çağrı, hangi biçim tutuyor?
--
-- ORAN ORTALANMAZ
-- CTR = SUM(tiklama) / SUM(gosterim). AVG(ctr) DEĞİL. Günlük oranların
-- ortalaması, az gösterim alan bir günü çok gösterim alan günle eşit
-- ağırlıklandırır ve yanlış sonuç verir. Aynısı CPC ve CPM için de geçerli.
--
-- ÖRNEK BÜYÜKLÜĞÜ GİZLENMEZ
-- 40 günlük veride bazı kreatifler birkaç yüz gösterim almış. Onları
-- "en iyi kreatif" diye sıralamak gürültüyü sinyal sanmaktır. `yeterli_ornek`
-- sütunu bunu açıkça söyler; panel ve cevap katmanı sıralarken buna bakmalı.
-- Eşik 1000 gösterim -- düşük ama bu veri hacminde anlamlı olan taban.
--
-- 63 KREATIFIN 51'İ BAĞLANIYOR
-- Kalan 12'nin performans kaydı yok (hiç yayınlanmamış ya da veri
-- çekilmemiş). Bunlar görünümde KALIR, performans alanları NULL olur --
-- "yayınlanmadı" ile "veri yok" ayrı şeylerdir ve ikisi de bilgidir.

\set ON_ERROR_STOP on
BEGIN;

CREATE OR REPLACE VIEW mart.kreatif_performans AS
WITH perf AS (
  SELECT ad_id,
         count(DISTINCT gun)            AS gun_sayisi,
         min(gun)                       AS ilk_gun,
         max(gun)                       AS son_gun,
         sum(harcama)                   AS harcama,
         sum(gosterim)                  AS gosterim,
         sum(erisim)                    AS erisim,
         sum(tiklama)                   AS tiklama,
         sum(link_tiklama)              AS link_tiklama,
         max(frekans)                   AS en_yuksek_frekans
  FROM raw.meta_reklam
  GROUP BY ad_id
)
SELECT
  k.ad_id,
  k.ad_adi,
  k.kampanya_id,
  k.adset_id,
  k.etkin_durum,
  k.nesne_tipi                                   AS bicim,
  k.cta,
  k.baslik,
  -- Govde uzun olabilir; panelde ve cevapta kisasi kullanilir, tamami
  -- gerektiginde ham tablodan okunur.
  left(btrim(coalesce(k.govde, '')), 300)        AS govde,
  length(btrim(coalesce(k.govde, '')))           AS govde_uzunluk,
  (k.video_id IS NOT NULL)                       AS video_mu,
  p.gun_sayisi, p.ilk_gun, p.son_gun,
  p.harcama, p.gosterim, p.erisim, p.tiklama, p.link_tiklama,
  p.en_yuksek_frekans,

  -- ORAN ORTALANMAZ: toplamlardan hesaplanir.
  round(100.0 * p.tiklama      / NULLIF(p.gosterim, 0), 2) AS ctr,
  round(100.0 * p.link_tiklama / NULLIF(p.gosterim, 0), 2) AS link_ctr,
  round(p.harcama / NULLIF(p.link_tiklama, 0), 2)          AS link_basi_maliyet,
  round(1000.0 * p.harcama / NULLIF(p.gosterim, 0), 2)     AS cpm,

  -- Gurultuyu sinyal sanmayalim.
  (COALESCE(p.gosterim, 0) >= 1000)                        AS yeterli_ornek,
  CASE
    WHEN p.ad_id IS NULL              THEN 'PERFORMANS_KAYDI_YOK'
    WHEN COALESCE(p.gosterim,0) = 0   THEN 'HIC_GOSTERILMEDI'
    WHEN p.gosterim < 1000            THEN 'YETERSIZ_ORNEK'
    ELSE 'OLCULEBILIR'
  END                                                      AS olcum_durumu
FROM raw.meta_kreatif k
LEFT JOIN perf p ON p.ad_id = k.ad_id;

COMMENT ON VIEW mart.kreatif_performans IS
  'Reklam metni + reklam duzeyi performans. CTR/CPM toplamlardan hesaplanir, '
  'gunluk oranlarin ortalamasi DEGILDIR. yeterli_ornek=false olan satir '
  'siralamaya sokulmamali -- 1000 gosterim altinda oran gurultudur.';

GRANT SELECT ON mart.kreatif_performans TO ai_reader;

COMMIT;
