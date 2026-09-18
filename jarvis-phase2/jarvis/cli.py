from __future__ import annotations

import argparse
import json

from .benchmark import run_fake
from .capabilities import build_registry
from .runtime import respond


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("intent", nargs="*")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if args.capabilities:
        # Offline view: no database probe, so live-derived entries report
        # UNKNOWN rather than guessing.
        output = {name: capability.to_dict() for name, capability in build_registry().items()}
    elif args.benchmark:
        output = run_fake()
    else:
        output = respond(" ".join(args.intent))
    print(json.dumps(output, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
