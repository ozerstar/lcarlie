# PHASE 2D CONTRACT CLOSURE REPORT

**OVERALL: PASS** — F-1 and F-2 are both closed, proven against the live
database, with no new open blocker.

Executed 2026-09-18, 15:21–15:35 +03:00, on the production host. Continued from
the completed Phase 2C state; nothing was redesigned and no scope was added.

**This is not an activation phase.** Jarvis is still disabled.

---

## 1. VERIFIED STARTING STATE

| Check | Observed |
|---|---|
| `JARVIS_ENABLED` | `false` (env mtime 14:39:13, untouched since Phase 2B) |
| `jarvis-phase2.service` | `static` / `inactive` |
| Disabled run | exit **78** |
| PostgreSQL | `lcarlie-postgres` healthy; `core.ai_orchestrator_health()` clean |
| n8n | up; 4 workflows active, WEB SOHBET inactive (pre-existing) |
| Source commit | `37a3b96` (Phase 2C), clean tree, no remote |
| Deployment ↔ source | `rsync -ain` produced **no output** — byte identical |
| Pre-change hashes | recorded for all 8 files that could change |

**One drift item was found, explained, and cleared before any mutation.** A
container `lcarlie-measurement-generator-once` appeared in `docker ps`. It is
pre-existing CR-015 infrastructure: `run-measurement-generator.sh` launches a
hardened one-shot `--rm` container (non-root, read-only, cap-drop ALL) that had
already exited. It is unrelated to Jarvis and touches no file in the mutation
path, which was independently confirmed byte-identical to the canonical source.

## 2. BACKUP

`/opt/lcarlie/backups/phase2d-20260918T152553/`
- `jarvis-phase2.pre-phase2d.tgz` — SHA-256 `8fb67b482ba892233c78ebc73d88dbfd92a42dace860f580970092f7ac6db8fe`
- `ai_action_type.pre-phase2d.sql` — schema of the table the migration touches

Rollback commands:
```sh
# code
tar xzf /opt/lcarlie/backups/phase2d-20260918T152553/jarvis-phase2.pre-phase2d.tgz \
    -C /opt/lcarlie
# database grant
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -f - \
  < /opt/lcarlie/jarvis-phase2/migrations/rollback/004_action_contract_read_ROLLBACK.sql
# source
git -C /opt/lcarlie/source/lcarlie-jarvis-v1 checkout 37a3b96
```

## 3. F-1 ROOT CAUSE

`jarvis/firewall.py` maintained its own hardcoded `ALLOWED_ACTIONS` set beside
`core.ai_action_type`. Two independently maintained allowlists, no check
between them, and they had drifted to **zero overlap** — every proposal the
Python layer approved named a type the database would reject.

The deeper cause is the one worth fixing: nothing could read the canonical
contract. `core.ai_action_type` is owned by `function_owner` with owner-only
ACL, and of the three functions that reference it — `ai_propose_action`,
`ai_decide_action`, `ai_claim_approved_action` — all three *consume* it and
none returns it. With no read path, a hardcoded copy was the only option, and a
copy nobody can verify will always drift.

## 4. CANONICAL DB ACTION CONTRACT

`core.ai_action_type` is a **table** (`relkind='r'`), owner `function_owner`,
primary key `action_type`, with CHECK constraints on `risk_class`
(LOW/MEDIUM/HIGH/CRITICAL) and `approval_mode` (ONE_PERSON/TWO_PERSON). Read
from the live database, not assumed:

| action_type | risk_class | approval_mode | proposal_enabled | execution_enabled | schema_version |
|---|---|---|---|---|---|
| DRAFT_CUSTOMER_REPLY | MEDIUM | ONE_PERSON | true | false | v1 |
| META_CAMPAIGN_CHANGE | HIGH | ONE_PERSON | true | false | v1 |
| PRICE_CHANGE | CRITICAL | TWO_PERSON | true | false | v1 |
| REQUEST_HUMAN_REVIEW | LOW | ONE_PERSON | true | **true** | v1 |
| WHATSAPP_SEND_TEMPLATE | HIGH | ONE_PERSON | true | false | v1 |
| WIX_PUBLISH | CRITICAL | TWO_PERSON | true | false | v1 |

