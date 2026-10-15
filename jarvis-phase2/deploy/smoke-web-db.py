"""Read-only direct-DB smoke check under the web service account."""
import os
from jarvis.db_transport import run

os.environ['JARVIS_MEMORY_TRANSPORT'] = 'direct-pg'
os.environ['JARVIS_DB_PASSWORD_FILE'] = '/etc/lcarlie/jarvis-web-db.pass'
os.environ['JARVIS_DB_HOST'] = os.environ.get('JARVIS_DB_HOST', '172.19.0.4')

base = ['docker', 'exec', 'lcarlie-postgres', 'psql', '-X', '-q', '-U', 'n8n', '-d', 'n8n', '-Atc']
checks = [
    'BEGIN; SET SESSION AUTHORIZATION ai_reader; SELECT row_to_json(x) FROM (SELECT 1 AS ok) x; ROLLBACK;',
    'BEGIN; SET SESSION AUTHORIZATION human_approver; SELECT row_to_json(x) FROM (SELECT count(*) AS pending FROM core.ai_get_pending_actions()) x; ROLLBACK;',
    'SELECT row_to_json(x) FROM (SELECT count(*) AS n FROM mart.bayi_fiyat_gecerli) x;',
    'SELECT row_to_json(x) FROM (SELECT count(*) AS n FROM lcarlie.konusma) x;',
]
for statement in checks:
    result = run(base + [statement], text=True, capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise SystemExit('DB smoke failed: ' + result.stderr[:220])
print('web database read checks passed')
