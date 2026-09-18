#!/bin/sh
set -eu
exec docker run --rm --name lcarlie-measurement-generator-once --network lcarlie_dahili --env-file /opt/lcarlie/orchestrator/.env -e NODE_PATH=/usr/local/lib/node_modules/n8n/node_modules/.pnpm/pg@8.21.0_pg-native@3.8.0/node_modules --user 65534:65534 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --memory 96m --cpus .25 --pids-limit 32 -v /opt/lcarlie/orchestrator:/app:ro --entrypoint node n8nio/n8n:2.38.7 /app/measurement-generator.js
