#!/bin/sh
set -eu
# 03.11.2026: a run killed between create and start left the container in
# "Created" state; --rm never fired and every later run hit a name conflict
# (240 failures in 48h). Clear any leftover before starting.
docker rm -f lcarlie-ai-health-once >/dev/null 2>&1 || true
exec docker run --rm \
  --name lcarlie-ai-health-once \
  --network lcarlie_dahili \
  --env-file /opt/lcarlie/orchestrator/.env \
  -e NODE_PATH=/usr/local/lib/node_modules/n8n/node_modules/.pnpm/pg@8.21.0_pg-native@3.8.0/node_modules \
  --user 65534:65534 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=8m \
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 96m --cpus 0.20 --pids-limit 32 \
  -v /opt/lcarlie/orchestrator:/app:ro \
  --entrypoint node n8nio/n8n:2.38.7 /app/healthcheck.js
