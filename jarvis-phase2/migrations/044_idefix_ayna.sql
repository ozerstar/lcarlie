-- 044 — raw.idefix_urun: Idefix ürün kaydının ham aynası
--
-- NEDEN
-- Sahip 22.10.2026'da Idefix Satıcı API anahtarını teslim etti. Trendyol
-- 20.09'da bağlandı ve ham aynası 012'de kuruldu; Idefix aynı desenle
-- bağlanıyor. Lonca SDK'sında Idefix YOK, bu yüzden adaptör kendi
-- betiğimizdir (/opt/lcarlie/idefix-cek.sh).
--
-- raw.trendyol_urun ile AYNI DESEN
-- Ham JSON olduğu gibi tutulur, yorumlanmaz. Her çekimde üzerine yazılır;
-- bu bir ayna, geçmiş kaydı değil. Niyet ve karar geçmişi
-- core.urun_platform_fiyat ve onay kuyruğunda durur.
--
-- ANAHTAR BARKOD
-- Wix ile eşleştirme barkod üzerinden (Wix'te raw.wix_urun.sku).
-- Idefix'in kendi kimlikleri: stok_kodu (vendorStockCode) ve referans
-- (reference) — güncelleme çağrıları bunları ister, ayrı sütunda tutulur.
--
-- 🔴 KOMİSYON YOK
-- Trendyol kendi komisyon oranını API'de bildiriyordu; Idefix'in
-- /pim/pool/{vendorId}/list ve /pim/catalog/{vendorId}/inventory/list
-- yanıtlarında komisyon alanı YOKTUR. core.urun_platform_komisyon'a
-- Idefix satırı YAZILMAZ — uyduruk oran girilmez. Oran satıcı panelinden
-- insan beyanıyla gelmeli.

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS raw.idefix_urun (
  barkod       text PRIMARY KEY,
  stok_kodu    text,
  referans     bigint,
  ad           text,
  durum        text,
  ham          jsonb NOT NULL,
  cekildi      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.idefix_urun IS
  'Idefix urun kaydinin ham aynasi. raw.trendyol_urun ile ayni desen: JSON '
  'oldugu gibi tutulur, her cekimde uzerine yazilir. Anahtar barkod -- Wix '
  'ile eslestirme bunun uzerinden (raw.wix_urun.sku).';
COMMENT ON COLUMN raw.idefix_urun.stok_kodu IS
  'Idefix vendorStockCode. inventory-upload bu kodu ister.';
COMMENT ON COLUMN raw.idefix_urun.referans IS
  'Idefix reference alani (urunun havuzdaki kimligi).';
COMMENT ON COLUMN raw.idefix_urun.durum IS
  'Idefix status alani (onay surecindeki durum). Yorumlanmadan saklanir.';

CREATE INDEX IF NOT EXISTS idefix_urun_stok_kodu ON raw.idefix_urun(stok_kodu);

GRANT SELECT ON raw.idefix_urun TO ai_reader;

-- Platform satiri: hesap artik dogrulandi sayilmaz -- API anahtari girildi,
-- ama yazma izni KAPALI kalir. Disari yazma ayri ve acik bir karar.
UPDATE core.platform
   SET not_ = 'Satici hesabi VAR (seller_id 22204); API anahtari girildi. '
              'Yazma izni KAPALI. Komisyon orani API''de yok -- insan beyani gerekir.',
       guncelleme = now()
 WHERE kod = 'idefix';

COMMIT;
