#!/bin/sh
set -eu
exec docker exec lcarlie-postgres psql -v ON_ERROR_STOP=1 -U n8n -d n8n -Atc 'SELECT * FROM core.ai_process_evidence_followups();'
