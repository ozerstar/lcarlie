-- Shared, append-only action history for company proposals and personal
-- Google actions. Existing source tables remain the execution contracts.
BEGIN;

CREATE TABLE IF NOT EXISTS core.jarvis_action_registry (
    action_key text PRIMARY KEY,
    source text NOT NULL CHECK (source IN ('company','personal')),
    source_id text NOT NULL,
    owner text NOT NULL,
    kind text NOT NULL,
    description text NOT NULL,
    risk_level text NOT NULL,
    payload_hash text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    expires_at timestamptz,
    UNIQUE (source,source_id)
);

CREATE INDEX IF NOT EXISTS jarvis_action_registry_owner_status
    ON core.jarvis_action_registry(owner,status,created_at DESC);

CREATE TABLE IF NOT EXISTS core.jarvis_action_registry_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_key text NOT NULL REFERENCES core.jarvis_action_registry(action_key),
    event_type text NOT NULL,
    from_status text,
    to_status text NOT NULL,
    actor text NOT NULL,
    note text NOT NULL DEFAULT '',
    at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION core.jarvis_company_status(p_state text)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,core AS $$
    SELECT CASE p_state
        WHEN 'PROPOSED' THEN 'AWAITING_APPROVAL'
        WHEN 'APPROVED' THEN 'APPROVED'
        WHEN 'REJECTED' THEN 'DENIED'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        WHEN 'EXECUTING' THEN 'RUNNING'
        WHEN 'EXECUTED' THEN 'COMPLETED'
        WHEN 'EXECUTION_FAILED' THEN 'FAILED'
        ELSE 'UNCERTAIN' END
$$;

CREATE OR REPLACE FUNCTION core.jarvis_sync_company_action()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,core,pg_temp AS $$
DECLARE v_before text; v_after text;
BEGIN
    v_after := core.jarvis_company_status(NEW.state);
    SELECT status INTO v_before FROM core.jarvis_action_registry
        WHERE action_key='company:' || NEW.action_id FOR UPDATE;
    INSERT INTO core.jarvis_action_registry
        (action_key,source,source_id,owner,kind,description,risk_level,
         payload_hash,status,created_at,updated_at,expires_at)
    VALUES ('company:' || NEW.action_id,'company',NEW.action_id::text,'company',
            NEW.action_type,left(coalesce(NEW.payload->>'reason',NEW.action_type),2000),
            NEW.risk_class,NEW.payload_hash,v_after,NEW.proposed_at,
            coalesce(NEW.decided_at,NEW.proposed_at),NEW.expires_at)
    ON CONFLICT(action_key) DO UPDATE SET
        kind=EXCLUDED.kind,description=EXCLUDED.description,
        risk_level=EXCLUDED.risk_level,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=clock_timestamp(),
        expires_at=EXCLUDED.expires_at;
    IF v_before IS NULL OR v_before IS DISTINCT FROM v_after THEN
        INSERT INTO core.jarvis_action_registry_event
            (action_key,event_type,from_status,to_status,actor,note)
        VALUES ('company:' || NEW.action_id,'STATE',v_before,v_after,
                coalesce(NEW.decided_by,NEW.proposed_by),
                left(coalesce(NEW.decision_reason,''),300));
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION core.jarvis_sync_personal_action()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,core,pg_temp AS $$
DECLARE v_before text;
BEGIN
    SELECT status INTO v_before FROM core.jarvis_action_registry
        WHERE action_key='personal:' || NEW.action_id FOR UPDATE;
    INSERT INTO core.jarvis_action_registry
        (action_key,source,source_id,owner,kind,description,risk_level,
         payload_hash,status,created_at,updated_at,expires_at)
    VALUES ('personal:' || NEW.action_id,'personal',NEW.action_id,NEW.owner,
            NEW.kind,left(NEW.description,2000),NEW.risk_level,
            NEW.payload_hash,NEW.status,NEW.created_at,NEW.updated_at,NEW.expires_at)
    ON CONFLICT(action_key) DO UPDATE SET
        description=EXCLUDED.description,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=EXCLUDED.updated_at,
        expires_at=EXCLUDED.expires_at;
    IF v_before IS NULL OR v_before IS DISTINCT FROM NEW.status THEN
        INSERT INTO core.jarvis_action_registry_event
            (action_key,event_type,from_status,to_status,actor,note)
        VALUES ('personal:' || NEW.action_id,'STATE',v_before,NEW.status,
                coalesce(NEW.approved_by,NEW.owner),left(coalesce(NEW.message,''),300));
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION core.jarvis_record_company_vote()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,core,pg_temp AS $$
BEGIN
    INSERT INTO core.jarvis_action_registry_event
        (action_key,event_type,from_status,to_status,actor,note,at)
    VALUES ('company:' || NEW.action_id,'APPROVAL_VOTE',
            'AWAITING_APPROVAL','AWAITING_APPROVAL',NEW.approver_identity,
            left(NEW.decision || ': ' || NEW.reason,300),NEW.decided_at);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS jarvis_company_action_registry ON core.ai_action_proposal;
