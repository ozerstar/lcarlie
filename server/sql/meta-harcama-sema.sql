-- =============================================================================
-- L'CARLIE - META REKLAM HARCAMASI  (CR-005 Faz 2)
--
-- 🔴 GERIYE DONUK DEGISEN VERI.  Meta'nin harcama ve sonuc rakamlari
--    GECMISE DONUK DEGISIR: gec raporlanan gosterimler, atif penceresi
--    kapanmasi, fatura duzeltmesi. "Bir kez cektim, bitti" YANLISTIR.
--    Bu yuzden ETL her calismada son N gunu YENIDEN yazar; tablo
--    upsert'e gore kurulmustur.
--
-- 🔴 META'NIN KENDI DONUSUM RAKAMI AYRI TUTULUR.
--    Meta "su kadar satis getirdim" der; bu bizim Wix cirosu DEGILDIR
--    (atif penceresi, view-through, cihaz eslestirme). Ikisi ayri
--    kolonlarda durur, TOPLANMAZ, birbirinin yerine kullanilmaz.
--
-- 🔴 KAYNAK ISARETLENIR: META_API mi, ELLE mi. Ciro tarafindaki
--    dogrulanmis/beyan ayriminin aynisi.
--
-- Idempotent: tekrar calistirilabilir.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Reklam hesaplari
-- --------------------------------------------------------------------------
-- 🔴 UC hesap var ve varsayilan acilan YANLIS olani (CR 13.09 dersi).
--    Hangi hesabin okundugu her satirda yazili olsun diye ayri tablo.
CREATE TABLE IF NOT EXISTS raw.meta_hesap (
  hesap_id     text PRIMARY KEY,       -- act_ ONEKSIZ, orn. 1301171572214198
  ad           text,
  durum        int,                    -- account_status
  para_birimi  text,
  portfolyo    text,
  ham          jsonb,
  cekim_at     timestamptz NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- Gunluk harcama (gun x kampanya)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.meta_harcama (
  gun            date NOT NULL,
  hesap_id       text NOT NULL,
  kampanya_id    text NOT NULL,          -- hesap toplami icin '_HESAP'
  kaynak         text NOT NULL DEFAULT 'META_API'
                 CHECK (kaynak IN ('META_API','ELLE')),
  kampanya_adi   text,                   -- zamanla degisebilir, ham'da da durur
  harcama        numeric(14,2),
  para_birimi    text,
  gosterim       bigint,
  erisim         bigint,
  tiklama        bigint,                 -- clicks (tum tiklamalar)
  link_tiklama   bigint,                 -- inline_link_clicks
  cpm            numeric(14,4),
  cpc            numeric(14,4),
  ctr            numeric(10,6),
  sikligi        numeric(10,4),

  -- 🔴 META'NIN KENDI IDDIASI. Bizim ciromuz DEGIL. Karsilastirmak icin
  --    tutulur, yerine gecmek icin degil.
  meta_donusum       numeric(14,2),
  meta_donusum_degeri numeric(14,2),

  ham            jsonb NOT NULL,
  cekim_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (gun, hesap_id, kampanya_id, kaynak)
);
CREATE INDEX IF NOT EXISTS meta_harcama_gun_idx ON raw.meta_harcama (gun);

COMMENT ON TABLE raw.meta_harcama IS
  'Meta reklam harcamasi, gun x kampanya. Rakamlar GERIYE DONUK DEGISIR - ETL son N gunu her seferinde yeniden yazar.';
COMMENT ON COLUMN raw.meta_harcama.meta_donusum_degeri IS
  'Meta''nin atif modeline gore iddia ettigi gelir. Wix cirosu ile AYNI SEY DEGILDIR, toplanmaz.';

-- --------------------------------------------------------------------------
-- Cikarma fonksiyonu (ham JSON -> kolon)
-- --------------------------------------------------------------------------
-- Ayri fonksiyon olmasinin gerekcesi raw-cikarma.sql ile ayni: bir kural
-- yanlis cikarsa kaynaga dokunmadan ham'dan yeniden turetilir.
CREATE OR REPLACE FUNCTION raw.meta_harcama_yaz(j jsonb, p_hesap text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_gun date; v_kmp text; v_yeni boolean;
BEGIN
  v_gun := raw.bos_null(j->>'date_start')::date;
  IF v_gun IS NULL THEN
    RAISE EXCEPTION 'Meta satirinda date_start yok: %', left(j::text,200);
  END IF;
  -- Kampanya kirilimi istenmediginde Meta campaign_id dondurmez ->
  -- hesap toplami oldugu ACIKCA isaretlenir, bos string birakilmaz.
  v_kmp := coalesce(raw.bos_null(j->>'campaign_id'), '_HESAP');

  INSERT INTO raw.meta_harcama AS m (
    gun, hesap_id, kampanya_id, kaynak, kampanya_adi, harcama, para_birimi,
    gosterim, erisim, tiklama, link_tiklama, cpm, cpc, ctr, sikligi,
    meta_donusum, meta_donusum_degeri, ham, cekim_at)
  VALUES (
    v_gun, p_hesap, v_kmp, 'META_API',
    raw.bos_null(j->>'campaign_name'),
    raw.sayi(j->>'spend'),
    raw.bos_null(j->>'account_currency'),
    raw.sayi(j->>'impressions')::bigint,
    raw.sayi(j->>'reach')::bigint,
    raw.sayi(j->>'clicks')::bigint,
    raw.sayi(j->>'inline_link_clicks')::bigint,
    raw.sayi(j->>'cpm'), raw.sayi(j->>'cpc'),
    raw.sayi(j->>'ctr'), raw.sayi(j->>'frequency'),
    -- actions / action_values dizileri: satin alma satirini bul
    (SELECT raw.sayi(a->>'value') FROM jsonb_array_elements(coalesce(j->'actions','[]'::jsonb)) a
      WHERE a->>'action_type' IN ('purchase','omni_purchase','offsite_conversion.fb_pixel_purchase')
      ORDER BY raw.sayi(a->>'value') DESC NULLS LAST LIMIT 1),
    (SELECT raw.sayi(a->>'value') FROM jsonb_array_elements(coalesce(j->'action_values','[]'::jsonb)) a
      WHERE a->>'action_type' IN ('purchase','omni_purchase','offsite_conversion.fb_pixel_purchase')
      ORDER BY raw.sayi(a->>'value') DESC NULLS LAST LIMIT 1),
    j, now())
  ON CONFLICT (gun, hesap_id, kampanya_id, kaynak) DO UPDATE SET
    kampanya_adi        = EXCLUDED.kampanya_adi,
    harcama             = EXCLUDED.harcama,
    para_birimi         = EXCLUDED.para_birimi,
    gosterim            = EXCLUDED.gosterim,
    erisim              = EXCLUDED.erisim,
    tiklama             = EXCLUDED.tiklama,
    link_tiklama        = EXCLUDED.link_tiklama,
    cpm                 = EXCLUDED.cpm,
    cpc                 = EXCLUDED.cpc,
    ctr                 = EXCLUDED.ctr,
    sikligi             = EXCLUDED.sikligi,
    meta_donusum        = EXCLUDED.meta_donusum,
    meta_donusum_degeri = EXCLUDED.meta_donusum_degeri,
    ham                 = EXCLUDED.ham,
    cekim_at            = EXCLUDED.cekim_at
  RETURNING (m.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;

CREATE OR REPLACE FUNCTION raw.meta_hesap_yaz(j jsonb)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_id text; v_yeni boolean;
BEGIN
  -- API 'act_123' dondurur; biz her yerde oneksiz tutariz ki
  -- hafizadaki hesap kodlariyla birebir eslessin.
  v_id := regexp_replace(coalesce(j->>'id', j->>'account_id',''), '^act_', '');
  IF raw.bos_null(v_id) IS NULL THEN
    RAISE EXCEPTION 'Meta hesabinda id yok: %', left(j::text,200);
  END IF;

  INSERT INTO raw.meta_hesap AS h (hesap_id, ad, durum, para_birimi, portfolyo, ham, cekim_at)
  VALUES (v_id, raw.bos_null(j->>'name'), raw.sayi(j->>'account_status')::int,
          raw.bos_null(j->>'currency'), raw.bos_null(j#>>'{business,name}'), j, now())
  ON CONFLICT (hesap_id) DO UPDATE SET
    ad = EXCLUDED.ad, durum = EXCLUDED.durum, para_birimi = EXCLUDED.para_birimi,
    portfolyo = EXCLUDED.portfolyo, ham = EXCLUDED.ham, cekim_at = EXCLUDED.cekim_at
  RETURNING (h.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;

COMMIT;
