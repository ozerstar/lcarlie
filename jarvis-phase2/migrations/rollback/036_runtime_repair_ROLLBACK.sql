BEGIN;
CREATE OR REPLACE FUNCTION core.ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'core', 'pg_temp'
AS $function$
DECLARE
  v_task core.ai_task%ROWTYPE;
BEGIN
  IF p_result_class NOT IN ('FAILED_RETRYABLE','FAILED_FINAL','POLICY_BLOCKED','VALIDATION_FAILED') THEN
    RAISE EXCEPTION 'invalid failure class';
  END IF;

  SELECT * INTO v_task
  FROM core.ai_task
  WHERE task_id = p_task_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'task not found';
  END IF;
  IF v_task.lease_token IS DISTINCT FROM p_lease_token OR v_task.lease_until < clock_timestamp() THEN
    RAISE EXCEPTION 'invalid or expired lease';
  END IF;

  UPDATE core.ai_task
     SET state = CASE WHEN p_result_class = 'FAILED_RETRYABLE' THEN 'FAILED_RETRYABLE' ELSE 'FAILED_FINAL' END,
         last_error = left(COALESCE(p_fail_reason, p_result_class), 1000),
         lease_until = NULL
   WHERE task_id = p_task_id;
END;
$function$;
CREATE OR REPLACE FUNCTION core.ai_orchestrator_health()
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core'
AS $function$
SELECT jsonb_build_object(
  'ai_worker_enabled',(SELECT config_value::boolean FROM core.ai_orchestrator_config WHERE config_key='ai_worker_enabled'),
  'action_worker_enabled',(SELECT config_value::boolean FROM core.ai_orchestrator_config WHERE config_key='action_worker_enabled'),
  'open_tasks',(SELECT count(*) FROM core.ai_task WHERE state IN ('OPEN','FAILED_RETRYABLE')),
  'leased_tasks',(SELECT count(*) FROM core.ai_task WHERE state='LEASED'),
  'pending_actions',(SELECT count(*) FROM core.ai_action_proposal WHERE state='PROPOSED'),
  'approved_actions',(SELECT count(*) FROM core.ai_action_proposal WHERE state='APPROVED'),
  'open_executions',(SELECT count(*) FROM core.ai_action_execution WHERE state IN ('OPEN','FAILED_RETRYABLE')),
  'failed_executions',(SELECT count(*) FROM core.ai_action_execution WHERE state='FAILED_FINAL'),
  'checked_at',clock_timestamp()) $function$;
COMMIT;
-- Historical task state changes are documented in exhausted-tasks-before.json.
