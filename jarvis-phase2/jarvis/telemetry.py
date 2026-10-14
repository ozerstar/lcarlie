from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median


@dataclass
class Telemetry:
    samples: list[dict[str, float | int | str | bool]] = field(default_factory=list)

    def record(self, **sample):
        self.samples.append(sample)

    def percentile(self, field_name: str, percentile: float) -> float:
        values = sorted(float(row[field_name]) for row in self.samples if field_name in row)
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int((len(values) - 1) * percentile)))
        return round(values[index], 3)

    def summary(self, field_name: str = "total_ms") -> dict[str, float]:
        values = [float(row[field_name]) for row in self.samples if field_name in row]
        return {"p50": round(median(values), 3) if values else 0.0,
                "p95": self.percentile(field_name, 0.95)}
