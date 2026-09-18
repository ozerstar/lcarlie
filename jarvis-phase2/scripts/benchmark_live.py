from __future__ import annotations

import json
from time import perf_counter

from jarvis.context import ContextCompiler
from jarvis.memory import CompanyMemory
from jarvis.phase2 import Phase2Runtime
from jarvis.telemetry import Telemetry


def main() -> None:
    runtime = Phase2Runtime(ContextCompiler(CompanyMemory()))
    telemetry = Telemetry()
    intents = [
        "Jarvis, sistem durumu ne?",
        "Jarvis, Vireon hakkında şirket hafızasında ne biliyoruz?",
        "Jarvis, bekleyen AI task ve proposal durumunu göster.",
    ]
    for index in range(18):
        started = perf_counter()
        result = runtime.handle(intents[index % len(intents)])
        total_ms = (perf_counter() - started) * 1000
        telemetry.record(
            total_ms=total_ms,
            context_compile_ms=result["context"]["compile_ms"],
            db_ms=total_ms,
            retrieval_ms=0,
            model_ms=0,
            network_ms=total_ms,
            mode=result["envelope"]["mode"],
            executor="deterministic",
            cache_hit=False,
            tokens=0,
            fallback_count=0,
            success=True,
        )
    print(json.dumps({
        "samples": len(telemetry.samples),
        "total_ms": telemetry.summary("total_ms"),
        "context_compile_ms": telemetry.summary("context_compile_ms"),
        "model_calls": 0,
        "failures": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
