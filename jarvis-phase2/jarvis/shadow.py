from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from time import perf_counter

from .context import ContextCompiler
from .memory import CompanyMemory
from .phase2 import Phase2Runtime
from .transport import memory_host


INJECTION_TERMS = ("ignore policy", "approve yourself", "set role", "run shell", "reveal secret")
SELF_MOD_TERMS = ("production kodunu", "modify production", "change your own permissions")


def require_shadow_environment() -> None:
    required = {
        "JARVIS_ENABLED": "true",
        "JARVIS_MODE": "SHADOW",
        "EXTERNAL_ACTIONS": "false",
    }
    invalid = [key for key, value in required.items() if os.environ.get(key) != value]
    if invalid:
        raise RuntimeError("SHADOW_ENVIRONMENT_REQUIRED:" + ",".join(invalid))


class ShadowRunner:
    def __init__(self, runtime: Phase2Runtime):
        self.runtime = runtime

    def handle(self, intent: str) -> dict:
        require_shadow_environment()
        started = perf_counter()
        text = intent.casefold()
        result = self.runtime.handle(intent)
        if any(term in text for term in INJECTION_TERMS):
            result["envelope"]["risk"] = "CRITICAL"
            result["envelope"]["status"] = "BLOCKED"
            result["plan"]["status"] = "BLOCKED"
            result["plan"]["route"] = "policy-block"
        elif any(term in text for term in SELF_MOD_TERMS):
            result["envelope"]["risk"] = "HIGH"
            result["envelope"]["status"] = "PROPOSED"
            result["plan"]["status"] = "PROPOSED"
            result["plan"]["route"] = "development-proposal-only"
        result["shadow"] = {
            "mode": "SHADOW",
            "action_path": ["REQUEST", "PLAN", "RISK", result["envelope"]["status"], "STOP"],
            "external_actions": False,
            "external_provider_calls": 0,
            "production_code_mutated": False,
            "human_approval_required": result["envelope"]["status"] == "PROPOSED",
        }
        result["telemetry"] = {
            "queue_wait_ms": 0.0,
            "db_ms": result["context"]["compile_ms"],
            "context_compile_ms": result["context"]["compile_ms"],
            "retrieval_ms": result["context"]["compile_ms"],
            "planner_ms": 0.0,
            "router_ms": 0.0,
            "state_ms": 0.0,
            "total_ms": round((perf_counter() - started) * 1000, 3),
            "mode": result["envelope"]["mode"],
            "model_calls": 0,
            "cache_hit": False,
            "fallback_count": 0,
            "success": True,
        }
        return result


def main() -> None:
    require_shadow_environment()
    intent = " ".join(sys.argv[1:]).strip()
    if not intent:
        raise RuntimeError("intent required")
    runner = ShadowRunner(Phase2Runtime(ContextCompiler(CompanyMemory(host=memory_host()))))
    print(json.dumps(runner.handle(intent), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
