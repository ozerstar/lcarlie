#!/usr/bin/env python3
"""Pick up complete structural jobs and run/resume their per-image review."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.image_jobs import ImageJobs


def main() -> None:
    state = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
    jobs = ImageJobs(state)
    worker = Path(__file__).with_name("image-job-visual-review.py")
    for job in jobs.list(100):
        if job["status"] not in ("REVIEW_PENDING", "CHANGES_REQUIRED", "READY_FOR_OWNER"):
            continue
        if not job["report"].get("structural_pass") or job["visual_review"]["complete"]:
            continue
        subprocess.run([sys.executable, str(worker), job["id"],
                        "--state-dir", str(state), "--provider", "gemini"],
                       check=True, timeout=3600)


if __name__ == "__main__":
    main()
