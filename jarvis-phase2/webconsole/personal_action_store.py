"""PostgreSQL state machine for owner-scoped personal external actions.

The existing company proposal tables live in the same PostgreSQL database.
No external request is made by this module. A committed RUNNING transition
always precedes the caller's provider request, so a crash cannot cause an
automatic second send.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone


class ActionConflict(ValueError):
    pass


KINDS = frozenset({'calendar.create', 'gmail.send', 'drive.upload'})
KEY_RE = re.compile(r'^[A-Za-z0-9_.:-]{16,120}$')


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    with open(os.environ['JARVIS_DB_PASSWORD_FILE'], encoding='utf-8') as stream:
        password = stream.read().strip()
    return psycopg.connect(
        host=os.environ.get('JARVIS_DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('JARVIS_DB_PORT', '5433')),
        dbname='n8n', user='jarvis_web', password=password,
        connect_timeout=8, row_factory=dict_row,
    )


def fingerprint(kind: str, payload: dict, description: str) -> str:
    encoded = json.dumps({'kind': kind, 'payload': payload, 'description': description},
                         ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _public(row: dict) -> dict:
    expires = row['expires_at']
    if isinstance(expires, datetime):
        expires = expires.timestamp()
    return {'id': row['action_id'], 'kind': row['kind'],
            'description': row['description'], 'status': row['status'],
            'expires_at': expires, 'fingerprint': row['payload_hash'],
            'external_id': row['external_id'], 'message': row['message']}


def _event(cur, action_id: str, before: str | None, after: str,
           actor: str, note: str = '') -> None:
    cur.execute('''INSERT INTO core.jarvis_personal_action_event
        (action_id,from_status,to_status,actor,note) VALUES (%s,%s,%s,%s,%s)''',
        (action_id, before, after, actor, note[:300]))


def create(owner: str, kind: str, payload: dict, description: str,
           *, idempotency_key: str | None = None, ttl_s: int = 600,
           source_conversation: str | None = None) -> dict:
    if (kind not in KINDS or not isinstance(payload, dict) or
            not isinstance(description, str) or not description.strip()):
        raise ActionConflict('Geçersiz işlem.')
    digest = fingerprint(kind, payload, description)
    if idempotency_key is None:
        # Old clients send no request key. Identical payloads stay one action,
        # including after a response is lost or a previous send completed.
        idempotency_key = 'payload:' + digest
    if not isinstance(idempotency_key, str) or not KEY_RE.fullmatch(idempotency_key):
        raise ActionConflict('Geçersiz istek kimliği.')
    action_id = uuid.uuid4().hex
    risk = 'HIGH' if kind == 'gmail.send' else 'MEDIUM'
    from psycopg.types.json import Jsonb

    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                    (owner + ':' + kind + ':' + digest,))
        cur.execute('''SELECT * FROM core.jarvis_personal_action
            WHERE owner=%s AND idempotency_key=%s''', (owner, idempotency_key))
        reused_key = cur.fetchone()
        if reused_key is not None and (reused_key['payload_hash'] != digest or reused_key['kind'] != kind):
            raise ActionConflict('İstek kimliği başka bir işlem için kullanılmış.')
        cur.execute('''SELECT * FROM core.jarvis_personal_action
            WHERE owner=%s AND kind=%s AND payload_hash=%s
            ORDER BY (status='COMPLETED') DESC, created_at DESC LIMIT 1''',
            (owner, kind, digest))
        previous = cur.fetchone()
        if previous is not None:
            return _public(previous)
        cur.execute('''INSERT INTO core.jarvis_personal_action
            (action_id,owner,source_conversation,kind,payload,payload_hash,
             description,risk_level,idempotency_key,status,expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'AWAITING_APPROVAL',
                    clock_timestamp() + (%s * interval '1 second'))
            ON CONFLICT(owner,idempotency_key) DO NOTHING RETURNING *''',
            (action_id, owner, source_conversation, kind, Jsonb(payload), digest,
             description, risk, idempotency_key, ttl_s))
        row = cur.fetchone()
        if row is None:
            cur.execute('''SELECT * FROM core.jarvis_personal_action
                WHERE owner=%s AND idempotency_key=%s''', (owner, idempotency_key))
            row = cur.fetchone()
            if row is None or row['payload_hash'] != digest or row['kind'] != kind:
                raise ActionConflict('İstek kimliği başka bir işlem için kullanılmış.')
        else:
            _event(cur, action_id, None, 'AWAITING_APPROVAL', owner)
    return _public(row)


def list_visible(owner: str) -> list[dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT action_id,status FROM core.jarvis_personal_action
            WHERE owner=%s AND
              ((status='AWAITING_APPROVAL' AND expires_at<=clock_timestamp()) OR
               (status='RUNNING' AND updated_at<=clock_timestamp()-interval '120 seconds'))
            FOR UPDATE''', (owner,))
        stale = cur.fetchall()
        for item in stale:
            before = item['status']
            after = 'EXPIRED' if before == 'AWAITING_APPROVAL' else 'UNCERTAIN'
            message = ('Onay süresi doldu.' if after == 'EXPIRED' else
                       'Sonuç belirsiz. Dış hesapta kontrol edin; otomatik tekrar yapılmadı.')
            cur.execute('''UPDATE core.jarvis_personal_action SET
                status=%s,updated_at=clock_timestamp(),message=%s WHERE action_id=%s''',
                (after, message, item['action_id']))
            _event(cur, item['action_id'], before, after, 'system', 'timeout')
        cur.execute('''SELECT * FROM core.jarvis_personal_action
            WHERE owner=%s AND status IN ('AWAITING_APPROVAL','UNCERTAIN')
            ORDER BY created_at DESC LIMIT 20''', (owner,))
        rows = cur.fetchall()
    return rows


def decide(owner: str, action_id: str, decision: str,
           shown_fingerprint: str | None) -> tuple[dict, dict | None]:
    if decision not in ('APPROVED', 'REJECTED') or not re.fullmatch(r'[0-9a-f]{32}', str(action_id)):
        raise ActionConflict('Geçersiz karar.')
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT * FROM core.jarvis_personal_action
            WHERE owner=%s AND action_id=%s FOR UPDATE''', (owner, action_id))
        row = cur.fetchone()
        if row is None:
            raise ActionConflict('Bu işlem bulunamadı.')
        if row['status'] != 'AWAITING_APPROVAL':
            raise ActionConflict('Bu işlem zaten karara bağlandı; tekrar uygulanmaz.')
        if row['expires_at'] <= datetime.now(timezone.utc):
            raise ActionConflict('Onay süresi doldu. Yeni işlem hazırlayın.')
        if not shown_fingerprint or shown_fingerprint != row['payload_hash']:
            raise ActionConflict('İşlem ayrıntıları değişmiş. Onayı yeniden açın.')
        next_status = 'RUNNING' if decision == 'APPROVED' else 'DENIED'
        message = 'İşlem uygulanıyor.' if next_status == 'RUNNING' else 'İşlem reddedildi.'
        cur.execute('''UPDATE core.jarvis_personal_action SET
            status=%s,approved_by=%s,updated_at=clock_timestamp(),message=%s,
            finished_at=CASE WHEN %s='DENIED' THEN clock_timestamp() ELSE NULL END
            WHERE action_id=%s RETURNING *''',
            (next_status, owner, message, next_status, action_id))
        updated = cur.fetchone()
        _event(cur, action_id, row['status'], next_status, owner)
    return _public(updated), row['payload'] if next_status == 'RUNNING' else None


def finish(owner: str, action_id: str, status: str, message: str,
           external_id: str | None = None) -> dict:
    if status not in ('COMPLETED', 'FAILED', 'UNCERTAIN'):
        raise ActionConflict('Geçersiz sonuç durumu.')
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT status FROM core.jarvis_personal_action
            WHERE owner=%s AND action_id=%s FOR UPDATE''', (owner, action_id))
        row = cur.fetchone()
        if row is None or row['status'] != 'RUNNING':
            raise ActionConflict('Bu işlem çalışmıyor; sonuç elle uzlaştırılmalı.')
        cur.execute('''UPDATE core.jarvis_personal_action SET status=%s,
            message=%s,external_id=%s,updated_at=clock_timestamp(),
            finished_at=clock_timestamp() WHERE action_id=%s RETURNING *''',
            (status, message[:500], external_id, action_id))
        updated = cur.fetchone()
        _event(cur, action_id, 'RUNNING', status, 'system', message)
    return _public(updated)


def import_legacy(rows: list[dict]) -> int:
    """Idempotent one-time import. EXECUTING is uncertain, never resumed."""
    from psycopg.types.json import Jsonb

    count = 0
    with _connect() as conn, conn.cursor() as cur:
        for old in rows:
            action_id = str(old.get('id') or '')
            owner = str(old.get('user') or '')
            kind = str(old.get('kind') or '')
            payload = old.get('payload')
            description = str(old.get('description') or '')
            if (not re.fullmatch(r'[0-9a-f]{32}', action_id) or not owner or
                    kind not in KINDS or not isinstance(payload, dict) or not description):
                raise ActionConflict('Eski işlem kaydı geçersiz; içe aktarma durduruldu.')
            old_status = old.get('status')
            status = {'PENDING': 'AWAITING_APPROVAL', 'EXECUTING': 'UNCERTAIN',
                      'DONE': 'COMPLETED', 'FAILED': 'FAILED',
                      'REJECTED': 'DENIED', 'UNCERTAIN': 'UNCERTAIN'}.get(old_status)
            if status is None:
                raise ActionConflict('Bilinmeyen eski işlem durumu.')
            expires = datetime.fromtimestamp(float(old.get('expires') or time.time()), timezone.utc)
            if status == 'AWAITING_APPROVAL' and expires <= datetime.now(timezone.utc):
                status = 'EXPIRED'
            digest = fingerprint(kind, payload, description)
            cur.execute('''INSERT INTO core.jarvis_personal_action
                (action_id,owner,kind,payload,payload_hash,description,risk_level,
                 idempotency_key,status,expires_at,message)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(action_id) DO NOTHING RETURNING action_id''',
                (action_id, owner, kind, Jsonb(payload), digest, description,
                 'HIGH' if kind == 'gmail.send' else 'MEDIUM',
                 'legacy:' + action_id, status, expires,
                 'Eski kayıttan aktarıldı.' if status != 'UNCERTAIN' else
                 'Eski işlem çalışırken kesildi; dış hesapta kontrol edin.'))
            if cur.fetchone():
                _event(cur, action_id, None, status, 'migration', 'actions.json')
                count += 1
            else:
                cur.execute('''SELECT owner,kind,payload_hash FROM core.jarvis_personal_action
                    WHERE action_id=%s''', (action_id,))
                existing = cur.fetchone()
                if (existing is None or existing['owner'] != owner or
                        existing['kind'] != kind or existing['payload_hash'] != digest):
                    raise ActionConflict('Eski işlem kimliği farklı içerikle çakıştı; aktarım durduruldu.')
        cur.execute('''SELECT p.action_id FROM core.jarvis_personal_action p
            WHERE p.idempotency_key LIKE 'legacy:%' AND p.status='AWAITING_APPROVAL'
              AND EXISTS (SELECT 1 FROM core.jarvis_personal_action done
                  WHERE done.owner=p.owner AND done.kind=p.kind
                    AND done.payload_hash=p.payload_hash AND done.status='COMPLETED')
            FOR UPDATE''')
        for duplicate in cur.fetchall():
            cur.execute('''UPDATE core.jarvis_personal_action SET
                status='UNCERTAIN',updated_at=clock_timestamp(),
                message='Aynı işlem daha önce tamamlandı; yeniden onaylanamaz.'
                WHERE action_id=%s''', (duplicate['action_id'],))
            _event(cur, duplicate['action_id'], 'AWAITING_APPROVAL',
                   'UNCERTAIN', 'migration', 'duplicate completed action')
    return count