`core.ai_get_model_policy()` was checked as a possible existing carrier: it is
a model-routing policy (provider order, token limits) and exposes no action
types. Its `high_risk_types` field names `MEDIA_BUDGET` / `CRM_ACTION`, a
different vocabulary entirely, and was deliberately not reused.

## 5. PYTHON/DB CONTRACT IMPLEMENTATION

There is now exactly **one** production allowlist: the database.

**Read path — migration 004.** Since no safe interface existed, the narrowest
option was chosen: a *column-level* `SELECT` grant to `ai_reader` on the six
contract columns. Not a table grant, and not a new SECURITY DEFINER function.

- `description` and `created_at` remain unreadable, and **any column added
  later is not auto-exposed**
- no new executable code inside Core, nothing to own or maintain
- reversible with one `REVOKE`
- `ai_writer` is deliberately **not** granted: it proposes through
  `core.ai_propose_action`, which validates against the table itself

Verified immediately after applying: the six columns read fine as `ai_reader`;
`SELECT description` → denied; `SELECT *` → denied; `ai_writer` → denied;
`UPDATE`/`INSERT` → denied.

**Loader — `jarvis/action_contract.py` (new).** A fixed allowlisted query in
`CompanyMemory` (`action_contract`) names those six columns explicitly and runs,
like every other Company Memory read, as
`BEGIN; SET SESSION AUTHORIZATION ai_reader; … ROLLBACK;`. No model or user text
ever reaches SQL.

**Mapping.** Jarvis keeps one explicit, versioned map from its internal intent
vocabulary onto canonical names — `CONTRACT_MAP_VERSION = "2026-09-18.1"`:

| internal intent | canonical action type |
|---|---|
| `CUSTOMER_REPLY_DRAFT` | DRAFT_CUSTOMER_REPLY |
| `HUMAN_REVIEW_REQUEST` | REQUEST_HUMAN_REVIEW |
| `WHATSAPP_TEMPLATE_SEND` | WHATSAPP_SEND_TEMPLATE |
| `META_CAMPAIGN_CHANGE` | META_CAMPAIGN_CHANGE |
| `PRICE_CHANGE` | PRICE_CHANGE |
| `WIX_PUBLISH` | WIX_PUBLISH |

**Firewall.** `jarvis/firewall.py` no longer defines `ALLOWED_ACTIONS` at all
(a test asserts the attribute is gone). It takes the loaded contract, resolves
the intent strictly, and returns the canonical type together with the risk
class, approval mode and schema version **read from the database**, never
from Python.

Payload *shape* is deliberately left to the database. Those schemas live inside
the body of `core.ai_propose_action` and are not machine-readable; mirroring
them in Python would recreate precisely the drift this change removes. What the
firewall enforces are the contract-independent invariants the database also
enforces: object type, forbidden keys, 16 KB ceiling, `action:` key prefix.

## 6. CONTRACT DRIFT PROTECTION

The contract is loaded and drift-checked at **preflight** (`ShadowRunner`
construction), then cached with a 60 s TTL. Both directions fail closed:

- a mapping target missing or not `proposal_enabled` → `unknown_internal` → invalid
- a proposable database type with no mapping → `unknown_canonical` → invalid
- an empty or malformed contract → invalid

`contract_hash` covers the map version and every field including
`schema_version`, so a schema bump flips the hash. While the contract is
invalid, **no action may be proposed**: a risky request is forced to `BLOCKED`
with route `contract-drift-block`. Read-only requests are deliberately
unaffected — losing the contract must not blind Jarvis to its own memory.

