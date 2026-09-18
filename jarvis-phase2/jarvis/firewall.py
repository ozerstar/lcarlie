"""Jarvis-side Action Firewall.

This is the EARLY gate, not the authority. The authority is
core.ai_propose_action, which re-validates everything against
core.ai_action_type and the per-type payload schema. This layer exists so a
bad proposal fails closed before it reaches the database, and so Jarvis can
say *why*.

It deliberately keeps NO allowlist of its own: the allowlist is the live
contract loaded from PostgreSQL (see jarvis/action_contract.py). That is what
closes Phase 2C finding F-1.

Payload SHAPE is intentionally left to the database. The per-type schemas live
in the body of core.ai_propose_action and are not machine-readable from here;
mirroring them in Python would recreate exactly the drift this change removes.
What is enforced here are the contract-independent invariants the database
also enforces: object type, forbidden keys, size ceiling.
"""
from __future__ import annotations

import json
from typing import Any

from .action_contract import ActionContract, ContractError, INTENT_TO_CANONICAL

# Same forbidden set as core.ai_jsonb_has_forbidden_key guards against.
FORBIDDEN_KEYS = {"sql", "shell", "command", "url", "webhook", "token", "secret"}
# core.ai_propose_action rejects payloads over 16384 bytes.
MAX_PAYLOAD_BYTES = 16384
# core.ai_propose_action requires this idempotency key prefix.
IDEMPOTENCY_PREFIX = "action:"


class FirewallError(ValueError):
    """A proposal was refused. Always fails closed."""


class ContractDriftError(FirewallError):
    """The canonical contract is unusable; no proposal may be built."""


def known_internal_intents() -> tuple[str, ...]:
    return tuple(sorted(INTENT_TO_CANONICAL))


def validate_proposal(
    internal_intent: Any,
    payload: dict[str, Any],
    contract: ActionContract | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Validate and translate an internal intent into a canonical proposal.

    Returns the envelope the controlled interface needs. Raises on anything
    else -- there is no permissive path.
    """
    if contract is None:
        raise ContractDriftError("CONTRACT_DRIFT: no action contract loaded")
    if not contract.valid:
        raise ContractDriftError(contract.reason or "CONTRACT_DRIFT: contract invalid")

    # Strict: no strip(), no casefold(), no nearest match. "price_change",
    # " PRICE_CHANGE" and "Price_Change" are all unknown actions.
    try:
        canonical = contract.canonical_for(internal_intent)
    except ContractError as exc:
        raise (ContractDriftError(str(exc)) if "CONTRACT_DRIFT" in str(exc)
               else FirewallError(str(exc))) from exc

    action = contract.action(canonical)

    if not isinstance(payload, dict):
        raise FirewallError("payload must be a JSON object")
    found = FORBIDDEN_KEYS.intersection(
        key.casefold() for key in payload if isinstance(key, str)
    )
    if found:
        raise FirewallError(f"forbidden payload keys: {', '.join(sorted(found))}")
    if any(not isinstance(key, str) for key in payload):
        raise FirewallError("payload keys must be strings")

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise FirewallError(f"payload too large: {len(encoded)} > {MAX_PAYLOAD_BYTES}")

    if idempotency_key is not None and not idempotency_key.startswith(IDEMPOTENCY_PREFIX):
        raise FirewallError(f"idempotency key must start with {IDEMPOTENCY_PREFIX!r}")

    return {
        "internal_intent": internal_intent,
        "action_type": canonical,
        "payload": payload,
        "payload_bytes": len(encoded),
        "risk_class": action.risk_class,
        "approval_mode": action.approval_mode,
        "schema_version": action.schema_version,
        "execution_enabled": action.execution_enabled,
        "idempotency_key": idempotency_key,
        "status": "PROPOSED",
        "contract_hash": contract.contract_hash,
        "human_approval_required": True,
    }
