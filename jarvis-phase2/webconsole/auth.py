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
import sqlite3
from contextlib import contextmanager
import tempfile
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
    payload = json.dumps({
        "username": username, "password_hash": password_hash, "salt": salt,
        "created_at": time.time(),
    })
    descriptor, temporary_path = tempfile.mkstemp(prefix=".auth-", dir=AUTH_FILE.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, AUTH_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


# -- Ek kullanıcılar ----------------------------------------------------------
# auth.json'daki operatör hesabı YÖNETİCİ'dir ve değişmez. Ek hesaplar ayrı
# dosyada durur: operatör dosyasının biçimine dokunmamak, mevcut girişin hiçbir
# koşulda kırılmaması demektir. Rol her istekte bu dosyadan OKUNUR, oturuma
# yazılmaz -- rol değişikliği ya da hesabı kapatma bir sonraki istekte geçerli.
USERS_FILE = AUTH_FILE.parent / "users.json"
ROLE_ADMIN = "YONETICI"
ROLE_OFIS = "OFIS"
ROLES = (ROLE_ADMIN, ROLE_OFIS)


def _load_users() -> dict[str, dict[str, Any]]:
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))


def _write_users(users: dict[str, dict[str, Any]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".users-", dir=USERS_FILE.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(users, ensure_ascii=False, indent=1))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, USERS_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def find_account(username: str) -> dict[str, Any] | None:
    """Giriş yapabilecek hesabı rolüyle döndürür; kapatılmış hesap yok sayılır."""
    operator = load_account()
    if operator and username == operator["username"]:
        return {**operator, "role": ROLE_ADMIN}
    user = _load_users().get(username)
    if not user or user.get("disabled"):
        return None
    return {**user, "username": username}


def role_of(username: str) -> str | None:
    account = find_account(username)
    return account["role"] if account else None


def add_user(username: str, role: str) -> str:
    """Yeni hesap açar, rastgele parolayı YALNIZ BİR KEZ döndürür."""
    if role not in ROLES or role == ROLE_ADMIN:
        raise ValueError("ek hesap yalniz OFIS rolunde acilabilir")
    if not username or not username.isascii() or not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("kullanici adi yalniz harf, rakam, - ve _ icerebilir")
    operator = load_account()
    users = _load_users()
    if username in users or (operator and operator["username"] == username):
        raise ValueError("bu kullanici adi zaten var")
    password = secrets.token_urlsafe(12)
    password_hash, salt = hash_password(password)
    users[username] = {"password_hash": password_hash, "salt": salt, "role": role,
                       "must_change": True, "created_at": time.time()}
    _write_users(users)
    return password


def set_user_password(username: str, password: str) -> None:
    operator = load_account()
    if operator and username == operator["username"]:
        set_password(username, password)
        return
    users = _load_users()
    if username not in users:
        raise ValueError("kullanici yok")
    password_hash, salt = hash_password(password)
    users[username].update(password_hash=password_hash, salt=salt, must_change=False)
    _write_users(users)


def set_disabled(username: str, disabled: bool) -> None:
    users = _load_users()
    if username not in users:
        raise ValueError("kullanici yok")
    users[username]["disabled"] = bool(disabled)
    _write_users(users)


def list_users() -> list[dict[str, Any]]:
    return [{"username": name, "role": user.get("role"), "disabled": bool(user.get("disabled")),
             "must_change": bool(user.get("must_change"))} for name, user in sorted(_load_users().items())]


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

    def create(self, username: str, device: str = "", source_ip: str = "") -> Session:
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

    def destroy_all(self) -> None:
        with self._lock:
            self._sessions.clear()

    def destroy_user(self, username: str) -> None:
        with self._lock:
            for sid in [sid for sid, s in self._sessions.items() if s.username == username]:
                del self._sessions[sid]

    def sweep(self) -> None:
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.expired(now)]
            for sid in expired:
                del self._sessions[sid]


