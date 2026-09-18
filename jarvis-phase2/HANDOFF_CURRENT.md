# HANDOFF — CURRENT STATE

Describes the system **as it actually is** at 2026-09-18 15:15 +03:00, not as
planned. No secret values appear here; environment variables are listed by key
name only.

Read this first. Then `PHASE2C_ACTIVATION_PREFLIGHT_REPORT.md` for the
evidence behind every claim.

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

PostgreSQL is canonical verified truth. Vector similarity is retrieval only.
Models own neither truth nor authorization. The Action Firewall and human
approval are authoritative and live in the database.

## 3. CURRENT PHASE

**Phase 2C complete.** Marker `PHASE2C_SHADOW_READY` exists.
**Not activated.** The marker means shadow-ready, nothing more.

## 4. COMPLETED PHASES

| Phase | Result |
|---|---|
| 1 | deterministic local-first bootstrap, FakeProvider tests, no external execution |
| 2 | real Company Memory adapter, Context Compiler, controlled task/proposal, execution planner, provider-independent routing |
| 2B | production integration: pgvector image, semantic schema, `core.jarvis_task_state`, packaged service — `PHASE2_PRODUCTION_INTEGRATION_READY`, Jarvis still disabled |
| 2C | activation preflight, source-of-truth baseline, SHADOW mode, first controlled SHADOW execution, acceptance A–H, security recheck — `PHASE2C_SHADOW_READY` |

## 5. PRODUCTION STATE

All healthy: `lcarlie-postgres` (healthy), `lcarlie-n8n`, `lcarlie-caddy`,
`icaz-site`, `icaz-oyun`, `icaz-postgres`.
n8n workflows unchanged — MEVZUAT FILTRESI, SATIS AJANI, WHATSAPP, INSTAGRAM
active; WEB SOHBET inactive (deliberate, pre-existing).
Host: 13.6 GiB RAM, disk 19 % used (70 GB free).

## 6. JARVIS ENABLED/DISABLED

**DISABLED.**
`JARVIS_ENABLED=false` in `/etc/lcarlie/jarvis-phase2.env` (mtime 14:39:13 —
not written during Phase 2C).
`jarvis-phase2.service`: `static` / `inactive`, no `[Install]` section.
Direct run: `{"status":"DISABLED","reason":"JARVIS_ENABLED is not true"}`, exit
**78**.

## 7. DATABASE COMPONENTS

- pgvector `0.8.6`
- `ai_semantic.memory_embedding` + `memory_embedding_cosine_idx` (HNSW cosine).
  **No embeddings and no embedding model are installed** — the schema is empty
  and unused.
- `core.jarvis_task_state` (task_id, state_json, version, updated_at), 1:1 with
  `core.ai_task`. **0 rows.**
- `core.ai_task` 16 rows, all `PROPOSED_WRITTEN`. `core.ai_action_proposal`
  **0 rows**.
- Controlled interfaces: `ai_save_jarvis_task_state`,
  `ai_load_jarvis_task_state`, `ai_enqueue_task`, `ai_claim_task`,
  `ai_propose_action`, `ai_decide_action`, `ai_claim_approved_action`,
  `ai_orchestrator_health`, `ai_get_model_policy`, `ai_get_pending_actions` —
  all SECURITY DEFINER, owned by `function_owner`.

## 8. SECURITY BOUNDARIES

Roles `ai_reader`, `ai_writer`, `human_approver`, `action_executor`,
`function_owner`: all NOLOGIN, NOINHERIT, NOSUPERUSER, NOCREATEDB,
NOCREATEROLE, NOREPLICATION, NOBYPASSRLS.

`ai_writer` holds **no table privileges at all**. Verified blocked live
(26/26, every denial SQLSTATE 42501): raw DML, `SET ROLE` to any privileged
role, `ALTER ROLE … SUPERUSER`, `GRANT`, `CREATE ROLE`, self-approval, direct
execution, self-enqueue, `COPY … TO PROGRAM`, credential reads, state replay,
duplicate proposal replay. `ai_reader` cannot write, propose, approve, or call
`core.ai_provider_allowed`.

Because `SET SESSION AUTHORIZATION` changes `session_user`, a superuser
connection that assumes `ai_writer` genuinely loses superuser — that is why
these tests are valid rather than theatre.

## 9. ACTION FIREWALL

