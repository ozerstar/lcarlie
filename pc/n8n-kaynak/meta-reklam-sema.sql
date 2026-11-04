-- =============================================================================
-- L'CARLIE - META AD-LEVEL + CREATIVE  (CR-016 corrective patch)
--
-- 🔴 KAMPANYA SEVIYESI ETL'E DOKUNULMADI. raw.meta_harcama oldugu gibi
--    duruyor; bu tablolar ONUN YANINA eklenir.
--
-- 🔴 ALANLAR API'DEN OLCULDU (16.09.2026), UYDURULMADI.
--    Ad-level insights'in TUM satirlarda dondurdugu alanlar:
--      account_id, ad_id, ad_name, adset_id, adset_name, campaign_id,
--      campaign_name, clicks, cpm, ctr, date_start/stop, frequency,
--      impressions, inline_link_clicks, reach, spend
--    Bazi satirlarda: cpc, actions, action_values
--    API'nin dondurmedigi alan icin kolon ACILMADI.
--
-- 🔴 KAPSAMA 1/3.  Yalniz act_1301171572214198 erisilebilir; diger iki
--    hesap sistem kullanicisina ATANMAMIS (#200). Bu tablolar o yuzden
--    TAM harcamayi degil, GORULEN harcamayi tutar.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- JETON OTORITE HARITASI
-- ---------------------------------------------------------------------------
-- 🔴 NEDEN VAR: CR-016'da reklam testi YANLIS JETONLA yapildi
--    (META_SYSTEM_TOKEN = Pages/Instagram mesajlasma). Sonuc: "ads_read yok"
--    diye hatali bulgu raporlandi. Jetonun AMACI yazili olsaydi bu hata
--    olmazdi. Bundan sonra hangi jetonun neye yetkili oldugu BURADA durur.
-- 🔴 SECRET DEGERI YAZILMAZ - yalniz AD, AMAC ve YETKI.
CREATE TABLE IF NOT EXISTS core.jeton_otorite (
  jeton_adi       text PRIMARY KEY,          -- .env degisken ADI (deger DEGIL)
  amac            text NOT NULL,
  izinler         text[],
  paid_media_yetkisi boolean NOT NULL DEFAULT false,
  durum           text NOT NULL DEFAULT 'ACTIVE',
  dogrulama_zamani timestamptz,
  dogrulama_yontemi text,
  not_            text
);

INSERT INTO core.jeton_otorite (jeton_adi, amac, izinler, paid_media_yetkisi,
                                durum, dogrulama_zamani, dogrulama_yontemi, not_)
VALUES
 ('META_ADS_TOKEN', 'paid_media_read', ARRAY['ads_read','public_profile'], true,
  'ACTIVE', now(), 'debug_token + act_/insights level=ad/adset/campaign + /ads + /adcreatives',
  'REKLAM ANALIZI ICIN TEK GECERLI JETON. business_management YOK: hesap '
  'kesfi (me/adaccounts) ve hesap bilgisi calismaz, yalniz ID''si bilinen '
  'hesap sorgulanabilir.'),
 ('META_SYSTEM_TOKEN', 'pages_instagram_messaging',
  ARRAY['business_management','instagram_basic','instagram_manage_comments',
        'instagram_manage_messages','pages_manage_metadata','pages_messaging',
        'pages_read_engagement','pages_show_list','public_profile'], false,
  'ACTIVE', now(), 'debug_token; act_/insights denendi -> #200 RED',
  '🔴 REKLAM ANALIZINDE KULLANILMAZ. ads_read YOK. CR-016''da bu jetonla '
  'test yapildigi icin "ads_read yok" diye HATALI bulgu uretildi.')
ON CONFLICT (jeton_adi) DO UPDATE SET
  amac=EXCLUDED.amac, izinler=EXCLUDED.izinler,
  paid_media_yetkisi=EXCLUDED.paid_media_yetkisi, durum=EXCLUDED.durum,
  dogrulama_zamani=EXCLUDED.dogrulama_zamani,
  dogrulama_yontemi=EXCLUDED.dogrulama_yontemi, not_=EXCLUDED.not_;

COMMENT ON TABLE core.jeton_otorite IS
  'Hangi jeton neye yetkili. SECRET DEGERI TUTMAZ. Reklam testi yanlis '
  'jetonla yapilmasin diye var (CR-016 hatasi).';

-- ---------------------------------------------------------------------------
-- AD-LEVEL GUNLUK PERFORMANS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.meta_reklam (
  hesap_id        text NOT NULL,
  gun             date NOT NULL,
  ad_id           text NOT NULL,
  ad_adi          text,
  adset_id        text,
  adset_adi       text,
  kampanya_id     text,
  kampanya_adi    text,
  harcama         numeric(14,2),
  gosterim        bigint,
  erisim          bigint,          -- reach
  tiklama         bigint,          -- clicks (tum tiklamalar)
  link_tiklama    bigint,          -- inline_link_clicks
  ctr             numeric(10,6),
  cpc             numeric(14,6),   -- 🔴 her satirda gelmeyebilir -> NULL
  cpm             numeric(14,6),
  frekans         numeric(10,6),
  -- 🔴 actions/action_values HAM JSONB olarak durur: Meta'nin event
  --    taksonomisi degisiyor, kolona sabitlemek kirilgan olur.
  --    Ayrica bunlar META'NIN IDDIASIDIR, dogrulanmis satis DEGILDIR.
  eylemler        jsonb,
  eylem_degerleri jsonb,
  ham             jsonb NOT NULL,
  cekim_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (hesap_id, gun, ad_id)
);
CREATE INDEX IF NOT EXISTS meta_reklam_gun_idx ON raw.meta_reklam (gun);
CREATE INDEX IF NOT EXISTS meta_reklam_ad_idx  ON raw.meta_reklam (ad_id);

COMMENT ON TABLE raw.meta_reklam IS
  'Meta ad-level gunluk performans. KAPSAMA 1/3 hesap. '
  'eylemler = Meta''nin kendi iddiasi, dogrulanmis satis DEGIL.';

-- ---------------------------------------------------------------------------
-- KREATIF VARLIK
-- ---------------------------------------------------------------------------
-- 🔴 BINARY GORSEL/VIDEO INDIRILMEZ (bu yamanin konusu degil).
--    Yalniz metin ve referans alanlari tutulur.
CREATE TABLE IF NOT EXISTS raw.meta_kreatif (
  ad_id           text PRIMARY KEY,
  ad_adi          text,
  ad_durumu       text,           -- status
  etkin_durum     text,           -- effective_status
  adset_id        text,
  kampanya_id     text,
  kreatif_id      text,
  kreatif_adi     text,
  baslik          text,           -- title
  govde           text,           -- body
  cta             text,           -- call_to_action_type
  nesne_tipi      text,           -- object_type (VIDEO / SHARE / ...)
  kucuk_gorsel    text,           -- thumbnail_url (REFERANS, indirilmez)
  video_id        text,
  hedef_url       text,           -- reklamin GITTIGI adres (CTA link)
  url_etiketleri  text,           -- url_tags (Meta'nin ekledigi utm kuyrugu)
  olusturma       timestamptz,
  guncelleme      timestamptz,
  ham             jsonb NOT NULL,
  cekim_at        timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE raw.meta_kreatif ADD COLUMN IF NOT EXISTS hedef_url      text;
ALTER TABLE raw.meta_kreatif ADD COLUMN IF NOT EXISTS url_etiketleri text;
CREATE INDEX IF NOT EXISTS meta_kreatif_kid_idx ON raw.meta_kreatif (kreatif_id);

COMMENT ON TABLE raw.meta_kreatif IS
  'Reklam + kreatif metadatasi. Binary medya INDIRILMEZ, yalniz referans. '
  'Access token/secret ASLA yazilmaz.';

-- ---------------------------------------------------------------------------
-- YAZMA FONKSIYONLARI
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION raw.meta_reklam_yaz(j jsonb, p_hesap text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_ad text; v_gun date;
BEGIN
  v_ad  := j->>'ad_id';
  v_gun := (j->>'date_start')::date;
  IF v_ad IS NULL OR v_gun IS NULL THEN RETURN 'ATLANDI'; END IF;

  INSERT INTO raw.meta_reklam AS m (
    hesap_id, gun, ad_id, ad_adi, adset_id, adset_adi, kampanya_id, kampanya_adi,
    harcama, gosterim, erisim, tiklama, link_tiklama, ctr, cpc, cpm, frekans,
    eylemler, eylem_degerleri, ham, cekim_at)
  VALUES (
    p_hesap, v_gun, v_ad,
    j->>'ad_name', j->>'adset_id', j->>'adset_name',
    j->>'campaign_id', j->>'campaign_name',
    raw.sayi(j->>'spend'), raw.sayi(j->>'impressions')::bigint,
    raw.sayi(j->>'reach')::bigint, raw.sayi(j->>'clicks')::bigint,
    raw.sayi(j->>'inline_link_clicks')::bigint,
    raw.sayi(j->>'ctr'), raw.sayi(j->>'cpc'), raw.sayi(j->>'cpm'),
    raw.sayi(j->>'frequency'),
    j->'actions', j->'action_values', j, now())
  ON CONFLICT (hesap_id, gun, ad_id) DO UPDATE SET
    ad_adi=EXCLUDED.ad_adi, adset_id=EXCLUDED.adset_id, adset_adi=EXCLUDED.adset_adi,
    kampanya_id=EXCLUDED.kampanya_id, kampanya_adi=EXCLUDED.kampanya_adi,
    harcama=EXCLUDED.harcama, gosterim=EXCLUDED.gosterim, erisim=EXCLUDED.erisim,
    tiklama=EXCLUDED.tiklama, link_tiklama=EXCLUDED.link_tiklama,
    ctr=EXCLUDED.ctr, cpc=EXCLUDED.cpc, cpm=EXCLUDED.cpm, frekans=EXCLUDED.frekans,
    eylemler=EXCLUDED.eylemler, eylem_degerleri=EXCLUDED.eylem_degerleri,
    ham=EXCLUDED.ham, cekim_at=EXCLUDED.cekim_at
  ;
  -- 🔴 RETURNING ile YENI/GUNCEL ayirmaya calismak (xmax hilesi) hatali ve
  --    gereksizdi; sayim ETL tarafinda yapiliyor.
  RETURN 'OK';
END $$;

CREATE OR REPLACE FUNCTION raw.meta_cta(c jsonb)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(coalesce(
    c->>'call_to_action_type',
    c->'object_story_spec'->'video_data'->'call_to_action'->>'type',
    c->'object_story_spec'->'link_data'->'call_to_action'->>'type',
    c->'asset_feed_spec'->'call_to_action_types'->>0
  ), '');
$$;

CREATE OR REPLACE FUNCTION raw.meta_hedef_url(c jsonb)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(coalesce(
    c->'object_story_spec'->'video_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'link_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'link_data'->>'link',
    c->'object_story_spec'->'photo_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'template_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'template_data'->>'link',
    c->'asset_feed_spec'->'link_urls'->0->>'website_url'
  ), '');
$$;

CREATE OR REPLACE FUNCTION raw.meta_kreatif_yaz(j jsonb)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE c jsonb;
BEGIN
  IF j->>'id' IS NULL THEN RETURN 'ATLANDI'; END IF;
  c := coalesce(j->'creative', '{}'::jsonb);
  INSERT INTO raw.meta_kreatif AS k (
    ad_id, ad_adi, ad_durumu, etkin_durum, adset_id, kampanya_id,
    kreatif_id, kreatif_adi, baslik, govde, cta, nesne_tipi,
    kucuk_gorsel, video_id, hedef_url, url_etiketleri,
    olusturma, guncelleme, ham, cekim_at)
  VALUES (
    j->>'id', j->>'name', j->>'status', j->>'effective_status',
    j->>'adset_id', j->>'campaign_id',
    c->>'id', c->>'name', c->>'title', c->>'body',
    raw.meta_cta(c), c->>'object_type',
    c->>'thumbnail_url', c->>'video_id',
    raw.meta_hedef_url(c), c->>'url_tags',
    raw.zaman(j->>'created_time'), raw.zaman(j->>'updated_time'), j, now())
  ON CONFLICT (ad_id) DO UPDATE SET
    ad_adi=EXCLUDED.ad_adi, ad_durumu=EXCLUDED.ad_durumu,
    etkin_durum=EXCLUDED.etkin_durum, adset_id=EXCLUDED.adset_id,
    kampanya_id=EXCLUDED.kampanya_id, kreatif_id=EXCLUDED.kreatif_id,
    kreatif_adi=EXCLUDED.kreatif_adi, baslik=EXCLUDED.baslik, govde=EXCLUDED.govde,
    cta=EXCLUDED.cta, nesne_tipi=EXCLUDED.nesne_tipi,
    kucuk_gorsel=EXCLUDED.kucuk_gorsel, video_id=EXCLUDED.video_id,
    hedef_url=EXCLUDED.hedef_url, url_etiketleri=EXCLUDED.url_etiketleri,
    guncelleme=EXCLUDED.guncelleme, ham=EXCLUDED.ham, cekim_at=EXCLUDED.cekim_at;
  RETURN 'OK';
END $$;

COMMIT;
