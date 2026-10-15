"""Live PostgreSQL state-machine check; no Google request is made.

Run on the server as root after migration. Synthetic rows are removed even if
an assertion fails. The test needs Docker only for its cleanup step; the web
service itself never touches Docker.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'webconsole'))
import personal_action_store as actions  # noqa: E402


def main() -> None:
    owner = 'test_action_' + uuid.uuid4().hex[:16]
    payload = {'summary': 'synthetic no-send test', 'start': {'dateTime': '2030-01-01T09:00:00+03:00'}}
    try:
        first = actions.create(owner, 'calendar.create', payload, 'Synthetic calendar test',
                               idempotency_key='test:' + uuid.uuid4().hex)
        same = actions.create(owner, 'calendar.create', payload, 'Synthetic calendar test',
                              idempotency_key='test:' + uuid.uuid4().hex)
        assert same['id'] == first['id'], 'duplicate payload created a second action'
        try:
            actions.decide(owner, first['id'], 'APPROVED', 'wrong')
        except actions.ActionConflict:
            pass
        else:
            raise AssertionError('stale fingerprint accepted')
        try:
            actions.decide(owner + '_other', first['id'], 'APPROVED', first['fingerprint'])
        except actions.ActionConflict:
            pass
        else:
            raise AssertionError('cross-owner approval accepted')
        decided, _ = actions.decide(owner, first['id'], 'APPROVED', first['fingerprint'])
        assert decided['status'] == 'RUNNING'
        try:
            actions.decide(owner, first['id'], 'APPROVED', first['fingerprint'])
        except actions.ActionConflict:
            pass
        else:
            raise AssertionError('second approval accepted')
        final = actions.finish(owner, first['id'], 'UNCERTAIN', 'Synthetic timeout; no send made')
        assert final['status'] == 'UNCERTAIN'
        assert actions.create(owner, 'calendar.create', payload, 'Synthetic calendar test')['id'] == first['id']
        print('PG action checks passed: dedupe, owner, fingerprint, single decision, uncertain')
    finally:
        sql = ("DELETE FROM core.jarvis_action_registry_event WHERE action_key IN "
               f"(SELECT action_key FROM core.jarvis_action_registry WHERE owner='{owner}'); "
               f"DELETE FROM core.jarvis_action_registry WHERE owner='{owner}'; "
               "DELETE FROM core.jarvis_personal_action_event WHERE action_id IN "
               f"(SELECT action_id FROM core.jarvis_personal_action WHERE owner='{owner}'); "
               f"DELETE FROM core.jarvis_personal_action WHERE owner='{owner}';")
        result = subprocess.run(['docker', 'exec', 'lcarlie-postgres', 'psql', '-X', '-q',
                                 '-v', 'ON_ERROR_STOP=1', '-U', 'n8n', '-d', 'n8n',
                                 '-c', sql], capture_output=True, text=True, check=False)
        if result.returncode:
            raise SystemExit('Synthetic rows need cleanup: ' + result.stderr[:160])


if __name__ == '__main__':
    main()
