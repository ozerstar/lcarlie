"""Small, owner-scoped mobile features. Files stay outside the static tree."""
from __future__ import annotations

import base64
import calendar
import io
import json
import os
import re
import threading
import uuid
import urllib.request
from datetime import datetime, timedelta, timezone
from datetime import date
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


def _reminder_fields(text: str, when: str, repeat: str) -> tuple[str, datetime, str]:
    text = " ".join((text or "").split())[:240]
    if not text:
        raise ValueError("Hatırlatılacak konuyu yazın.")
    if repeat not in ("none", "daily", "weekly", "monthly"):
        raise ValueError("Geçerli bir tekrar aralığı seçin.")
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
    return text, due, repeat


def add_reminder(username: str, text: str, when: str, repeat: str = "none") -> dict:
    text, due, repeat = _reminder_fields(text, when, repeat)
    row = {"id": uuid.uuid4().hex, "user": _user(username), "text": text,
           "due_at": due.isoformat(), "repeat": repeat, "anchor_day": due.day, "sent_to": []}
    with _LOCK:
        rows = _read(_reminders_path())
        rows.append(row)
        _atomic(_reminders_path(), rows[-500:])
    return row


def update_reminder(username: str, identifier: str, text: str, when: str, repeat: str = "none") -> dict:
    text, due, repeat = _reminder_fields(text, when, repeat)
    with _LOCK:
        rows = _read(_reminders_path())
        for row in rows:
            if row.get("id") == identifier and row.get("user") == _user(username):
                row.update(text=text, due_at=due.isoformat(), repeat=repeat,
                           anchor_day=due.day, sent_to=[])
                _atomic(_reminders_path(), rows)
                return dict(row)
    raise ValueError("Hatırlatıcı bulunamadı.")


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


def advance_reminder(identifier: str, subscription_ids: set[str]) -> bool:
    if not subscription_ids:
        return False
    with _LOCK:
        rows = _read(_reminders_path())
        for row in rows:
            if row.get("id") != identifier or row.get("repeat", "none") == "none":
                continue
            if not subscription_ids.issubset(set(row.get("sent_to", []))):
                return False
            due = datetime.fromisoformat(row["due_at"])
            now = datetime.now(timezone.utc)
            while due <= now:
                if row["repeat"] == "daily":
                    due += timedelta(days=1)
                elif row["repeat"] == "weekly":
                    due += timedelta(days=7)
                elif row["repeat"] == "monthly":
                    year, month = due.year + (due.month == 12), due.month % 12 + 1
                    day = min(int(row.get("anchor_day", due.day)), calendar.monthrange(year, month)[1])
                    due = due.replace(year=year, month=month, day=day)
                else:
                    return False
            row["due_at"] = due.isoformat()
            row["sent_to"] = []
            _atomic(_reminders_path(), rows)
            return True
    return False


def personal_notes(username: str) -> list[dict]:
    with _LOCK:
        return _read(STATE / "notes" / (_user(username) + ".json"))[-60:]


def contacts(username: str) -> list[dict]:
    with _LOCK:
        return _read(STATE / "contacts" / (_user(username) + ".json"))[-100:]


def save_contact(username: str, name: str, relationship: str, detail: str = "",
                 special_day: str = "", occasion: str = "", identifier: str = "") -> dict:
    name = " ".join((name or "").split())[:80]
    relationship = " ".join((relationship or "").split())[:80]
    detail = " ".join((detail or "").split())[:220]
    occasion = " ".join((occasion or "").split())[:80] or "Doğum günü"
    special_day = (special_day or "").strip()
    if not name or not relationship:
        raise ValueError("Kişinin adını ve yakınlığını yazın.")
    if special_day:
        try:
            day, month = [int(part) for part in special_day.split(".")]
            date(2000, month, day)
        except (TypeError, ValueError):
            raise ValueError("Özel gün için GG.AA biçimini kullanın.") from None
        special_day = f"{month:02d}-{day:02d}"
    path = STATE / "contacts" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        if any(row.get("name", "").casefold() == name.casefold() and row.get("id") != identifier for row in rows):
            raise ValueError("Bu kişi zaten kayıtlı.")
        if identifier:
            row = next((item for item in rows if item.get("id") == identifier), None)
            if row is None:
                raise ValueError("Kişi bulunamadı.")
            row.update(name=name, relationship=relationship, detail=detail,
                       special_day=special_day, occasion=occasion)
        else:
            row = {"id": uuid.uuid4().hex, "name": name, "relationship": relationship,
                   "detail": detail, "special_day": special_day, "occasion": occasion}
            rows.append(row)
        _atomic(path, rows[-100:])
    return dict(row)