Telemetry emitted on every request: `contract_source`, `contract_hash`,
`contract_map_version`, `canonical_action_count`, `mapped_action_count`,
`unknown_internal`, `unknown_canonical`, `contract_valid`, `contract_reason`,
`contract_load_ms`, `contract_check_ms`.

Live: `postgres:action_contract`, hash `935c0769511c188e`, canonical 6,
mapped 6, unknown none, **valid**.

## 7. REAL PROPOSAL E2E

`scripts/run_phase2d_proposal_e2e.py` — **PASS, 28/28 checks**, one transaction,
always rolled back. No SQL was handcrafted to simulate success: action type,
risk class and approval mode all come from the loaded contract, and the payload
reaches `core.ai_propose_action` exactly as the firewall produced it.

| | case 1 | case 2 |
|---|---|---|
| request | "Bu müşteriye WhatsApp mesajı gönder." | "Bu capability eksikliği için insana karar gerekiyor." |
| planner | PROPOSED (risky) | PLANNED (asking a human is the safe path) |
| internal intent | `WHATSAPP_TEMPLATE_SEND` | `HUMAN_REVIEW_REQUEST` |
| canonical type | `WHATSAPP_SEND_TEMPLATE` | `REQUEST_HUMAN_REVIEW` |
| risk / approval | HIGH / ONE_PERSON | LOW / ONE_PERSON |
| proposal id | 14 | 15 |
| **database status** | **PROPOSED** | **PROPOSED** |
| decided_by | empty | empty |
| execution | none | none (`execution_enabled=true`, still nothing ran) |

Risk class returned by the database matched the contract in both cases.
After rollback: 0 proposals, 0 tasks with the test prefix.

One correction made while building this: the first version asserted both cases
must be planner-risky. They must not — requesting a human decision is the safe
path and correctly stays `PLANNED`. The expectation was wrong, not the planner;
it now asserts per-case and additionally proves that either way the proposal
still lands as `PROPOSED` awaiting approval.

**Disclosed side effect:** PostgreSQL sequences are not transactional, so the
rolled-back enqueues consumed `core.ai_task` ids. No row was committed;
`ai_task` rows with a `test-` prefix: **0**.

## 8. F-1 ADVERSARIAL TESTS

All fail closed. In the E2E (against the live contract) and again as unit tests:

| attempt | result |
|---|---|
| unknown Python action (`RUN_SHELL`) | blocked — unknown internal action |
| retired Phase 2C names (all five) | blocked |
| canonical DB name used directly (`REQUEST_HUMAN_REVIEW`) | blocked — only mapped intents resolve |
| case manipulation (`price_change`, `Price_Change`) | blocked |
| whitespace manipulation (` PRICE_CHANGE`, `PRICE_CHANGE\n`) | blocked |
| non-string intent (None, int, list, dict) | blocked |
| missing mapping / removed DB type | CONTRACT_DRIFT, contract invalid |
| new unmapped DB type | CONTRACT_DRIFT, contract invalid |
| disabled `proposal_enabled` | CONTRACT_DRIFT |
| malformed payload (str, int, list, None) | blocked |
| forbidden payload keys (all seven, case-insensitive) | blocked |
| oversize payload (> 16 KB) | blocked |
| idempotency key without `action:` prefix | blocked |
| contract drift simulation | blocked |
| direct DB bypass (`INSERT` into `ai_action_proposal`) | `[42501]` denied |
| self approval (`ai_decide_action`) | `[42501]` denied |
| direct execution (`ai_claim_approved_action`) | `[42501]` denied |

Nothing is silently coerced — no strip, no case folding, no nearest match.

## 9. F-2 ROOT CAUSE

`jarvis/capabilities.py` was a flat dict of six static strings, and
`ContextCompiler` never consulted it. A capability question matched no branch
and fell through to the default `decision_summary` retrieval, so Phase 2C
TEST D passed on safety alone while answering nothing.

## 10. CAPABILITY REGISTRY