Authoritative implementation: `core.ai_propose_action`. Requires an `action:`
prefixed idempotency key · task `LEASED` and of type `PROPOSE_ACTION` ·
matching unexpired lease token · action type enabled in `core.ai_action_type` ·
exact per-type payload shape · `core.ai_jsonb_has_forbidden_key` · payload
≤ 16 KB. On success the task becomes `NEEDS_REVIEW`, which is what makes
replay impossible.

Enabled types (6): `DRAFT_CUSTOMER_REPLY` (MEDIUM), `META_CAMPAIGN_CHANGE`
(HIGH), `PRICE_CHANGE` (CRITICAL), `REQUEST_HUMAN_REVIEW` (LOW),
`WHATSAPP_SEND_TEMPLATE` (HIGH), `WIX_PUBLISH` (CRITICAL).

**Unchanged by Phase 2C.** See blocker F-1 in §21 — the Python-side allowlist
does not match this one.

## 10. HUMAN APPROVAL

Unchanged and authoritative. `ai_decide_action` and `ai_get_pending_actions`:
`human_approver` only. `ai_enqueue_task`: `human_approver` only — Jarvis
cannot create its own work. Execution surfaces: `action_executor` only. Jarvis
holds `ai_writer`, which has none of these.

## 11. COMPANY MEMORY INTERFACES

`jarvis/memory.py` — fixed allowlisted queries only, no user or model text ever
interpolated into SQL. Every query runs as
`BEGIN; SET SESSION AUTHORIZATION ai_reader; … ROLLBACK;`.

Queries: `system` → `core.ai_orchestrator_health()` · `agenda` →
`mart.sirket_gundemi` (25) · `open_work` → `mart.acik_isler` (25) ·
`decision_summary` → `mart.karar_ozet` · `capabilities` →
`core.ai_get_model_policy()` · `company_dashboard` →
`mart.ai_company_intelligence_dashboard`.

Transport resolved in one place, `jarvis/transport.py`:
`JARVIS_MEMORY_TRANSPORT=local-docker` → direct docker exec on the host;
otherwise SSH via `JARVIS_SSH_HOST` (default alias `lcarlie`).
**On the server you must use `local-docker`** — the alias does not resolve
there.

## 12. PERSISTENT STATE

PostgreSQL-backed, via controlled functions only. Optimistic concurrency:
a stale `expected_version` is rejected with `[P0001] task state version
conflict`. Proven in TEST G: save v1 → provider interruption → reload → provider
B continuation → save v2 → stale replay rejected → state untouched.
`jarvis/state.py` (sqlite) still exists but is **not** the production backend.

## 13. PGVECTOR / SEMANTIC STATE

Schema and index exist and are tested; **no embeddings, no embedding model, no
semantic retrieval in use**. BGE-M3 remains `WAITING_RESOURCE_UPGRADE`
(needs ≥ 32 GiB, host has 13.6 GiB).

## 14. SERVICES / CONTAINERS

`jarvis-phase2.service` — static, inactive, `User=jarvis` (uid 996), oneshot,
`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`,
`MemoryMax=256M`, `CPUQuota=100%`, `TasksMax=64`, deliberately no `[Install]`.
Containers as listed in §5.
`question-worker` service: **inactive**, deliberately not started.

## 15. RELEVANT PATHS

