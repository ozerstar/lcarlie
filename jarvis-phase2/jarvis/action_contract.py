"""Canonical action contract: PostgreSQL is the single source of truth.

Phase 2C finding F-1: jarvis/firewall.py carried its own hardcoded action-type
allowlist alongside core.ai_action_type, and the two had drifted to *zero*
overlap -- every proposal the Python layer approved was unpersistable.

The fix is not a better second list. There is now exactly ONE production
allowlist, `core.ai_action_type`, loaded through a fixed allowlisted read.
Python keeps only an explicit, versioned, tested map from its own internal
intent vocabulary onto that contract, and everything fails closed:

  unknown internal intent  -> BLOCK
  unknown canonical type   -> CONTRACT_DRIFT
  missing mapping          -> CONTRACT_DRIFT
  contract not loaded      -> CONTRACT_DRIFT

Nothing is ever silently coerced -- not case, not whitespace, not a near miss.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

# Bump when the mapping below changes. It is part of the contract hash, so a
# stale deployment cannot masquerade as a current one.
CONTRACT_MAP_VERSION = "2026-09-18.2"

# Jarvis internal intent -> canonical core.ai_action_type.action_type
#
# The right-hand side is NOT editable by hand to make a test pass: it must
# name a row that exists in the live contract with proposal_enabled = true,
# and the drift check below proves it on every load.
#
# Two internal intents may map to the same canonical type -- CODE_CHANGE_REVIEW
# reuses REQUEST_HUMAN_REVIEW rather than inventing a new database action type
# for CodingExecutor results; the drift check's unmapped/unknown checks are
# set-based and already tolerate this (see build_contract below).
INTENT_TO_CANONICAL: Mapping[str, str] = {
    "CUSTOMER_REPLY_DRAFT": "DRAFT_CUSTOMER_REPLY",
    "HUMAN_REVIEW_REQUEST": "REQUEST_HUMAN_REVIEW",
    "CODE_CHANGE_REVIEW": "REQUEST_HUMAN_REVIEW",
    # Kreatif partisi de yeni bir DB action type UYDURMAZ: uretilen
    # reklam gorselleri sahibin GOZUYLE bakip karar verecegi bir seydir,
    # yani tam olarak bir insan incelemesi talebidir.
    # Iki asama, iki ayri onay (sahip karari 21.09.2026):
    #   KREATIF_BRIEF    -> brief + promptlar hazir, GORSEL URETIMI icin onay
    #   KREATIF_INCELEME -> gorseller uretildi ve ekip inceledi, YAYIN icin onay
    # Ikisi de ayni kanonik tipe duser cunku ikisi de "insan baksin" talebidir;
    # yeni bir DB action type uydurmak icin sebep yok.
    "KREATIF_BRIEF": "REQUEST_HUMAN_REVIEW",
    "KREATIF_INCELEME": "REQUEST_HUMAN_REVIEW",
    "WHATSAPP_TEMPLATE_SEND": "WHATSAPP_SEND_TEMPLATE",
    "META_CAMPAIGN_CHANGE": "META_CAMPAIGN_CHANGE",
    "PRICE_CHANGE": "PRICE_CHANGE",
    "WIX_PUBLISH": "WIX_PUBLISH",
}

CONTRACT_FIELDS = (
    "action_type", "risk_class", "approval_mode",
    "proposal_enabled", "execution_enabled", "schema_version",
)

# Deterministic selection of an internal intent from a request. Evaluated in
# order, first match wins, and NO match means no action can be built -- the
# request stays a proposal for a human to shape. There is no default.
INTENT_TRIGGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("WHATSAPP_TEMPLATE_SEND", ("whatsapp",)),
    ("WIX_PUBLISH", ("wix", "yayınla", "yayinla", "publish")),
    ("PRICE_CHANGE", ("fiyat", "price")),
    ("META_CAMPAIGN_CHANGE", ("kampanya", "campaign", "meta budget", "reklam")),
    ("CUSTOMER_REPLY_DRAFT", ("müşteriye", "musteriye", "taslak", "draft reply", "cevap yaz")),
    ("HUMAN_REVIEW_REQUEST", ("insana", "human review", "inceleme", "karar gerekiyor")),
)


def propose_intent_for(text: str) -> str | None:
    """Pick the internal intent a request implies, or None. Never guesses."""
    if not isinstance(text, str):
        return None
    lowered = text.casefold()
    for intent, terms in INTENT_TRIGGERS:
        if any(term in lowered for term in terms):
            return intent
    return None


class ContractError(RuntimeError):
    """Raised when the contract cannot be trusted. Always fails closed."""


@dataclass(frozen=True)
class CanonicalAction:
    action_type: str
    risk_class: str
    approval_mode: str
    proposal_enabled: bool
    execution_enabled: bool
    schema_version: str


@dataclass(frozen=True)
class ActionContract:
    actions: Mapping[str, CanonicalAction]
    source: str
    contract_hash: str
    map_version: str
    loaded_at: str
    unknown_internal: tuple[str, ...] = ()
    unknown_canonical: tuple[str, ...] = ()
    valid: bool = False
    reason: str = ""
    load_ms: float = 0.0

    @property
    def canonical_action_count(self) -> int:
        return len(self.actions)

    @property
    def mapped_action_count(self) -> int:
        return sum(1 for name in INTENT_TO_CANONICAL.values() if name in self.actions)

    def canonical_for(self, internal_intent: Any) -> str:
        """Strict lookup. No stripping, no case folding, no fuzzy matching."""
        if not isinstance(internal_intent, str) or internal_intent not in INTENT_TO_CANONICAL:
            raise ContractError(f"unknown internal action: {internal_intent!r}")
        canonical = INTENT_TO_CANONICAL[internal_intent]
        action = self.actions.get(canonical)
        if action is None:
            raise ContractError(f"CONTRACT_DRIFT: canonical type absent: {canonical}")
        if not action.proposal_enabled:
            raise ContractError(f"CONTRACT_DRIFT: proposals disabled for {canonical}")
        return canonical

    def action(self, canonical: str) -> CanonicalAction:
        action = self.actions.get(canonical)
        if action is None:
            raise ContractError(f"CONTRACT_DRIFT: unknown canonical type: {canonical}")
        return action

    def telemetry(self) -> dict[str, Any]:
        return {
            "contract_source": self.source,
            "contract_hash": self.contract_hash,
            "contract_map_version": self.map_version,
            "canonical_action_count": self.canonical_action_count,
            "mapped_action_count": self.mapped_action_count,
            "unknown_internal": list(self.unknown_internal),
            "unknown_canonical": list(self.unknown_canonical),
            "contract_valid": self.valid,
            "contract_reason": self.reason,
            "contract_load_ms": self.load_ms,
        }


def _coerce_bool(value: Any) -> bool:
    # psql -At renders booleans as t/f; row_to_json renders real JSON booleans.
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"t", "true"}
    raise ContractError(f"non-boolean contract flag: {value!r}")


def build_contract(records: list[dict[str, Any]], source: str, load_ms: float = 0.0) -> ActionContract:
    """Turn raw contract rows into a validated contract. Never raises on drift
    -- it returns an invalid contract carrying the reason, so callers can emit
    evidence before failing closed."""
    actions: dict[str, CanonicalAction] = {}
    for row in records:
        missing = [name for name in CONTRACT_FIELDS if name not in row]
        if missing:
            return ActionContract(
                actions={}, source=source, contract_hash="", map_version=CONTRACT_MAP_VERSION,
                loaded_at=datetime.now(timezone.utc).isoformat(), valid=False,
                reason=f"CONTRACT_DRIFT: row missing fields {missing}", load_ms=load_ms,
            )
        action = CanonicalAction(
            action_type=str(row["action_type"]),
            risk_class=str(row["risk_class"]),
            approval_mode=str(row["approval_mode"]),
            proposal_enabled=_coerce_bool(row["proposal_enabled"]),
            execution_enabled=_coerce_bool(row["execution_enabled"]),
            schema_version=str(row["schema_version"]),
        )
        actions[action.action_type] = action

    proposable = {name for name, action in actions.items() if action.proposal_enabled}
    mapped = set(INTENT_TO_CANONICAL.values())

    # a mapping that points at nothing the database will accept
    unknown_internal = tuple(sorted(
        intent for intent, canonical in INTENT_TO_CANONICAL.items() if canonical not in proposable
    ))
    # a proposable database type nothing in Jarvis can reach
    unknown_canonical = tuple(sorted(proposable - mapped))

    digest = sha256()
    digest.update(CONTRACT_MAP_VERSION.encode("utf-8"))
    for name in sorted(actions):
        action = actions[name]
        digest.update(json.dumps(
            [action.action_type, action.risk_class, action.approval_mode,
             action.proposal_enabled, action.execution_enabled, action.schema_version],
            separators=(",", ":"),
        ).encode("utf-8"))

    if not actions:
        valid, reason = False, "CONTRACT_DRIFT: contract is empty or unreadable"
    elif unknown_internal:
        valid, reason = False, f"CONTRACT_DRIFT: mapping targets missing types: {list(unknown_internal)}"
    elif unknown_canonical:
        valid, reason = False, f"CONTRACT_DRIFT: unmapped canonical types: {list(unknown_canonical)}"
    else:
        valid, reason = True, "contract matches mapping"

    return ActionContract(
        actions=actions, source=source, contract_hash=digest.hexdigest(),
        map_version=CONTRACT_MAP_VERSION,
        loaded_at=datetime.now(timezone.utc).isoformat(),
        unknown_internal=unknown_internal, unknown_canonical=unknown_canonical,
        valid=valid, reason=reason, load_ms=round(load_ms, 3),
    )


def load_contract(memory) -> ActionContract:
    """Load the canonical contract through the fixed allowlisted read."""
    evidence = memory.get_action_contract()
    return build_contract(evidence.records, source=evidence.source, load_ms=evidence.latency_ms)


class ContractCache:
    """One contract load per runner, refreshed on TTL. Keeps the drift check
    off the hot path without ever letting it go stale silently."""

    def __init__(self, memory, ttl_s: float = 60.0):
        self.memory = memory
        self.ttl_s = ttl_s
        self._contract: ActionContract | None = None
        self._loaded_monotonic: float = 0.0

    def get(self, now: float | None = None) -> ActionContract:
        from time import monotonic
        current = monotonic() if now is None else now
        if self._contract is not None and (current - self._loaded_monotonic) < self.ttl_s:
            return self._contract
        self._contract = load_contract(self.memory)
        self._loaded_monotonic = current
        return self._contract

    def invalidate(self) -> None:
        self._contract = None
