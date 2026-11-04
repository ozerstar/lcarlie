import os
import sys

sys.path.insert(0, '/opt/lcarlie/jarvis-phase2/webconsole')
sys.path.insert(0, '/opt/lcarlie/jarvis-phase2')
os.environ.update({
    'JARVIS_MEMORY_TRANSPORT': 'direct-pg',
    'JARVIS_DB_PASSWORD_FILE': '/etc/lcarlie/jarvis-web-db.pass',
    'JARVIS_DB_HOST': '127.0.0.1',
    'JARVIS_DB_PORT': '5433',
    'JARVIS_STATE_DIR': '/opt/lcarlie/jarvis-phase2/state',
    'JARVIS_WEB_STATE_DIR': '/opt/lcarlie/jarvis-phase2/state/webconsole',
})

import app

checks = [
    ('company', lambda: app._memory.get_capability_state().records),
    ('approvals', lambda: app._operator.list_pending()),
    ('sales', app._satis_merkezi),
    ('catalog', app.katalog.katalog),
    ('field', app.saha.filtre_secenekleri),
    ('inbox', app.gelen_kutusu.ozet),
    ('generated', app.uretilenler.uretilenler),
]
for name, fn in checks:
    try:
        result = fn()
        if isinstance(result, dict) and ('hata' in result or 'error' in result):
            raise RuntimeError(str(result)[:200])
        print(name + ': ok')
    except Exception as exc:
        print(name + ': ERROR ' + str(exc)[:220])
        raise