def delete_contact(username: str, identifier: str) -> bool:
    path = STATE / "contacts" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        kept = [row for row in rows if row.get("id") != identifier]
        if len(kept) == len(rows):
            return False
        _atomic(path, kept)
    return True


def special_days(username: str, day: date) -> list[dict]:
    key = day.strftime("%m-%d")
    return [row for row in contacts(username) if row.get("special_day") == key]


def record_activity(username: str, kind: str, summary: str) -> None:
    if kind not in {"reminder", "memory", "contact", "google"}:
        raise ValueError("Geçersiz etkinlik türü.")
    row = {"at": datetime.now(timezone.utc).isoformat(), "kind": kind,
           "summary": " ".join((summary or "").split())[:180]}
    path = STATE / "activity" / (_user(username) + ".json")
    with _LOCK:
        _atomic(path, (_read(path) + [row])[-100:])


def activities(username: str, day: date) -> list[dict]:
    from zoneinfo import ZoneInfo
    local = ZoneInfo("Europe/Istanbul")
    return [row for row in _read(STATE / "activity" / (_user(username) + ".json"))
            if datetime.fromisoformat(row["at"]).astimezone(local).date() == day]


def notification_settings(username: str) -> dict:
    path = STATE / "notifications" / (_user(username) + ".json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"morning": data.get("morning", True) is True,
            "evening": data.get("evening", True) is True}


def save_notification_settings(username: str, morning: bool, evening: bool) -> dict:
    if type(morning) is not bool or type(evening) is not bool:
        raise ValueError("Bildirim seçimlerini kontrol edin.")
    data = {"morning": morning, "evening": evening}
    _atomic(STATE / "notifications" / (_user(username) + ".json"), data)
    return data


def _memory_thread(username: str) -> str:
    return "personal_" + _user(username)


def _tombstone_path(username: str) -> Path:
    return STATE / "notes" / (_user(username) + ".pending-delete.json")


def _reconcile_deletions(username: str) -> None:
    if STATE.parent != Path("/opt/lcarlie/jarvis-phase2/state"):
        return
    from jarvis import hatira
    path = _tombstone_path(username)
    with _LOCK:
        pending = _read(path)
    if not pending:
        return
    done = []
    for item in pending:
        if hatira.unut_tam(str(item.get("text") or ""), thread=_memory_thread(username)) >= 0:
            done.append(item.get("id"))
    if done:
        with _LOCK:
            _atomic(path, [item for item in _read(path) if item.get("id") not in done])


def _index_note(username: str, text: str) -> bool:
    # The JSON note is authoritative; pgvector is a rebuildable search index.
    if STATE.parent != Path("/opt/lcarlie/jarvis-phase2/state"):
        return False
    from jarvis import hatira
    return hatira.kaydet(text, thread=_memory_thread(username))


def memory_search(username: str, query: str, limit: int = 8) -> dict:
    query = " ".join((query or "").split())[:240]
    rows = personal_notes(username)
    if not query:
        return {"notes": rows[::-1], "method": "recent"}
    if not rows:
        return {"notes": [], "method": "text"}
    active = {str(row.get("text") or "") for row in rows}
    matches = []
    method = "text"
    if STATE.parent == Path("/opt/lcarlie/jarvis-phase2/state"):
        from jarvis import hatira
        _reconcile_deletions(username)
        for text in hatira.ara(query, limit=limit, thread=_memory_thread(username)):
            if text in active and text not in matches:
                matches.append(text)
        if matches:
            method = "meaning"
    for row in reversed(rows):
        value = str(row.get("text") or "")
        if query.casefold() in value.casefold() and value not in matches:
            matches.append(value)
    return {"notes": [row for text in matches[:limit] for row in reversed(rows) if row.get("text") == text][:limit],
            "method": method}


