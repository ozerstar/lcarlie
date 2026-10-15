-- Make the shared action record complete enough to serve every approval UI.
-- Older tables stay as compatibility inputs for existing workers/functions.
BEGIN;

ALTER TABLE core.jarvis_action_registry
    ADD COLUMN IF NOT EXISTS payload jsonb,
    ADD COLUMN IF NOT EXISTS idempotency_key text,
    ADD COLUMN IF NOT EXISTS approved_by text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS message text,
    ADD COLUMN IF NOT EXISTS task_id bigint;

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
         payload_hash,status,created_at,updated_at,expires_at,payload,
         idempotency_key,approved_by,message,task_id)
    VALUES ('company:' || NEW.action_id,'company',NEW.action_id::text,'company',
            NEW.action_type,left(coalesce(NEW.payload->>'reason',NEW.action_type),2000),
            NEW.risk_class,NEW.payload_hash,v_after,NEW.proposed_at,
            coalesce(NEW.decided_at,NEW.proposed_at),NEW.expires_at,NEW.payload,
            NEW.idempotency_key,NEW.decided_by,NEW.decision_reason,NEW.task_id)
    ON CONFLICT(action_key) DO UPDATE SET
        kind=EXCLUDED.kind,description=EXCLUDED.description,
        risk_level=EXCLUDED.risk_level,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=clock_timestamp(),
        expires_at=EXCLUDED.expires_at,payload=EXCLUDED.payload,
        idempotency_key=EXCLUDED.idempotency_key,
        approved_by=EXCLUDED.approved_by,message=EXCLUDED.message,
        task_id=EXCLUDED.task_id;
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
         payload_hash,status,created_at,updated_at,expires_at,payload,
         idempotency_key,approved_by,external_id,message)
    VALUES ('personal:' || NEW.action_id,'personal',NEW.action_id,NEW.owner,
            NEW.kind,left(NEW.description,2000),NEW.risk_level,
            NEW.payload_hash,NEW.status,NEW.created_at,NEW.updated_at,NEW.expires_at,
            NEW.payload,NEW.idempotency_key,NEW.approved_by,NEW.external_id,NEW.message)
    ON CONFLICT(action_key) DO UPDATE SET
        description=EXCLUDED.description,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=EXCLUDED.updated_at,
        expires_at=EXCLUDED.expires_at,payload=EXCLUDED.payload,
        idempotency_key=EXCLUDED.idempotency_key,
        approved_by=EXCLUDED.approved_by,external_id=EXCLUDED.external_id,
        message=EXCLUDED.message;
    IF v_before IS NULL OR v_before IS DISTINCT FROM NEW.status THEN
        INSERT INTO core.jarvis_action_registry_event
            (action_key,event_type,from_status,to_status,actor,note)
        VALUES ('personal:' || NEW.action_id,'STATE',v_before,NEW.status,
                coalesce(NEW.approved_by,NEW.owner),left(coalesce(NEW.message,''),300));
    END IF;
    RETURN NEW;
END $$;

UPDATE core.jarvis_action_registry r SET
    payload=p.payload,idempotency_key=p.idempotency_key,
    approved_by=p.decided_by,message=p.decision_reason,task_id=p.task_id
FROM core.ai_action_proposal p
WHERE r.action_key='company:' || p.action_id;

UPDATE core.jarvis_action_registry r SET
    payload=p.payload,idempotency_key=p.idempotency_key,
    approved_by=p.approved_by,external_id=p.external_id,message=p.message
FROM core.jarvis_personal_action p
WHERE r.action_key='personal:' || p.action_id;

ALTER TABLE core.jarvis_action_registry
    ALTER COLUMN payload SET NOT NULL,
    ALTER COLUMN idempotency_key SET NOT NULL;

COMMIT;
