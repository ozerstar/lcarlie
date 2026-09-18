# HANDOFF — CURRENT STATE

Describes the system **as it actually is** at 2026-09-18 15:35 +03:00, not as
planned. No secret values appear here; environment variables are listed by key
name only.

Read this first, then `PHASE2D_CONTRACT_CLOSURE_REPORT.md` and
`PHASE2C_ACTIVATION_PREFLIGHT_REPORT.md` for the evidence behind every claim.

---

## 1. PROJECT OBJECTIVE

L'CARLIÉ Autonomous Company Intelligence OS, with **Jarvis** as its
natural-language management and execution-coordination layer. Jarvis is not a
model: models are replaceable compute. Task state and company memory belong to
the OS.

Target loop: human → intent → Company Memory → plan → capability selection →
deterministic first → stronger model only if needed → proposal → Action
Firewall → human approval → controlled execution → audit → measurement →
memory.

## 2. CURRENT ARCHITECTURE

Deterministic first → local/small intelligence → cheap model → frontier model →
multi-frontier only when justified. FAST / SMART / DEEP modes.

PostgreSQL is canonical verified truth — for company facts **and, since Phase
2D, for the action contract itself**. Vector similarity is retrieval only.
Models own neither truth nor authorization. The Action Firewall and human
approval are authoritative and live in the database.

## 3. CURRENT PHASE

**Phase 2D complete.** Markers `PHASE2C_SHADOW_READY` and
`PHASE2D_CONTRACT_READY` exist. **Not activated.** Neither marker authorizes
activation.

## 4. COMPLETED PHASES

| Phase | Result |
|---|---|
| 1 | deterministic local-first bootstrap, FakeProvider tests, no external execution |
| 2 | real Company Memory adapter, Context Compiler, controlled task/proposal, execution planner, provider-independent routing |
| 2B | production integration: pgvector image, semantic schema, `core.jarvis_task_state`, packaged service — Jarvis still disabled |
| 2C | activation preflight, source-of-truth baseline, SHADOW mode, acceptance A–H, security recheck — `PHASE2C_SHADOW_READY`, two findings left open |
| 2D | F-1 action contract closed, F-2 capability gap closed, real proposal E2E — `PHASE2D_CONTRACT_READY`, **no open blocker** |

## 5. PRODUCTION STATE

All healthy: `lcarlie-postgres` (healthy), `lcarlie-n8n`, `lcarlie-caddy`,
`icaz-site`, `icaz-oyun`, `icaz-postgres`.
n8n workflows unchanged — MEVZUAT FILTRESI, SATIS AJANI, WHATSAPP, INSTAGRAM
active; WEB SOHBET inactive (deliberate, pre-existing).
Host: 13.65 GiB RAM, 4 CPU cores, disk 19 % used.

A transient container `lcarlie-measurement-generator-once` may appear in
`docker ps`: pre-existing CR-015 infrastructure, hardened `--rm` one-shot
launched by `/opt/lcarlie/orchestrator/run-measurement-generator.sh`. It is not
Jarvis and not drift.

## 6. JARVIS ENABLED/DISABLED

**DISABLED.**
`JARVIS_ENABLED=false` in `/etc/lcarlie/jarvis-phase2.env` (mtime 14:39:13 —
not written during Phase 2C or 2D).
`jarvis-phase2.service`: `static` / `inactive`, no `[Install]` section.
Direct run: `{"status":"DISABLED","reason":"JARVIS_ENABLED is not true"}`, exit
**78**. No Jarvis process runs.

## 7. DATABASE COMPONENTS

- pgvector `0.8.6`
- `ai_semantic.memory_embedding` + `memory_embedding_cosine_idx` (HNSW cosine).
  **No embeddings and no embedding model are installed** — the schema is empty.
- `core.jarvis_task_state` (task_id, state_json, version, updated_at), 1:1 with
  `core.ai_task`. **0 rows.** Optimistic concurrency; a stale
  `expected_version` raises `[P0001] task state version conflict`.
