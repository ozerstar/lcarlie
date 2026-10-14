"""CodingExecutor: spec validation, scope enforcement, evidence shape.

No real Kimi/OpenRouter calls here -- those are exercised exactly once, by a
separate authorized live smoke test (scripts/run_coding_executor_smoke.py),
per this integration's explicit "one smoke test only" instruction.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis import coding_executor as ce


class SpecValidationTests(unittest.TestCase):
    def test_valid_spec_parses(self):
        spec = ce.CodingTaskSpec.from_dict({"objective": "fix bug", "allowed_files": ["a.py"]})
        self.assertEqual(spec.objective, "fix bug")
        self.assertEqual(spec.allowed_files, ("a.py",))
        self.assertEqual(spec.test_cwd, "jarvis-phase2")  # sensible default

    def test_missing_objective_rejected(self):
        with self.assertRaises(ValueError):
            ce.CodingTaskSpec.from_dict({"allowed_files": ["a.py"]})

    def test_empty_allowed_files_rejected(self):
        with self.assertRaises(ValueError):
            ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": []})

    def test_non_string_allowed_files_rejected(self):
        with self.assertRaises(ValueError):
            ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": [1, 2]})

    def test_always_forbidden_pattern_cannot_be_allowlisted(self):
        for forbidden in (".git/config", "deploy/jarvis-web.service", "state/webconsole/auth.json", ".env"):
            with self.assertRaises(ValueError):
                ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": [forbidden]})

    def test_custom_test_command_accepted(self):
        spec = ce.CodingTaskSpec.from_dict({
            "objective": "x", "allowed_files": ["a.py"],
            "test_command": ["python3", "-m", "unittest", "test_a"], "test_cwd": "sub",
        })
        self.assertEqual(spec.test_command, ("python3", "-m", "unittest", "test_a"))
        self.assertEqual(spec.test_cwd, "sub")


class ScopeEnforcementTests(unittest.TestCase):
    def test_allowed_file_passes(self):
        spec = ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": ["jarvis/foo.py"]})
        self.assertIsNone(ce._enforce_scope(["jarvis/foo.py"], spec))

    def test_glob_allowlist_matches(self):
        spec = ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": ["jarvis/*.py"]})
        self.assertIsNone(ce._enforce_scope(["jarvis/foo.py", "jarvis/bar.py"], spec))

    def test_file_outside_allowlist_denied(self):
        spec = ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": ["jarvis/foo.py"]})
        denial = ce._enforce_scope(["jarvis/foo.py", "jarvis/other.py"], spec)
        self.assertIsNotNone(denial)
        self.assertIn("other.py", denial)

    def test_always_forbidden_denied_even_if_somehow_reached(self):
        spec = ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": ["*"]})
        denial = ce._enforce_scope([".git/config"], spec)
        self.assertIsNotNone(denial)

    def test_untracked_stray_file_is_caught_not_just_modified_tracked_files(self):
        # Real finding from /tmp/jarvis-executor-bench: the model created two
        # stray UNTRACKED files no allowlist covered. _changed_paths must
        # surface untracked files too, or this scope check never sees them.
        spec = ce.CodingTaskSpec.from_dict({"objective": "x", "allowed_files": ["a.py"]})
        denial = ce._enforce_scope(["a.py", "değişmedi."], spec)
        self.assertIsNotNone(denial)


class ChangedPathsIncludesUntrackedTests(unittest.TestCase):
    """Integration-ish but no network/model calls: real git, a real tmp repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.tmp, check=True)
        (self.tmp / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "a.py"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.tmp, check=True)
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.tmp,
                                   capture_output=True, text=True, check=True).stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_modified_tracked_file_detected(self):
        (self.tmp / "a.py").write_text("x = 2\n")
        changed = ce._changed_paths(self.tmp, self.base)
        self.assertIn("a.py", changed)

    def test_new_untracked_file_detected(self):
        (self.tmp / "junk.txt").write_text("stray\n")
        changed = ce._changed_paths(self.tmp, self.base)
        self.assertIn("junk.txt", changed)

    def test_untracked_file_with_natural_language_name_detected(self):
        # Exactly the shape of the real stray files found in the benchmark.
        (self.tmp / "erisi veya uzun analiz istemiyorum.").write_text("x\n")
        changed = ce._changed_paths(self.tmp, self.base)
        self.assertTrue(any("erisi" in path for path in changed))

    def test_no_changes_yields_empty(self):
        self.assertEqual(ce._changed_paths(self.tmp, self.base), [])


