BEGIN;
DROP FUNCTION IF EXISTS core.ai_load_jarvis_task_state(bigint);
DROP FUNCTION IF EXISTS core.ai_save_jarvis_task_state(bigint, bigint, jsonb);
DROP TABLE IF EXISTS core.jarvis_task_state;
COMMIT;