- `core.ai_action_type` — the canonical action contract, 6 rows, owner
  `function_owner`. **Phase 2D:** `ai_reader` holds column-level `SELECT` on
  six columns only (migration 004). `description` and `created_at` remain
  unreadable; `ai_writer` has no access at all; writes are denied to both.
- `core.ai_task` 16 rows (all `PROPOSED_WRITTEN`); `core.ai_action_proposal`
  **0 rows**.
- Controlled interfaces (SECURITY DEFINER, owned by `function_owner`):
  `ai_save_jarvis_task_state`, `ai_load_jarvis_task_state`, `ai_enqueue_task`,
  `ai_claim_task`, `ai_propose_action`, `ai_decide_action`,
  `ai_claim_approved_action`, `ai_orchestrator_health`, `ai_get_model_policy`,
  `ai_get_pending_actions`.

## 8. SECURITY BOUNDARIES

Roles `ai_reader`, `ai_writer`, `human_approver`, `action_executor`,
`function_owner`: all NOLOGIN, NOINHERIT, NOSUPERUSER, NOCREATEDB,
NOCREATEROLE, NOREPLICATION, NOBYPASSRLS.

`ai_writer` holds **no table privileges**. `ai_reader` holds exactly one:
column-level SELECT on the action contract. Verified blocked live (32/32, every
denial SQLSTATE 42501): raw DML, every `SET ROLE`, `ALTER ROLE … SUPERUSER`,
`GRANT`, `CREATE ROLE`, self-approval, direct execution, self-enqueue,
`COPY … TO PROGRAM`, credential reads, `core.ai_provider_allowed` for
`ai_reader`, state replay, duplicate proposal replay, and — new in Phase 2D —
reading ungranted contract columns, `SELECT *`, `ai_writer` reading the
contract, and `ai_reader` writing or inserting an action type.

**Jarvis cannot add an entry to its own allowlist.**

Because `SET SESSION AUTHORIZATION` changes `session_user`, a superuser
connection that assumes `ai_writer` genuinely loses superuser — that is why
these tests are valid rather than theatre.

## 9. ACTION FIREWALL

**Two layers, one allowlist.**

Authority: `core.ai_propose_action`. Requires an `action:` prefixed idempotency
key · task `LEASED` and of type `PROPOSE_ACTION` · matching unexpired lease ·
action type enabled in `core.ai_action_type` · exact per-type payload shape ·
`core.ai_jsonb_has_forbidden_key` · payload ≤ 16 KB. On success the task moves
to `NEEDS_REVIEW`, which is what makes replay impossible. **Unchanged by
Phase 2D.**

Early gate: `jarvis/firewall.py`. It keeps **no allowlist of its own** (a test
asserts `ALLOWED_ACTIONS` no longer exists). It resolves an internal intent
against the contract loaded from PostgreSQL and returns the canonical type with
the risk class, approval mode and schema version read from the database.
Payload *shape* is deliberately left to the database — mirroring those schemas
in Python would recreate the drift F-1 was about.

Canonical types (6): `DRAFT_CUSTOMER_REPLY` (MEDIUM/ONE_PERSON) ·
`META_CAMPAIGN_CHANGE` (HIGH/ONE_PERSON) · `PRICE_CHANGE` (CRITICAL/TWO_PERSON)
· `REQUEST_HUMAN_REVIEW` (LOW/ONE_PERSON, execution_enabled) ·
`WHATSAPP_SEND_TEMPLATE` (HIGH/ONE_PERSON) · `WIX_PUBLISH` (CRITICAL/TWO_PERSON).

Internal intent → canonical map (`CONTRACT_MAP_VERSION = 2026-09-18.1`):
`CUSTOMER_REPLY_DRAFT`, `HUMAN_REVIEW_REQUEST`, `WHATSAPP_TEMPLATE_SEND`,
`META_CAMPAIGN_CHANGE`, `PRICE_CHANGE`, `WIX_PUBLISH`.

