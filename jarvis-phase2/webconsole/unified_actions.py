"""One owner-scoped read surface for company and personal actions."""
from __future__ import annotations

import re

import google_workspace
import personal_action_store


def parse_key(key: str) -> tuple[str, str]:
    match = re.fullmatch(r"(company|personal):([0-9a-f]{32}|[0-9]+)", str(key))
    if not match:
        raise ValueError("Geçersiz işlem kimliği.")
    source, identifier = match.groups()
    if source == "company" and not identifier.isdecimal():
        raise ValueError("Geçersiz şirket işlemi.")
    if source == "personal" and not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Geçersiz kişisel işlem.")
    return source, identifier


def _public(row: dict) -> dict:
    personal = row["source"] == "personal"
    payload = row["payload"]
    result = {
        "key": row["action_key"], "source": row["source"],
        "action_id": row["source_id"] if personal else int(row["source_id"]),
        "kind": row["kind"], "action_type": row["kind"],
        "description": row["description"], "payload": payload,
        "risk_class": row["risk_level"], "status": row["status"],
        "fingerprint": row["payload_hash"],
        "proposed_at": row["created_at"].isoformat(),
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }
    if personal:
        result["details"] = google_workspace._approval_details(
            row["kind"], payload, row["description"])
        creative_id = payload.get("creative_id") if row["kind"] == "drive.upload" else None
        result["preview_url"] = "/kreatif/" + creative_id if creative_id else None
        result["payload"] = {"reason": result["details"]}
    return result


def list_pending(username: str) -> list[dict]:
    personal_action_store.list_visible(username.strip().lower())
    with personal_action_store._connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT * FROM core.jarvis_action_registry
            WHERE (source='company' OR (source='personal' AND owner=%s))
              AND ((status='AWAITING_APPROVAL' AND expires_at>clock_timestamp())
                   OR status='UNCERTAIN')
            ORDER BY created_at DESC LIMIT 100''', (username.strip().lower(),))
        rows = cur.fetchall()
    return [_public(row) for row in rows]


def inspect(username: str, key: str) -> dict | None:
    source, identifier = parse_key(key)
    if source == "personal":
        personal_action_store.list_visible(username.strip().lower())
    with personal_action_store._connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT * FROM core.jarvis_action_registry
            WHERE action_key=%s AND source=%s
              AND (source='company' OR (source='personal' AND owner=%s))
              AND ((status='AWAITING_APPROVAL' AND expires_at>clock_timestamp())
                   OR status='UNCERTAIN')''',
            (f"{source}:{identifier}", source, username.strip().lower()))
        row = cur.fetchone()
    return _public(row) if row else None
