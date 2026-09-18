-- PHASE 2D / F-1 -- canonical action contract becomes readable by Jarvis.
--
-- WHY THIS IS NEEDED
-- core.ai_action_type is the canonical allowlist of proposable action types.
-- It is owned by function_owner with owner-only ACL, and no function exposes
-- it: ai_propose_action, ai_decide_action and ai_claim_approved_action all
-- CONSUME it, none returns it. Jarvis therefore had no way to read the
-- contract and carried its own hardcoded Python allowlist instead -- which
-- drifted to zero overlap (Phase 2C finding F-1).
--
-- WHY A COLUMN-LEVEL GRANT AND NOT A NEW FUNCTION
-- This is the narrowest change that removes the second allowlist:
--   * read-only, one 6-row metadata table
--   * only the six columns the contract needs; description and created_at
--     stay unreadable, and any column added later is NOT auto-exposed
--   * no new executable code inside Core, nothing to own or maintain
--   * reversible with a single REVOKE (see rollback/004)
-- ai_writer is deliberately NOT granted: it proposes through
-- core.ai_propose_action, which validates against this table itself.
--
-- SECURITY IMPACT: none beyond read visibility of the action-type metadata.
-- No business data, no PII, no credential, no authorization change.
-- The Action Firewall remains core.ai_propose_action; this grant lets Jarvis
-- fail closed EARLY instead of only at the database.

BEGIN;

GRANT SELECT (
    action_type,
    risk_class,
    approval_mode,
    proposal_enabled,
    execution_enabled,
    schema_version
) ON core.ai_action_type TO ai_reader;

COMMIT;

-- Verification (expect the six canonical rows, and a failure on description):
--   SET SESSION AUTHORIZATION ai_reader;
--   SELECT action_type, risk_class, approval_mode, proposal_enabled,
--          execution_enabled, schema_version
--     FROM core.ai_action_type ORDER BY action_type;   -- must succeed
--   SELECT description FROM core.ai_action_type;        -- must be denied
--   RESET SESSION AUTHORIZATION;
