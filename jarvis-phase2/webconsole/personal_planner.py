"""Owner-scoped, read-only personal day and evening views."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import google_workspace
import mobile_features

LOCAL = ZoneInfo("Europe/Istanbul")


def _local_date(value: str):
    if len(value) == 10:
        return datetime.fromisoformat(value).date()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LOCAL).date()


def overview(username: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(LOCAL)).astimezone(LOCAL)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    reminders = mobile_features.reminders(username)
    due = []
    next_day = []
    overdue = []
    for row in reminders:
        try:
            day = _local_date(row["due_at"])
        except (ValueError, KeyError, TypeError):
            continue
        if day == today:
            due.append(row)
        elif day == tomorrow:
            next_day.append(row)
        elif day < today:
            overdue.append(row)

    calendar_connected = google_workspace.status(username)["connected"]
    calendar_error = False
    events = []
    if calendar_connected:
        try:
            events = google_workspace.calendar_events(username)
        except google_workspace.GoogleError:
            calendar_error = True
    today_events = []
    tomorrow_events = []
    for row in events:
        try:
            day = _local_date(row["start"])
        except (ValueError, KeyError, TypeError):
            continue
        if day == today:
            today_events.append(row)
        elif day == tomorrow:
            tomorrow_events.append(row)

    return {"date": today.isoformat(), "today_events": today_events,
            "tomorrow_events": tomorrow_events,
            "today_reminders": due, "tomorrow_reminders": next_day,
            "overdue_reminders": overdue,
            "special_days": mobile_features.special_days(username, today),
            "pending": google_workspace.pending_actions(username),
            "activities": mobile_features.activities(username, today),
            "calendar_connected": calendar_connected, "calendar_error": calendar_error}