**Drift check** runs at preflight and on a 60 s TTL, failing closed in both
directions (mapping target missing/disabled → `unknown_internal`; unmapped
canonical type → `unknown_canonical`). While invalid, a risky request is forced
to `BLOCKED` with route `contract-drift-block`; read-only requests are
unaffected by design. Live: hash `935c0769511c188e`, canonical 6, mapped 6,
valid.

## 10. HUMAN APPROVAL

Unchanged and authoritative. `ai_decide_action` and `ai_get_pending_actions`:
`human_approver` only. `ai_enqueue_task`: `human_approver` only — Jarvis cannot
create its own work. Execution surfaces: `action_executor` only. Jarvis holds
`ai_writer`, which has none of these.

**No operator-facing surface exists for approving a proposal.** The path exists
in the database; nothing presents pending actions to a person yet.

## 11. COMPANY MEMORY INTERFACES

`jarvis/memory.py` — fixed allowlisted queries only, no user or model text ever
interpolated into SQL. Every query runs as
`BEGIN; SET SESSION AUTHORIZATION ai_reader; … ROLLBACK;`.

`system` → `core.ai_orchestrator_health()` · `agenda` → `mart.sirket_gundemi`
(25) · `open_work` → `mart.acik_isler` (25) · `decision_summary` →
`mart.karar_ozet` · `capabilities` → `core.ai_get_model_policy()` ·
`company_dashboard` → `mart.ai_company_intelligence_dashboard` ·
**`action_contract`** → the six granted columns of `core.ai_action_type` ·
**`capability_state`** → `pg_catalog` infrastructure facts plus the health
record, in one snapshot.

`capability_state` uses `pg_catalog`, not `information_schema`, deliberately:
`information_schema.routines` is filtered by the caller's privileges, so a
missing EXECUTE grant would masquerade as a missing function.

Transport resolved in one place, `jarvis/transport.py`:
`JARVIS_MEMORY_TRANSPORT=local-docker` → direct docker exec on the host;
otherwise SSH via `JARVIS_SSH_HOST` (default alias `lcarlie`).
**On the server you must use `local-docker`** — the alias does not resolve there.

## 12. PERSISTENT STATE

PostgreSQL-backed through controlled functions only. Proven in TEST G: save v1
→ provider interruption → reload → provider B continuation → save v2 → stale
replay rejected → state untouched. `jarvis/state.py` (sqlite) still exists but
is **not** the production backend.

## 13. PGVECTOR / SEMANTIC STATE

Schema and index exist and are tested; **no embeddings, no embedding model, no
semantic retrieval in use**. The capability registry now reports this as a
measured `RESOURCE_BLOCKED` rather than an assumption: host 13.65 GiB / 4 cores
against BGE-M3's 32 GiB / 8 cores.

## 14. SERVICES / CONTAINERS

`jarvis-phase2.service` — static, inactive, `User=jarvis` (uid 996), oneshot,
`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`,
`MemoryMax=256M`, `CPUQuota=100%`, `TasksMax=64`, deliberately no `[Install]`.
Containers as listed in §5. `question-worker` service: **inactive**,
deliberately not started.

## 15. RELEVANT PATHS

```
/opt/lcarlie/jarvis-phase2/                  Jarvis package (production)
  jarvis/            memory, transport, context, phase2, shadow, runtime,
                     action_contract, firewall, capabilities, routing,
                     state_pg, telemetry, governors, cache, cli, benchmark
  scripts/           run_shadow_acceptance.py (gate), run_phase2c_acceptance.py,
                     run_phase2d_proposal_e2e.py, run_test_g_state_fallback.py,
                     run_phase2c_security_recheck.py, psql_session.py,
                     benchmark_live.py
  tests/             test_bootstrap, test_phase2, test_shadow, test_state_pg,
                     test_live_phase2, test_action_contract, test_capabilities,
                     question-worker-phase2b.test.js
  migrations/        001 pgvector, 002 semantic, 003 jarvis_task_state,
                     004 action contract read grant (+ rollback for each)
  deploy/            service unit, env template, pgvector Dockerfile/patch,
                     question-worker-phase2b.js (candidate)
  evidence/          Phase 2C and Phase 2D evidence JSON
/etc/lcarlie/jarvis-phase2.env               persistent env (keys in §29)
/opt/lcarlie/source/lcarlie-jarvis-v1        canonical source baseline (git)
/opt/lcarlie/orchestrator/question-worker.js production worker (UNTOUCHED)
/opt/lcarlie/backups/                        rollback points
```

