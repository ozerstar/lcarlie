#!/bin/sh
set -eu
export DOCKER_API_VERSION=1.43
violations=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "
WITH checks AS(
 SELECT 'function_owner_login' n,(SELECT rolcanlogin FROM pg_roles WHERE rolname='function_owner') bad
 UNION ALL SELECT 'ai_writer_login',(SELECT rolcanlogin FROM pg_roles WHERE rolname='ai_writer')
 UNION ALL SELECT 'human_approver_login',(SELECT rolcanlogin FROM pg_roles WHERE rolname='human_approver')
 UNION ALL SELECT 'action_executor_login',(SELECT rolcanlogin FROM pg_roles WHERE rolname='action_executor')
 UNION ALL SELECT 'ai_to_human',pg_has_role('ai_writer','human_approver','member')
 UNION ALL SELECT 'ai_to_executor',pg_has_role('ai_writer','action_executor','member')
 UNION ALL SELECT 'ai_to_owner',pg_has_role('ai_writer','function_owner','member')
 UNION ALL SELECT 'ai_karar_insert',has_table_privilege('ai_writer','core.karar','insert')
 UNION ALL SELECT 'ai_karar_update',has_table_privilege('ai_writer','core.karar','update')
 UNION ALL SELECT 'ai_redteam_insert',has_table_privilege('ai_writer','core.karar_red_team','insert')
 UNION ALL SELECT 'human_direct_update',has_table_privilege('human_approver','core.karar','update')
 UNION ALL SELECT 'executor_can_approve',has_function_privilege('action_executor','core.ai_decide_action(bigint,text,text)','execute')
 UNION ALL SELECT 'human_can_execute',has_function_privilege('human_approver','core.ai_claim_approved_action(text,integer)','execute')
)SELECT count(*) FROM checks WHERE bad;")
unsafe=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "select count(*) from core.ai_action_type where execution_enabled and action_type<>'REQUEST_HUMAN_REVIEW';")
stale=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "select (select count(*) from core.ai_red_team_job where state='LEASED' and lease_until<now())+(select count(*) from core.ai_action_execution where state='LEASED' and lease_until<now());")
secret_bad=0
for f in /opt/lcarlie/orchestrator/.env /opt/lcarlie/orchestrator/.action-env;do
 [ -f "$f" ]||{ secret_bad=$((secret_bad+1));continue;}
 [ "$(stat -c %a "$f")" = "600" ]||secret_bad=$((secret_bad+1))
 [ "$(stat -c %U "$f")" = "root" ]||secret_bad=$((secret_bad+1))
done
timer_bad=0
for u in lcarlie-ai-worker.timer lcarlie-red-team.timer lcarlie-red-team-health.timer lcarlie-action-worker.timer lcarlie-action-gateway-health.timer lcarlie-company-intelligence-generator.timer lcarlie-executive-brief.timer lcarlie-question-worker.timer lcarlie-measurement-generator.timer;do systemctl is-active --quiet "$u"||timer_bad=$((timer_bad+1));done
printf '{"component":"orchestrator-security-selftest","rbac_violations":%s,"unsafe_external_actions":%s,"stale_leases":%s,"secret_permission_violations":%s,"inactive_timers":%s}\n' "$violations" "$unsafe" "$stale" "$secret_bad" "$timer_bad"
[ "$violations" -eq 0 ]&&[ "$unsafe" -eq 0 ]&&[ "$stale" -eq 0 ]&&[ "$secret_bad" -eq 0 ]&&[ "$timer_bad" -eq 0 ]
