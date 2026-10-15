"""Durable, owner-scoped chat turns; a reconnect never executes a turn twice."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Callable, Iterator


DB_PATH = Path(os.environ.get("JARVIS_WEB_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state/webconsole")) / "chat_turns.sqlite3"
TURN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_lock = threading.RLock()
_active: set[str] = set()
_initialized_path: Path | None = None


def _connect() -> sqlite3.Connection:
    global _initialized_path
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    if os.name != "nt":
        os.chmod(DB_PATH, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    with _lock:
        if _initialized_path == DB_PATH:
            return db
        db.execute("""CREATE TABLE IF NOT EXISTS turns (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
        message_hash TEXT NOT NULL, status TEXT NOT NULL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )""")
        db.execute("""CREATE TABLE IF NOT EXISTS frames (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, turn_id TEXT NOT NULL
            REFERENCES turns(id) ON DELETE CASCADE,
        body TEXT NOT NULL
    )""")
        db.execute("CREATE INDEX IF NOT EXISTS frames_turn_seq ON frames(turn_id,seq)")
        db.commit()
        _initialized_path = DB_PATH
    return db


@contextmanager
def _db():
    db = _connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def _append(turn_id: str, event: dict, status: str | None = None) -> None:
    with _db() as db:
        db.execute("INSERT INTO frames(turn_id,body) VALUES (?,?)",
                   (turn_id, json.dumps(event, ensure_ascii=False, default=str)))
        if status:
            db.execute("UPDATE turns SET status=?,updated_at=? WHERE id=?",
                       (status, time.time(), turn_id))


def _run(turn_id: str, make_events: Callable[[], Iterator[dict]]) -> None:
    terminal = False
    tokens = ""
    last_flush = time.monotonic()

    def flush() -> None:
        nonlocal tokens, last_flush
        if tokens:
            _append(turn_id, {"type": "token", "delta": tokens})
            tokens = ""
            last_flush = time.monotonic()

    try:
        for event in make_events():
            if event.get("type") == "token":
                tokens += str(event.get("delta") or "")
                if len(tokens) >= 48 or time.monotonic() - last_flush >= 0.12:
                    flush()
                continue
            flush()
            kind = event.get("type")
            terminal = kind in ("done", "error")
            _append(turn_id, event, "DONE" if kind == "done" else "ERROR" if kind == "error" else None)
            if terminal:
                break
        flush()
        if not terminal:
            _append(turn_id, {"type": "error", "message": "Yanıt tamamlanamadı. Tekrar göndermeden önce iş durumunu kontrol edin."}, "ERROR")
    except Exception:
        try:
            flush()
            _append(turn_id, {"type": "error", "message": "Yanıt tamamlanamadı. İşlem durumunu kontrol edin."}, "ERROR")
        except Exception:
            pass
    finally:
        with _lock:
            _active.discard(turn_id)


def start_or_resume(turn_id: str, owner: str, mode: str, message: str | None,
                    make_events: Callable[[], Iterator[dict]]) -> None:
    if not isinstance(turn_id, str) or not TURN_ID.fullmatch(turn_id):
        raise ValueError("Geçersiz sohbet kimliği.")
    if mode not in ("work", "personal"):
        raise ValueError("Geçersiz sohbet alanı.")
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest() if message is not None else None
    with _lock:
        with _db() as db:
            row = db.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
            if row:
                if row["owner"] != owner or row["mode"] != mode or (digest and row["message_hash"] != digest):
                    raise ValueError("Bu sohbet isteği mevcut konuşmayla eşleşmiyor.")
                if row["status"] == "RUNNING" and turn_id not in _active:
                    db.execute("INSERT INTO frames(turn_id,body) VALUES (?,?)", (turn_id, json.dumps({
                        "type": "error", "message": "Sunucu yeniden başladı. İşlem durumunu kontrol edin; mesaj otomatik yeniden gönderilmedi."
                    }, ensure_ascii=False)))
                    db.execute("UPDATE turns SET status='UNCERTAIN',updated_at=? WHERE id=?", (time.time(), turn_id))
                return
            if not message or not message.strip():
                raise ValueError("Devam edilecek sohbet bulunamadı.")
            now = time.time()
            db.execute("INSERT INTO turns VALUES (?,?,?,?,?,?,?)",
                       (turn_id, owner, mode, digest, "RUNNING", now, now))
        _active.add(turn_id)
        threading.Thread(target=_run, args=(turn_id, make_events), daemon=True,
                         name="chat-turn-" + turn_id[:8]).start()


def read_after(turn_id: str, owner: str, after: int) -> tuple[list[dict], str]:
    if not isinstance(after, int) or after < 0:
        raise ValueError("Geçersiz devam noktası.")
    with _db() as db:
        row = db.execute("SELECT status FROM turns WHERE id=? AND owner=?", (turn_id, owner)).fetchone()
        if row is None:
            raise ValueError("Sohbet bulunamadı.")
        frames = db.execute("SELECT seq,body FROM frames WHERE turn_id=? AND seq>? ORDER BY seq LIMIT 100",
                            (turn_id, after)).fetchall()
    return [{**json.loads(item["body"]), "seq": item["seq"]} for item in frames], row["status"]
