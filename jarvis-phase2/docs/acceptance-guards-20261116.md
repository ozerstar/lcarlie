# Acceptance guards after PR #1

Prepared from `f8afe6c059d542f94b3f0d50455349e92afba709` on an isolated branch.
No merge, deployment, live message, production database access or service change
is included. Existing external-action switches remain unchanged.

## Result

- A missing/malformed WhatsApp message ID is not provider acceptance. Timeouts,
  decoding failures, HTTP 408/5xx and unrecognised failures raise
  `GonderimBelirsiz`, separately from a confirmed refusal. An accepted message
  is still not proof of delivery; the result explicitly leaves delivery unknown.
- Automatic replies, order confirmation (including the manual confirmation CLI),
  shipping-confirmation closing messages and owner order notifications pass a
  stable business key. Under a cross-process file lock, the sender checks the
  durable JSONL history and writes/fsyncs intent before the network request.
  A previously accepted matching request returns its existing ID. A pending,
  uncertain, unreadable or conflicting record prevents another network call.
  Confirmed request refusals can be retried with unchanged content.
- Order confirmation and owner notifications retain `GONDERILIYOR` on ambiguous
  delivery, with an explicit BELIRSIZ/operator-resolution reason; this existing
  schema state is not eligible for automatic retry. It is a held lock, not a
  delivery confirmation. No new SQL state/migration is required. Post-acceptance
  audit failure emits a visible warning and an explicit reconciliation flag;
  order confirmation alarms, and automatic replies hand off to a human.
- The core task runner now invokes the existing delivery reconciler, including
  when no new task is executed. It can repair missing application evidence
  without re-generating a completed delivery. Explicit pending/correction/reject
  manager decisions cannot be credited by the reconciler. Repeating an identical
  ledger application no longer creates duplicate application audit events.
- Kurul cannot route review to the producing department or its member under
  another department. It records the actual reviewer member, rechecks queued
  review provenance before dispatch, and blocks legacy queued reviews without
  that member evidence. Frozen owner payloads cannot bypass this gate.
  Sources waiting for an independent reviewer remain checkpointed past the
  initial 36-hour source window; blocking reasons name the owner and are counted.
- Explicit chat error frames and error/capability terminal results preserve
  streamed text and report an error rather than a successful completed answer.

## Correction to the preceding audit

The earlier isolated `yurut()` reproduction showed missing evidence was not
repaired by a second direct runner call. The production entry script already
called `Store.reconcile_team_deliveries()` after execution. Therefore a blanket
claim that the whole system had no repair path was too broad. This change shares
that existing repair path with direct runner callers and strengthens its approval
gate; it does not introduce an unrelated replacement ledger.

## Verification

Local Python 3.12 with `requirements-test.txt` dependencies:

| Suite | Total | Passed | Skipped |
|---|---:|---:|---:|
| Core | 1,650 | 1,598 | 52 |
| Web console | 576 | 551 | 25 |
| Node logic | 16 | 16 | 0 |

The new cases cover empty/malformed provider responses; timeout/server failure
replay; JSON failure privacy; confirmed refusal retry; concurrent identical
requests; changed-content conflicts; crash after intent; failed acceptance-audit
write; corrupt history; caller retry locks; direct-runner evidence recovery;
unapproved-delivery rejection; shared/missing reviewer identities; delayed source
recovery; frozen self-review dispatch; and preservation of partial chat answers.
The 135-test focused Python group and eight chat-stream Node cases passed before
broader verification. Node tests initially lacked the locked `three` dependency;
after `npm ci --ignore-scripts --omit=dev`, all 16 passed. Local Node is 24; remote
CI uses Node 22. CI must be checked on the published commit.

## Remaining production acceptance

This completes the approved isolated correction package, not production rollout.
Real schema/proposal readback, backup restore, deployed revision reconciliation,
browser visual acceptance and real provider/webhook checks remain separate gates.
No customer message should be enabled based only on these offline tests.

The key-history guard is local to the shared state filesystem and Linux flock.
All senders must use the same durable history and lock. Do not truncate, rotate
away or restore an older send history while channels are active; reconcile it
with business locks/provider outcomes first. Hosts with independent copies of
state do not share this guard. A repeated manual inbox action without a supplied
business key is a separate request; the sender does not invent a permanent key
from message text. Ambiguous sends require operator reconciliation, not an
automatic resend or deletion of the held row.

Reviewer separation here is by recorded department/member identity; it does not
establish different underlying model-provider identities. Capability-based task
assignment, review backoff/escalation, older completed approvals, and chat resume
after page/browser closure remain documented follow-up work. Legacy queued
reviews without member provenance are intentionally held for operator resolution.

Rollback, if deployment is later authorised, must first stop relevant workers
and external channels. Retain send history and held business locks, select the
previous verified deployed code/config, and reconcile external effects before
re-enabling anything. Code rollback does not undo accepted messages. No database
restore is part of this change.
