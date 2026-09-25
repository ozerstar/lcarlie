"""Authentication: single-operator login, sessions, CSRF, rate limiting.

Stdlib only (hashlib.scrypt for password hashing -- no bcrypt/argon2 install
needed). In-memory session/rate-limit state: a restart clears sessions,
which is a safe default (forces re-login), not a security hole.

This module owns NO business data and NO Jarvis capability -- it only
answers "is this request authenticated as the operator". It never touches
core.ai_* or human_approver; that separation lives entirely in
jarvis/operator.py, unchanged and reused as-is.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

AUTH_FILE = Path(os.environ.get("JARVIS_WEB_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state/webconsole")) / "auth.json"

SESSION_IDLE_TIMEOUT_S = 30 * 60
SESSION_ABSOLUTE_TIMEOUT_S = 12 * 60 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_S = 15 * 60
LOGIN_WINDOW_S = 15 * 60

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                             p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return derived.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    computed, _ = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(computed, hash_hex)


def ensure_operator_account(username: str | None = None) -> tuple[str, str] | None:
    """Create the operator account with a random password if none exists yet.

    Returns (username, plaintext_password) ONLY on first creation, so the
    caller can print it once. Never returns the plaintext again afterward --
    only the hash is persisted.
    """
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    if AUTH_FILE.exists():
        return None
    username = username or "operator"
    password = secrets.token_urlsafe(18)
    password_hash, salt = hash_password(password)
    AUTH_FILE.write_text(json.dumps({
        "username": username, "password_hash": password_hash, "salt": salt,
        "created_at": time.time(),
    }), encoding="utf-8")
    os.chmod(AUTH_FILE, 0o600)
    return username, password


def load_account() -> dict[str, Any] | None:
    if not AUTH_FILE.exists():
        return None
    return json.loads(AUTH_FILE.read_text(encoding="utf-8"))


def set_password(username: str, password: str) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    password_hash, salt = hash_password(password)
    AUTH_FILE.write_text(json.dumps({
        "username": username, "password_hash": password_hash, "salt": salt,
        "created_at": time.time(),
    }), encoding="utf-8")
    os.chmod(AUTH_FILE, 0o600)


@dataclass
class Session:
    session_id: str
    username: str
    csrf_token: str
    created_at: float
    last_seen_at: float

    def expired(self, now: float) -> bool:
        if now - self.created_at > SESSION_ABSOLUTE_TIMEOUT_S:
            return True
        if now - self.last_seen_at > SESSION_IDLE_TIMEOUT_S:
            return True
        return False


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def create(self, username: str) -> Session:
        now = time.time()
        session = Session(
            session_id=secrets.token_urlsafe(32), username=username,
            csrf_token=secrets.token_urlsafe(32), created_at=now, last_seen_at=now,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        now = time.time()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expired(now):
                del self._sessions[session_id]
                return None
            session.last_seen_at = now
            return session

    def destroy(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def sweep(self) -> None:
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.expired(now)]
            for sid in expired:
                del self._sessions[sid]


class LoginThrottle:
    """Per-source-IP login attempt limiter. Locks out after repeated failures."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}
        self._lockout_until: dict[str, float] = {}
        self._lock = Lock()

    def check(self, source: str) -> tuple[bool, int]:
        """Returns (allowed, seconds_remaining_if_locked)."""
        now = time.time()
        with self._lock:
            until = self._lockout_until.get(source, 0)
            if until > now:
                return False, int(until - now)
            return True, 0

    def record_failure(self, source: str) -> None:
        now = time.time()
        with self._lock:
            window = [t for t in self._attempts.get(source, []) if now - t < LOGIN_WINDOW_S]
            window.append(now)
            self._attempts[source] = window
            if len(window) >= LOGIN_MAX_ATTEMPTS:
                self._lockout_until[source] = now + LOGIN_LOCKOUT_S
                self._attempts[source] = []

    def record_success(self, source: str) -> None:
        with self._lock:
            self._attempts.pop(source, None)
            self._lockout_until.pop(source, None)
