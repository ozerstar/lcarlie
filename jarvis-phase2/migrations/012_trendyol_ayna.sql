-- 012 — raw.trendyol_urun: Trendyol ürün kaydının ham aynası
--
-- NEDEN
-- Panelde "değiştirilebilir tüm bilgiler" görünsün isteniyor. Wix tarafı
-- zaten raw.wix_urun'da tam JSON olarak duruyor; Trendyol tarafında ise
-- yalnız fiyat ve komisyon saklanmıştı. Başlık, açıklama, görseller ve
-- attribute'lar veritabanında yoktu.
--
-- raw.wix_urun ile AYNI DESEN
-- Ham JSON olduğu gibi tutulur, yorumlanmaz. Alanları ayıklamak mart
-- katmanının işidir; raw katmanı yalnız gerçeği aynalar.
--
-- ANAHTAR BARKOD
-- Wix ile eşleştirme barkod üzerinden yapılır (Wix'te ham->>'sku').
-- contentId Trendyol'un kendi kimliği; güncelleme çağrıları onu ister,
-- bu yüzden ayrı sütunda tutulur.
--
-- VERSIYONLAMA YOK, ANLIK GORUNTU VAR
-- Bu bir AYNA. Her cekimde uzerine yazilir; "gecen hafta baslik neydi"
-- sorusu bu tablonun isi degil. Niyet ve karar gecmisi
-- core.urun_platform_fiyat ve onay kuyrugunda tutulur.

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS raw.trendyol_urun (
  barkod        text PRIMARY KEY,
  content_id    bigint,
  ad            text,
  ham           jsonb NOT NULL,
  cekildi       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.trendyol_urun IS
  'Trendyol urun kaydinin ham aynasi. raw.wix_urun ile ayni desen: JSON '
  'oldugu gibi tutulur. Anahtar barkod -- Wix ile eslestirme bunun uzerinden.';
COMMENT ON COLUMN raw.trendyol_urun.content_id IS
  'Trendyol contentId. products.updateContent bu kimligi ister.';

CREATE INDEX IF NOT EXISTS trendyol_urun_content ON raw.trendyol_urun(content_id);

GRANT SELECT ON raw.trendyol_urun TO ai_reader;

COMMIT;
