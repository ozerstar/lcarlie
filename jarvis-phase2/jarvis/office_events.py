"""Bounded, read-only event source for the operator's 3D office.

Writers only append short status records. No model output, credentials, or
raw evidence is sent to browsers. The authenticated web console tails this
file to show work that is actually underway.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MAX_FIELD = 220
MAX_TAIL = 2_000_000


def path() -> Path:
    return Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "office-events.jsonl"


def emit(kind: str, *, member_key: str = "", status: str = "", task: str = "",
         run_id: str = "", capability: str = "") -> None:
    """Append one complete JSON line; event recording never blocks a task."""
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": str(kind)[:40],
        "member_key": str(member_key)[:80],
        "status": str(status)[:40],
        "task": " ".join(str(task).split())[:MAX_FIELD],
        "run_id": str(run_id)[:100],
        "capability": str(capability)[:80],
    }
    try:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o660)
        try:
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o660)
            except PermissionError:
                pass
            try:
                import grp
                os.fchown(fd, -1, grp.getgrnam("jarvis-web").gr_gid)
            except (ImportError, KeyError, PermissionError):
                pass
            os.write(fd, (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass


def recent(limit: int = 500) -> list[dict]:
    """Return recent complete events without reading an unbounded log."""
    target = path()
    try:
        with target.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            start = max(0, size - MAX_TAIL)
            stream.seek(start)
            if start:
                stream.readline()
            lines = stream.readlines()
    except OSError:
        return []
    events = []
    for line in lines[-max(1, min(limit, 1000)):]:
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except (ValueError, UnicodeDecodeError):
            continue
    return events


def active_members(now: datetime | None = None) -> dict[str, dict]:
    """Keep only fresh WORKING events; interrupted work expires in ten minutes."""
    now = now or datetime.now(timezone.utc)
    latest: dict[str, dict] = {}
    for event in recent(1000):
        key = event.get("member_key")
        if key:
            latest[str(key)] = event
    active = {}
    for key, event in latest.items():
        if event.get("status") != "WORKING":
            continue
        try:
            age = (now - datetime.fromisoformat(event["at"])).total_seconds()
        except (ValueError, TypeError, KeyError):
            continue
        if 0 <= age < 600:
            active[key] = event
    return active
