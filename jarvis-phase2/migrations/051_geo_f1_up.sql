BEGIN;

-- ============================================================
-- GEO F1 -- UP migration  (sahip sartlari 27.09.2026 islendi)
--
-- SART 1  RAW retention OTOMATIK DEGIL. Hicbir DELETE/cron yok.
--         Politika yalniz COMMENT olarak yazili; gercek buyume
--         olculdukten sonra karar verilecek.
-- SART 2  mention ile citation AYRI. Ayni gozlemde bulunmak
--         "bu kaynak su markayi destekliyor" DEMEK DEGIL.
--         Acik iliski kurulabiliyorsa geo_citation_mention'a
--         yazilir; kurulamiyorsa yalniz co-occurrence kalir.
-- SART 3  alias: canonical_brand_id/alias/normalized_alias/
--         alias_type/language/active
-- SART 4  locale: language + country + surface AYRI
-- SART 5  URL normalizasyonu test edilecek (kod tarafi)
-- SART 6  observation IMMUTABLE + parser/normalizer surumu
-- SART 7  GEO deneyi karar'a typed relation ile baglanir,
--         JSON icinde kaybolmaz
-- SART 8  yedek once dogrulandi (51 satir, md5 esit)
-- ============================================================

-- ───────── RAW ─────────
CREATE TABLE raw.geo_response (
  ham_id           bigserial PRIMARY KEY,
  saglayici        text NOT NULL,
  yuzey            text NOT NULL,
  sorgu_metni      text NOT NULL,
  language         text NOT NULL,
  country          text NOT NULL,
  cevap_hash       text NOT NULL,
  ham              jsonb NOT NULL,
  cekim_at         timestamptz NOT NULL DEFAULT now(),
  is_id            bigint REFERENCES core.ai_task(task_id),
  parser_surum     text NOT NULL
);
COMMENT ON TABLE raw.geo_response IS
  'Ham AI/arama cevabi. RETENTION: politika 90 gun ONERILIYOR ama '
  'OTOMATIK SILME YOK (sahip karari 27.09.2026). Once bytes/observation, '
  'gunluk observation, raw/core orani, citation/observation orani '
  'olculecek; retention karari o olcumden sonra verilecek.';
CREATE UNIQUE INDEX ux_geo_response_tekil
  ON raw.geo_response (saglayici, yuzey, language, country,
                       cevap_hash, cekim_at);

