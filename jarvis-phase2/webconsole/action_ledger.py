"""Durable, owner-scoped action state machine for personal tool writes.

The database is the authority. Callers must never retry an external write after
an EXECUTING/UNCERTAIN result without first reconciling the provider state.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class ActionConflict(ValueError):
    pass


@contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS actions (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('AWAITING_APPROVAL','EXECUTING','DONE','FAILED','REJECTED','UNCERTAIN','EXPIRED')),
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            external_id TEXT,
            message TEXT
        );
        CREATE INDEX IF NOT EXISTS actions_owner_recent ON actions(owner, created_at DESC);
        CREATE TABLE IF NOT EXISTS action_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT NOT NULL REFERENCES actions(id),
            from_status TEXT,
            to_status TEXT NOT NULL,
            at REAL NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def _event(db: sqlite3.Connection, action_id: str, before: str | None,
           after: str, note: str = "") -> None:
    db.execute("INSERT INTO action_events(action_id,from_status,to_status,at,note) VALUES(?,?,?,?,?)",
               (action_id, before, after, time.time(), note[:300]))


def _public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "kind": row["kind"], "description": row["description"],
            "status": row["status"], "expires_at": row["expires_at"],
            "external_id": row["external_id"], "message": row["message"]}


def create(path: Path, owner: str, kind: str, payload: dict,
           description: str, ttl: int = 600) -> dict:
    now = time.time()
    action_id = uuid.uuid4().hex
    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (action_id, owner, kind, json.dumps(payload, ensure_ascii=False), description,
                    "AWAITING_APPROVAL", now, now, now + ttl, None, None))
        _event(db, action_id, None, "AWAITING_APPROVAL")
    return {"id": action_id, "kind": kind, "description": description,
            "status": "AWAITING_APPROVAL", "expires_at": now + ttl}


def decide(path: Path, owner: str, action_id: str, decision: str) -> tuple[dict, dict | None]:
    if decision not in ("APPROVED", "REJECTED"):
        raise ActionConflict("Onayla veya reddet seçin.")
    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM actions WHERE id=? AND owner=?",
                         (action_id, owner)).fetchone()
        if row is None:
            raise ActionConflict("Bu işlem bulunamadı.")
        if row["status"] != "AWAITING_APPROVAL":
            raise ActionConflict("Bu işlem zaten karara bağlandı; yeniden uygulanmaz.")
        now = time.time()
        if row["expires_at"] <= now:
            new_status, message = "EXPIRED", "Onay süresi doldu. Yeni işlem hazırlayın."
        elif decision == "REJECTED":
            new_status, message = "REJECTED", "İşlem iptal edildi."
        else:
            new_status, message = "EXECUTING", "İşlem uygulanıyor."
        db.execute("UPDATE actions SET status=?,updated_at=?,message=? WHERE id=?",
                   (new_status, now, message, action_id))
        _event(db, action_id, row["status"], new_status)
        updated = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
    return _public(updated), json.loads(row["payload"]) if new_status == "EXECUTING" else None


def finish(path: Path, owner: str, action_id: str, status: str,
           message: str, external_id: str | None = None) -> dict:
    if status not in ("DONE", "FAILED", "UNCERTAIN"):
        raise ActionConflict("Geçersiz sonuç durumu.")
    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM actions WHERE id=? AND owner=?",
                         (action_id, owner)).fetchone()
        if row is None or row["status"] != "EXECUTING":
            raise ActionConflict("Bu işlem uygulanmıyor.")
        db.execute("UPDATE actions SET status=?,updated_at=?,message=?,external_id=? WHERE id=?",
                   (status, time.time(), message[:500], external_id, action_id))
        _event(db, action_id, "EXECUTING", status, message)
        updated = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
    return _public(updated)


def list_visible(path: Path, owner: str) -> list[dict]:
    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        now = time.time()
        expired = db.execute("SELECT id FROM actions WHERE owner=? AND status='AWAITING_APPROVAL' AND expires_at<=?",
                             (owner, now)).fetchall()
        stale = db.execute("SELECT id FROM actions WHERE owner=? AND status='EXECUTING' AND updated_at<=?",
                           (owner, now - 120)).fetchall()
        for row in expired:
            db.execute("UPDATE actions SET status='EXPIRED',updated_at=? WHERE id=?", (now, row["id"]))
            _event(db, row["id"], "AWAITING_APPROVAL", "EXPIRED")
        for row in stale:
            db.execute("UPDATE actions SET status='UNCERTAIN',updated_at=?,message=? WHERE id=?",
                       (now, "Sonuç belirsiz; dış hesapta kontrol edin. Otomatik tekrar yapılmadı.", row["id"]))
            _event(db, row["id"], "EXECUTING", "UNCERTAIN", "stale execution")
        rows = db.execute("SELECT * FROM actions WHERE owner=? AND status IN ('AWAITING_APPROVAL','UNCERTAIN') "
                          "ORDER BY created_at DESC LIMIT 20", (owner,)).fetchall()
    return [_public(row) for row in rows]
