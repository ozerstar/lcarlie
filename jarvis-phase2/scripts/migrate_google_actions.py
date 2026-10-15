"""One-time actions.json -> PostgreSQL migration, with fail-closed verification.

Stop jarvis-web.service first, run as jarvis-web, then restart the service.
The old JSON file is archived only after every action ID exists in PostgreSQL.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'webconsole'))
import personal_action_store as store  # noqa: E402


def main() -> None:
    state = Path(os.environ.get('JARVIS_STATE_DIR', '/opt/lcarlie/jarvis-phase2/state'))
    path = state / 'mobile' / 'google' / 'actions.json'
    if not path.exists():
        print('No legacy action file; nothing to migrate')
        return
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise SystemExit('Legacy action file must contain a list')
    identifiers = [str(row.get('id') or '') for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise SystemExit('Duplicate legacy IDs; migration stopped')
    inserted = store.import_legacy(rows)
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT action_id FROM core.jarvis_personal_action
            WHERE action_id=ANY(%s)''', (identifiers,))
        found = {row['action_id'] for row in cur.fetchall()}
    if found != set(identifiers):
        raise SystemExit('Action count mismatch; original JSON retained')
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archived = path.with_name('actions.json.migrated-' + suffix)
    os.replace(path, archived)
    os.chmod(archived, 0o600)
    print(f'Migrated {len(rows)} actions ({inserted} new); legacy file archived')


if __name__ == '__main__':
    main()
