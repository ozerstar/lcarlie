"""jarvis-operator: the minimum human proposal surface.

Usage:
  jarvis-operator list
  jarvis-operator inspect <action_id>
  jarvis-operator approve <action_id> "<reason>" <fingerprint>
  jarvis-operator reject  <action_id> "<reason>" <fingerprint>
  jarvis-operator create-task <INTERNAL_INTENT> <slug>
  jarvis-operator create-coding-task <slug> <spec.json>

This is a human-run terminal command, not a Jarvis code path. See
jarvis/operator.py for the authority separation this relies on.

A coding task spec (spec.json) looks like:
  {
    "objective": "bounded description of the change",
    "allowed_files": ["jarvis-phase2/jarvis/some_module.py"],
    "test_command": ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
    "test_cwd": "jarvis-phase2"
  }
test_command/test_cwd are optional and default to the full Jarvis suite.
"""
from __future__ import annotations

import json
import sys

from .operator import OperatorSession
from .transport import memory_host


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    session = OperatorSession(host=memory_host())
    command = args[0]

    if command == "list":
        pending = session.list_pending()
        _print({"pending_count": len(pending), "pending": pending})
        return 0

    if command == "inspect":
        if len(args) < 2:
            print("usage: jarvis-operator inspect <action_id>")
            return 1
        proposal = session.inspect(args[1])
        if proposal is None:
            _print({"error": "not found", "action_id": args[1]})
            return 1
        _print(proposal)
        return 0

    if command in ("approve", "reject"):
        if len(args) != 4:
            print(f"usage: jarvis-operator {command} <action_id> \"<reason>\" <fingerprint>")
            return 1
        decision = "APPROVED" if command == "approve" else "REJECTED"
        result = session.decide(args[1], decision, args[2], expected_hash=args[3])
        _print(result)
        return 0

    if command == "create-task":
        if len(args) < 3:
            print("usage: jarvis-operator create-task <INTERNAL_INTENT> <slug>")
            return 1
        try:
            result = session.create_task(args[1], args[2])
        except ValueError as exc:
            _print({"error": str(exc)})
            return 1
        _print(result)
        return 0

    if command == "create-coding-task":
        if len(args) < 3:
            print("usage: jarvis-operator create-coding-task <slug> <spec.json>")
            return 1
        try:
            result = session.create_coding_task(args[1], args[2])
        except (ValueError, OSError) as exc:
            _print({"error": str(exc)})
            return 1
        _print(result)
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