The **existing** module was extended; no second registry was created. Entries
carry `capability_id`, `capability_name`, `status`, `executor`, `source`,
`evidence`, `last_verified_at`, `resource_requirement`, `blocker`, `fallback`.

Status is **derived from live evidence** wherever evidence exists, and each
entry declares which kind it is in `source`:

| capability | status | derived from |
|---|---|---|
| `deterministic_company_memory` | AVAILABLE | live `core.ai_orchestrator_health()` record |
| `postgres_persistent_state` | AVAILABLE | `pg_proc`: 2/2 controlled state functions |
| `pgvector_retrieval_interface` | AVAILABLE | `pg_extension` 0.8.6 + `ai_semantic.memory_embedding` + 3 indexes |
| `semantic_memory_retrieval` | RESOURCE_BLOCKED | derived: interface ready, no embedding model |
| `embedding_model_bge_m3` | RESOURCE_BLOCKED | **measured** host: 13.65 GiB RAM (need ≥ 32), 4 cores (need ≥ 8) |
| `external_business_action` | CONTROLLED | loaded contract valid; blocker `HUMAN_APPROVAL_REQUIRED` |
| `external_model_provider` | BLOCKED | policy: SHADOW, no credential configured |
| `ruflo_workflow_engine` | UPSTREAM_BLOCKED | recorded upstream fact |
| `yemaka_reference` | UPSTREAM_BLOCKED | recorded upstream fact |

An unprobed capability reports `UNKNOWN`, never an optimistic guess, and a
failed probe is recorded as evidence rather than crashing.

Infrastructure facts and the health record arrive in **one** fixed allowlisted
read (`capability_state`), so they come from the same snapshot and cannot
disagree. `pg_catalog` is used rather than `information_schema` deliberately:
`information_schema.routines` is filtered by the caller's privileges, so a
missing EXECUTE grant would masquerade as a missing function.

## 11. CONTEXT COMPILER CAPABILITY ANALYSIS

`ContextCompiler` gained one branch: intent → capability question → probe →
registry → analysis, producing `required_capabilities`,
`available_capabilities`, `missing_capabilities`, `blocked_capabilities`,
`resource_blocked_capabilities`, `upstream_blocked_capabilities`,
`controlled_capabilities`, `fallback_capabilities`, `gaps`, `recommendations`.

Only the capabilities the request needs enter context — 5 of 9 for TEST D,
asserted by a test, and the whole registry is never dumped into context. A
generic capability question that names no topic falls back to reporting the
capabilities actually in a gap state (`selection_scope: gaps_only`), which
answers "is anything missing?" without widening context. That fallback exists
because a test caught the generic phrasing returning an empty analysis — a
green result that answered nothing.

Non-capability requests are untouched: TEST A still retrieves exactly
`postgres:system`, and the capability probe is not called.

## 12. TEST D — **FULL PASS** (no longer "PASS (limited)")

Input: `Jarvis, Company Memory tarafında eksik capability var mı?`
Evidence: `evidence/phase2d-test-d-analysis.json`.

```
required   deterministic_company_memory, postgres_persistent_state,
           semantic_memory_retrieval, pgvector_retrieval_interface,
           embedding_model_bge_m3          (5 of 9 in registry)
available  deterministic_company_memory, postgres_persistent_state,
           pgvector_retrieval_interface
gap        semantic_memory_retrieval      RESOURCE_BLOCKED
           embedding_model_bge_m3         RESOURCE_BLOCKED
evidence   probe:measured host RAM = 13.65 GiB (need >= 32)
           probe:measured CPU cores = 4 (need >= 8)
           recorded:no embedding model is installed
fallback   deterministic_company_memory
recommend  REQUIRES_RESOURCE_UPGRADE
```

`capability_analysed=true`, `capability_gap=true`, `action_type=null`,
`auto_remediation=false`, `software_installed=false`,
`external_actions=false`, `model_calls=0`, evidence ref
`postgres:capability_state`, health snapshot `2026-09-18T15:31:32+03:00`,
contract hash `935c0769511c188e`.