## 16. SHA-256

| File | SHA-256 |
|---|---|
| `orchestrator/question-worker.js` (production) | `d0a6e9acfc60f513656a006fad6b4790d69c4bc195fb891d028619e5cb4db65e` |
| `deploy/question-worker-phase2b.js` (candidate) | `af0061921fff01ec72002f093e79bf0d689d4b287db5ca02a5edde09e20e59ba` |
| `jarvis/action_contract.py` | `21975b064ad530b63cdeb54ccce3da63e34ec5d127f5e10127c9100922f37a3a` |
| `jarvis/firewall.py` | `241896a899901a65e7ad51defeba2d1cfe33161fff79893fb419ddea7c0490d0` |
| `jarvis/capabilities.py` | `da97c261a74d3ced454359ddfa07807a7917d7e21755e6b673e72240adccfc3b` |
| `jarvis/context.py` | `ee0e102e2eed9fbd4b73274be91cde119f52a016b6441b3261f358a3aff7286a` |
| `jarvis/phase2.py` | `be60d58f537da19ccd5d67d8bde17591a96c1ef625e4c39a8fcd339412d89f3e` |
| `jarvis/shadow.py` | `8e867cee34bfc6837897ca95af040c454b7e8fcb55ae943500e3226a61f17073` |
| `jarvis/memory.py` | `9067c2b89380965681c590c83bdb07b35561cd36331528f92cd703e8b24b67ec` |
| `jarvis/cli.py` | `b0c642c4ca5e74ab1a48fdde5764f51e093767e26158847b96982909f92769da` |
| `scripts/run_phase2d_proposal_e2e.py` | `8ef05cf96294b0a0389a16546e0c68821fec8f86ef52f05d7f7526cb4dfc737e` |
| `scripts/run_phase2c_acceptance.py` | `07fde400adbfa4d6723fc2a90efa57b46d5885217e1f283c727d73033c45a4ea` |
| `scripts/run_phase2c_security_recheck.py` | `ed436e06f7d9381c16031e3518940dd716c99e8215054f3bc436e475277b4496` |
| `scripts/run_test_g_state_fallback.py` | `da5c878c414678f2d95ad2690cb631f448c24684e10ff4ca3adcbc71d9ed160c` |
| `migrations/004_action_contract_read_PROPOSED.sql` | `630dd6382a854a74d507aa3a2d175316db4ffad6615cb7781b268572f9ffede7` |
| `migrations/rollback/004_action_contract_read_ROLLBACK.sql` | `4dd6ca87ac41436ab00273aff3ab493c8eac0e1d0690966858c9b3213614a102` |
| `tests/test_action_contract.py` | `24ceb44f5420851ec121b4e58784ac44bc906aacacaf46939f4c2c9985b15a42` |
| `tests/test_capabilities.py` | `26ac8537d7380cb47df7e21902e44fab4ab96d86ec4919abde2cdf5db3c2f7ab` |
| `tests/test_shadow.py` | `54107b73edb45ac030f06e61f08097cfca4002291be739f62a33ec2fe026e0ba` |
| `tests/test_bootstrap.py` | `342316098acbd1900c3485c8309324d5ead26754977ce541827864ea57a3181b` |
| source snapshot `lcarlie-jarvis-source-v1b.tar.gz` | `a0f6cbed2e7ac284dd1cf5eab4deaf733075ac38f2acd736c0f6c0f7786e113f` |
| Phase 2B DB dump | `22a26127448981e62b27679f11b8609f3a4460e0a3549760d77bf4c1935df535` |
| Phase 2D package backup | `8fb67b482ba892233c78ebc73d88dbfd92a42dace860f580970092f7ac6db8fe` |