def add_note(username: str, text: str, source: str = "Kullanıcı") -> dict:
    text = " ".join((text or "").split())[:400]
    if not text:
        raise ValueError("Hatırlanacak bilgiyi yazın.")
    row = {"id": uuid.uuid4().hex, "text": text, "source": source[:80],
           "created_at": datetime.now(timezone.utc).isoformat()}
    path = STATE / "notes" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        rows.append(row)
        evicted = rows[:-60]
        _atomic(path, rows[-60:])
        tombstones = _tombstone_path(username)
        retained = {item.get("text") for item in rows[-60:]}
        pending = [item for item in _read(tombstones) if item.get("text") != text]
        pending += [{"id": uuid.uuid4().hex, "text": old.get("text")}
                    for old in evicted if old.get("text") not in retained]
        _atomic(tombstones, pending[-100:])
    try:
        _index_note(username, text)
        _reconcile_deletions(username)
    except Exception:  # noqa: BLE001 - dizin coksa bile kalici not gorunur
        pass  # The durable note remains visible even when the index is down.
    return row


def update_note(username: str, identifier: str, text: str) -> dict:
    text = " ".join((text or "").split())[:400]
    if not text:
        raise ValueError("Hatırlanacak bilgiyi yazın.")
    path = STATE / "notes" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        for row in rows:
            if row.get("id") == identifier:
                old_text = row["text"]
                row["text"] = text
                row["source"] = "Kullanıcı tarafından düzeltildi"
                _atomic(path, rows)
                break
        else:
            raise ValueError("Kişisel bilgi bulunamadı.")
        tombstones = _tombstone_path(username)
        pending = [item for item in _read(tombstones) if item.get("text") != text]
        if old_text != text and not any(item.get("text") == old_text for item in rows):
            pending.append({"id": uuid.uuid4().hex, "text": old_text})
        _atomic(tombstones, pending[-100:])
    try:
        _index_note(username, text)
        _reconcile_deletions(username)
    except Exception:  # noqa: BLE001 - dizin coksa bile kalici not gorunur
        pass
    return dict(row)


def delete_note(username: str, identifier: str) -> bool:
    path = STATE / "notes" / (_user(username) + ".json")
    with _LOCK:
        rows = _read(path)
        removed = [row for row in rows if row.get("id") == identifier]
        kept = [row for row in rows if row.get("id") != identifier]
        if len(kept) == len(rows):
            return False
        _atomic(path, kept)
    if removed and not any(row.get("text") == removed[0].get("text") for row in kept):
        tombstones = _tombstone_path(username)
        with _LOCK:
            pending = _read(tombstones)
            pending.append({"id": uuid.uuid4().hex, "text": removed[0]["text"]})
            _atomic(tombstones, pending[-100:])
        try:
            _reconcile_deletions(username)
        except Exception:  # noqa: BLE001 - arama yetkili satirlara gore suzuyor
            pass  # Search still filters against the authoritative rows.
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
            if image.width * image.height > 16_000_000:
                raise ValueError("Görsel çok büyük. Daha küçük bir dosya seçin.")
            image.verify()
            image = Image.open(io.BytesIO(data)).convert("RGB")
            image.thumbnail((1600, 1600))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
            payload = out.getvalue()
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        except (UnidentifiedImageError, OSError):
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
    """Analyze an uploaded image on the server's local Ollama instance."""
    meta, path = attachment(username, identifier)
    if meta["kind"] != "image":
        raise ValueError("Görsel seçin.")
    image = base64.b64encode(path.read_bytes()).decode("ascii")
    request_body = json.dumps({
        "model": os.environ.get("JARVIS_LOCAL_VISION_MODEL", "qwen3-vl:2b"),
        "stream": False,
        "keep_alive": "0",
        "options": {"num_predict": 420, "num_ctx": 4096},
        "messages": [
            {"role": "system", "content": "Görseli Türkçe, sade ve kısa anlat. Gördüğünle tahmini ayır. Şirket verisi uydurma."},
            {"role": "user", "content": (question or "Bu görselde ne var? Kendini açıkça gösteren sorunları söyle.")[:500],
             "images": [image]},
        ],
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", request_body,
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
        answer = result["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("empty vision answer")
        return answer.strip()[:3000]
    except (HTTPError, URLError, KeyError, ValueError, TimeoutError):
        raise ValueError("Görsel yerel sunucuda analiz edilemedi. Biraz sonra tekrar deneyin.") from None
