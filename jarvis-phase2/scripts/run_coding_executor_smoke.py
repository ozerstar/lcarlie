#!/usr/bin/env python3
"""ONE authorized live smoke test of the CodingExecutor integration.

Calls jarvis.coding_executor.run_coding_task() directly -- no DB, no loop,
no proposal -- against the REAL Kimi binary, REAL OpenRouter/Nemotron model,
and a REAL disposable clone of the canonical source. Proves the actual
integration module works end to end, distinct from (and not a repeat of)
the earlier standalone /tmp/jarvis-executor-bench benchmark of the model
itself.

A single, deliberately minimal, harmless task: add one new markdown file
containing a fixed sentence. Nothing else may change. The full jarvis-phase2
test suite (the real default test_command) is run inside the clone
afterward to prove "preserve all existing tests" holds for a genuinely
unrelated change.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from jarvis.coding_executor import CodingTaskSpec, run_coding_task  # noqa: E402

TASK_ID = f"smoke-{int(datetime.now(timezone.utc).timestamp())}"
TARGET_FILE = "jarvis-phase2/CODING_EXECUTOR_SMOKE_TEST.md"
SENTENCE = f"CodingExecutor smoke test {TASK_ID} -- no functional change."


def main() -> int:
    spec = CodingTaskSpec.from_dict({
        "objective": (
            f"Create exactly one new file at the path '{TARGET_FILE}' (relative to the "
            f"repository root) containing exactly this single line and nothing else:\n\n"
            f"{SENTENCE}\n\n"
            "Do not modify, create, or delete any other file."
        ),
        "allowed_files": [TARGET_FILE],
    })
    print(json.dumps({"phase": "starting", "task_id": TASK_ID, "spec": spec.objective}, ensure_ascii=False))

    result = run_coding_task(spec, task_id=TASK_ID)
    report = result.to_dict()

    if result.success:
        evidence_dir = Path(result.evidence_dir)
        report["diff_preview"] = (evidence_dir / "diff.patch").read_text(encoding="utf-8")[:2000]
        report["evidence_json"] = json.loads((evidence_dir / "evidence.json").read_text(encoding="utf-8"))
        report["file_content_correct"] = SENTENCE in report["diff_preview"]

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
