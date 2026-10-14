#!/bin/sh
set -eu
unsafe=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "select count(*) from core.ai_action_type where execution_enabled and action_type<>'REQUEST_HUMAN_REVIEW';")
stale=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "select count(*) from core.ai_action_execution where state='LEASED' and lease_until<now();")
separation=$(docker exec lcarlie-postgres psql -U n8n -d n8n -Atqc "select (has_function_privilege('human_approver','core.ai_claim_approved_action(text,integer)','execute') or has_function_privilege('action_executor','core.ai_decide_action(bigint,text,text)','execute') or has_function_privilege('ai_writer','core.ai_decide_action(bigint,text,text)','execute'))::int;")
printf '{"component":"action-gateway","unsafe_external_types":%s,"stale_leases":%s,"separation_violation":%s}\n' "$unsafe" "$stale" "$separation"
[ "$unsafe" -eq 0 ] && [ "$stale" -eq 0 ] && [ "$separation" -eq 0 ]
