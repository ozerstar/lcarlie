-- =============================================================================
-- 034 · LEAD KESIF: Ankara B2B hedef listesi
--
-- SAHIP KARARI (24.09.2026): once Ankara. Segmentler: eczane, muayenehane,
-- klinik, tip merkezi, guzellik merkezi, spa/masaj, spor salonu.
--
-- OLCULEN GERCEK -- bu semanin bicimini belirleyen sey
--   segment           OSM kayit   telefonlu
--   eczane                 1799    1374 (%76)   <- OSM YETERLI
--   klinik                  207      16 (%8)
--   spor salonu             185      15 (%8)
--   guzellik merkezi        111      14 (%13)
--   muayenehane              20       4 (%20)
--   spa / masaj               7       1 (%14)
--   tip merkezi               0       -
-- OSM yalniz eczanede ise yariyor. Digerleri Places API ile doldurulacak.
-- Bu yuzden `kaynak` sutunu var: iki kaynak AYNI tabloda ama AYIRT EDILEBILIR.
--
-- 🔴 PLACES VERISI KALICI SAKLANAMAZ. Google sartlari onbellek suresi
--    daytiyor; OSM verisi (ODbL) saklanabilir. `kaynak` ayrimi bunun icin
--    sart: temizlik isi Places satirlarini suresi dolunca silebilsin.
--
-- 🔴 KVKK SEMAYA GOMULU. `saklama_sonu` NOT NULL: saklama suresi olmayan
--    kayit YAZILAMAZ. Varsayilan 2 yil -- ticari bir karardir, HUKUKI GORUS
--    DEGILDIR ve avukat teyidi gerekir.
--
-- 🔴 IYS SEMAYA GOMULU. `iys_durumu` varsayilani SORULMADI. Ticari elektronik
--    ileti gonderen taraf ONAYLI olmayan satira gonderemez. Kurali koda
--    birakmak, kural koymamakla ayni seydir -- bu yuzden kisit burada.
--
-- GERI ALMA: rollback/034_lead_kesif_ROLLBACK.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------- ham katman
CREATE TABLE IF NOT EXISTS raw.lead_osm (
    osm_tip     text        NOT NULL,
    osm_id      bigint      NOT NULL,
    segment     text        NOT NULL,
    il          text        NOT NULL,
    etiketler   jsonb       NOT NULL,
    enlem       double precision,
    boylam      double precision,
    cekildi     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (osm_tip, osm_id)
);
COMMENT ON TABLE raw.lead_osm IS
  'OpenStreetMap ham kayitlari. ODbL -- saklanabilir. Etiketler oldugu gibi durur.';

-- ------------------------------------------------------------- calisma katmani
CREATE TABLE IF NOT EXISTS core.lead (
    lead_id       bigserial   PRIMARY KEY,
    kaynak        text        NOT NULL CHECK (kaynak IN ('osm', 'places', 'elle')),
    kaynak_kimlik text        NOT NULL,
    segment       text        NOT NULL,
    il            text        NOT NULL,
    ilce          text,
    ad            text        NOT NULL CHECK (length(btrim(ad)) > 1),
    telefon       text,
    site          text,
    adres         text,
    enlem         double precision,
    boylam        double precision,

    -- Temas edilebilirlik TUREV: telefonu olmayan kayit lead degildir.
    -- Sayiyi tek yerde tutmak, iki yerde saymaktan iyidir.
    temas_edilebilir boolean GENERATED ALWAYS AS (telefon IS NOT NULL) STORED,

    -- 6563 sayili Kanun / IYS. Gonderim yapan taraf ONAYLI olmayana gonderemez.
    iys_durumu    text        NOT NULL DEFAULT 'SORULMADI'
                  CHECK (iys_durumu IN ('SORULMADI', 'ONAYLI', 'RET')),
    iys_tarih     timestamptz,

    -- KVKK. Saklama suresi olmayan kayit yazilamaz.
    toplandi      timestamptz NOT NULL DEFAULT now(),
    saklama_sonu  date        NOT NULL,

    notlar        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (kaynak, kaynak_kimlik)
);
COMMENT ON COLUMN core.lead.saklama_sonu IS
  'KVKK saklama suresi sonu. Varsayilan 2 yil -- TICARI KARAR, hukuki gorus degil.';
COMMENT ON COLUMN core.lead.iys_durumu IS
  '6563/IYS. ONAYLI olmayan satira ticari elektronik ileti GONDERILEMEZ.';

CREATE INDEX IF NOT EXISTS lead_segment_idx     ON core.lead (il, segment);
CREATE INDEX IF NOT EXISTS lead_temas_idx       ON core.lead (temas_edilebilir)
       WHERE temas_edilebilir;
CREATE INDEX IF NOT EXISTS lead_saklama_idx     ON core.lead (saklama_sonu);

-- --------------------------------------------------------- suresi dolani temizle
CREATE OR REPLACE FUNCTION core.lead_saklama_temizligi() RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
DECLARE v_silinen integer;
BEGIN
  -- KVKK: suresi dolan kayit silinir. Ayrica Places kaynakli satirlar
  -- Google sartlari geregi daha kisa omurlu olabilir; suresi saklama_sonu
  -- ile yonetilir, kaynaga gore ayri deger yazilir.
  DELETE FROM core.lead WHERE saklama_sonu < current_date;
  GET DIAGNOSTICS v_silinen = ROW_COUNT;
  RETURN v_silinen;
END;
$fn$;

-- ------------------------------------------------------------------- gorunum
CREATE OR REPLACE VIEW mart.lead_ozet AS
SELECT il, segment, kaynak,
       count(*)                                        AS kayit,
       count(*) FILTER (WHERE temas_edilebilir)        AS telefonlu,
       count(*) FILTER (WHERE site IS NOT NULL)        AS siteli,
       count(*) FILTER (WHERE iys_durumu = 'ONAYLI')   AS iys_onayli,
       min(toplandi)                                   AS ilk_toplama,
       max(toplandi)                                   AS son_toplama
FROM core.lead
GROUP BY il, segment, kaynak;

-- --------------------------------------------------------------------- yetki
-- En az ayricalik: okuyucu okur, yazici yazar, ikisi de silemez.
GRANT USAGE ON SCHEMA raw, core, mart TO ai_reader, ai_writer;
GRANT SELECT ON raw.lead_osm, core.lead, mart.lead_ozet TO ai_reader;
GRANT SELECT, INSERT, UPDATE ON raw.lead_osm, core.lead  TO ai_writer;
GRANT USAGE, SELECT ON SEQUENCE core.lead_lead_id_seq    TO ai_writer;

COMMIT;
