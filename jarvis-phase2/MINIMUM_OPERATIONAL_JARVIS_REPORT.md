# MINIMUM OPERATIONAL JARVIS

**OVERALL: PASS**

Executed 2026-09-18, 15:41–16:02 +03:00, continuing directly from the completed
Phase 2D state (verified, not repeated).

---

## 1. WHAT CHANGED

Two new modules, both additive to the existing Phase 2D runtime:

- **`jarvis/operator.py` + `operator_cli.py`** (`bin/jarvis-operator`) — the
  minimum human proposal surface: `list`, `inspect`, `approve`, `reject`,
  `create-task`. Root required (matches the existing `human-approval-cli.sh`
  convention). Never imported by any Jarvis autonomous code path.
- **`jarvis/loop.py` + `loop_cli.py`** — one deterministic operational cycle:
  observe → analyze → claim at most one task → validate → propose. Zero model
  calls. Triggered by a new `jarvis-phase2.timer` (5 min interval), the same
  oneshot+timer pattern already used by `lcarlie-action-worker.{service,timer}`
  — no second daemon.

Two **real, previously-latent bugs** were found and fixed while activating
(not before — the systemd path had literally never been exercised in any
prior phase):

1. `jarvis-phase2.service` ran as `User=jarvis`, but that user is not in the
   `docker` group (socket is `root:docker`, mode 660) — it could never reach
   PostgreSQL at all. Fixed by running as root with the same hardening
   already audited on `action-worker.service` (`CapabilityBoundingSet=`,
   `NoNewPrivileges`, `ProtectSystem=strict`, etc.) — matching existing
   precedent rather than adding `jarvis` to `docker` group, which would have
   been root-equivalent anyway with none of the sandbox review that unit has.
2. `ProtectSystem=strict` makes the filesystem read-only outside listed
   paths; `ReadWritePaths=/opt/lcarlie/jarvis-phase2/state` was missing.

Both fixed and verified via a real `systemctl start`.

## 2. HUMAN PROPOSAL SURFACE

Verified against the **live grants**, not assumed — this caught a design bug
before deployment: `core.ai_get_pending_actions()` and `core.ai_enqueue_task()`
are `human_approver`-only (`ai_reader` has nothing), and
`core.ai_action_proposal` has **no** table-level read grant for anyone but its
owner. So every operator statement runs as `human_approver`, `inspect` can
only see **pending** proposals (disclosed limitation — no controlled function
returns decided-proposal detail), and `decide()` confirms its own effect by
re-checking the pending list rather than reading the row back.

```
jarvis-operator list                              # pending proposals
jarvis-operator inspect <action_id>                # one pending proposal
jarvis-operator approve <action_id> "<reason>"     # -> core.ai_decide_action
jarvis-operator reject  <action_id> "<reason>"
jarvis-operator create-task <INTENT> <slug>        # human originates work
```

Jarvis (`ai_writer`) is not, and cannot be, a member of `human_approver` —
unchanged, re-verified live (security recheck below).

## 3. OPERATIONAL LOOP

`observe()` — two existing allowlisted Company Memory queries (system health,
company agenda). `analyze()` — fixed deterministic rules (`failed_executions
> 0`, `open_tasks > 50`); no model call, no fabricated issue. Then: claim at
most one task; if its `task_type` isn't `PROPOSE_ACTION`, hand it straight
back via `core.ai_fail_task` and stop.

**Discovery during this task:** a separate, older, pre-existing orchestrator
already runs on this host (`ai_generate_company_intelligence_task` →
`PROPOSE_DECISION` tasks → `core.karar` → `mart.ai_approval_inbox` →
`human-approval-cli.sh`), with its own worker (`worker.js`, currently
**failing** on an unrelated DNS issue, `EAI_AGAIN lcarlie-postgres` inside its
own docker network — not touched, not fixed, out of scope). `core.ai_claim_task`
has no `task_type` filter, so this loop must never silently absorb that
system's tasks — the hand-back-on-mismatch behavior exists specifically for
this, and is unit-tested.

`ai_writer` has no `SELECT` on `core.ai_task`, so the only task content
visible after claiming is what `ai_claim_task()` itself returns. The internal
intent is carried by convention in the idempotency key
(`jarvis:<INTENT>:<slug>`, set by a human via `create-task`) — no new grant
needed for this.

## 4. REAL COMPANY MEMORY DEMONSTRATION

Real cycle #1, against production: **NOOP** — `failed_executions=0`,
`open_tasks=0`. Truthful; nothing was fabricated.

Then, to demonstrate the operator interface (Task 9/10), a human created one
deterministic `REQUEST_HUMAN_REVIEW` task via `create-task`. The next real
cycle claimed it, validated it through the Phase 2D firewall/contract, and
called `core.ai_propose_action` → **proposal 20, PROPOSED**. This was
**committed, not rollback-tested** — a genuine end-to-end run of the real code
path, clearly distinguished from real observation in the audit log.

## 5. APPROVAL TEST

```
jarvis-operator inspect 20      -> full pending detail
jarvis-operator approve 20 "…"  -> {"still_pending": false, "confirmed": true}
jarvis-operator list            -> pending_count: 0
```

`core.ai_action_execution` row created (execution_enabled=true for
`REQUEST_HUMAN_REVIEW`). The existing `action-worker.js` FakeExecutor claimed
and completed it: **state `EXECUTED`, summary "internal human review request
recorded by FakeExecutor"** — zero external calls, exactly as designed for
this action type. Verified: Jarvis never touched `human_approver`;
`EXTERNAL_ACTIONS=false` held throughout; `action-gateway-health.sh` stayed
clean (`unsafe_external_types:0, separation_violation:0`) before and after.