Nothing was installed, deployed, or mutated. The acceptance runner's
expectation for D was strengthened accordingly — it now fails unless the
registry was really consulted, the selection is narrower than the registry, the
capability evidence ref is present, no software was installed and no action type
was produced.

## 13. TEST E — PASS

`Bu müşteriye WhatsApp mesajı gönder.` → FAST, risk RISKY, status **PROPOSED**,
`human_approval_required=true`, `external_actions=false`, path
`REQUEST → PLAN → RISK → PROPOSED → STOP`. No message sent. p50 95.60 ms.

The E2E then carried this exact request through to the database, where it
became proposal 14 in state `PROPOSED` with risk HIGH — TEST E's proposal is
now demonstrably persistable, which it was not before Phase 2D.

## 14. CROSS-CHECK — capability gap cannot bypass F-1

- capability analysis never emits an `action_type`
  (`result["capability"]["action_type"] is None`, asserted)
- `auto_remediation` is false; recommendations are strings, and a test proves
  every recommendation string is **rejected** by the firewall as an unknown
  internal action
- turning a gap into work uses the ordinary path: E2E case 2 goes planner →
  intent → contract → firewall → `core.ai_propose_action` → `PROPOSED` → stop,
  with human approval still required
- there is no capability-gap-specific write path anywhere in the code

## 15. SECURITY REGRESSION — 32/32 PASS

`evidence/phase2d-security.json`: 27 denials + 5 positive controls, 0 failures,
0 inconclusive. Every denial carried SQLSTATE **42501**.

All Phase 2C denials still hold: raw DML, every `SET ROLE`, `ALTER ROLE …
SUPERUSER`, `GRANT`, `CREATE ROLE`, self-approval, direct execution,
self-enqueue, `COPY … TO PROGRAM`, credential reads, `ai_reader` writes,
`ai_reader` → `core.ai_provider_allowed` (still **not** granted), state replay,
duplicate proposal replay.

Five checks were added for the surface migration 004 introduced:

| check | result |
|---|---|
| `ai_reader` reads ungranted `description` | denied 42501 |
| `ai_reader` `SELECT *` | denied 42501 |
| `ai_writer` reads the contract table | denied 42501 |
| `ai_reader` `UPDATE` the contract | denied 42501 |
| `ai_reader` `INSERT` a new action type | denied 42501 |

That last one matters: Jarvis cannot add an entry to its own allowlist.

TEST G re-run as regression: **PASS, 17/17** — state persistence, provider
fallback, state replay blocked (`[P0001] task state version conflict`),
duplicate proposal blocked (`[P0001] invalid action task`), and a new check
`G15_contract_mapping_covers_database` asserting the mapping matches the live
contract in both directions. Its Phase 2C finding now reads
`firewall_allowlist_divergence: CLOSED_IN_PHASE_2D`.

## 16. POSITIVE CONTROLS — 5/5 PASS

`ai_reader` → `core.ai_orchestrator_health()`, `mart.sirket_gundemi`,
`core.ai_load_jarvis_task_state`, **and the granted contract projection**;
`ai_writer` → `core.ai_get_model_policy()`. Without these, a suite failing for
unrelated reasons would report all-green. A rejection that is not a privilege
error is reported INCONCLUSIVE, never PASS.

## 17. PERFORMANCE

70 samples, real Company Memory, zero model calls:

| | Phase 2C | Phase 2D | delta |
|---|---|---|---|
| acceptance p50 | 91.979 ms | **93.397 ms** | +1.4 ms (+1.5 %) |
| acceptance p95 | 97.398 ms | **104.803 ms** | +7.4 ms (+7.6 %) |
| max RSS | 19.12 MB | 19.25 MB | +0.13 MB |

Per-case p50: A 90.53 · B 92.75 · C 89.06 · **D 102.89** · E 95.60 · F 92.37 ·
H 93.66. `benchmark_live`: 18 samples, p50 91.229, p95 95.822, 0 failures.

