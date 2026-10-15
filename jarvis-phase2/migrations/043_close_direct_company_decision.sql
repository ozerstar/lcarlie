-- Human approvals must pass the displayed-payload fingerprint check.
-- The compatibility function remains callable only inside the SECURITY DEFINER
-- wrapper, whose owner performs the original company approval policy.
BEGIN;

REVOKE EXECUTE ON FUNCTION core.ai_decide_action(bigint,text,text)
    FROM human_approver;

DO $$
BEGIN
    IF has_function_privilege('human_approver',
            'core.ai_decide_action(bigint,text,text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'legacy company decision is still callable directly';
    END IF;
    IF NOT has_function_privilege('human_approver',
            'core.jarvis_decide_company_action(bigint,text,text,text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'fingerprint-bound company decision is unavailable';
    END IF;
END $$;

COMMIT;
