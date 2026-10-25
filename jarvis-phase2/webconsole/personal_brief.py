"""Owner-scoped morning briefing preferences and deterministic preview."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import mobile_features

try:
    ZONE = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    # Windows development environments may lack the IANA timezone database.
    ZONE = timezone(timedelta(hours=3))
STATE = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "mobile"
_LOCK = threading.RLock()


def _owner(username: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", username)[:60] or "operator"


def _path() -> Path:
    return STATE / "morning-settings.json"


def _read() -> dict:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def settings(username: str) -> dict:
    row = _read().get(_owner(username), {})
    time = row.get("time", "07:30")
    if not isinstance(time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        time = "07:30"
    return {"enabled": row.get("enabled") is True, "time": time}


def save_settings(username: str, enabled: bool, time: str) -> dict:
    if not isinstance(enabled, bool) or not isinstance(time, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", time
    ):
        raise ValueError("Geçerli bir saat seçin.")
    with _LOCK:
        rows = _read()
        rows[_owner(username)] = {"enabled": enabled, "time": time}
        STATE.mkdir(parents=True, exist_ok=True)
        os.chmod(STATE, 0o750)
        temp = _path().with_name(".morning-settings-" + uuid.uuid4().hex)
        try:
            temp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            os.chmod(temp, 0o600)
            os.replace(temp, _path())
        finally:
            temp.unlink(missing_ok=True)
    return settings(username)


def briefing(username: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(ZONE)
    today = now.date()
    upcoming = []
    for item in mobile_features.reminders(username):
        try:
            due = datetime.fromisoformat(item["due_at"]).astimezone(ZONE)
        except (KeyError, TypeError, ValueError):
            continue
        if due.date() == today and due >= now:
            upcoming.append({"id": item["id"], "text": item["text"],
                             "time": due.strftime("%H:%M")})
    upcoming.sort(key=lambda item: item["time"])
    return {"date": today.isoformat(), "reminders": upcoming[:20],
            "total_reminders": len(upcoming), "settings": settings(username)}


def morning_due(config: dict, now: datetime) -> bool:
    if config.get("enabled") is not True:
        return False
    local = now.astimezone(ZONE)
    hour, minute = map(int, config["time"].split(":"))
    elapsed = local.hour * 60 + local.minute - (hour * 60 + minute)
    return 0 <= elapsed < 30