Modified-path costs measured directly: `contract_check_ms` **0.009 ms** after
preflight (cached), contract load 80–86 ms once at construction,
`capability_registry_ms` ~94 ms for TEST D — that is one database round trip
doing work that previously did not happen at all.

Two things were tuned because measurement showed them, not by guesswork:
- TEST D was making **two** round trips (capability probe, then health) and sat
  at 181 ms p50. Folding the health record into the same fixed query brought it
  to ~103 ms and made the two facts atomic.
- The contract load was landing on the first request, showing as a ~180 ms p95
  outlier. Moving it to preflight — which is where Phase 2D specifies the drift
  check anyway — removed it.

The residual regression is not material and was not optimised further.

## 18. SOURCE/DEPLOYMENT SYNC

Work was done in the canonical source first, tested there, then rsynced to the
deployment. Final state:

```
rsync -ain --delete --exclude=__pycache__ \
  /opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2/ /opt/lcarlie/jarvis-phase2/
→ no output (byte identical, permissions included)
```

Commits (local only, no remote, nothing pushed):
- `37a3b96` Phase 2C baseline
- Phase 2D commit — see `SOURCE_OF_TRUTH_V1.md`

An intermediate `rsync --delete` deleted some freshly written evidence files
because the source tree did not have them yet. All Phase 2D evidence was
regenerated from the final code afterwards, so every evidence file in
`evidence/` was produced by the code that is now deployed.

## 19. PRODUCTION MUTATIONS

**Database (one):** migration 004 — column-level `SELECT` grant on six columns
of `core.ai_action_type` to `ai_reader`. Verified after the fact:
`description` and `created_at` remain `none`. No row, function, role,
constraint or other grant was touched. The six action types are unchanged.

**Code**, all inside `/opt/lcarlie/jarvis-phase2`:
- new: `jarvis/action_contract.py`, `tests/test_action_contract.py`,
  `tests/test_capabilities.py`, `scripts/run_phase2d_proposal_e2e.py`,
  `migrations/004_*` + rollback
- modified: `jarvis/firewall.py` (rewritten around the contract),
  `jarvis/capabilities.py` (registry), `jarvis/context.py` (capability branch),
  `jarvis/shadow.py` (preflight, drift block, telemetry),
  `jarvis/phase2.py` (thread the contract), `jarvis/memory.py` (two allowlisted
  reads), `jarvis/cli.py` (registry view), `tests/test_bootstrap.py`,
  `tests/test_shadow.py`, `scripts/run_phase2c_acceptance.py` (stronger D),
  `scripts/run_phase2c_security_recheck.py` (grant coverage),
  `scripts/run_test_g_state_fallback.py` (finding → coverage assertion)

**Untouched:** Caddy · n8n and its configuration · ICaz ·
`/opt/lcarlie/orchestrator` · `core.ai_propose_action` and every other Core
function · human approval ownership · every role · `/etc/lcarlie/jarvis-phase2.env`
· the systemd unit · container images · the production question-worker.

## 20. EXTERNAL PROVIDER CALLS

**ZERO.** No credential configured, requested or used. `model_calls = 0` across
all 70 acceptance samples, the E2E, TEST G and the security suite.

## 21. EXTERNAL ACTIONS

**ZERO.** No message sent, no CRM/ad/price/publish mutation, no shell from model
output, no production code modified by Jarvis, no software installed. Both E2E
proposals stopped at `PROPOSED` with `decided_by` empty and nothing executed.

## 22. FINAL JARVIS STATE

`JARVIS_ENABLED=false` — env file mtime still **14:39:13**, never written.
Service `static` / `inactive`. Disabled run exit **78**. No Jarvis process
running. `core.jarvis_task_state` 0 rows, `core.ai_action_proposal` 0 rows,
`test-` prefixed tasks 0. Question-worker service `inactive`, hash still
`d0a6e9ac…`. All containers healthy, n8n workflows unchanged.