## 6. DEDUP / LOOP SAFETY

- One task claimed per cycle, by construction (unit-tested).
- Wrong-`task_type` tasks are hand-backed via `ai_fail_task`, never silently
  absorbed (unit-tested against a simulated `PROPOSE_DECISION` task).
- Issue findings are logged once per distinct signature, not every cycle
  (unit-tested: two identical unhealthy observations → one log line).
- No task/proposal storm possible: after the one demo proposal, the queue was
  empty again, and 20 rapid subsequent cycles created **zero** further tasks
  or proposals.

## 7. SOAK RESULT

Accelerated (per Task 8's explicit allowance — 30 min wall-clock would prove
nothing more than tight cycling already does):

**20 cycles in 8 seconds.** Before → after: `ai_task` rows 17→17,
`ai_action_proposal` rows 1→1, `open_leased_tasks` 0, DB connections stable at
2, all 6 containers healthy throughout, gateway health clean throughout. No
runaway loop, no storm, no growth, no errors, no restarts.

Kill switch (Task 11), on the real systemd path:
`systemctl stop && disable jarvis-phase2.timer` → timer inactive/disabled, **no
orphan process**, DB consistent (`ai_orchestrator_health` clean) →
`enable --now` once → timer active/enabled again, scheduled correctly. Clean
in both directions.

## 8. SECURITY

Full recheck after all changes: **32/32 PASS** (27 denials — all SQLSTATE
42501 — + 5 positive controls, 0 failures, 0 inconclusive). Still blocked:
self approval, `SET ROLE human_approver`, raw DML, direct execution, unknown
action, contract drift, state replay, duplicate proposal replay, and the
Phase 2D contract-grant boundary. No security setting was weakened; the
`User=`→root change moves *which OS account starts `docker exec`*, not *which
PostgreSQL role a session runs as* — that boundary (`ai_writer` vs
`human_approver` vs `ai_reader`) is what's actually authoritative and is
unchanged and re-verified.

Full local suite: **108 tests, OK** (103 executed + 5 live-gated).

## 9. PERFORMANCE

Per cycle (production, real DB): observe ~200–260 ms, claim ~90–125 ms,
propose (when it runs) ~180 ms; total ~300–440 ms. Well within the 5-minute
timer interval; bounded resources (`MemoryMax=256M`, `CPUQuota=100%`,
`TasksMax=64`, unchanged from Phase 2B/2C). Not a material regression from
anything measured in Phase 2C/2D — this is a new code path, not a modification
of an existing hot one.

## 10. EXTERNAL PROVIDER CALLS

**ZERO** throughout — every cycle report carries `model_calls: 0,
external_provider_calls: 0`. Analysis is pure deterministic Python.

## 11. EXTERNAL ACTIONS

**ZERO.** The one approved action (`REQUEST_HUMAN_REVIEW`) executed as an
internal audit-record write only, by the existing fail-closed FakeExecutor.
No WhatsApp, no Wix, no Meta, no price change was possible or attempted —
`EXTERNAL_ACTIONS=false` held, and the DB-level execution boundary
(`execution_enabled=false` for every other action type, enforced since
Phase 2D) is independently unchanged.

## 12. SERVICE STATE

```
JARVIS_ENABLED=true
JARVIS_MODE=OPERATIONAL
EXTERNAL_ACTIONS=false
JARVIS_MEMORY_TRANSPORT=local-docker
jarvis-phase2.timer:   active, enabled   (fires every 5 min)
jarvis-phase2.service: inactive between cycles -- normal for Type=oneshot,
                       triggered only by the timer, exactly like
                       lcarlie-action-worker.service
```

## 13. SOURCE COMMIT

Canonical source `/opt/lcarlie/source/lcarlie-jarvis-v1`, commit
`0b560cfb5fff2bb2d628a4db316888e574388465`. Deployment verified
byte-identical (`rsync -ain --delete`, excluding `evidence/` and `state/`,
prints nothing). Backup taken first:
`/opt/lcarlie/backups/minop-20260918T155302/jarvis-phase2.pre-minop.tgz`
(sha256 `40d75222d6860d65331892f1a54b9acbc8d3b56f00876522d026f64e65851c61`),
plus the pre-activation env file and service unit.

## 14. OPEN BLOCKERS

None for this task's scope.

Backlog (recorded, not implemented — explicitly out of scope for "minimum"):

- Jarvis has no controlled read path for a task's free-text context, only the
  idempotency-key convention used here. A real `p_context`/description field
  ai_writer could read would remove that convention.
- `inspect` cannot show a *decided* proposal's detail (no controlled function
  returns it); acceptable for now since the requirement was "pending
  proposals."
- The separate pre-existing orchestrator's `worker.js` is failing
  (`EAI_AGAIN lcarlie-postgres`, unrelated DNS/network issue) — not touched,
  not this task's scope, but worth someone's attention.
- `analyze()`'s rule set is intentionally minimal (2 rules on 2 fields); more
  company-memory surfaces can be added later without architecture change.

## 15. EXACT NEXT STEP

None required — the loop is live and self-sustaining via its timer. The next
natural step, whenever a human chooses it, is widening `analyze()`'s rule set
or the `INTENT_TO_CANONICAL` mapping as real operational needs appear;
neither requires another activation phase.

---

**JARVIS IS NOW OPERATIONAL IN READ → ANALYZE → PROPOSE MODE.**
**EXTERNAL ACTION EXECUTION REMAINS DISABLED.**
