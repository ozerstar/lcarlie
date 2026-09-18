-- PHASE 2D / F-1 rollback: revoke the canonical action contract read grant.
-- After this, Jarvis loads no contract, the drift check reports
-- contract_valid=false, and every proposal path fails closed.

BEGIN;

REVOKE SELECT (
    action_type,
    risk_class,
    approval_mode,
    proposal_enabled,
    execution_enabled,
    schema_version
) ON core.ai_action_type FROM ai_reader;

COMMIT;
