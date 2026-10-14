\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE human_approver;
SELECT core.ai_enqueue_task(
  'MANUAL', NULL, 'PROPOSE_ACTION', 'phase2b:duplicate-proposal-test',
  'default', 100, clock_timestamp(), true, 'phase2b rollback test', NULL
) AS task_id \gset
RESET ROLE;
SET LOCAL ROLE ai_writer;
SELECT task_id, lease_token::text AS lease_token
  FROM core.ai_claim_task('phase2b-duplicate-test', 60)
 WHERE task_id = :task_id \gset
SELECT core.ai_propose_action(
  :task_id, :'lease_token'::uuid, 'action:phase2b-duplicate-test',
  'REQUEST_HUMAN_REVIEW', '{"reason":"rollback-only test"}'::jsonb
) AS first_action_id;
\set ON_ERROR_STOP off
SELECT core.ai_propose_action(
  :task_id, :'lease_token'::uuid, 'action:phase2b-duplicate-test',
  'REQUEST_HUMAN_REVIEW', '{"reason":"replay"}'::jsonb
) AS replay_action_id;
\set ON_ERROR_STOP on
ROLLBACK;
