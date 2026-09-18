from __future__ import annotations

import argparse
import json

from .benchmark import run_fake
from .capabilities import CAPABILITIES
from .runtime import respond


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("intent", nargs="*")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if args.capabilities:
        output = CAPABILITIES
    elif args.benchmark:
        output = run_fake()
    else:
        output = respond(" ".join(args.intent))
    print(json.dumps(output, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
