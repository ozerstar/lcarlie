from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    generation: int


class QueryCache:
    def __init__(self, ttl_s: float = 30.0):
        self.ttl_s = ttl_s
        self.generation = 0
        self._items: dict[str, CacheEntry] = {}

    def get_or_load(self, key: str, loader: Callable[[], Any]) -> tuple[Any, bool]:
        now = monotonic()
        entry = self._items.get(key)
        if entry and entry.expires_at > now and entry.generation == self.generation:
            return entry.value, True
        value = loader()
        self._items[key] = CacheEntry(value, now + self.ttl_s, self.generation)
        return value, False

    def invalidate(self) -> None:
        self.generation += 1


SemanticCache = QueryCache
ResearchCache = QueryCache
