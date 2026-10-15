"""Private storage for the operator's Web Push subscriptions."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

STATE_DIR = Path(os.environ.get("JARVIS_WEB_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state/webconsole"))
SUBSCRIPTIONS_FILE = STATE_DIR / "push-subscriptions.json"
PUBLIC_KEY_FILE = STATE_DIR / "push-vapid-public.txt"
PRIVATE_KEY_FILE = STATE_DIR / "push-vapid-private.pem"
SEEN_FILE = STATE_DIR / "push-seen.json"
LOCK_FILE = STATE_DIR / "push-subscriptions.lock"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,256}$")


def public_key() -> str:
    return PUBLIC_KEY_FILE.read_text(encoding="ascii").strip()


def subscription_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _valid_endpoint(endpoint: str) -> bool:
    if len(endpoint) > 2048:
        return False
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    return (parsed.scheme == "https" and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443) and bool(parsed.path)
            and (host == "fcm.googleapis.com" or host == "updates.push.services.mozilla.com"
                 or host.endswith(".push.apple.com")))


def _validate(subscription: dict) -> dict:
    if not isinstance(subscription, dict):
        raise ValueError("invalid subscription")
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")
    if not isinstance(endpoint, str) or not _valid_endpoint(endpoint):
        raise ValueError("invalid push endpoint")
    if not isinstance(keys, dict) or not all(
        isinstance(keys.get(name), str) and KEY_PATTERN.fullmatch(keys[name])
        for name in ("p256dh", "auth")
    ):
        raise ValueError("invalid push keys")
    return {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


def _read() -> dict:
    if not SUBSCRIPTIONS_FILE.exists():
        return {}
    return json.loads(SUBSCRIPTIONS_FILE.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".push-", dir=STATE_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, SUBSCRIPTIONS_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def save(subscription: dict, owner: str | None = None) -> str:
    clean = _validate(subscription)
    if owner is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", owner):
        raise ValueError("invalid owner")
    identifier = subscription_id(clean["endpoint"])
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        os.chmod(LOCK_FILE, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read()
        if identifier not in data and len(data) >= 10:
            raise ValueError("too many devices")
        previous = data.get(identifier, {})
        if owner is not None and previous.get("owner") not in (None, owner):
            raise ValueError("device belongs to another user")
        data[identifier] = {**clean, "created_at": previous.get("created_at", time.time()),
                            "owner": owner if owner is not None else previous.get("owner")}
        _write(data)
    return identifier


def remove(endpoint: str, owner: str | None = None) -> None:
    identifier = subscription_id(endpoint)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read()
        if owner is None or data.get(identifier, {}).get("owner") == owner:
            data.pop(identifier, None)
        _write(data)


def get(identifier: str) -> dict | None:
    return _read().get(identifier)


def all_subscriptions() -> dict:
    return _read()
