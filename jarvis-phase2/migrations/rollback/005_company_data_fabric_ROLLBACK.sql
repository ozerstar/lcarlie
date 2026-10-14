-- ROLLBACK for 005_company_data_fabric_PROPOSED.sql
--
-- Restores ai_reader to its pre-fabric read surface. After this runs, the
-- sales queries still work (those grants predate this migration), while the
-- ecommerce, advertising and crm_customers queries raise 42501 and the
-- planner correctly returns those domains to DATA_UNAVAILABLE.
--
-- The five development-time grants that were revoked during the migration
-- itself (urun_sinyal, meta_sinyal, roas_kapisi, maliyet_kalite,
-- ekonomi_gunluk) are included defensively: revoking a privilege that is not
-- held is a no-op, and this makes the rollback safe to run against a database
-- that was left in the intermediate state.

BEGIN;

REVOKE SELECT ON mart.reklam_performans FROM ai_reader;
REVOKE SELECT ON mart.harcama           FROM ai_reader;

REVOKE SELECT ON mart.urun_karlilik     FROM ai_reader;
REVOKE SELECT ON mart.fiyat_gercegi     FROM ai_reader;
REVOKE SELECT ON mart.funnel_orani      FROM ai_reader;

REVOKE SELECT ON mart.musteri           FROM ai_reader;

REVOKE SELECT ON mart.urun_sinyal       FROM ai_reader;
REVOKE SELECT ON mart.meta_sinyal       FROM ai_reader;
REVOKE SELECT ON mart.roas_kapisi       FROM ai_reader;
REVOKE SELECT ON mart.maliyet_kalite    FROM ai_reader;
REVOKE SELECT ON mart.ekonomi_gunluk    FROM ai_reader;

COMMIT;
