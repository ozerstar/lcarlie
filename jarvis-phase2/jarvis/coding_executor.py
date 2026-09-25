"""CodingExecutor: bounded, disposable, human-reviewed coding tasks.

    Jarvis -> Execution Planner -> CodingExecutor -> Kimi Code 2.0.1
    -> OpenRouter -> Nemotron 3 Super 120B A12B (free)
    -> isolated/disposable clone of the canonical source
    -> bounded coding task -> approved tests -> diff + structured evidence
    -> PROPOSED -> HUMAN APPROVAL

This module NEVER touches the canonical source
(/opt/lcarlie/source/lcarlie-jarvis-v1) or the production deployment tree
(/opt/lcarlie/jarvis-phase2) directly. It works only inside a throwaway
`git clone --local` that is deleted after every run, success or failure.
Approving the resulting proposal records a human decision that the diff was
reviewed -- it does NOT deploy anything. Applying a reviewed diff to the
canonical source remains an entirely manual, separate human action.

Isolation is layered, not assumed from one mechanism:
  1. filesystem: a disposable local clone, never the shared repo
  2. workspace: Kimi is given no --add-dir, so its own workspace is the
     clone directory only
  3. environment: the subprocess gets a minimal env (no JARVIS_*,
     POSTGRES_*, DOCKER_* secrets to find even if it went looking)
  4. gate, not trust: the model's own claim to have stayed in scope is
     never taken at face value -- every changed AND untracked path is
     checked against the human-supplied allowlist after the run. A prior
     disposable benchmark of this exact model (see
     /tmp/jarvis-executor-bench, task.txt) modified only its three allowed
     files and left protected files untouched, but ALSO created two stray
     untracked junk files outside any allowlist -- a `git diff --name-only`
     check alone would have missed them entirely, since diff only reports
     changes to tracked files. This is why step 4 below also inspects
     `git status --porcelain` for untracked (`??`) entries.
  5. disposal: the clone is removed unconditionally in a `finally` block

Known operational limitation, disclosed not hidden: the free OpenRouter tier
for this model hit "429 free-models-per-day" mid-run during that same prior
benchmark and only succeeded after several minutes of Kimi's own internal
retry/backoff. A CodingExecutor run can legitimately take much longer than a
typical Jarvis cycle, or fail outright on a given day once the free quota is
exhausted; both are treated as an ordinary failure (task failed, no
proposal), never as a reason to relax the scope gate.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

CANONICAL_SOURCE = Path(os.environ.get("JARVIS_CANONICAL_SOURCE",
                                       "/opt/lcarlie/source/lcarlie-jarvis-v1"))
WORKTREE_ROOT = Path(os.environ.get("JARVIS_CODING_WORKTREE_ROOT",
                                    "/opt/lcarlie/coding-executor-worktrees"))
EVIDENCE_ROOT = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "coding_executor"
KIMI_BIN = os.environ.get("JARVIS_KIMI_BIN", "/root/kimi-sandbox/bin/kimi")
KIMI_HOME = os.environ.get("JARVIS_KIMI_HOME", "/root/kimi-sandbox-home")
KIMI_MODEL = os.environ.get("JARVIS_KIMI_MODEL", "openrouter/nvidia/nemotron-3-super-120b-a12b:free")
DEFAULT_TIMEOUT_S = int(os.environ.get("JARVIS_CODING_TIMEOUT_S", "600"))
MAX_REASON_CHARS = 2000  # core.ai_propose_action rejects a longer 'reason'

# Never allowed to be touched by a coding task, regardless of what the human
# spec's allowed_files says -- a spec cannot opt back into these.
ALWAYS_FORBIDDEN_PATTERNS = (
    ".git/*", ".git", "deploy/*", "migrations/*",
    "state/*", "*/state/*", "**/state/webconsole/*",
    "*.env", "*/.env",
)


class CodingExecutorError(RuntimeError):
    """A CodingExecutor run could not even start (bad spec, missing binary,
    clone failure). Distinct from a run that started and was correctly
    denied for being out of scope or failing tests -- see CodingTaskResult."""


@dataclass(frozen=True)
class CodingTaskSpec:
    objective: str
    allowed_files: tuple[str, ...]
    test_command: tuple[str, ...] = ("python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")
    test_cwd: str = "jarvis-phase2"
    timeout_s: int = DEFAULT_TIMEOUT_S

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CodingTaskSpec":
        objective = str(data.get("objective", "")).strip()
        allowed = data.get("allowed_files")
        if not objective:
            raise ValueError("spec.objective is required")
        if not isinstance(allowed, list) or not allowed or not all(isinstance(p, str) and p for p in allowed):
            raise ValueError("spec.allowed_files must be a non-empty list of strings")
        for pattern in allowed:
            if _matches_any(pattern, ALWAYS_FORBIDDEN_PATTERNS):
                raise ValueError(f"spec.allowed_files entry is always-forbidden: {pattern!r}")
        test_command = tuple(data["test_command"]) if data.get("test_command") else CodingTaskSpec.__dataclass_fields__["test_command"].default
        test_cwd = str(data.get("test_cwd") or "jarvis-phase2")
        timeout_s = int(data.get("timeout_s") or DEFAULT_TIMEOUT_S)
        return CodingTaskSpec(objective=objective, allowed_files=tuple(allowed),
                              test_command=test_command, test_cwd=test_cwd, timeout_s=timeout_s)


@dataclass(frozen=True)
class CodingTaskResult:
    task_id: str
    success: bool
    denied_reason: str | None
    files_changed: tuple[str, ...]
    test_passed: bool | None
    test_summary: str
    model: str
    evidence_dir: str | None
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "success": self.success, "denied_reason": self.denied_reason,
            "files_changed": list(self.files_changed), "test_passed": self.test_passed,
            "test_summary": self.test_summary, "model": self.model,
            "evidence_dir": self.evidence_dir, "duration_s": self.duration_s,
        }


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _run(cmd: list[str], cwd: Path, timeout_s: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), timeout=timeout_s, capture_output=True, text=True,
                          env=env, check=False)


def _build_prompt(spec: CodingTaskSpec) -> str:
    allowed = "\n".join(f"- {f}" for f in spec.allowed_files)
    return f"""You are working in a disposable, isolated coding sandbox. Nothing you
