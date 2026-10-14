from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.orchestration_status import snapshot


class OrchestrationStatusTests(unittest.TestCase):
    def test_reports_evidence_gap_without_claiming_action_was_submitted(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            path = run_dir / "run-plan-1.json"
            path.write_text(json.dumps({
                "run_id": "run-plan-1", "plan_id": "plan-1", "request": "Analyze",
                "originator": "operator", "status": "COMPLETED", "started_at": "now",
                "steps": {
                    "S1": {"capability": "crm_analysis", "status": "SUCCEEDED",
                           "evidence_refs": [], "output": {"private": "do not leak"},
                           "acceptance": {"status": "FAILED", "checks": [
                               {"criterion": "source_traceable", "passed": False}]}},
                    "S2": {"capability": "action_plan", "status": "PROPOSED",
                           "output": {"payload": {"secret": "do not leak"}}},
                },
            }), encoding="utf-8")
            result = snapshot(run_dir)
            self.assertEqual(result["needs_attention"], 1)
            self.assertEqual(result["runs"][0]["status"], "UNVERIFIED")
            self.assertEqual(result["runs"][0]["steps"][0]["evidence_state"], "MISSING")
            self.assertEqual(result["runs"][0]["steps"][0]["failed_criteria"],
                             ["source_traceable"])
            self.assertEqual(result["runs"][0]["steps"][1]["status"], "PROPOSED")
            self.assertNotIn("do not leak", json.dumps(result))

    def test_stale_running_record_is_labeled_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            path = run_dir / "run-plan-2.json"
            path.write_text(json.dumps({"run_id": "run-plan-2", "status": "RUNNING"}), encoding="utf-8")
            old = (datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp()
            os.utime(path, (old, old))
            result = snapshot(run_dir)
            self.assertEqual(result["runs"][0]["status"], "INTERRUPTED")
            self.assertEqual(json.loads(path.read_text())["status"], "RUNNING")

    def test_skips_corrupt_oversize_and_symlink_records(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "run-bad.json").write_text("{", encoding="utf-8")
            (run_dir / "run-large.json").write_bytes(b"x" * 2_000_001)
            (run_dir / "run-link.json").symlink_to(run_dir / "run-large.json")
            self.assertEqual(snapshot(run_dir)["runs"], [])
