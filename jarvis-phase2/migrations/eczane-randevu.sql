-- Eczane e-posta kampanyası + ziyaret randevusu (13.11.2026).
-- Sahip: "randevuları üst üste bindirmeyecek şekilde oluşturacağız",
-- "geri dönüşleri sisteme entegre et", "önce Ankara, sonra il il".
BEGIN;

CREATE TABLE IF NOT EXISTS core.eczane_hedef (
  id          bigserial PRIMARY KEY,
  il          text NOT NULL,
  eczane      text NOT NULL,
  eczaci      text,
  telefon     text,
  adres       text,
  eposta      text,
  -- Kişiye özel bağlantı anahtarı: randevu ve listeden çıkma bununla.
  -- Tahmin edilemez olmalı; sıra numarası bağlantıya KONMAZ.
  anahtar     text NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(12), 'hex'),
  durum       text NOT NULL DEFAULT 'YENI'
              CHECK (durum IN ('YENI','GONDERILDI','ILGILENDI','RANDEVU','ZIYARET_EDILDI',
                               'MUSTERI','ILGISIZ','CIKTI','GECERSIZ')),
  kaynak      text NOT NULL DEFAULT 'eczaneler-20240815 (Drive, M. Arslan)',
  eklendi     timestamptz NOT NULL DEFAULT now(),
  guncellendi timestamptz NOT NULL DEFAULT now(),
  UNIQUE (il, eczane, telefon)
);
COMMENT ON TABLE core.eczane_hedef IS
  'Eczane hedef listesi (PII: eczacı adı/telefon). Yalnız kampanya/randevu; dışarı ve CompanyMemory''ye çıkmaz.';

CREATE TABLE IF NOT EXISTS core.eczane_randevu (
  id          bigserial PRIMARY KEY,
  hedef_id    bigint NOT NULL REFERENCES core.eczane_hedef(id),
  baslangic   timestamptz NOT NULL,
  bitis       timestamptz NOT NULL,
  yetkili     text NOT NULL CHECK (length(trim(yetkili)) >= 3),
  unvan       text,
  telefon     text NOT NULL CHECK (length(regexp_replace(telefon, '\D', '', 'g')) >= 10),
  ilgi        text,
  notu        text,
  durum       text NOT NULL DEFAULT 'TALEP'
              CHECK (durum IN ('TALEP','ONAYLANDI','IPTAL','YAPILDI','GELMEDI')),
  olusturuldu timestamptz NOT NULL DEFAULT now(),
  CHECK (bitis > baslangic),
  -- 🔴 ÇAKIŞMA KAPISI: iptal edilmemiş iki randevunun zaman aralığı kesişemez.
  --    Kontrol uygulamada DEĞİL veritabanında: aynı saniyede gelen iki
  --    istekten yalnız biri yazılır, diğeri hata alır.
  EXCLUDE USING gist (tstzrange(baslangic, bitis) WITH &&) WHERE (durum <> 'IPTAL')
);
-- Bir eczanenin aynı anda tek açık randevusu olur.
CREATE UNIQUE INDEX IF NOT EXISTS eczane_randevu_tek_acik
  ON core.eczane_randevu (hedef_id) WHERE durum IN ('TALEP','ONAYLANDI');

CREATE TABLE IF NOT EXISTS core.eczane_etkilesim (
  id        bigserial PRIMARY KEY,
  hedef_id  bigint REFERENCES core.eczane_hedef(id),
  tur       text NOT NULL CHECK (tur IN ('GONDERILDI','ACILDI','TIKLADI','SAYFA','RANDEVU',
                                         'YANIT','CIKIS','IPTAL','NOT')),
  ayrinti   jsonb NOT NULL DEFAULT '{}'::jsonb,
  zaman     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS eczane_etkilesim_hedef ON core.eczane_etkilesim (hedef_id, zaman DESC);

COMMIT;