```
/opt/lcarlie/jarvis-phase2/                  Jarvis package (production)
  jarvis/            runtime: memory, context, phase2, shadow, routing,
                     state_pg, firewall, transport, telemetry, governors, cache
  scripts/           run_shadow_acceptance.py (gate), run_phase2c_acceptance.py,
                     run_test_g_state_fallback.py,
                     run_phase2c_security_recheck.py, psql_session.py,
                     benchmark_live.py
  tests/             test_bootstrap, test_phase2, test_shadow, test_state_pg,
                     test_live_phase2, question-worker-phase2b.test.js
  migrations/        001 pgvector, 002 semantic, 003 jarvis_task_state (+rollback)
  deploy/            service unit, env template, pgvector Dockerfile/patch,
                     question-worker-phase2b.js (candidate)
  evidence/          Phase 2C evidence JSON
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
| `bin/jarvis-phase2` | `6ec03f1c5adeb764bdb4e85f0aee59b53115b61d06f2b4fd05fc7596c4c1f8a2` |
| `jarvis/shadow.py` | `6751b85b91fd25a137858b8c86904fbae8baecbd7370d55e45d24e7a6c24f8a0` |
| `jarvis/transport.py` | `816e2b064e792ebaa990b1f377096be20ae34824d34e0c45ac49a909111fc61e` |
| `jarvis/memory.py` | `9f467dd8056dd1502c835ce08364c48b8329b2e4d55843575d3528e7059e6097` |
| `scripts/run_shadow_acceptance.py` | `da869bdd485a122f42fb6ef8d57b773e4ef264c2409539415f824f16348e1767` |
| `scripts/run_phase2c_acceptance.py` | `41ef02847bfd75a1a1f5ab166cac75e46c462d5b0a77a50344f851310bd542cf` |
| `scripts/run_test_g_state_fallback.py` | `b0b3459dfa9397a702c3920d9495f153afd653b8d9dfe8a2fea58f27d7fec778` |
| `scripts/run_phase2c_security_recheck.py` | `68a78cc0509321f7eee04db97af693c63807fbac6c0363fbfb9de51cd9a7cf69` |
| `scripts/psql_session.py` | `897a026c3ae1cebc32b016d37c6e9f7cc7d62643ab312babf508be76857690a8` |
| source snapshot `lcarlie-jarvis-source-v1b.tar.gz` | `a0f6cbed2e7ac284dd1cf5eab4deaf733075ac38f2acd736c0f6c0f7786e113f` |
| Phase 2B DB dump | `22a26127448981e62b27679f11b8609f3a4460e0a3549760d77bf4c1935df535` |
| `orchestrator.pre-phase2b.tar.gz` | `b25e10fe65ad9f2c4bfc1dcadbf325098cd7db127605b1d1117805f57f2bad3d` |
| Phase 2C package backup (this session) | `47f5e1b6c5c93b10da748c3acfe4dc6a8b355bee24eb6f8a38a5415c38e397ee` |

## 17. BACKUPS

```
/opt/lcarlie/backups/phase2b-20260918T142200+0300   DB dump, globals, orchestrator archive,
                                                     compose, restore-gate result
/opt/lcarlie/backups/phase2c-20260918T145500+0300   pre-Phase2C package, hashes,
                                                     Codex's shadow-acceptance.json
