"""Small, owner-scoped mobile features. Files stay outside the static tree."""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import uuid
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

STATE = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "mobile"
MAX_UPLOAD = 5 * 1024 * 1024
_LOCK = threading.RLock()


def _user(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:60] or "operator"


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o750)
    tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _reminders_path() -> Path:
    return STATE / "reminders.json"


def reminders(username: str) -> list[dict]:
    with _LOCK:
        return [dict(row) for row in _read(_reminders_path()) if row.get("user") == _user(username)][-100:]


def add_reminder(username: str, text: str, when: str) -> dict:
    text = " ".join((text or "").split())[:240]
    if not text:
        raise ValueError("Hatırlatılacak konuyu yazın.")
    try:
        due = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError("Geçerli bir tarih ve saat seçin.") from None
    if due.tzinfo is None:
        raise ValueError("Saat dilimi eksik. Sayfayı yenileyip tekrar deneyin.")
    now = datetime.now(timezone.utc)
    due = due.astimezone(timezone.utc)
    if due <= now or due > now + timedelta(days=365):
        raise ValueError("Gelecek bir yıl içinden tarih ve saat seçin.")
    row = {"id": uuid.uuid4().hex, "user": _user(username), "text": text,
           "due_at": due.isoformat(), "sent_to": []}
    with _LOCK:
        rows = _read(_reminders_path())
        rows.append(row)
        _atomic(_reminders_path(), rows[-500:])
    return row


def delete_reminder(username: str, identifier: str) -> bool:
    with _LOCK:
        rows = _read(_reminders_path())
        kept = [r for r in rows if not (r.get("id") == identifier and r.get("user") == _user(username))]
        if len(kept) == len(rows):
            return False
        _atomic(_reminders_path(), kept)
        return True


def due_reminders() -> list[dict]:
    now = datetime.now(timezone.utc)
    with _LOCK:
        rows = _read(_reminders_path())
    due = []
    for row in rows:
        try:
            if datetime.fromisoformat(row["due_at"]) <= now:
                due.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    return due[:50]


def mark_sent(identifier: str, subscription_id: str) -> None:
    with _LOCK:
        rows = _read(_reminders_path())
        for row in rows:
            if row.get("id") == identifier and subscription_id not in row.get("sent_to", []):
                row.setdefault("sent_to", []).append(subscription_id)
        _atomic(_reminders_path(), rows)


def personal_notes(username: str) -> list[dict]:
    with _LOCK:
        return _read(STATE / "notes" / (_user(username) + ".json"))[-60:]


def add_note(username: str, text: str) -> dict:
    text = " ".join((text or "").split())[:400]
    if not text:
        raise ValueError("Hatırlanacak bilgiyi yazın.")
    row = {"id": uuid.uuid4().hex, "text": text,
           "created_at": datetime.now(timezone.utc).isoformat()}
    path = STATE / "notes" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        rows.append(row)
        _atomic(path, rows[-60:])
    return row


def delete_note(username: str, identifier: str) -> bool:
    path = STATE / "notes" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        kept = [row for row in rows if row.get("id") != identifier]
        if len(kept) == len(rows):
            return False
        _atomic(path, kept)
        return True


def _attachment_dir(username: str) -> Path:
    return STATE / "attachments" / _user(username)


def upload(username: str, filename: str, data: bytes) -> dict:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Dosya en fazla 5 MB olabilir.")
    filename = Path(filename or "dosya").name[:100]
    identifier = uuid.uuid4().hex
    kind, suffix, text, payload = "", "", "", data
    if data.startswith(b"%PDF-"):
        import fitz
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.page_count > 30:
                    raise ValueError("PDF en fazla 30 sayfa olabilir.")
                text = "\n".join(page.get_text() for page in doc)[:12000]
        except fitz.FileDataError:
            raise ValueError("PDF okunamadı. Başka bir dosya deneyin.") from None
        kind, suffix = "pdf", ".pdf"
    elif data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")):
        from PIL import Image, UnidentifiedImageError
        try:
            image = Image.open(io.BytesIO(data))
            image.verify()
            image = Image.open(io.BytesIO(data)).convert("RGB")
            image.thumbnail((1600, 1600))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
            payload = out.getvalue()
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValueError("Görsel okunamadı. JPG veya PNG deneyin.") from None
        kind, suffix = "image", ".jpg"
    else:
        try:
            text = data.decode("utf-8")[:12000]
        except UnicodeDecodeError:
            raise ValueError("JPG, PNG, PDF veya metin dosyası seçin.") from None
        kind, suffix = "text", ".txt"
    folder = _attachment_dir(username)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o750)
    path = folder / (identifier + suffix)
    path.write_bytes(payload)
    os.chmod(path, 0o640)
    meta = {"id": identifier, "user": _user(username), "name": filename,
            "kind": kind, "suffix": suffix, "text": text,
            "created_at": datetime.now(timezone.utc).isoformat()}
    _atomic(folder / (identifier + ".json"), meta)
    return {"id": identifier, "name": filename, "kind": kind,
            "text_available": bool(text.strip()),
            "url": f"/api/mobile-attachment/{identifier}" if kind == "image" else None}


def attachment(username: str, identifier: str) -> tuple[dict, Path]:
    if not re.fullmatch(r"[0-9a-f]{32}", identifier or ""):
        raise ValueError("Dosya bulunamadı.")
    folder = _attachment_dir(username)
    try:
        meta = json.loads((folder / (identifier + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("Dosya bulunamadı.") from None
    if meta.get("user") != _user(username):
        raise ValueError("Dosya bulunamadı.")
    return meta, folder / (identifier + meta["suffix"])


def vision_answer(username: str, identifier: str, question: str) -> str:
    """Explicit opt-in call; never runs merely because an image was uploaded."""
    from jarvis.model_layer import ExternalProvider
    meta, path = attachment(username, identifier)
    if meta["kind"] != "image":
        raise ValueError("Görsel seçin.")
    key = ExternalProvider()._key()
    if not key:
        raise ValueError("Görsel analiz servisi şu anda kullanılamıyor.")
    image = base64.b64encode(path.read_bytes()).decode("ascii")
    request_body = json.dumps({
        "model": os.environ.get("JARVIS_VISION_MODEL", "google/gemini-3.5-flash-lite"),
        "max_tokens": 420,
        "messages": [
            {"role": "system", "content": "Görseli Türkçe, sade ve kısa anlat. Gördüğünle tahmini ayır. Şirket verisi uydurma."},
            {"role": "user", "content": [
                {"type": "text", "text": (question or "Bu görselde ne var? Kendini açıkça gösteren sorunları söyle.")[:500]},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}},
            ]},
        ],
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", request_body,
                                 {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
        answer = result["choices"][0]["message"]["content"]
        return str(answer).strip()[:3000]
    except (HTTPError, URLError, KeyError, IndexError, ValueError):
        raise ValueError("Görsel şu anda analiz edilemedi. Biraz sonra tekrar deneyin.") from None
