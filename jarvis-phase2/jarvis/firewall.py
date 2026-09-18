from __future__ import annotations

from typing import Any


ALLOWED_ACTIONS = {
    "CRM_REPLY_DRAFT",
    "META_BUDGET_CHANGE_PROPOSAL",
    "WIX_PRICE_CHANGE_PROPOSAL",
    "CONTENT_CHANGE_PROPOSAL",
    "DATA_QUALITY_INVESTIGATION",
}
FORBIDDEN_KEYS = {"sql", "shell", "command", "url", "webhook", "token", "secret"}


def validate_proposal(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError("unknown action type")
    found = FORBIDDEN_KEYS.intersection(k.casefold() for k in payload)
    if found:
        raise ValueError(f"forbidden payload keys: {', '.join(sorted(found))}")
    return {"action_type": action_type, "payload": payload, "status": "PROPOSED"}