do here reaches production directly -- your result will be reviewed by a
human before anything is ever applied anywhere.

GOAL

{spec.objective}

ALLOWED FILES TO MODIFY OR CREATE

{allowed}

CONSTRAINTS

- Do not modify or create any file outside the list above.
- Do not install packages.
- Do not weaken any existing approval, permission, or firewall check.
- Do not enable external actions or remove safety checks.
- Do not create a new framework.
- Make the smallest correct change.
- Preserve all existing tests unless the goal explicitly asks you to change one.
- Stay inside the current working directory.
- Do not create any file for notes, scratch, or explanation -- report only in
  your final message.

WHEN FINISHED, REPORT IN YOUR FINAL MESSAGE

1. files changed
2. brief explanation of each change
3. confirmation that no file outside the allowed list was touched
"""


def _clone_canonical_source(task_id: str) -> Path:
    if not CANONICAL_SOURCE.is_dir():
        raise CodingExecutorError(f"canonical source not found: {CANONICAL_SOURCE}")
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(WORKTREE_ROOT, 0o700)
    clone_path = WORKTREE_ROOT / task_id
    if clone_path.exists():
        shutil.rmtree(clone_path)
    # --local: disposable working copy, fully separate .git, zero shared
    # state with the canonical repo -- a stray/misbehaving run in here can
    # never corrupt the canonical repo's own git metadata.
    result = _run(["git", "clone", "--local", "--", str(CANONICAL_SOURCE), str(clone_path)],
                  cwd=WORKTREE_ROOT, timeout_s=60)
    if result.returncode != 0:
        raise CodingExecutorError(f"clone failed: {result.stderr.strip()}")
    return clone_path


def _base_commit(clone_path: Path) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=clone_path, timeout_s=10)
    return result.stdout.strip()


def _changed_paths(clone_path: Path, base_commit: str) -> list[str]:
    """Tracked modifications AND untracked new files -- see module docstring
    point 4 for why both are required."""
    diff = _run(["git", "diff", "--name-only", base_commit], cwd=clone_path, timeout_s=15)
    tracked = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    status = _run(["git", "status", "--porcelain"], cwd=clone_path, timeout_s=15)
    untracked = [line[3:].strip() for line in status.stdout.splitlines() if line.startswith("??")]
    return sorted(set(tracked) | set(untracked))


def _enforce_scope(changed: list[str], spec: CodingTaskSpec) -> str | None:
    """Returns a denial reason, or None if every changed path is allowed."""
    for path in changed:
        if _matches_any(path, ALWAYS_FORBIDDEN_PATTERNS):
            return f"touched an always-forbidden path: {path}"
        if not _matches_any(path, spec.allowed_files):
            return f"touched a path outside allowed_files: {path}"
    return None


def _kimi_env() -> dict[str, str]:
    """Minimal environment: nothing Jarvis-, Postgres- or Docker-specific to
    find even if the model went looking for secrets."""
    # KIMI_CODE_HOME -- not HOME -- is what Kimi Code 2.0.1 actually reads to
    # locate config.toml and its provider credentials. With only HOME set it
    # silently falls back to $HOME/.kimi-code/, finds no model catalog, and
    # fails with "Model ... is not configured in config.toml".
    return {"HOME": KIMI_HOME, "KIMI_CODE_HOME": KIMI_HOME,
            "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")}


def run_coding_task(spec: CodingTaskSpec, task_id: str) -> CodingTaskResult:
    started = perf_counter()
    clone_path: Path | None = None
    try:
        # 🔴 is_file() "yok" demek yerine ISTISNA FIRLATABILIR.
        # Path.is_file() yalnizca dosya yoksa False doner; UST DIZIN
        # okunamiyorsa PermissionError ATAR. Burada tam olarak o oluyor:
        # KIMI_BIN varsayilani /root/kimi-sandbox/bin/kimi, ama
        # jarvis-phase2.service `ProtectHome=true` ile kosuyor -- yani
        # /root, servis root olarak calissa bile erisilemez.
        #
        # Eski hali bu istisnayi yakalamiyordu. PermissionError
        # CodingExecutorError DEGIL, dolayisiyla loop.py'deki
        # CodingTaskDenied cevrimine de girmiyor ve TUM DONGUYU cokertiyordu.
        # Olculdu 25.09.2026: takilmis bir CODE_CHANGE_REVIEW isi yeniden
        # denenebilir hale gelince jarvis-phase2 her 5 dakikada bir
        # PermissionError ile duserek crash-loop'a girdi. Ayni cokme
        # 21.09.2026'da isin kirasini da askida birakmisti (is 4 gun
        # LEASED kaldi, kimse fark etmedi).
        #
        # Artik erisilemeyen ikili "yok" sayilir: is ZARIFCE reddedilir
        # (CodingTaskDenied), dongu ayakta kalir. Sebep metninde erisim
        # sorunu ayrica yazilir -- "yok" ile "bakamadim" ayri seylerdir.
        try:
            kimi_var = Path(KIMI_BIN).is_file()
            erisim_hatasi = None
        except OSError as exc:
            kimi_var, erisim_hatasi = False, exc
        if not kimi_var:
            if erisim_hatasi is not None:
                raise CodingExecutorError(
                    f"kimi binary unreachable: {KIMI_BIN} ({erisim_hatasi.__class__.__name__}: "
                    f"{erisim_hatasi}). ProtectHome=true ise /root servise kapalidir; "
                    f"ikiliyi /root disina tasiyin ya da JARVIS_KIMI_BIN ile yolunu verin.")
            raise CodingExecutorError(f"kimi binary not found: {KIMI_BIN}")

        clone_path = _clone_canonical_source(task_id)
        base_commit = _base_commit(clone_path)
        prompt = _build_prompt(spec)

        kimi_result = _run(
            # No --auto: Kimi 2.0.1 rejects it outright when combined with -p
            # ("error: Cannot combine --prompt with --auto"). -p is already a
            # one-shot non-interactive run that cannot stop to ask.
            [KIMI_BIN, "-p", prompt, "-m", KIMI_MODEL],
            cwd=clone_path, timeout_s=spec.timeout_s, env=_kimi_env(),
        )
        kimi_output = (kimi_result.stdout or "") + (("\n[stderr]\n" + kimi_result.stderr) if kimi_result.stderr else "")

        changed = _changed_paths(clone_path, base_commit)
        denial = _enforce_scope(changed, spec)
        if denial:
            return CodingTaskResult(task_id=task_id, success=False, denied_reason=denial,
                                    files_changed=tuple(changed), test_passed=None,
                                    test_summary="not run (scope violation)", model=KIMI_MODEL,
                                    evidence_dir=None, duration_s=round(perf_counter() - started, 3))

        if not changed:
            # Carry a tail of Kimi's own output into the reason. "No files
            # changed" has several very different causes -- the model declined,
            # the CLI rejected its arguments, the provider returned 429 -- and
            # without this the operator sees an identical, undiagnosable
            # message for all of them.
            tail = kimi_output.strip()[-400:]
            return CodingTaskResult(task_id=task_id, success=False,
                                    denied_reason=f"no files were changed; kimi output tail: {tail}",
                                    files_changed=(), test_passed=None, test_summary="not run (nothing to test)",
                                    model=KIMI_MODEL, evidence_dir=None,
                                    duration_s=round(perf_counter() - started, 3))

        test_cwd = clone_path / spec.test_cwd
        env = dict(os.environ)
        env["PYTHONPATH"] = str(test_cwd)
        test_result = _run(list(spec.test_command), cwd=test_cwd, timeout_s=120, env=env)
        test_passed = test_result.returncode == 0
        test_summary = (test_result.stderr or test_result.stdout or "").strip()[-2000:]

        if not test_passed:
            return CodingTaskResult(task_id=task_id, success=False, denied_reason="tests failed",
                                    files_changed=tuple(changed), test_passed=False,
                                    test_summary=test_summary, model=KIMI_MODEL, evidence_dir=None,
                                    duration_s=round(perf_counter() - started, 3))

        diff_result = _run(["git", "diff", base_commit], cwd=clone_path, timeout_s=15)
        evidence_dir = EVIDENCE_ROOT / task_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "diff.patch").write_text(diff_result.stdout, encoding="utf-8")
        (evidence_dir / "kimi_output.txt").write_text(kimi_output, encoding="utf-8")
        evidence = {
            "task_id": task_id, "objective": spec.objective, "model": KIMI_MODEL,
            "files_changed": changed, "test_command": list(spec.test_command),
            "test_passed": True, "test_summary": test_summary,
            "base_commit": base_commit, "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (evidence_dir / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
        for path in evidence_dir.glob("*"):
            os.chmod(path, 0o640)

        return CodingTaskResult(task_id=task_id, success=True, denied_reason=None,
                                files_changed=tuple(changed), test_passed=True, test_summary=test_summary,
                                model=KIMI_MODEL, evidence_dir=str(evidence_dir),
                                duration_s=round(perf_counter() - started, 3))
    except subprocess.TimeoutExpired:
        return CodingTaskResult(task_id=task_id, success=False, denied_reason="timed out",
                                files_changed=(), test_passed=None, test_summary="",
                                model=KIMI_MODEL, evidence_dir=None, duration_s=round(perf_counter() - started, 3))
    finally:
        # Disposable, unconditionally -- success or failure, nothing lingers.
        if clone_path is not None and clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)


def summarize_for_proposal(result: CodingTaskResult) -> str:
    """A short human-readable reason string for the REQUEST_HUMAN_REVIEW
    proposal payload -- core.ai_propose_action caps 'reason' at 2000 bytes."""
    text = (f"CodingExecutor ({result.model}): {len(result.files_changed)} dosya değişti "
           f"({', '.join(result.files_changed)}), testler geçti. "
           f"Kanıt: {result.evidence_dir}")
    return text[:MAX_REASON_CHARS]
