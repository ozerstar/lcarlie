"""One operator-facing queue across company and personal action contracts.

The database registry audits both sources. Each source retains its existing
authorization and executor; this module never grants a model approval rights.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import google_workspace


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


def company_item(row: dict) -> dict:
    payload = row.get("payload") or {}
    return {**row, "key": f"company:{row['action_id']}", "source": "company",
            "status": "AWAITING_APPROVAL", "description": str(payload.get("reason") or "").strip(),
            "fingerprint": row.get("fingerprint")}


def personal_item(row: dict) -> dict:
    expires = row.get("expires_at")
    if isinstance(expires, (int, float)):
        expires = datetime.fromtimestamp(expires, timezone.utc).isoformat()
    return {**row, "key": f"personal:{row['id']}", "source": "personal",
            "risk_class": "HIGH" if row.get("kind") == "gmail.send" else "MEDIUM",
            "proposed_at": None, "expires_at": expires,
            "payload": {"reason": row.get("details") or row.get("description")}}


def list_pending(operator, username: str) -> list[dict]:
    company = [company_item(row) for row in operator.list_pending()]
    personal = [personal_item(row) for row in google_workspace.pending_actions(username)]
    return company + personal


def inspect(operator, username: str, key: str) -> dict | None:
    source, identifier = parse_key(key)
    if source == "company":
        row = operator.inspect(int(identifier))
        return company_item(row) if row else None
    for row in google_workspace.pending_actions(username):
        if row["id"] == identifier:
            return personal_item(row)
    return None
