#!/bin/sh
set -eu
row=$(docker exec lcarlie-postgres psql -U n8n -d n8n -AtF '|' -c "select count(*) filter(where state='OPEN'),count(*) filter(where state='RETRY'),count(*) filter(where state='FAILED'),count(*) filter(where state='LEASED' and lease_until<now()),coalesce(extract(epoch from(now()-max(created_at)))::int,0) from core.ai_red_team_job;")
IFS='|' read -r open retry failed stale oldest <<EOF
$row
EOF
attempts=$(docker exec lcarlie-postgres psql -U n8n -d n8n -AtF '|' -c "select count(*),count(*) filter(where result_class='ERROR'),count(*) filter(where result_class='POLICY_BLOCKED') from core.ai_red_team_attempt where created_at>=now()-interval '24 hours';")
IFS='|' read -r total errors blocked <<EOF
$attempts
EOF
printf '{"component":"ai-red-team","open":%s,"retry":%s,"failed":%s,"stale_leases":%s,"oldest_age_seconds":%s,"attempts_24h":%s,"errors_24h":%s,"policy_blocked_24h":%s}\n' "$open" "$retry" "$failed" "$stale" "$oldest" "$total" "$errors" "$blocked"
[ "$failed" -eq 0 ] && [ "$stale" -eq 0 ]