/opt/lcarlie/backups/phase2c-claude-20260918T150824 package backup before this session's edits
/opt/lcarlie/phase2b-staging/                        migrations, compose patch, packaged tgz
```
Phase 2B restore was actually tested in an isolated PostgreSQL 17 (129
core/mart tables, 16 AI tasks recovered). Migration rollbacks tested.

## 18. ROLLBACK

- Jarvis package → untar a backup above over `/opt/lcarlie/jarvis-phase2`.
- Source → `git -C /opt/lcarlie/source/lcarlie-jarvis-v1 checkout 28f1bb6e…`
  (the pre-Phase-2C baseline).
- DB objects → `migrations/rollback/001…003_*_ROLLBACK.sql`.
- Full DB → `/opt/lcarlie/backups/backup/geri-yukle.sh` (validate → safety dump
  → restore → verify; refuses without a pty unless `--onayla`).

Nothing needs rolling back right now: no production behaviour changed.

## 19. TEST RESULTS

| Suite | Result |
|---|---|
| Local Python suite | **22 tests, OK** (17 executed + 5 live) |
| Live Company Memory (on host) | **5/5 PASS** — previously impossible, see §26 |
| Acceptance A–F/H, 5 repeats | **PASS**, 35 samples |
| Acceptance gate (Codex's assertions) | **PASS**, exit 0 |
| TEST G state/fallback | **PASS**, 16/16 checks |
| Security recheck | **PASS**, 26/26 (22 denials + 4 positive controls) |
| question-worker one-shot | **9/9 PASS** |
| External provider calls | **0** |
| External actions | **0** |

## 20. PERFORMANCE

Acceptance: 35 samples, **p50 91.979 ms, p95 97.398 ms** (min 84.702, max
101.949), max RSS 19.12 MB, CPU 0.109 s, 0 model calls, 0 failures.
`benchmark_live`: 18 samples, p50 88.304 ms, p95 94.654 ms.
TEST G whole transaction: 116.73 ms.

Not comparable to the Phase 2 numbers (431.761 / 453.378 ms): those were
measured over SSH from a workstation, these are local-docker on the host.

## 21. BLOCKERS

**F-1 (must close before activation) — Action Firewall allowlists diverge.**
`jarvis/firewall.py` allows `CRM_REPLY_DRAFT`, `META_BUDGET_CHANGE_PROPOSAL`,
`WIX_PRICE_CHANGE_PROPOSAL`, `CONTENT_CHANGE_PROPOSAL`,
`DATA_QUALITY_INVESTIGATION`; the database allows six entirely different
names. **Overlap: none.** A proposal validated by the Python firewall can never
be persisted. Not an escalation path — the database is authoritative and
stricter — but the first real proposal would fail.

**F-2 (should close) — capability-gap analysis not implemented.**
`ContextCompiler` has no capability branch, so capability questions retrieve
`mart.karar_ozet` instead of `core.ai_get_model_policy()`. TEST D passes its
safety requirement but not its analytical one.

Carried forward: BGE-M3 `WAITING_RESOURCE_UPGRADE` · Ruflo
`WAITING_UPSTREAM_REPRODUCIBILITY` · Yemaka reference-only · remote canonical
repository unresolved by design · production `question-worker` service
`FAILED_SAFE`, deliberately not restarted.

## 22. RESOURCE REQUIREMENTS

Current host: 13.6 GiB RAM, 70 GB free disk, no GPU. Sufficient for everything
Phase 2C does (peak RSS 19 MB).
BGE-M3 needs ≥ 32 GiB RAM dedicated (64 GiB if co-located), 8 modern cores,
20 GiB disk; GPU optional, 12 GiB VRAM practical minimum, 16–24 GiB for heavier
evaluation. **Do not load it on this host.** Hardware limitation is not a
rejection criterion — report `REQUIRES_RESOURCE_UPGRADE` instead of choosing a
weaker architecture.

## 23. UPSTREAM STATUS

RouteLabs Router — 138 upstream tests PASS; routing candidate only, must never
own truth, approval, the firewall, or business authorization.
pgvector 0.8.6 — PASS, in production.
Qwen-Agent 0.0.34 — import/smoke PASS; four undeclared runtime dependencies;
needs a reviewed reproducible lock before any production model use.
smolagents — smoke PASS, restricted candidate.
Agno — smoke PASS, challenger only.
Ruflo — BLOCKED upstream (manifest/lock mismatch); do not force install.
Yemaka — root build blocked (missing `frontend/dist`); architecture reference.
BGE-M3 — `WAITING_RESOURCE_UPGRADE`.

**Do not re-research any of this.**

## 24. QUESTION WORKER

Production worker untouched and unstarted (hash `d0a6e9ac…`), still in its
known `FAILED_SAFE: no json` condition. Candidate `af006192…` passes 9/9
deterministic one-shot tests (schema, prose/markdown wrapping, truncation,
empty output, approval-injection, hash-without-logging, deterministic fallback,
all-providers-fail). **Do not promote or start it in Phase 2C.**

`node` does not exist on the host — it lives only inside the n8n image. Run the
tests with a throwaway container and a read-only mount; never `docker cp` into
the live n8n container (root-owned files in its sticky `/tmp` have broken the
publish pipeline before).

## 25. SOURCE OF TRUTH

`/opt/lcarlie/source/lcarlie-jarvis-v1`, no remote, clean tree.
Baseline `28f1bb6e167ab92dc7c4cbdd39d9e5e81d4951f3`; Phase 2C
`5a4b2dd6e04cd4c959ca38c23ae1a4243e14cb9b`. The baseline had been cut before
Codex finished, so it did not contain Codex's own Phase 2C work — that gap is
now closed and deployment and source are in sync. Details:
`SOURCE_OF_TRUTH_V1.md`.

## 26. LAST SUCCESSFUL STEP

Phase 2C finished: acceptance A–F/H verified and independently reproduced,
TEST G written and passed, security rechecked (26/26), the Company Memory
transport defect fixed so live tests run on the host at all, Phase 2C work
committed to the canonical source, Jarvis confirmed back in its disabled state,
and the handoff and report files written. `PHASE2C_SHADOW_READY` created.

## 27. NEXT STEP

Close **F-1**: reconcile `jarvis/firewall.py` with `core.ai_action_type` —
preferably by deriving the allowlist from the database at runtime, which
removes the drift class entirely — then re-run TEST G so a real Python-built
proposal is exercised end to end. F-2 after it.

Both are development proposals. **Neither is started, and neither authorizes
activation.**

## 28. DO NOT TOUCH

Caddy · n8n and its configuration · ICaz · `/opt/lcarlie/orchestrator` ·
the Action Firewall · human approval ownership · any role or grant (in
particular do **not** grant `ai_reader` EXECUTE on `core.ai_provider_allowed`)
· `/etc/lcarlie/jarvis-phase2.env` · the systemd unit's missing `[Install]`
section · the production `question-worker` service.

Do not set `JARVIS_ENABLED=true` persistently. Do not enable or start
autonomous Jarvis. Do not send external actions. Do not install new software,
research more repositories, or expand scope.

## 29. VERIFICATION COMMANDS

Environment **key names** only — no values are recorded anywhere in this
document set. Keys present in `/etc/lcarlie/jarvis-phase2.env`:
`JARVIS_ENABLED`, `JARVIS_STATE_BACKEND`, `JARVIS_DB_HOST`, `JARVIS_DB_PORT`,
`JARVIS_DB_NAME`, `JARVIS_DB_ROLE`, `JARVIS_MAX_CONCURRENCY`.
Shadow-only process keys: `JARVIS_MODE`, `EXTERNAL_ACTIONS`,
`JARVIS_MEMORY_TRANSPORT`, `JARVIS_SSH_HOST`, `JARVIS_LIVE_TEST`.

```sh
# safe state
grep '^JARVIS_ENABLED=' /etc/lcarlie/jarvis-phase2.env      # expect false
systemctl is-enabled jarvis-phase2.service                  # expect static
systemctl is-active  jarvis-phase2.service                  # expect inactive
/opt/lcarlie/jarvis-phase2/bin/jarvis-phase2; echo $?        # expect 78

