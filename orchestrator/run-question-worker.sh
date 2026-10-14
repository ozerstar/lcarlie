#!/bin/sh
set -eu
exec docker run --rm --name lcarlie-question-worker-once --network lcarlie_ai_egress --env-file /opt/lcarlie/orchestrator/.env -e NODE_PATH=/usr/local/lib/node_modules/n8n/node_modules/.pnpm/pg@8.21.0_pg-native@3.8.0/node_modules --user 65534:65534 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --memory 160m --cpus .5 --pids-limit 48 -v /opt/lcarlie/orchestrator:/app:ro --entrypoint node n8nio/n8n:2.38.7 /app/question-worker.js