## 17. BACKUPS

```
/opt/lcarlie/backups/phase2b-20260918T142200+0300   DB dump, globals, orchestrator archive
/opt/lcarlie/backups/phase2c-20260918T145500+0300   pre-Phase2C package + Codex acceptance evidence
/opt/lcarlie/backups/phase2c-claude-20260918T150824 package before Phase 2C edits
/opt/lcarlie/backups/phase2d-20260918T152553        package + ai_action_type schema before Phase 2D
/opt/lcarlie/phase2b-staging/                        migrations, compose patch, packaged tgz
```
Phase 2B restore was tested in an isolated PostgreSQL 17 (129 core/mart tables,
16 AI tasks recovered). Migration rollbacks tested.

## 18. ROLLBACK

```sh
# Jarvis package
tar xzf /opt/lcarlie/backups/phase2d-20260918T152553/jarvis-phase2.pre-phase2d.tgz \
    -C /opt/lcarlie
# Phase 2D database grant
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -f - \
  < /opt/lcarlie/jarvis-phase2/migrations/rollback/004_action_contract_read_ROLLBACK.sql
# source
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 checkout 37a3b96
# earlier DB objects
#   migrations/rollback/001..003_*_ROLLBACK.sql
# full DB
#   /opt/lcarlie/backups/backup/geri-yukle.sh   (validate -> safety dump -> restore -> verify)
```

Revoking grant 004 makes the contract unreadable, `contract_valid` false, and
every proposal path fail closed. That is the intended degraded behaviour.

Nothing needs rolling back now: no production behaviour changed.

## 19. TEST RESULTS

| Suite | Result |
|---|---|
| Local Python suite | **85 tests, OK** (80 executed + 5 live-gated) |
| Live Company Memory (on host) | **5/5 PASS** |
| Acceptance A–F/H, 10 repeats | **PASS**, 70 samples |
| Acceptance gate (Codex assertions) | **PASS** |
| Proposal E2E (Phase 2D) | **PASS**, 28/28 checks |
| TEST G state/fallback | **PASS**, 17/17 checks |
| Security recheck | **PASS**, 32/32 (27 denials + 5 positive controls) |
| question-worker one-shot | **9/9 PASS** |
| External provider calls | **0** |
| External actions | **0** |

## 20. PERFORMANCE

Acceptance: 70 samples, **p50 93.397 ms, p95 104.803 ms** (min 84.841, max
109.398), max RSS 19.25 MB, 0 model calls, 0 failures.
Per-case p50: A 90.53 · B 92.75 · C 89.06 · D 102.89 · E 95.60 · F 92.37 ·
H 93.66. `benchmark_live`: 18 samples, p50 91.229, p95 95.822.

Phase 2C baseline was p50 91.979 / p95 97.398 — Phase 2D costs +1.4 ms p50 for
a live contract check and real capability analysis. Not material.
`contract_check_ms` is 0.009 ms after preflight; the contract load (~86 ms)
happens once at construction.

Not comparable to the Phase 2 numbers (431.761 / 453.378 ms): those were
measured over SSH from a workstation, these are local-docker on the host.

## 21. BLOCKERS

**No open blocker.** F-1 and F-2 were closed in Phase 2D.

Carried forward, unchanged: BGE-M3 `WAITING_RESOURCE_UPGRADE` (now measured:
13.65 GiB / 4 cores against 32 GiB / 8 cores) · Ruflo
`WAITING_UPSTREAM_REPRODUCIBILITY` · Yemaka reference-only · remote canonical
repository unresolved by design · production `question-worker` service
`FAILED_SAFE`, deliberately not restarted.

Design note, not a blocker: per-type payload schemas are enforced only by
`core.ai_propose_action`. Duplicating them in Python would recreate the drift
F-1 was about, so a wrong payload shape is caught at the database.
`schema_version` is part of the contract hash, so a schema change flips
`contract_valid` and fails closed.

## 22. RESOURCE REQUIREMENTS