# health
docker ps --format '{{.Names}}: {{.Status}}'
docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -At \
  -c "SELECT core.ai_orchestrator_health()"

# no side effects
docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -At \
  -c "SELECT count(*) FROM core.jarvis_task_state"          # expect 0

# local suites
cd /opt/lcarlie/jarvis-phase2/tests && \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 python3 -m unittest discover -s . -t .
cd /opt/lcarlie/jarvis-phase2/tests && JARVIS_LIVE_TEST=1 \
  JARVIS_MEMORY_TRANSPORT=local-docker \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 python3 -m unittest test_live_phase2

# shadow acceptance / TEST G / security  (SHADOW env is per-process only)
cd /opt/lcarlie/jarvis-phase2 && export JARVIS_ENABLED=true JARVIS_MODE=SHADOW \
  EXTERNAL_ACTIONS=false JARVIS_MEMORY_TRANSPORT=local-docker \
  PYTHONPATH=/opt/lcarlie/jarvis-phase2 && \
  python3 scripts/run_shadow_acceptance.py && \
  python3 scripts/run_phase2c_acceptance.py
cd /opt/lcarlie/jarvis-phase2 && PYTHONPATH=$PWD \
  python3 scripts/run_test_g_state_fallback.py
cd /opt/lcarlie/jarvis-phase2 && PYTHONPATH=$PWD \
  python3 scripts/run_phase2c_security_recheck.py

# question worker (host has no node)
docker run --rm --entrypoint node -v /opt/lcarlie/jarvis-phase2:/w:ro -w /w \
  n8nio/n8n:2.38.7 --test tests/question-worker-phase2b.test.js

# source of truth
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 status --porcelain   # expect empty
rsync -ain --delete --exclude=__pycache__ --exclude=evidence \
  /opt/lcarlie/jarvis-phase2/ \
  /opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2/            # expect empty
```

## 30. STOP / ROLLBACK CONDITIONS

Stop immediately and roll back if any of these is ever observed:

- `JARVIS_ENABLED=true` persisted in `/etc/lcarlie/jarvis-phase2.env`
- `jarvis-phase2.service` becomes `enabled` or `active`, or gains an
  `[Install]` section
- any row in `core.jarvis_task_state` outside a rolled-back test
- any row in `core.ai_action_proposal` not created by a human-approved flow
- any `ai_task` in state `APPROVED` or beyond without a `human_approver`
  decision
- any grant widened on `ai_reader` or `ai_writer`, especially
  `core.ai_provider_allowed`
- any external provider call or any external action from SHADOW
- the production `question-worker.js` hash ceasing to be `d0a6e9ac…`, or its
  service becoming active
- `rsync -ain` between deployment and canonical source producing output
- any container unhealthy, or an n8n workflow changing active state
