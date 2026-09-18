# SOURCE OF TRUTH V1 — L'CARLIÉ Jarvis

Status: **VERIFIED (local canonical baseline, no remote)**
Verified at: 2026-09-18 15:12 +03:00

## 1. Why a separate baseline exists

A targeted search for a canonical repository or deployment origin for
`/opt/lcarlie/orchestrator` found none. `git init` was deliberately **not** run
inside the live deployment: initialising a repository inside a running
production tree would make the deployment its own change-control authority and
risk accidental checkouts against live files.

Instead a private canonical development baseline lives **outside** the live
deployment.

## 2. Location and identity

| Item | Value |
|---|---|
| Path | `/opt/lcarlie/source/lcarlie-jarvis-v1` |
| Remote | **none configured** (no push has ever been performed) |
| Baseline commit | `28f1bb6e167ab92dc7c4cbdd39d9e5e81d4951f3` — "Establish verified production source baseline v1", 2026-09-18 14:54:03 +0300 |
| Phase 2C commit | `5a4b2dd6e04cd4c959ca38c23ae1a4243e14cb9b` — "Phase 2C: shadow acceptance, TEST G, security recheck, transport fix" |
| Snapshot archive | `/opt/lcarlie/source-snapshots/lcarlie-jarvis-source-v1b.tar.gz` |
| Snapshot SHA-256 | `a0f6cbed2e7ac284dd1cf5eab4deaf733075ac38f2acd736c0f6c0f7786e113f` |
| Tracked files | 77 at baseline |
| Working tree | clean |

Both abbreviated values quoted in the incoming handoff (`28f1bb6e…`,
`a0f6cbed…`) were checked against the live filesystem and are correct.

## 3. Change-control gap found and closed

The v1 baseline was cut at 14:54, but Codex continued editing the deployment
until 14:58. The baseline therefore did **not** contain Codex's own Phase 2C
work. Files missing from the canonical source at the time of this verification:

- `jarvis/shadow.py` (the SHADOW runner itself)
- `tests/test_shadow.py`
- `scripts/run_shadow_acceptance.py`
- `tests/phase2b_duplicate_proposal.sql`

and modified-but-uncommitted: `jarvis/memory.py`, `bin/jarvis-phase2`,
`deploy/bin/jarvis-phase2`, `deploy/jarvis-phase2.service`,
`deploy/question-worker-phase2b.js`, `tests/question-worker-phase2b.test.js`.

All of it is now committed in `5a4b2dd`. **The canonical source and the live
`/opt/lcarlie/jarvis-phase2` deployment are in sync** (verified by `rsync -a
--delete`, excluding `__pycache__` and `evidence/`).

## 4. What this baseline does NOT cover

- `/opt/lcarlie/orchestrator` — still has no change-control origin. It is
  mirrored into the baseline tree as a snapshot only.
- Remote ownership is unresolved and remains acceptable: a verified local
  baseline plus dated tarball snapshots is the current authority.

## 5. Verification commands

```sh
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 rev-parse HEAD
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 status --porcelain     # expect empty
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 remote -v              # expect empty
sha256sum /opt/lcarlie/source-snapshots/lcarlie-jarvis-source-v1b.tar.gz
rsync -ain --delete --exclude=__pycache__ --exclude=evidence \
  /opt/lcarlie/jarvis-phase2/ /opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2/
```

The last command must print nothing: any output means the deployment and the
canonical source have diverged again.
