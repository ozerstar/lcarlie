-- Cleanup for the development-time grants in 005.
--
-- urun_sinyal, meta_sinyal and roas_kapisi were granted, measured to be
-- unreadable anyway (they resolve further mart views with the caller's
-- privileges), and no CompanyMemory query references them. maliyet_kalite and
-- ekonomi_gunluk were granted only as their dependencies. Minimum privilege:
-- take all five back.

BEGIN;

REVOKE SELECT ON mart.urun_sinyal    FROM ai_reader;
REVOKE SELECT ON mart.meta_sinyal    FROM ai_reader;
REVOKE SELECT ON mart.roas_kapisi    FROM ai_reader;
REVOKE SELECT ON mart.maliyet_kalite FROM ai_reader;
REVOKE SELECT ON mart.ekonomi_gunluk FROM ai_reader;

COMMIT;
