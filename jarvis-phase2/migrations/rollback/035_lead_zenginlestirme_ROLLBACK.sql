BEGIN;
DROP VIEW IF EXISTS mart.lead_ozet;
DROP FUNCTION IF EXISTS core.lead_zenginlestir(text);
DROP FUNCTION IF EXISTS core.lead_mesafe_m(double precision,double precision,double precision,double precision);
ALTER TABLE core.lead
  DROP COLUMN IF EXISTS yakin_saglik_500m,
  DROP COLUMN IF EXISTS yakin_rakip_200m,
  DROP COLUMN IF EXISTS yakin_guzellik_1km,
  DROP COLUMN IF EXISTS zenginlestirildi;
COMMIT;
