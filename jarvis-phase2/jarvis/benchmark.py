from __future__ import annotations

from time import perf_counter

from .runtime import respond


def run_fake(iterations: int = 100) -> dict[str, float | int | str]:
    samples = []
    for _ in range(iterations):
        started = perf_counter()
        respond("show capability registry")
        samples.append((perf_counter() - started) * 1000)
    samples.sort()
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    return {"candidate": "deterministic-fake", "iterations": iterations, "p95_ms": round(p95, 3), "status": "PASS"}