Current host: 13.65 GiB RAM, 4 cores, 70 GB free disk, no GPU. Sufficient for
everything Phase 2C/2D does (peak RSS 19 MB).
BGE-M3 needs ≥ 32 GiB RAM dedicated (64 GiB co-located), 8 modern cores,
20 GiB disk; GPU optional, 12 GiB VRAM practical minimum, 16–24 GiB for heavier
evaluation. **Do not load it on this host.** Hardware limitation is not a
rejection criterion — report `REQUIRES_RESOURCE_UPGRADE`.

## 23. UPSTREAM STATUS

RouteLabs Router — 138 upstream tests PASS; routing candidate only, must never
own truth, approval, the firewall, or business authorization.
pgvector 0.8.6 — PASS, in production.
Qwen-Agent 0.0.34 — import/smoke PASS; four undeclared runtime dependencies.
smolagents — smoke PASS, restricted candidate. Agno — smoke PASS, challenger.
Ruflo — BLOCKED upstream; do not force install.
Yemaka — root build blocked; architecture reference.
BGE-M3 — `WAITING_RESOURCE_UPGRADE`.

**Do not re-research any of this.**

## 24. QUESTION WORKER

Production worker untouched and unstarted (hash `d0a6e9ac…`), still in its
known `FAILED_SAFE: no json` condition. Candidate `af006192…` passes 9/9
deterministic one-shot tests. **Do not promote or start it.**

`node` does not exist on the host — it lives only inside the n8n image. Run the
tests with a throwaway container and a read-only mount; never `docker cp` into
the live n8n container.

## 25. SOURCE OF TRUTH

`/opt/lcarlie/source/lcarlie-jarvis-v1`, no remote, clean tree.
Baseline `28f1bb6e…`; Phase 2C `5a4b2dd`, `37a3b96`; Phase 2D — see
`SOURCE_OF_TRUTH_V1.md`. Deployment and source verify byte-identical
(permissions included).

## 26. LAST SUCCESSFUL STEP

Phase 2D closed both Phase 2C findings. F-1: the Python allowlist was deleted
and replaced by the live `core.ai_action_type` contract, read through a
column-level grant, with a versioned intent map and a fail-closed drift check;
a real Python-built proposal reached `core.ai_propose_action` and became
`PROPOSED` twice, then rolled back. F-2: the capability registry now derives
status from live probes and measured host resources, and `ContextCompiler`
performs real capability-gap analysis — TEST D is a full PASS. Security 32/32,
TEST G 17/17, acceptance A–F/H PASS, Jarvis returned to disabled.

## 27. NEXT STEP

**Nothing runs automatically. Phase 2D is closed and there is no open blocker.**

The next step is a human decision, not a task: pursue a narrow supervised
activation (one action type, one channel, human approval on every proposal), or
keep Jarvis shadow-only as a read-only analysis surface.

If activation is ever chosen, the first technical question is **who holds
`human_approver` in practice and how a pending proposal is shown to them** —
the approval path exists in the database but has no operator-facing surface.

## 28. DO NOT TOUCH

Caddy · n8n and its configuration · ICaz · `/opt/lcarlie/orchestrator` ·
`core.ai_propose_action` and every other Core function · human approval
ownership · any role or grant beyond migration 004 (in particular do **not**
grant `ai_reader` EXECUTE on `core.ai_provider_allowed`, and do not widen 004
to the whole table) · `/etc/lcarlie/jarvis-phase2.env` · the systemd unit's
missing `[Install]` section · the production `question-worker` service.

Do not set `JARVIS_ENABLED=true` persistently. Do not enable or start
autonomous Jarvis. Do not send external actions. Do not install new software,
research more repositories, or expand scope.

## 29. VERIFICATION COMMANDS