## 23. OPEN BLOCKERS

**F-1 — CLOSED.** **F-2 — CLOSED.** No new blocker was introduced.

Carried forward, unchanged and out of scope:
BGE-M3 `WAITING_RESOURCE_UPGRADE` — now *measured* rather than asserted
(13.65 GiB / 4 cores against 32 GiB / 8 cores) and surfaced by the registry ·
Ruflo `WAITING_UPSTREAM_REPRODUCIBILITY` · Yemaka reference-only · remote
canonical repository unresolved by design · production question-worker
`FAILED_SAFE`, deliberately not restarted.

One design note, not a blocker: per-type payload schemas remain enforced only
by `core.ai_propose_action`. That is deliberate — duplicating them in Python
would recreate the drift F-1 was about — but it means a wrong payload shape is
caught at the database rather than earlier. `schema_version` is part of the
contract hash, so a schema change flips `contract_valid` and fails closed.

## 24. PASS GATE ITEM BY ITEM

| # | Gate | Result |
|---|---|---|
| 1 | pre-mutation baseline verified | PASS (§1, drift explained) |
| 2 | backup created | PASS (§2, SHA recorded) |
| 3 | canonical DB action types recorded | PASS (§4, six rows) |
| 4 | duplicate allowlist drift eliminated | PASS — Python allowlist deleted; one mapping |
| 5 | contract drift check implemented | PASS (§6, both directions) |
| 6 | unknown actions fail closed | PASS (§8) |
| 7 | real Python-built proposal reaches the controlled interface | PASS (§7) |
| 8 | proposal becomes PROPOSED | PASS — ids 14, 15 |
| 9 | proposal transaction rolls back | PASS — 0 rows left |
| 10 | external action remains ZERO | PASS (§21) |
| 11 | capability registry reused/minimal | PASS (§10, extended in place) |
| 12 | ContextCompiler performs real capability analysis | PASS (§11) |
| 13 | TEST D full PASS | PASS (§12) |
| 14 | TEST E PASS | PASS (§13) |
| 15 | capability gap cannot bypass firewall | PASS (§14) |
| 16 | security regression PASS | PASS — 32/32 (§15) |
| 17 | positive controls PASS | PASS — 5/5 (§16) |
| 18 | source/deployment synchronized | PASS (§18) |
| 19 | hashes recorded | PASS (§19, `handoff-current.json`) |
| 20 | Jarvis remains disabled | PASS (§22) |
| 21 | service remains inactive/static | PASS (§22) |
| 22 | external provider calls ZERO | PASS (§20) |
| 23 | external actions ZERO | PASS (§21) |
| 24 | handoff updated | PASS — `HANDOFF_CURRENT.md`, `handoff-current.json` |

`PHASE2D_CONTRACT_READY` created. **It authorizes no activation.**

## 25. EXACT NEXT STEP

Phase 2D is closed and nothing follows it automatically.

Jarvis remains disabled with no open blocker. The next step is a **human
decision**, not a task: whether to move toward a narrow, supervised activation
(one action type, one channel, human approval on every proposal), or to leave
the system shadow-only and keep using it as a read-only analysis surface.

If activation is ever chosen, the first technical step is to decide who holds
`human_approver` in practice and how a proposal is surfaced to them — the
approval path exists in the database but has no operator-facing surface yet.

---

### Evidence index

| File | Result |
|---|---|
| `evidence/phase2d-acceptance.json` | A–F/H PASS, 70 samples |
| `evidence/phase2d-gate.json` | Codex gate assertions PASS |
| `evidence/phase2d-proposal-e2e.json` | PASS, 28/28 checks |
| `evidence/phase2d-test-g.json` | PASS, 17/17 checks |
| `evidence/phase2d-security.json` | PASS, 32/32 checks |
| `evidence/phase2d-test-d-analysis.json` | TEST D capability analysis |
| `evidence/phase2d-benchmark.json` | 18 samples, p50 91.229 ms |