class RunCodingTaskGatingTests(unittest.TestCase):
    """Exercise the full gate logic with the git clone + test run mocked
    out, so this suite never touches Kimi/OpenRouter."""

    def setUp(self):
        self.tmp_root = Path(tempfile.mkdtemp())
        self.canonical = self.tmp_root / "canonical"
        self.canonical.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.canonical, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.canonical, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.canonical, check=True)
        (self.canonical / "jarvis-phase2").mkdir()
        (self.canonical / "jarvis-phase2" / "tests").mkdir()
        (self.canonical / "jarvis-phase2" / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=self.canonical, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.canonical, check=True)

        self.worktree_root = self.tmp_root / "worktrees"
        self.evidence_root = self.tmp_root / "evidence"
        self.patches = [
            patch.object(ce, "CANONICAL_SOURCE", self.canonical),
            patch.object(ce, "WORKTREE_ROOT", self.worktree_root),
            patch.object(ce, "EVIDENCE_ROOT", self.evidence_root),
            patch.object(ce, "KIMI_BIN", "/bin/true"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def _spec(self, allowed=("jarvis-phase2/a.py",)):
        return ce.CodingTaskSpec.from_dict({"objective": "test", "allowed_files": list(allowed)})

    def test_missing_kimi_binary_raises_before_touching_anything(self):
        with patch.object(ce, "KIMI_BIN", "/does/not/exist"):
            with self.assertRaises(ce.CodingExecutorError):
                ce.run_coding_task(self._spec(), task_id="t1")

    def test_scope_violation_denies_and_produces_no_evidence(self):
        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":  # the kimi invocation
                (Path(cwd) / "jarvis-phase2" / "unexpected.py").write_text("evil = 1\n")
                return subprocess.CompletedProcess(cmd, 0, "did a thing", "")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            result = ce.run_coding_task(self._spec(allowed=("jarvis-phase2/a.py",)), task_id="t2")
        self.assertFalse(result.success)
        self.assertIn("unexpected.py", result.denied_reason)
        self.assertFalse(self.evidence_root.exists() and any(self.evidence_root.iterdir()))
        # disposal: the clone must not survive
        self.assertFalse((self.worktree_root / "t2").exists())

    def test_no_changes_is_denied_not_silently_proposed(self):
        with patch.object(ce, "_run", wraps=None) as run_mock:
            def side_effect(cmd, cwd, timeout_s, env=None):
                if str(cwd).endswith("t3") and cmd[0] == "/bin/true":
                    return subprocess.CompletedProcess(cmd, 0, "", "")
                return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)
            run_mock.side_effect = side_effect
            result = ce.run_coding_task(self._spec(), task_id="t3")
        self.assertFalse(result.success)
        self.assertTrue(result.denied_reason.startswith("no files were changed"))

    def test_failing_tests_deny_even_when_scope_is_respected(self):
        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":
                (Path(cwd) / "jarvis-phase2" / "a.py").write_text("x = 2\n")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:2] == ["python3", "-m"] and "unittest" in cmd:
                self.assertEqual("C.UTF-8", env["LC_ALL"])
                self.assertTrue(Path(env["HOME"]).is_dir())
                self.assertNotEqual("/root", env["HOME"])
                return subprocess.CompletedProcess(cmd, 1, "", "1 test failed")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            result = ce.run_coding_task(self._spec(), task_id="t4")
        self.assertFalse(result.success)
        self.assertEqual(result.denied_reason, "tests failed")
        self.assertIn("1 test failed", (Path(result.evidence_dir) / "test_output.txt").read_text())
        self.assertFalse((self.worktree_root / "t4").exists())

    def test_success_produces_evidence_and_disposes_clone(self):
        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":
                (Path(cwd) / "jarvis-phase2" / "a.py").write_text("x = 2\n")
                return subprocess.CompletedProcess(cmd, 0, "changed a.py", "")
            if cmd[:2] == ["python3", "-m"] and "unittest" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "OK", "")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            result = ce.run_coding_task(self._spec(), task_id="t5")
        self.assertTrue(result.success)
        self.assertEqual(result.files_changed, ("jarvis-phase2/a.py",))
        self.assertTrue(result.test_passed)
        self.assertIsNotNone(result.evidence_dir)
        evidence_dir = Path(result.evidence_dir)
        self.assertTrue((evidence_dir / "diff.patch").is_file())
        self.assertTrue((evidence_dir / "evidence.json").is_file())
        self.assertFalse((self.worktree_root / "t5").exists())  # disposed

    def test_evidence_json_never_contains_secrets_env(self):
        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":
                self.assertNotIn("JARVIS_DB_ROLE", env or {})
                self.assertNotIn("POSTGRES_PASSWORD", env or {})
                (Path(cwd) / "jarvis-phase2" / "a.py").write_text("x = 3\n")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:2] == ["python3", "-m"] and "unittest" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "OK", "")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            ce.run_coding_task(self._spec(), task_id="t6")

    def test_kimi_invocation_is_one_kimi_2_0_1_accepts(self):
        """Regression: the first live run failed instantly because the argv
        carried --auto ("Cannot combine --prompt with --auto") and the env
        lacked KIMI_CODE_HOME, so no model catalog was found. Every other test
        here mocks _run, so neither defect was visible to them."""
        seen = {}

        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":
                seen["cmd"], seen["env"] = list(cmd), dict(env or {})
                (Path(cwd) / "jarvis-phase2" / "a.py").write_text("x = 4\n")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:2] == ["python3", "-m"] and "unittest" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "OK", "")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            ce.run_coding_task(self._spec(), task_id="t8")

        self.assertNotIn("--auto", seen["cmd"])
        self.assertIn("-p", seen["cmd"])
        self.assertEqual(seen["env"].get("KIMI_CODE_HOME"), ce.KIMI_HOME)

    def test_no_changes_denial_carries_kimi_output_for_diagnosis(self):
        def fake_run(cmd, cwd, timeout_s, env=None):
            if cmd[0] == "/bin/true":
                return subprocess.CompletedProcess(cmd, 0, "", "429 Rate limit exceeded")
            return subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True, env=env)

        with patch.object(ce, "_run", side_effect=fake_run):
            result = ce.run_coding_task(self._spec(), task_id="t9")
        self.assertFalse(result.success)
        self.assertIn("429", result.denied_reason)

    def test_summarize_for_proposal_stays_under_reason_limit(self):
        result = ce.CodingTaskResult(
            task_id="t7", success=True, denied_reason=None,
            files_changed=tuple(f"file_{i}.py" for i in range(200)),
            test_passed=True, test_summary="ok", model="m", evidence_dir="/x", duration_s=1.0,
        )
        self.assertLessEqual(len(ce.summarize_for_proposal(result)), ce.MAX_REASON_CHARS)


if __name__ == "__main__":
    unittest.main()
