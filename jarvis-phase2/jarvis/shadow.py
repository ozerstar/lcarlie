from __future__ import annotations

import json
import os
import sys
from time import perf_counter

from .action_contract import ContractCache
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
    def __init__(self, runtime: Phase2Runtime, contract_cache: ContractCache | None = None):
        self.runtime = runtime
        # Phase 2D / F-1: the canonical contract is loaded once per runner and
        # re-checked on TTL, so drift cannot go unnoticed but the check stays
        # off the hot path.
        self.contract_cache = contract_cache if contract_cache is not None else ContractCache(
            runtime.compiler.memory
        )
        # Preflight: load and drift-check the contract now, so the first
        # request does not pay for it and a broken contract is visible before
        # any work is accepted. A failure here is recorded, never fatal --
        # handle() fails closed on its own.
        self.preflight_error = ""
        try:
            self.contract_cache.get()
        except Exception as exc:  # noqa: BLE001
            self.preflight_error = f"{type(exc).__name__}: {exc}"

    def handle(self, intent: str) -> dict:
        require_shadow_environment()
        started = perf_counter()
        text = intent.casefold()

        contract_started = perf_counter()
        try:
            contract = self.contract_cache.get()
            contract_error = ""
        except Exception as exc:  # noqa: BLE001 - a failed load must fail closed, not crash
            contract, contract_error = None, f"{type(exc).__name__}: {exc}"
        contract_check_ms = round((perf_counter() - contract_started) * 1000, 3)

        result = self.runtime.handle(intent, contract=contract)

        contract_valid = bool(contract is not None and contract.valid)
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
        elif not contract_valid and result["envelope"]["status"] == "PROPOSED":
            # No action may be proposed while the canonical contract is
            # untrustworthy. Read-only paths are unaffected.
            result["envelope"]["risk"] = "CRITICAL"
            result["envelope"]["status"] = "BLOCKED"
            result["plan"]["status"] = "BLOCKED"
            result["plan"]["route"] = "contract-drift-block"

        analysis = result["context"].get("capability_analysis")
        result["capability"] = {
            "analysed": analysis is not None,
            "capability_gap": bool(analysis and analysis.get("capability_gap")),
            "recommendations": (analysis or {}).get("recommendations", []),
            # A capability gap never becomes an action here. Any action still
            # has to go planner -> risk -> contract -> firewall -> PROPOSED.
            "action_type": None,
            "auto_remediation": False,
        }
        result["shadow"] = {
            "mode": "SHADOW",
            "action_path": ["REQUEST", "PLAN", "RISK", result["envelope"]["status"], "STOP"],
            "external_actions": False,
            "external_provider_calls": 0,
            "production_code_mutated": False,
            "software_installed": False,
            "human_approval_required": result["envelope"]["status"] == "PROPOSED",
            "contract_valid": contract_valid,
        }
        contract_telemetry = contract.telemetry() if contract is not None else {
            "contract_source": "", "contract_hash": "", "contract_map_version": "",
            "canonical_action_count": 0, "mapped_action_count": 0,
            "unknown_internal": [], "unknown_canonical": [],
            "contract_valid": False, "contract_reason": contract_error or "contract not loaded",
            "contract_load_ms": 0.0,
        }
        result["telemetry"] = {
            "queue_wait_ms": 0.0,
            "db_ms": result["context"]["compile_ms"],
            "context_compile_ms": result["context"]["compile_ms"],
            "retrieval_ms": result["context"]["compile_ms"],
            "capability_registry_ms": result["context"].get("registry_ms", 0.0),
            "contract_check_ms": contract_check_ms,
            "planner_ms": 0.0,
            "router_ms": 0.0,
            "state_ms": 0.0,
            "total_ms": round((perf_counter() - started) * 1000, 3),
            "mode": result["envelope"]["mode"],
            "model_calls": 0,
            "cache_hit": False,
            "fallback_count": 0,
            "success": True,
            **contract_telemetry,
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
