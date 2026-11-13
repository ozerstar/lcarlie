-- Türkiye geneli eczane iletişim verisi (13.11.2026).
-- Sahip: "Ankara, sonra büyükşehirler, sonra küçük şehirler — tüm ülkedeki
-- eczane datasını çıkaracaksın", "bunlar hep önemli datalar".
--
-- Her kaynak (Google Haritalar taraması, Overture, OSM, elle) AYNI tabloya
-- kaynağıyla yazılır. Kaynaklar birbirini EZMEZ: aynı eczane iki kaynakta
-- iki satırdır; birleştirme eczane_hedef'e bağlanırken yapılır.
-- 🔴 SİLME YOK: taramada görünmeyen kayıt silinmez (son_gorulme eskir).
BEGIN;

CREATE TABLE IF NOT EXISTS raw.eczane_kaynak (
  id           bigserial PRIMARY KEY,
  kaynak       text NOT NULL,              -- GMAPS / OVERTURE / OSM / ELLE
  kaynak_id    text NOT NULL,              -- place_id, overture id …
  il           text,
  ilce         text,
  ad           text NOT NULL,
  kategori     text,
  telefonlar   text[] NOT NULL DEFAULT '{}',
  epostalar    text[] NOT NULL DEFAULT '{}',
  web          text,
  sosyal       text[] NOT NULL DEFAULT '{}',
  adres        text,
  enlem        double precision,
  boylam       double precision,
  sorgu        text,                       -- hangi arama bu kaydı getirdi
  ham          jsonb NOT NULL DEFAULT '{}'::jsonb,
  hedef_id     bigint REFERENCES core.eczane_hedef(id),
  eslesme      text,                       -- TELEFON / AD_ILCE / YENI / NULL=bakılmadı
  ilk_gorulme  timestamptz NOT NULL DEFAULT now(),
  son_gorulme  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kaynak, kaynak_id)
);
CREATE INDEX IF NOT EXISTS eczane_kaynak_il ON raw.eczane_kaynak (il);
CREATE INDEX IF NOT EXISTS eczane_kaynak_hedef ON raw.eczane_kaynak (hedef_id);
COMMENT ON TABLE raw.eczane_kaynak IS
  'Eczane iletişim verisi, kaynak başına ham satır. PII olabilir (eczacı adı/kişisel e-posta); CompanyMemory''ye çıkmaz.';

-- Bir eczanenin birden çok e-postası olabilir (site + Google + Overture).
CREATE TABLE IF NOT EXISTS core.eczane_eposta (
  id          bigserial PRIMARY KEY,
  hedef_id    bigint NOT NULL REFERENCES core.eczane_hedef(id),
  eposta      text NOT NULL,
  kaynak      text NOT NULL,
  dogrulama   text CHECK (dogrulama IN ('GECERLI','GECERSIZ','BELIRSIZ')),
  dogrulandi  timestamptz,
  eklendi     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (hedef_id, eposta)
);

-- Önceliklendirme için il sırası (Ankara → büyükşehir → diğer).
ALTER TABLE core.eczane_hedef ADD COLUMN IF NOT EXISTS oncelik int;

COMMIT;