class DurableSessionStore:
    """Persistent, per-device sessions. Only SHA-256 hashes of bearer IDs reach disk."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else AUTH_FILE.parent / "sessions.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id_hash TEXT PRIMARY KEY, username TEXT NOT NULL, csrf_token TEXT NOT NULL,
                created_at REAL NOT NULL, last_seen_at REAL NOT NULL,
                device TEXT NOT NULL DEFAULT '', source_ip TEXT NOT NULL DEFAULT ''
            )""")
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _hash(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    def create(self, username: str, device: str = "", source_ip: str = "") -> Session:
        now = time.time()
        session = Session(secrets.token_urlsafe(32), username, secrets.token_urlsafe(32), now, now)
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", (
                self._hash(session.session_id), username, session.csrf_token, now, now,
                str(device)[:180], str(source_ip)[:80]))
        return session

    def get(self, session_id: str) -> Session | None:
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 160:
            return None
        key = self._hash(session_id)
        now = time.time()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id_hash=?", (key,)).fetchone()
            if row is None:
                return None
            session = Session(session_id, row["username"], row["csrf_token"],
                              row["created_at"], row["last_seen_at"])
            if session.expired(now):
                db.execute("DELETE FROM sessions WHERE id_hash=?", (key,))
                return None
            db.execute("UPDATE sessions SET last_seen_at=? WHERE id_hash=?", (now, key))
        session.last_seen_at = now
        return session

    def list_devices(self, username: str, current_id: str) -> list[dict[str, Any]]:
        self.sweep()
        current_hash = self._hash(current_id)
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id_hash,device,source_ip,created_at,last_seen_at "
                              "FROM sessions WHERE username=? ORDER BY last_seen_at DESC", (username,)).fetchall()
        return [{"id": row["id_hash"], "device": row["device"],
                 "source_ip": row["source_ip"], "created_at": row["created_at"],
                 "last_seen_at": row["last_seen_at"], "current": row["id_hash"] == current_hash}
                for row in rows]

    def revoke_device(self, username: str, id_hash: str) -> bool:
        if not isinstance(id_hash, str) or len(id_hash) != 64 or any(c not in "0123456789abcdef" for c in id_hash):
            return False
        with self._lock, self._connect() as db:
            result = db.execute("DELETE FROM sessions WHERE username=? AND id_hash=?", (username, id_hash))
            return result.rowcount == 1

    def destroy(self, session_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE id_hash=?", (self._hash(session_id),))

    def destroy_all(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions")

    def destroy_user(self, username: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE username=?", (username,))

    def sweep(self) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE ?-created_at>? OR ?-last_seen_at>?", (
                now, SESSION_ABSOLUTE_TIMEOUT_S, now, SESSION_IDLE_TIMEOUT_S))


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


def reset_user_password(username: str) -> str:
    """Ek hesabın parolasını rastgele yenisiyle değiştirir; ilk girişte değiştirilmesi istenir."""
    users = _load_users()
    if username not in users:
        raise ValueError("kullanici yok")
    password = secrets.token_urlsafe(12)
    password_hash, salt = hash_password(password)
    users[username].update(password_hash=password_hash, salt=salt, must_change=True)
    _write_users(users)
    return password


if __name__ == "__main__":
    # Hesap yönetimi yalnız sunucuda, root olarak yapılır; panelde bunun ucu YOK.
    # Parola yalnız bir kez ekrana basılır, hiçbir dosyaya düz metin yazılmaz.
    import sys
    komut, *arg = sys.argv[1:] or ["liste"]
    if komut == "ekle" and len(arg) == 2:
        print(arg[0], add_user(arg[0], arg[1]))
    elif komut == "sifirla" and len(arg) == 1:
        print(arg[0], reset_user_password(arg[0]))
    elif komut in ("kapat", "ac") and len(arg) == 1:
        set_disabled(arg[0], komut == "kapat")
        if komut == "kapat":
            DurableSessionStore().destroy_user(arg[0])
        print(arg[0], komut)
    elif komut == "liste":
        print(json.dumps(list_users(), ensure_ascii=False, indent=1))
    else:
        sys.exit("kullanim: auth.py ekle <ad> OFIS | sifirla <ad> | kapat <ad> | ac <ad> | liste")