-- ───────── MARKA ve ALIAS (SART 3) ─────────
CREATE TABLE core.geo_brand (
  brand_id    bigserial PRIMARY KEY,
  canonical_name text NOT NULL,
  bizim_mi    boolean NOT NULL DEFAULT false,
  ilk_gorulme timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_geo_brand_ad
  ON core.geo_brand (lower(canonical_name));

CREATE TABLE core.geo_alias (
  alias_id          bigserial PRIMARY KEY,
  canonical_brand_id bigint NOT NULL
    REFERENCES core.geo_brand(brand_id) ON DELETE CASCADE,
  alias             text NOT NULL,
  normalized_alias  text NOT NULL,
  alias_type        text NOT NULL,
  language          text,
  active            boolean NOT NULL DEFAULT true,
  CONSTRAINT ck_geo_alias_tip CHECK (alias_type IN
    ('OFFICIAL','UNICODE_VARIANT','ASCII_FOLD','SPACING','MISSPELLING',
     'ABBREVIATION','LEGACY'))
);
COMMENT ON COLUMN core.geo_alias.normalized_alias IS
  'Kucuk harf, aksan kaldirilmis, apostrof/tire/bosluk temizlenmis. '
  'Ornek: L''CARLIE / L-CARLIE / L Carlie -> lcarlie';
CREATE UNIQUE INDEX ux_geo_alias_normal
  ON core.geo_alias (normalized_alias) WHERE active;
CREATE INDEX ix_geo_alias_brand ON core.geo_alias (canonical_brand_id);

-- ───────── SORGU (SART 4) ─────────
CREATE TABLE core.geo_query (
  query_id      bigserial PRIMARY KEY,
  sorgu_metni   text NOT NULL,
  language      text NOT NULL,
  country       text NOT NULL,
  niyet         text NOT NULL,
  kume_anahtari text,
  urun          text,
  kaynak        text NOT NULL,
  oncelik       int  NOT NULL DEFAULT 5,
  uygunluk      text NOT NULL DEFAULT 'REQUIRES_EVIDENCE',
  iddia_riski   text NOT NULL DEFAULT 'UNKNOWN',
  set_surum     text NOT NULL,
  kesif_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_geo_query_uygunluk CHECK (uygunluk IN
    ('SUPPORTED','PARTIALLY_SUPPORTED','UNSUPPORTED','REQUIRES_EVIDENCE'))
);
COMMENT ON TABLE core.geo_query IS
  'language ve country AYRI: Turkiye-Turkce sorgu ile ABD-Ingilizce '
  'gozlem ayni benchmarka karismaz.';
CREATE UNIQUE INDEX ux_geo_query_tekil
  ON core.geo_query (lower(sorgu_metni), language, country, set_surum);

-- ───────── GOZLEM (SART 4 + 6) ─────────
CREATE TABLE core.geo_observation (
  observation_id bigserial PRIMARY KEY,
  query_id   bigint NOT NULL REFERENCES core.geo_query(query_id),
  yuzey      text NOT NULL,
  model      text,
  language   text NOT NULL,
  country    text NOT NULL,
  gozlem_at  timestamptz NOT NULL,
  durum      text NOT NULL,
  ham_id     bigint REFERENCES raw.geo_response(ham_id),
  cevap_hash text,
  guven      numeric(4,3),
  parser_surum     text NOT NULL,
  normalizer_surum text NOT NULL,
  CONSTRAINT ck_geo_obs_durum CHECK (durum IN
    ('OBSERVED','UNAVAILABLE','UNSUPPORTED','REQUIRES_MANUAL_VALIDATION')),
  CONSTRAINT ck_geo_obs_kanit CHECK (durum <> 'OBSERVED' OR ham_id IS NOT NULL)
);
COMMENT ON TABLE core.geo_observation IS
  'IMMUTABLE: gecmis gozlem UPDATE edilmez. Yeni olcum = yeni satir. '
  'Parser/normalizer degisirse surum kolonlari hangi mantikla '
  'islendigini tasir.';
CREATE UNIQUE INDEX ux_geo_obs_tekil
  ON core.geo_observation (query_id, yuzey, language, country, gozlem_at);
CREATE INDEX ix_geo_obs_zaman ON core.geo_observation (gozlem_at DESC);
CREATE INDEX ix_geo_obs_durum ON core.geo_observation (durum);

-- IMMUTABLE koruma: yalniz durum/guven duzeltilebilir, olcum verisi HAYIR
CREATE OR REPLACE FUNCTION core.geo_obs_immutable() RETURNS trigger AS $$
BEGIN
  IF NEW.query_id  IS DISTINCT FROM OLD.query_id
  OR NEW.yuzey     IS DISTINCT FROM OLD.yuzey
  OR NEW.language  IS DISTINCT FROM OLD.language
  OR NEW.country   IS DISTINCT FROM OLD.country
  OR NEW.gozlem_at IS DISTINCT FROM OLD.gozlem_at
  OR NEW.ham_id    IS DISTINCT FROM OLD.ham_id
  OR NEW.cevap_hash IS DISTINCT FROM OLD.cevap_hash THEN
    RAISE EXCEPTION
      'geo_observation IMMUTABLE: yeni olcum yeni satir olmali '
      '(observation_id=%)', OLD.observation_id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_geo_obs_immutable
  BEFORE UPDATE ON core.geo_observation
  FOR EACH ROW EXECUTE FUNCTION core.geo_obs_immutable();

-- ───────── ANMA (SART 2: citation'dan AYRI) ─────────
CREATE TABLE core.geo_mention (
  mention_id     bigserial PRIMARY KEY,
  observation_id bigint NOT NULL
    REFERENCES core.geo_observation(observation_id) ON DELETE CASCADE,
  brand_id bigint NOT NULL REFERENCES core.geo_brand(brand_id),
  urun     text,
  tip      text NOT NULL,
  baglam   text,
  sira     int,
  CONSTRAINT ck_geo_mention_tip CHECK (tip IN ('BRAND','PRODUCT'))
);
COMMENT ON TABLE core.geo_mention IS
  'Cevapta KIM anildi. Ayni gozlemdeki citation ile ILISKILI OLMAK '
  'ZORUNDA DEGILDIR -- bkz. geo_citation_mention.';
CREATE UNIQUE INDEX ux_geo_mention_tekil
  ON core.geo_mention (observation_id, brand_id, coalesce(urun,''), tip);
CREATE INDEX ix_geo_mention_brand ON core.geo_mention (brand_id);

-- ───────── KAYNAK ve CITATION ─────────
CREATE TABLE core.geo_source (
  source_id   bigserial PRIMARY KEY,
  domain      text NOT NULL,
  tur         text,
  ilk_gorulme timestamptz NOT NULL DEFAULT now(),
  son_gorulme timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN core.geo_source.domain IS
  'Normalize: kucuk harf, www. kaldirilmis, punycode cozulmus. '
  'Path/query DAHIL DEGIL -- o geo_citation.kanonik_url''de.';
CREATE UNIQUE INDEX ux_geo_source_domain ON core.geo_source (domain);

CREATE TABLE core.geo_citation (
  citation_id    bigserial PRIMARY KEY,
  observation_id bigint NOT NULL
    REFERENCES core.geo_observation(observation_id) ON DELETE CASCADE,
  source_id   bigint NOT NULL REFERENCES core.geo_source(source_id),
  kanonik_url text NOT NULL,
  url_hash    text NOT NULL,
  baslik      text,
  sira        int
);
COMMENT ON TABLE core.geo_citation IS
  'Cevapta NE kaynak gosterildi. Ayni gozlemdeki mention ile '
  'otomatik iliskilendirilmez.';
CREATE UNIQUE INDEX ux_geo_citation_tekil
  ON core.geo_citation (observation_id, url_hash);
CREATE INDEX ix_geo_citation_source ON core.geo_citation (source_id);

-- SART 2: ACIK atif. Yalniz citation bir mention/claim ile
-- GERCEKTEN iliskilendirilebiliyorsa satir yazilir.
CREATE TABLE core.geo_citation_mention (
  citation_id bigint NOT NULL
    REFERENCES core.geo_citation(citation_id) ON DELETE CASCADE,
  mention_id  bigint NOT NULL
    REFERENCES core.geo_mention(mention_id) ON DELETE CASCADE,
  iliski_turu text NOT NULL,
  kanit       text NOT NULL,
  guven       numeric(4,3) NOT NULL,
  PRIMARY KEY (citation_id, mention_id),
  CONSTRAINT ck_geo_cm_turu CHECK (iliski_turu IN
    ('EXPLICIT_INLINE','EXPLICIT_FOOTNOTE','EXPLICIT_ATTRIBUTION'))
);
COMMENT ON TABLE core.geo_citation_mention IS
  'ACIK ATIF -- yalniz cevapta citation ile mention ACIKCA '
  'baglanmissa (satir ici referans, dipnot). Co-occurrence BURAYA '
  'YAZILMAZ. Raporlarda co-occurrence attribution gibi gosterilemez.';

-- ───────── CELISKI ─────────
CREATE TABLE core.geo_entity_conflict (
  conflict_id bigserial PRIMARY KEY,
  urun       text NOT NULL,
  alan       text NOT NULL,
  beklenen   text NOT NULL,
  gozlenen   text NOT NULL,
  kaynak_url text,
  source_id  bigint REFERENCES core.geo_source(source_id),
  siddet     text NOT NULL,
  guven      numeric(4,3),
  durum      text NOT NULL DEFAULT 'ACIK',
  tespit_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_geo_conflict_tekil
  ON core.geo_entity_conflict (urun, alan, gozlenen, coalesce(kaynak_url,''));

-- ───────── ACIK (GAP) ─────────
CREATE TABLE core.geo_gap (
  gap_id    bigserial PRIMARY KEY,
  tip       text NOT NULL,
  urun      text,
  query_id  bigint REFERENCES core.geo_query(query_id),
  source_id bigint REFERENCES core.geo_source(source_id),
  siddet    text NOT NULL,
  kanit     text NOT NULL,
  action_id bigint REFERENCES core.ai_action_proposal(action_id),
  durum     text NOT NULL DEFAULT 'ACIK',
  tespit_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_geo_gap_tip CHECK (tip IN
    ('QUERY','CONTENT','ENTITY','CITATION','AUTHORITY','TECHNICAL','EVIDENCE'))
);
CREATE UNIQUE INDEX ux_geo_gap_tekil
  ON core.geo_gap (tip, coalesce(urun,''), coalesce(query_id,0),
                   coalesce(source_id,0));

-- ───────── SART 7: GEO deneyi -> karar, TYPED RELATION ─────────
CREATE TABLE core.geo_karar_kapsami (
  karar_id      bigint NOT NULL REFERENCES core.karar(karar_id)
                ON DELETE CASCADE,
  query_id      bigint REFERENCES core.geo_query(query_id),
  kume_anahtari text,
  urun          text,
  rol           text NOT NULL,
  kapsam_id     bigserial PRIMARY KEY,
  CONSTRAINT ck_geo_kk_rol CHECK (rol IN ('TARGET','CONTROL','CONFOUNDER')),
  CONSTRAINT ck_geo_kk_dolu CHECK (
    query_id IS NOT NULL OR kume_anahtari IS NOT NULL OR urun IS NOT NULL)
);
COMMENT ON TABLE core.geo_karar_kapsami IS
  'GEO deneyinin hangi sorgu/kume/urun ile ilgili oldugu. JSON icinde '
  'kaybolmasin diye typed relation. Deney core.karar (karar_tipi='
  '''GEO_DENEY'') ve olcum core.karar_sonuc icinde durur.';
-- PostgreSQL PRIMARY KEY icinde ifade kabul etmiyor (kuru kosuda yakalandi);
-- tekillik ifadeli UNIQUE INDEX ile saglanir.
CREATE UNIQUE INDEX ux_geo_kk_tekil ON core.geo_karar_kapsami
  (karar_id, coalesce(query_id,0), coalesce(kume_anahtari,''),
   coalesce(urun,''));
CREATE INDEX ix_geo_kk_query ON core.geo_karar_kapsami (query_id);

-- ───────── MEVCUT TABLOYA DOKUNAN TEK DEGISIKLIK ─────────
ALTER TABLE core.sayfa_olcum
  ADD COLUMN IF NOT EXISTS robots_durumu       text,
  ADD COLUMN IF NOT EXISTS sitemap_var         boolean,
  ADD COLUMN IF NOT EXISTS jsonld_turleri      text[],
  ADD COLUMN IF NOT EXISTS hreflang_sayisi     int,
  ADD COLUMN IF NOT EXISTS yonlendirme_zinciri int;

COMMIT;
