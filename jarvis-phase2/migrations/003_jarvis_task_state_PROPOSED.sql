BEGIN;

CREATE TABLE core.jarvis_task_state (
  task_id bigint PRIMARY KEY REFERENCES core.ai_task(task_id) ON DELETE CASCADE,
  state_json jsonb NOT NULL,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (jsonb_typeof(state_json) = 'object')
);

REVOKE ALL ON core.jarvis_task_state FROM PUBLIC;

CREATE OR REPLACE FUNCTION core.ai_save_jarvis_task_state(
  p_task_id bigint,
  p_expected_version bigint,
  p_state jsonb
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $$
DECLARE
  v_version bigint;
BEGIN
  IF p_task_id IS NULL OR p_expected_version IS NULL OR p_expected_version < 0 THEN
    RAISE EXCEPTION 'invalid task state request';
  END IF;
  IF p_state IS NULL OR jsonb_typeof(p_state) <> 'object' THEN
    RAISE EXCEPTION 'state must be a JSON object';
  END IF;
  IF core.ai_jsonb_has_forbidden_key(p_state) THEN
    RAISE EXCEPTION 'forbidden state payload';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM core.ai_task WHERE task_id = p_task_id) THEN
    RAISE EXCEPTION 'unknown task';
  END IF;

  IF p_expected_version = 0 THEN
    INSERT INTO core.jarvis_task_state(task_id, state_json)
    VALUES (p_task_id, p_state)
    ON CONFLICT (task_id) DO NOTHING
    RETURNING version INTO v_version;
  ELSE
    UPDATE core.jarvis_task_state
       SET state_json = p_state,
           version = version + 1,
           updated_at = clock_timestamp()
     WHERE task_id = p_task_id
       AND version = p_expected_version
    RETURNING version INTO v_version;
  END IF;

  IF v_version IS NULL THEN
    RAISE EXCEPTION 'task state version conflict';
  END IF;
  RETURN v_version;
END;
$$;

CREATE OR REPLACE FUNCTION core.ai_load_jarvis_task_state(p_task_id bigint)
RETURNS TABLE(task_id bigint, state_json jsonb, version bigint, updated_at timestamptz)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = core, pg_temp
AS $$
  SELECT s.task_id, s.state_json, s.version, s.updated_at
    FROM core.jarvis_task_state s
   WHERE s.task_id = p_task_id;
$$;

REVOKE ALL ON FUNCTION core.ai_save_jarvis_task_state(bigint, bigint, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.ai_load_jarvis_task_state(bigint) FROM PUBLIC;
ALTER TABLE core.jarvis_task_state OWNER TO function_owner;
ALTER FUNCTION core.ai_save_jarvis_task_state(bigint, bigint, jsonb) OWNER TO function_owner;
ALTER FUNCTION core.ai_load_jarvis_task_state(bigint) OWNER TO function_owner;
GRANT EXECUTE ON FUNCTION core.ai_save_jarvis_task_state(bigint, bigint, jsonb) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_load_jarvis_task_state(bigint) TO ai_writer, ai_reader;

COMMIT;
