from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import BoundedSemaphore
from time import monotonic


@dataclass(frozen=True)
class ResourceBudget:
    max_concurrency: int = 2
    timeout_s: float = 8.0
    memory_mb: int = 256
    cpu_units: float = 1.0


class ResourceGovernor:
    def __init__(self, budget: ResourceBudget):
        self.budget = budget
        self._slots = BoundedSemaphore(budget.max_concurrency)

    @contextmanager
    def slot(self):
        if not self._slots.acquire(timeout=self.budget.timeout_s):
            raise TimeoutError("resource backpressure timeout")
        started = monotonic()
        try:
            yield
            if monotonic() - started > self.budget.timeout_s:
                raise TimeoutError("resource execution timeout")
        finally:
            self._slots.release()
