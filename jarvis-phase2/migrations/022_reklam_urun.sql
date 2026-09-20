-- 022 — Reklam → ürün eşlemesi: "fiyatı nedir?" sorusunun hangi ürüne ait olduğu
--
-- SORUN (ÖLÇÜLDÜ, 20.09.2026)
-- 540 müşteri mesajının HİÇBİRİNDE ürün adı geçmiyor: VIREON 0 kez,
-- INTIMBLANC 0 kez. Ama 183'ü fiyat, 166'sı içerik soruyor. Yani müşterinin
-- hangi ürünü kastettiği YAZDIĞINDAN anlaşılamaz. Tek sinyal: hangi
-- reklamdan geldiği (click-to-Messenger `referral.ad_id`).
--
-- Reklam ADI da yetmiyor -- adlar "k9", "K2", "6", "N. ETK" gibi. Ama
-- kreatif GÖVDESİ ürünü söylüyor ("L'CARLIÉ HYDRAVIE • kuru ve hassas
-- ciltler için..."). Ölçülen kapsama: **63 reklamın 47'si = %74,6**.
-- Kalan 16'sı gerçekten ürünsüz marka reklamı; orada ürün uydurmak yerine
-- müşteriye doğal biçimde sormak DOĞRU davranış.
--
-- 🔴 TÜREV EŞLEŞME ELLE EŞLEŞMEYİ EZEMEZ
-- `kaynak='ELLE'` satırı insan koyar ve tazeleme betiği ona DOKUNMAZ.
-- Yoksa insanın düzelttiği eşleşme bir sonraki çalıştırmada geri alınır --
-- bu projede benzeri yaşandı (kurulum betikleri elle değişiklikleri
-- koşulsuz eziyordu).

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS core.reklam_urun (
  ad_id      text PRIMARY KEY,
  urun_id    text,
  urun_adi   text,
  kaynak     text        NOT NULL CHECK (kaynak IN ('TUREV','ELLE','YOK')),
  gerekce    text,
  olusturma  timestamptz NOT NULL DEFAULT now(),
  guncelleme timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.reklam_urun IS
  'Reklam -> ürün. kaynak=TUREV kreatif metninden çıkarıldı (tazelenir), '
  'ELLE insan koydu (tazeleme DOKUNMAZ), YOK ürünsüz marka reklamı.';
COMMENT ON COLUMN core.reklam_urun.kaynak IS
  'YOK ile NULL farklı: YOK "bakıldı, ürün yok" demek; satırın hiç olmaması '
  '"henüz bakılmadı" demek. İkisini karıştırmak, sormak yerine susmaya yol açar.';

CREATE OR REPLACE VIEW mart.reklam_urun AS
SELECT
  r.ad_id,
  r.urun_id,
  r.urun_adi,
  r.kaynak,
  r.gerekce,
  k.ad_adi,
  k.etkin_durum,
  r.guncelleme
FROM core.reklam_urun r
LEFT JOIN raw.meta_kreatif k ON k.ad_id = r.ad_id;

COMMENT ON VIEW mart.reklam_urun IS
  'Gelen mesajın referral.ad_id''si buradan ürüne çevrilir. Eşleşme yoksa '
  'ürün TAHMİN EDİLMEZ; cevap müşteriye hangi ürün olduğunu sorar.';

GRANT SELECT ON mart.reklam_urun TO ai_reader;

COMMIT;
