-- One durable database for the existing company action contract and personal
-- Google actions. This table replaces mobile/google/actions.json; the older
-- core.ai_action_proposal pipeline stays in PostgreSQL and is not rewritten.
BEGIN;

CREATE TABLE IF NOT EXISTS core.jarvis_personal_action (
    action_id text PRIMARY KEY,
    owner text NOT NULL,
    source_conversation text,
    kind text NOT NULL CHECK (kind IN ('calendar.create','gmail.send','drive.upload')),
    payload jsonb NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    description text NOT NULL,
    risk_level text NOT NULL CHECK (risk_level IN ('MEDIUM','HIGH')),
    idempotency_key text NOT NULL,
    status text NOT NULL CHECK (status IN
        ('AWAITING_APPROVAL','RUNNING','COMPLETED','FAILED','DENIED','EXPIRED','UNCERTAIN')),
    approved_by text,
    external_id text,
    message text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    finished_at timestamptz,
    UNIQUE (owner,idempotency_key)
);

CREATE INDEX IF NOT EXISTS jarvis_personal_action_owner_recent
    ON core.jarvis_personal_action(owner,created_at DESC);

CREATE TABLE IF NOT EXISTS core.jarvis_personal_action_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id text NOT NULL REFERENCES core.jarvis_personal_action(action_id),
    from_status text,
    to_status text NOT NULL,
    actor text NOT NULL,
    note text NOT NULL DEFAULT '',
    at timestamptz NOT NULL DEFAULT clock_timestamp()
);

GRANT SELECT,INSERT,UPDATE ON core.jarvis_personal_action TO jarvis_web;
GRANT SELECT,INSERT ON core.jarvis_personal_action_event TO jarvis_web;
GRANT USAGE ON SEQUENCE core.jarvis_personal_action_event_event_id_seq TO jarvis_web;

COMMIT;
