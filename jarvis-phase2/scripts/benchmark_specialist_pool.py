from __future__ import annotations

import json

from jarvis.specialist_pool import benchmark_routing


if __name__ == "__main__":
    domains = ("sales", "ecommerce", "advertising", "crm", "operations")
    print(json.dumps(benchmark_routing(domains), ensure_ascii=False, indent=2))
