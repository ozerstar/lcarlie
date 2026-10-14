from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any


class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_LOW = "QUOTA_LOW"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class Provider:
    name: str
    capabilities: set[str]
    tier: int
    state: ProviderState
    execute: Callable[[dict[str, Any]], dict[str, Any]]


class CapabilityRouter:
    """RouteLabs-compatible boundary; routing never owns authorization."""

    def __init__(self, providers: list[Provider]):
        self.providers = providers

    def run(self, capability: str, envelope: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        attempts = []
        for provider in sorted(self.providers, key=lambda item: item.tier):
            if capability not in provider.capabilities or provider.state != ProviderState.AVAILABLE:
                continue
            attempts.append(provider.name)
            try:
                return provider.execute(envelope), attempts
            except (TimeoutError, ConnectionError):
                continue
        raise RuntimeError("no provider completed capability")
