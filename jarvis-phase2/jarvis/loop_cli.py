"""One operational cycle, invoked by bin/jarvis-phase2 in OPERATIONAL mode
(itself triggered periodically by jarvis-phase2.timer, the same oneshot +
timer pattern already used by lcarlie-action-worker.{service,timer} on this
host). Not a persistent daemon: each invocation runs exactly one cycle and
exits.
"""
from __future__ import annotations

import json

from .loop import run_cycle
from .transport import memory_host


def main() -> None:
    report = run_cycle(host=memory_host())
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
