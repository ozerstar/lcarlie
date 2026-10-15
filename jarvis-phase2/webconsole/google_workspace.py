"""Owner-scoped Google tools. Every write is prepared and explicitly decided."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import personal_action_store as action_store

STATE = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "mobile" / "google"
REDIRECT = "https://jarvis.lcarlie.shop/google/callback"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
)
DRIVE_WRITE_SCOPE = "https://www.googleapis.com/auth/drive.file"
CREATIVE_ROOT = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "kreatif-brief"
_LOCK = threading.RLock()


class GoogleError(ValueError):
    pass


def _user(username: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", username)[:60] or "operator"


def _path(username: str) -> Path:
    return STATE / ("token-" + _user(username) + ".json")


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"))


def status(username: str) -> dict:
    token = _read(_path(username), {})
    connected = configured() and bool(token.get("refresh_token"))
    return {"configured": configured(), "connected": connected,
            "drive_write": connected and DRIVE_WRITE_SCOPE in token.get("scope", []),
            "services": ["Takvim", "E-posta", "Drive"] if connected else []}


def start(username: str) -> str:
    if not configured():
        raise GoogleError("Google bağlantısı henüz kurulmadı.")
    nonce = secrets.token_urlsafe(32)
    with _LOCK:
        pending = _read(STATE / "oauth-pending.json", {})
        pending = {k: v for k, v in pending.items() if v.get("expires", 0) > time.time()}
        pending[nonce] = {"user": _user(username), "expires": time.time() + 900}
        _write(STATE / "oauth-pending.json", pending)
    params = {"client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"], "redirect_uri": REDIRECT,
              "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline",
              "prompt": "consent", "state": nonce}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _http_json(url: str, *, data: dict | None = None, bearer: str | None = None,
               method: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read(2_000_000))
    except (HTTPError, URLError, ValueError) as exc:
        raise GoogleError("Google işlemi tamamlanamadı. Bağlantıyı kontrol edin.") from exc


def _token_request(data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read(100_000))
    except (HTTPError, URLError, ValueError) as exc:
        raise GoogleError("Google hesabı bağlanamadı. Tekrar deneyin.") from exc


def callback(code: str, state: str) -> str:
    if not code or not state or not configured():
        raise GoogleError("Bağlantı bilgisi eksik.")
    with _LOCK:
        pending = _read(STATE / "oauth-pending.json", {})
        row = pending.pop(state, None)
        _write(STATE / "oauth-pending.json", pending)
    if not row or row.get("expires", 0) < time.time():
        raise GoogleError("Bağlantı süresi doldu. Tekrar başlayın.")
    token = _token_request({"code": code, "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                            "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
                            "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    old = _read(_path(row["user"]), {})
    refresh = token.get("refresh_token") or old.get("refresh_token")
    granted = set((token.get("scope") or "").split())
    if not refresh or not set(SCOPES).issubset(granted):
        raise GoogleError("Gerekli izinler verilmedi. Bağlantıyı yeniden başlatın.")
    _write(_path(row["user"]), {"refresh_token": refresh, "access_token": token["access_token"],
                                "expires": time.time() + int(token.get("expires_in", 3600)) - 60,
                                "scope": list(granted)})
    return row["user"]


def disconnect(username: str) -> None:
    path = _path(username)
    row = _read(path, {})
    token = row.get("refresh_token")
    path.unlink(missing_ok=True)
    if token:
        try:
            request = urllib.request.Request("https://oauth2.googleapis.com/revoke",
                data=urllib.parse.urlencode({"token": token}).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            urllib.request.urlopen(request, timeout=10).close()
        except (HTTPError, URLError):
            pass  # Local use is cut off; Google account settings can revoke the grant.


def _access_token(username: str) -> str:
    with _LOCK:
        if not configured():
            raise GoogleError("Google bağlantısı şu anda kullanılamıyor.")
        row = _read(_path(username), {})
        if not row.get("refresh_token"):
            raise GoogleError("Önce Google hesabınızı bağlayın.")
        if row.get("access_token") and row.get("expires", 0) > time.time():
            return row["access_token"]
        token = _token_request({"refresh_token": row["refresh_token"],
                                "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                                "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
                                "grant_type": "refresh_token"})
        row["access_token"] = token["access_token"]
        row["expires"] = time.time() + int(token.get("expires_in", 3600)) - 60
        _write(_path(username), row)
        return row["access_token"]


def _calendar_items(username: str, start: datetime, end: datetime) -> list[dict]:
    params = urllib.parse.urlencode({"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                                     "maxResults": 100, "singleEvents": "true", "orderBy": "startTime"})
    data = _http_json("https://www.googleapis.com/calendar/v3/calendars/primary/events?" + params,
                      bearer=_access_token(username))
    return data.get("items", [])


def _is_birthday(event: dict) -> bool:
    title = (event.get("summary") or "").casefold()
    return event.get("eventType") == "birthday" or "doğum günü" in title or "birthday" in title


def birthday_events_today(username: str) -> list[dict]:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return [event for event in _calendar_items(username, today, today + timedelta(days=1))
            if _is_birthday(event)]


def calendar_events(username: str) -> list[dict]:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    today = now.date()
    items = _calendar_items(username, now.replace(hour=0, minute=0, second=0, microsecond=0),
                            now + timedelta(days=30))
    visible = [event for event in items if not _is_birthday(event) or
               ((event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or "")[:10] == today.isoformat()]
    return [{"title": event.get("summary") or "Başlıksız etkinlik",
             "start": (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")}
            for event in visible[:10]]


def drive_files(username: str, query: str = "") -> list[dict]:
    needle = (query or "").strip()[:100]
    drive_query = "trashed = false"
    if needle:
        escaped = needle.replace("\\", "\\\\").replace("'", "\\'")
        drive_query += f" and name contains '{escaped}'"
    params = urllib.parse.urlencode({"pageSize": 20, "fields": "files(id,name,mimeType,webViewLink),nextPageToken",
                                     "q": drive_query, "orderBy": "modifiedTime desc"})
    data = _http_json("https://www.googleapis.com/drive/v3/files?" + params,
                      bearer=_access_token(username))
    return [{"id": x.get("id"), "name": x.get("name"), "mime_type": x.get("mimeType"),
             "url": x.get("webViewLink")}
            for x in data.get("files", [])]


def import_drive_file(username: str, identifier: str) -> dict:
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", identifier):
        raise GoogleError("Geçerli bir Drive dosyası seçin.")
    token = _access_token(username)
    base = "https://www.googleapis.com/drive/v3/files/" + urllib.parse.quote(identifier, safe="")
    meta = _http_json(base + "?fields=id,name,mimeType,size", bearer=token)
    kind = meta.get("mimeType")
    name = str(meta.get("name") or "Drive dosyası")[:100]
    if kind == "application/vnd.google-apps.document":
        url = base + "/export?mimeType=text%2Fplain"
        name += ".txt"
    elif kind == "application/vnd.google-apps.spreadsheet":
        url = base + "/export?mimeType=text%2Fcsv"
        name += ".csv"
    elif kind == "application/vnd.google-apps.presentation":
        url = base + "/export?mimeType=application%2Fpdf"
        name += ".pdf"
    elif kind in ("application/pdf", "text/plain", "text/csv", "text/markdown",
                  "image/jpeg", "image/png", "image/webp"):
        if int(meta.get("size") or 0) > 5 * 1024 * 1024:
            raise GoogleError("Dosya 5 MB sınırını aşıyor.")
        url = base + "?alt=media"
    else:
        raise GoogleError("Bu dosya türü henüz okunamıyor. PDF, metin, görsel veya Google dokümanı seçin.")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(5 * 1024 * 1024 + 1)
    except (HTTPError, URLError) as exc:
        raise GoogleError("Drive dosyası şu anda okunamadı.") from exc
    if len(data) > 5 * 1024 * 1024:
        raise GoogleError("Dosya 5 MB sınırını aşıyor.")
    from mobile_features import upload
    try:
        return upload(username, name, data)
    except (ValueError, ImportError) as exc:
        raise GoogleError(str(exc)) from exc


def _creative_path(identifier: str) -> Path:
    if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+-gorseller/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)", identifier, re.I):
        raise GoogleError("Geçerli bir ekip görseli seçin.")
    path = CREATIVE_ROOT / identifier
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        raise GoogleError("Ekip görseli bulunamadı.")
    if path.stat().st_size > 5 * 1024 * 1024:
        raise GoogleError("Görsel 5 MB sınırını aşıyor.")
    return path


def creative_files() -> list[dict]:
    files = sorted(CREATIVE_ROOT.glob("*-gorseller/*"),
                   key=lambda item: item.stat().st_mtime if item.is_file() else 0, reverse=True)
    result = []
    for path in files:
        identifier = path.relative_to(CREATIVE_ROOT).as_posix()
        try:
            _creative_path(identifier)
        except GoogleError:
            continue
        result.append({"id": identifier, "name": path.name, "group": path.parent.name,
                       "preview_url": "/kreatif/" + identifier})
        if len(result) == 30:
            break
    return result


def _upload_drive_attachment(username: str, payload: dict, token: str) -> dict:
    try:
        if payload.get("creative_id"):
            path = _creative_path(payload["creative_id"])
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != payload["sha256"]:
                raise GoogleError("Görsel onaydan sonra değişti. Yeniden hazırlayın.")
            mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
        else:
            from mobile_features import attachment
            meta, path = attachment(username, payload["attachment_id"])
            content = path.read_bytes()
            mime = {"image": "image/jpeg", "pdf": "application/pdf", "text": "text/plain"}.get(meta["kind"])
    except GoogleError:
        raise
    except (ValueError, OSError, KeyError) as exc:
        raise GoogleError("Kaydedilecek dosya bulunamadı.") from exc
    if len(content) > 5 * 1024 * 1024:
        raise GoogleError("Dosya 5 MB sınırını aşıyor.")
    if not mime:
        raise GoogleError("Bu dosya türü Drive'a kaydedilemiyor.")
    boundary = "jarvis_" + secrets.token_hex(16)
    metadata = {"name": payload["name"]}
    if payload.get("folder_id"):
        metadata["parents"] = [payload["folder_id"]]
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
            + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
            + content + f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink",
        data=body, headers={"Authorization": "Bearer " + token,
                            "Content-Type": "multipart/related; boundary=" + boundary}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.loads(response.read(100_000))
    except (HTTPError, URLError, ValueError) as exc:
        raise GoogleError("Drive'a kaydetme tamamlanamadı. Klasör erişimini kontrol edin.") from exc


def pending_actions(username: str) -> list[dict]:
    try:
        rows = action_store.list_visible(_user(username))
    except Exception as exc:
        raise GoogleError("Onaylar şu anda okunamıyor. İşlem tekrar edilmedi.") from exc
    return [{"id": row["action_id"],
             "description": row["description"].removeprefix("KIRMIZI UYARI · "),
             "kind": row["kind"], "status": row["status"],
             "fingerprint": row["payload_hash"],
             "expires_at": row["expires_at"].timestamp(),
             "preview_url": "/kreatif/" + row["payload"]["creative_id"]
             if row["kind"] == "drive.upload" and row["payload"].get("creative_id") else None}
            for row in rows]


def prepare(username: str, kind: str, fields: dict,
            request_id: str | None = None) -> dict:
    if not status(username)["connected"]:
        raise GoogleError("Önce Google hesabınızı bağlayın.")
    if kind == "calendar.create":
        title = " ".join(str(fields.get("title") or "").split())[:160]
        try:
            start = datetime.fromisoformat(str(fields.get("start") or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(fields.get("end") or "").replace("Z", "+00:00"))
        except ValueError:
            raise GoogleError("Geçerli bir başlangıç ve bitiş saati seçin.") from None
        if not title or not start.tzinfo or not end.tzinfo or start < datetime.now(timezone.utc) or not timedelta(minutes=5) <= end-start <= timedelta(days=1):
            raise GoogleError("Başlık ve uygun bir gelecek saat seçin.")
        payload = {"summary": title, "start": {"dateTime": start.isoformat()},
                   "end": {"dateTime": end.isoformat()}}
        description = f"Takvime '{title}' eklenecek: {start.astimezone().strftime('%d.%m.%Y %H:%M')}"
    elif kind == "gmail.send":
        recipient = str(fields.get("to") or "").strip()
        subject = " ".join(str(fields.get("subject") or "").split())[:160]
        body = str(fields.get("body") or "").strip()[:5000]
        if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", recipient) or not subject or not body:
            raise GoogleError("Alıcı, konu ve mesaj metnini kontrol edin.")
        payload = {"to": recipient, "subject": subject, "body": body}
        description = f"E-posta gönderilecek: {recipient} · {subject}\n\n{body}"
    elif kind == "drive.upload":
        if not status(username)["drive_write"]:
            raise GoogleError("Drive'a kaydetmek için Google hesabını yeniden bağlayıp dosya iznini verin.")
        creative_id = fields.get("creative_id")
        if creative_id:
            path = _creative_path(creative_id)
            name = path.name
            source = {"creative_id": creative_id, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        else:
            from mobile_features import attachment
            identifier = str(fields.get("attachment_id") or "")
            try:
                meta, path = attachment(username, identifier)
                if not path.is_file():
                    raise ValueError("Dosya bulunamadı.")
            except ValueError as exc:
                raise GoogleError("Kaydedilecek dosya bulunamadı.") from exc
            name = Path(str(meta["name"])).stem[:80] + meta["suffix"]
            source = {"attachment_id": identifier}
        folder_id = str(fields.get("folder_id") or "").strip()
        if folder_id and not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", folder_id):
            raise GoogleError("Geçerli bir Drive klasör bağlantısı girin.")
        payload = {**source, "folder_id": folder_id, "name": name}
        description = f"Drive'a yeni dosya yüklenecek: {name} · " + ("Seçilen klasör" if folder_id else "Drive ana dizini")
    else:
        raise GoogleError("Bilinmeyen işlem.")
    try:
        proposal = action_store.create(_user(username), kind, payload, description,
                                       idempotency_key=request_id)
    except action_store.ActionConflict as exc:
        raise GoogleError(str(exc)) from exc
    except Exception as exc:
        raise GoogleError("İşlem kaydedilemedi; Google'a hiçbir şey gönderilmedi.") from exc
    return {**proposal, "preview_url": "/kreatif/" + payload["creative_id"]
            if kind == "drive.upload" and payload.get("creative_id") else None}


def decide(username: str, identifier: str, decision: str,
           shown_fingerprint: str | None = None) -> dict:
    if decision not in ("APPROVED", "REJECTED"):
        raise GoogleError("Onayla veya reddet seçin.")
    owner = _user(username)
    try:
        approved, payload = action_store.decide(owner, identifier, decision,
                                                shown_fingerprint)
    except action_store.ActionConflict as exc:
        raise GoogleError(str(exc)) from exc
    except Exception as exc:
        raise GoogleError("Karar kaydedilemedi; Google'a hiçbir şey gönderilmedi.") from exc
    if decision == "REJECTED":
        return {"status": "REJECTED", "message": "İşlem iptal edildi."}
    try:
        token = _access_token(username)
        if approved["kind"] == "calendar.create":
            result = _http_json("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                                data=payload, bearer=token, method="POST")
            message = "Etkinlik takvime eklendi."
        elif approved["kind"] == "gmail.send":
            data = payload
            email = EmailMessage()
            email["To"] = data["to"]
            email["Subject"] = data["subject"]
            email.set_content(data["body"])
            raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii").rstrip("=")
            result = _http_json("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                                data={"raw": raw}, bearer=token, method="POST")
            message = "E-posta gönderildi."
        elif approved["kind"] == "drive.upload":
            result = _upload_drive_attachment(username, payload, token)
            message = "Dosya Drive'a yeni kopya olarak kaydedildi."
        else:
            raise GoogleError("Bilinmeyen işlem.")
        final = "COMPLETED"
    except Exception:
        result, message, final = {}, ("Sonuç belirsiz. Google hesabında kontrol edin; "
                                      "otomatik tekrar yapılmadı."), "UNCERTAIN"
    try:
        action_store.finish(owner, identifier, final, message, result.get("id"))
    except Exception as exc:
        raise GoogleError("Sonuç kaydı doğrulanamadı; işlemi tekrar etmeyin, Google hesabında kontrol edin.") from exc
    return {"status": "DONE" if final == "COMPLETED" else final,
            "message": message, "external_id": result.get("id")}
