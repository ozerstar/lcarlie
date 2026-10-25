"""Short-lived LiveKit joins and authenticated loopback agent requests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import time
import uuid


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _secret() -> tuple[str, str]:
    return os.environ.get("LIVEKIT_API_KEY", ""), os.environ.get("LIVEKIT_API_SECRET", "")


def ready() -> bool:
    key, secret = _secret()
    if os.environ.get("JARVIS_REALTIME_VOICE") != "true" or not key or len(secret) < 32:
        return False
    try:
        with socket.create_connection(("127.0.0.1", 7880), timeout=0.4), \
             socket.create_connection(("127.0.0.1", 8081), timeout=0.4):
            return True
    except OSError:
        return False


def issue_session(username: str, mode: str, chat_id: str | None = None) -> dict[str, str]:
    if mode not in ("work", "personal") or not username or len(username) > 100:
        raise ValueError("Geçerli bir sohbet alanı seçin.")
    if chat_id is not None:
        try:
            if str(uuid.UUID(chat_id)) != chat_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Geçerli bir sohbet seçin.") from None
    if not ready():
        raise RuntimeError("Gerçek zamanlı ses şu anda kullanılamıyor.")
    key, secret = _secret()
    now = int(time.time())
    room = "jarvis-voice-" + secrets.token_hex(12)
    metadata = {"owner": username, "mode": mode}
    if chat_id is not None:
        metadata["chat_id"] = chat_id
    claims = {
        "iss": key, "sub": "user-" + secrets.token_hex(12),
        "nbf": now - 5, "exp": now + 300, "iat": now,
        "jti": str(uuid.uuid4()),
        "metadata": json.dumps(metadata, ensure_ascii=False),
        "video": {"roomJoin": True, "room": room, "canPublish": True,
                  "canSubscribe": True, "canPublishData": False,
                  "canUpdateOwnMetadata": False},
    }
    head = _base64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = _base64url(json.dumps(claims, ensure_ascii=False, separators=(",", ":")).encode())
    signed = f"{head}.{payload}"
    signature = _base64url(hmac.new(secret.encode(), signed.encode(), hashlib.sha256).digest())
    return {"url": os.environ.get("LIVEKIT_PUBLIC_URL", "wss://jarvis.lcarlie.shop"),
            "token": f"{signed}.{signature}", "room": room}


def verify_agent(body: bytes, when: str, signature: str, remote_ip: str) -> bool:
    if remote_ip not in ("127.0.0.1", "::1") or len(body) > 4096:
        return False
    _key, secret = _secret()
    if len(secret) < 32 or not when.isdigit() or abs(time.time() - int(when)) > 30:
        return False
    expected = hmac.new(secret.encode(), when.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