Environment **key names** only — no values are recorded anywhere in this
document set. `/etc/lcarlie/jarvis-phase2.env`: `JARVIS_ENABLED`,
`JARVIS_STATE_BACKEND`, `JARVIS_DB_HOST`, `JARVIS_DB_PORT`, `JARVIS_DB_NAME`,
`JARVIS_DB_ROLE`, `JARVIS_MAX_CONCURRENCY`. Shadow-only process keys:
`JARVIS_MODE`, `EXTERNAL_ACTIONS`, `JARVIS_MEMORY_TRANSPORT`, `JARVIS_SSH_HOST`,
`JARVIS_LIVE_TEST`, `PHASE2C_REPEATS`.

```sh
# safe state
grep '^JARVIS_ENABLED=' /etc/lcarlie/jarvis-phase2.env      # expect false
systemctl is-enabled jarvis-phase2.service                  # expect static
systemctl is-active  jarvis-phase2.service                  # expect inactive
/opt/lcarlie/jarvis-phase2/bin/jarvis-phase2; echo $?        # expect 78

# no side effects
docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -At \
  -c "SELECT count(*) FROM core.jarvis_task_state"          # expect 0

# action contract grant (expect the six columns, description/created_at none)
docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -At -c \
 "SELECT attname||'='||COALESCE(array_to_string(attacl,','),'none')
    FROM pg_attribute WHERE attrelid='core.ai_action_type'::regclass AND attnum>0"

# local suites
cd /opt/lcarlie/jarvis-phase2/tests && \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 python3 -m unittest discover -s . -t .
cd /opt/lcarlie/jarvis-phase2/tests && JARVIS_LIVE_TEST=1 \
  JARVIS_MEMORY_TRANSPORT=local-docker \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 python3 -m unittest test_live_phase2

# shadow acceptance (SHADOW env is per-process only, never persisted)
cd /opt/lcarlie/jarvis-phase2 && export JARVIS_ENABLED=true JARVIS_MODE=SHADOW \
  EXTERNAL_ACTIONS=false JARVIS_MEMORY_TRANSPORT=local-docker \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 && \
  python3 scripts/run_shadow_acceptance.py && \
  python3 scripts/run_phase2c_acceptance.py

# proposal E2E / TEST G / security  (all rollback-safe)
cd /opt/lcarlie/jarvis-phase2 && PYTHONPATH=$PWD \
  python3 scripts/run_phase2d_proposal_e2e.py
cd /opt/lcarlie/jarvis-phase2 && PYTHONPATH=$PWD \
  python3 scripts/run_test_g_state_fallback.py
cd /opt/lcarlie/jarvis-phase2 && PYTHONPATH=$PWD \
  python3 scripts/run_phase2c_security_recheck.py

# question worker (host has no node)
docker run --rm --entrypoint node -v /opt/lcarlie/jarvis-phase2:/w:ro -w /w \
  n8nio/n8n:2.38.7 --test tests/question-worker-phase2b.test.js

# source of truth
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 status --porcelain   # expect empty
rsync -ain --delete --exclude=__pycache__ \
  /opt/lcarlie/jarvis-phase2/ \
  /opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2/            # expect empty
```

## 30. STOP / ROLLBACK CONDITIONS

Stop immediately and roll back if any of these is observed:

- `JARVIS_ENABLED=true` persisted in `/etc/lcarlie/jarvis-phase2.env`
- `jarvis-phase2.service` becomes `enabled` or `active`, or gains an
  `[Install]` section
- any row in `core.jarvis_task_state` outside a rolled-back test
- any row in `core.ai_action_proposal` not created by a human-approved flow
- any `ai_task` in state `APPROVED` or beyond without a `human_approver`
  decision
- `core.ai_action_type` gaining, losing or changing a row without a
  corresponding mapping update — Jarvis will fail closed, which is correct, but
  the cause must be found
- grant 004 widened beyond the six columns, extended to `ai_writer`, or any
  other grant added to `ai_reader`/`ai_writer`
- `jarvis/firewall.py` regaining an allowlist of its own
- any external provider call or any external action from SHADOW
- the production `question-worker.js` hash ceasing to be `d0a6e9ac…`, or its
  service becoming active
- `rsync -ain` between deployment and canonical source producing output
- any container unhealthy, or an n8n workflow changing active state