CREATE TRIGGER jarvis_company_action_registry
AFTER INSERT OR UPDATE ON core.ai_action_proposal
FOR EACH ROW EXECUTE FUNCTION core.jarvis_sync_company_action();

DROP TRIGGER IF EXISTS jarvis_personal_action_registry ON core.jarvis_personal_action;
CREATE TRIGGER jarvis_personal_action_registry
AFTER INSERT OR UPDATE ON core.jarvis_personal_action
FOR EACH ROW EXECUTE FUNCTION core.jarvis_sync_personal_action();

DROP TRIGGER IF EXISTS jarvis_company_vote_registry ON core.ai_action_approval;
CREATE TRIGGER jarvis_company_vote_registry
AFTER INSERT ON core.ai_action_approval
FOR EACH ROW EXECUTE FUNCTION core.jarvis_record_company_vote();

-- Backfill without rewriting decisions or causing execution.
INSERT INTO core.jarvis_action_registry
    (action_key,source,source_id,owner,kind,description,risk_level,
     payload_hash,status,created_at,updated_at,expires_at)
SELECT 'company:' || p.action_id,'company',p.action_id::text,'company',
       p.action_type,left(coalesce(p.payload->>'reason',p.action_type),2000),
       p.risk_class,p.payload_hash,core.jarvis_company_status(p.state),
       p.proposed_at,coalesce(p.decided_at,p.proposed_at),p.expires_at
FROM core.ai_action_proposal p
ON CONFLICT(action_key) DO NOTHING;

INSERT INTO core.jarvis_action_registry
    (action_key,source,source_id,owner,kind,description,risk_level,
     payload_hash,status,created_at,updated_at,expires_at)
SELECT 'personal:' || p.action_id,'personal',p.action_id,p.owner,
       p.kind,left(p.description,2000),p.risk_level,p.payload_hash,p.status,
       p.created_at,p.updated_at,p.expires_at
FROM core.jarvis_personal_action p
ON CONFLICT(action_key) DO NOTHING;

INSERT INTO core.jarvis_action_registry_event
    (action_key,event_type,from_status,to_status,actor,note,at)
SELECT r.action_key,'IMPORTED',NULL,r.status,'migration',
       'Existing action and decision retained',r.updated_at
FROM core.jarvis_action_registry r
WHERE NOT EXISTS (SELECT 1 FROM core.jarvis_action_registry_event e
                  WHERE e.action_key=r.action_key);

INSERT INTO core.jarvis_action_registry_event
    (action_key,event_type,from_status,to_status,actor,note,at)
SELECT 'company:' || a.action_id,'APPROVAL_VOTE',
       'AWAITING_APPROVAL','AWAITING_APPROVAL',a.approver_identity,
       left(a.decision || ': ' || a.reason,300),a.decided_at
FROM core.ai_action_approval a
WHERE NOT EXISTS (SELECT 1 FROM core.jarvis_action_registry_event e
                  WHERE e.action_key='company:' || a.action_id
                    AND e.event_type='APPROVAL_VOTE' AND e.actor=a.approver_identity
                    AND e.at=a.decided_at);

-- The web approval binds the exact proposal payload displayed to the user.
-- The existing company function keeps its one/two-person policy and execution gate.
CREATE OR REPLACE FUNCTION core.jarvis_decide_company_action(
    p_action_id bigint,p_decision text,p_reason text,p_expected_hash text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,core,pg_temp AS $$
DECLARE v_hash text;
BEGIN
    IF NOT pg_has_role(session_user,'human_approver','MEMBER') THEN
        RAISE EXCEPTION 'human approver membership required';
    END IF;
    IF p_expected_hash IS NULL OR p_expected_hash='' THEN
        RAISE EXCEPTION 'displayed action fingerprint required';
    END IF;
    SELECT payload_hash INTO v_hash FROM core.ai_action_proposal
        WHERE action_id=p_action_id AND state='PROPOSED' FOR UPDATE;
    IF NOT FOUND OR v_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'proposal changed or is no longer pending';
    END IF;
    PERFORM core.ai_decide_action(p_action_id,p_decision,p_reason);
END $$;

REVOKE ALL ON FUNCTION core.jarvis_decide_company_action(bigint,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.jarvis_decide_company_action(bigint,text,text,text)
    TO human_approver;
GRANT SELECT ON core.jarvis_action_registry TO jarvis_web,human_approver;
GRANT SELECT ON core.jarvis_action_registry_event TO jarvis_web,human_approver;

COMMIT;
