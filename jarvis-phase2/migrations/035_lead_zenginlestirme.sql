-- =============================================================================
-- 035 · LEAD ZENGINLESTIRME: cografi sinyaller
--
-- OLCULEN KISIT -- bu migration'in bicimini belirleyen sey
-- 1.752 Ankara eczanesinin YALNIZ 3'UNDE web sitesi var. "LLM siteyi okusun,
-- profil cikarsin" plani eczanelerde CALISMAZ: okunacak bir sey yok.
-- Ama koordinat 1.752'sinde de var. O yuzden zenginlestirme web degil
-- COGRAFI olacak.
--
-- SIFIR DIS CAGRI. Asagidaki sinyallerin hepsi zaten core.lead'de duran
-- koordinatlardan hesaplaniyor. Ne Places ne Nominatim gerekiyor.
--
-- NEDEN BU SINYALLER SATISLA ILGILI
--   yakin_saglik_500m   Hastane/klinik yanindaki eczanenin resete ve
--                       dermokozmetige talebi farklidir. 500 m yuruyus
--                       mesafesidir.
--   yakin_rakip_200m    Yan yana iki eczane ayni musteriyi paylasir; teklif
--                       goturulecek sirayi etkiler.
--   yakin_guzellik_1km  Guzellik merkezi yogunlugu, bolgenin bakim urunu
--                       talebinin vekil gostergesidir.
--
-- 🔴 BUNLAR VEKIL GOSTERGEDIR, KANIT DEGILDIR. "Hastane yanindaki eczane daha
--    cok satar" OLCULMEDI. Sinyal siralama icindir; satis kaniti gelince
--    (ilk siparisler) bu varsayim SINANMALI ve yanlissa atilmalidir.
--
-- GERI ALMA: rollback/035_lead_zenginlestirme_ROLLBACK.sql
-- =============================================================================

BEGIN;

ALTER TABLE core.lead
    ADD COLUMN IF NOT EXISTS yakin_saglik_500m  integer,
    ADD COLUMN IF NOT EXISTS yakin_rakip_200m   integer,
    ADD COLUMN IF NOT EXISTS yakin_guzellik_1km integer,
    ADD COLUMN IF NOT EXISTS zenginlestirildi   timestamptz;

COMMENT ON COLUMN core.lead.yakin_saglik_500m IS
  'VEKIL GOSTERGE: 500 m icindeki klinik/muayenehane/tip merkezi sayisi. Satis kaniti DEGIL.';

-- Derece cinsinden mesafe yerine gercek metre: Ankara enleminde (~39.9)
-- 1 derece boylam ~ 85,4 km, 1 derece enlem ~ 111,3 km. Kucuk mesafelerde
-- duzlem yaklasimi yeterli ve PostGIS gerektirmez.
CREATE OR REPLACE FUNCTION core.lead_mesafe_m(
    a_enlem double precision, a_boylam double precision,
    b_enlem double precision, b_boylam double precision
) RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $fn$
  SELECT sqrt(
      pow((a_enlem - b_enlem) * 111320.0, 2) +
      pow((a_boylam - b_boylam) * 111320.0 * cos(radians((a_enlem + b_enlem) / 2)), 2)
  );
$fn$;

CREATE OR REPLACE FUNCTION core.lead_zenginlestir(p_il text DEFAULT 'Ankara')
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
DECLARE v_sayi integer;
BEGIN
  WITH saglik AS (
      SELECT enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL
        AND segment IN ('klinik', 'muayenehane', 'tip merkezi')
  ), rakip AS (
      SELECT lead_id, enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL AND segment = 'eczane'
  ), guzellik AS (
      SELECT enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL
        AND segment IN ('guzellik merkezi', 'spa masaj')
  ), hesap AS (
      SELECT l.lead_id,
             (SELECT count(*) FROM saglik s
               WHERE core.lead_mesafe_m(l.enlem, l.boylam, s.enlem, s.boylam) <= 500)   AS s500,
             (SELECT count(*) FROM rakip r
               WHERE r.lead_id <> l.lead_id
                 AND core.lead_mesafe_m(l.enlem, l.boylam, r.enlem, r.boylam) <= 200)   AS r200,
             (SELECT count(*) FROM guzellik g
               WHERE core.lead_mesafe_m(l.enlem, l.boylam, g.enlem, g.boylam) <= 1000)  AS g1k
      FROM core.lead l
      WHERE l.il = p_il AND l.enlem IS NOT NULL
  )
  UPDATE core.lead l
     SET yakin_saglik_500m  = h.s500,
         yakin_rakip_200m   = h.r200,
         yakin_guzellik_1km = h.g1k,
         zenginlestirildi   = now()
    FROM hesap h
   WHERE l.lead_id = h.lead_id;
  GET DIAGNOSTICS v_sayi = ROW_COUNT;
  RETURN v_sayi;
END;
$fn$;

DROP VIEW IF EXISTS mart.lead_ozet;
CREATE VIEW mart.lead_ozet AS
SELECT il, segment, kaynak,
       count(*)                                      AS kayit,
       count(*) FILTER (WHERE temas_edilebilir)      AS telefonlu,
       count(*) FILTER (WHERE site IS NOT NULL)      AS siteli,
       count(*) FILTER (WHERE ilce IS NOT NULL)      AS ilceli,
       count(*) FILTER (WHERE iys_durumu = 'ONAYLI') AS iys_onayli,
       round(avg(yakin_saglik_500m), 2)              AS ort_yakin_saglik,
       max(zenginlestirildi)                         AS son_zenginlestirme
FROM core.lead
GROUP BY il, segment, kaynak;

GRANT SELECT ON mart.lead_ozet TO ai_reader;

COMMIT;
