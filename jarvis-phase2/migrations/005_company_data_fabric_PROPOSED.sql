-- COMPANY DATA FABRIC -- advertising, e-commerce and customer views become
-- readable by Jarvis.
--
-- WHY THIS IS NEEDED
-- The execution planner already models five business domains. Three of them
-- (sales, ecommerce, advertising) planned every request as DATA_UNAVAILABLE,
-- and the recorded reason was accurate: the underlying views exist and hold
-- real rows, but ai_reader could not read them and no CompanyMemory query
-- exposed them.
--
-- Sales needed NO grant: mart.siparis and mart.siparis_kalem were already
-- granted and only lacked a query. This migration covers the nine views that
-- were genuinely unreachable.
--
-- WHY THESE NINE AND NOTHING ELSE
--   advertising  mart.reklam_performans  ad/adset/campaign performance
--                mart.harcama            daily spend per campaign
--   ecommerce    mart.urun_karlilik      product profitability
--                mart.fiyat_gercegi      catalog price reality
--                mart.funnel_orani       funnel step ratios
--   crm          mart.musteri            customer order/revenue rollup
--
-- MEASURED AND EXCLUDED
-- mart.urun_sinyal, mart.meta_sinyal and mart.roas_kapisi were granted during
-- development and then revoked: they are not security-barrier views, so each
-- one resolves further mart views (maliyet_kalite, meta_kapsama,
-- ekonomi_gunluk, siparis_ekonomi) with the caller's own privileges. Reading
-- them would mean granting a dependency chain of unknown depth, so they stay
-- unreadable and no query references them.
-- mart.ai_operations_dashboard is excluded for a harder reason: it resolves
-- core.ai_provider_allowed, which ai_reader must never reach.
--
-- WHY TABLE-LEVEL ON VIEWS AND NOT COLUMN-LEVEL
-- Unlike migration 004, every object here is a derived mart VIEW, not a base
-- table. A view is read through its owner's privileges, so the grant exposes
-- exactly the projection its author already chose -- that is the controlled
-- surface. Column-level grants would add maintenance cost without narrowing
-- anything real.
--
-- PII
-- Deliberately NOT granted: lcarlie.konusma and lcarlie.mesaj carry customer
-- names and raw message text. mart.musteri carries customer_id only -- no
-- name, phone or address -- and mart.konusma_cevapsiz (already granted) uses
-- a pseudonymous musteri_takma. Customer-side analysis therefore runs on
-- identifiers and aggregates, never on raw personal data.
--
-- SECURITY IMPACT: read-only visibility of already-derived business
-- aggregates. No write, no EXECUTE, no role change, no new authorization
-- path. ai_writer is NOT granted anything: it proposes through
-- core.ai_propose_action, which is unchanged. Human approval, the Action
-- Firewall and EXTERNAL_ACTIONS are untouched.
--
-- Reversible with nine REVOKEs (see rollback/005).

BEGIN;

GRANT SELECT ON mart.reklam_performans TO ai_reader;
GRANT SELECT ON mart.harcama           TO ai_reader;

GRANT SELECT ON mart.urun_karlilik     TO ai_reader;
GRANT SELECT ON mart.fiyat_gercegi     TO ai_reader;
GRANT SELECT ON mart.funnel_orani      TO ai_reader;

GRANT SELECT ON mart.musteri           TO ai_reader;

COMMIT;

-- Verification (each must succeed as ai_reader):
--   SET SESSION AUTHORIZATION ai_reader;
--   SELECT count(*) FROM mart.reklam_performans;
--   SELECT count(*) FROM mart.harcama;
--   SELECT count(*) FROM mart.urun_karlilik;
--   SELECT count(*) FROM mart.fiyat_gercegi;
--   SELECT count(*) FROM mart.funnel_orani;
--   SELECT count(*) FROM mart.musteri;
--   RESET SESSION AUTHORIZATION;
