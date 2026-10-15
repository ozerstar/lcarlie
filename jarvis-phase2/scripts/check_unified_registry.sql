-- Read-only reconciliation. Any mismatch makes psql exit nonzero.
DO $$
DECLARE
    mismatches integer;
BEGIN
    SELECT count(*) INTO mismatches FROM (
        SELECT p.action_id::text AS id FROM core.ai_action_proposal p
        LEFT JOIN core.jarvis_action_registry r
            ON r.action_key = 'company:' || p.action_id
        WHERE r.action_key IS NULL OR r.source IS DISTINCT FROM 'company'
           OR r.source_id IS DISTINCT FROM p.action_id::text
           OR r.kind IS DISTINCT FROM p.action_type
           OR r.risk_level IS DISTINCT FROM p.risk_class
           OR r.payload IS DISTINCT FROM p.payload
           OR r.payload_hash IS DISTINCT FROM p.payload_hash
           OR r.idempotency_key IS DISTINCT FROM p.idempotency_key
           OR r.status IS DISTINCT FROM core.jarvis_company_status(p.state)
        UNION ALL
        SELECT p.action_id FROM core.jarvis_personal_action p
        LEFT JOIN core.jarvis_action_registry r
            ON r.action_key = 'personal:' || p.action_id
        WHERE r.action_key IS NULL OR r.source IS DISTINCT FROM 'personal'
           OR r.source_id IS DISTINCT FROM p.action_id
           OR r.owner IS DISTINCT FROM p.owner
           OR r.kind IS DISTINCT FROM p.kind
           OR r.risk_level IS DISTINCT FROM p.risk_level
           OR r.payload IS DISTINCT FROM p.payload
           OR r.payload_hash IS DISTINCT FROM p.payload_hash
           OR r.idempotency_key IS DISTINCT FROM p.idempotency_key
           OR r.status IS DISTINCT FROM p.status
        UNION ALL
        SELECT r.action_key FROM core.jarvis_action_registry r
        WHERE (r.source = 'company' AND NOT EXISTS
               (SELECT 1 FROM core.ai_action_proposal p
                WHERE r.action_key = 'company:' || p.action_id))
           OR (r.source = 'personal' AND NOT EXISTS
               (SELECT 1 FROM core.jarvis_personal_action p
                WHERE r.action_key = 'personal:' || p.action_id))
    ) differences;
    IF mismatches <> 0 THEN
        RAISE EXCEPTION 'Unified action registry has % mismatched rows', mismatches;
    END IF;
    RAISE NOTICE 'Unified action registry matches both sources';
END $$;
