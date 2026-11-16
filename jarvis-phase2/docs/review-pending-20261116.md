# Preserve deliveries until manager review succeeds

Prepared against PR #1 head `f30bb2b5fd99cb1c78ddb146394b240b991438f1`.
This resolves the first design gap in `team-professionalization-20261113.md`.

## Problem and decision contract

Previously, an absent or invalid model decision became `ONAY` when deterministic
checks found nothing. With findings it became `DUZELT`, spending content-correction
attempts even though no reviewer had judged the delivery. Neither fallback is a
completed model review.

`karar_ayikla` now returns `INCELEME_BEKLIYOR` for missing/invalid decisions and
truncated JSON recovered by the shared parser, regardless of deterministic
findings. Findings remain in review history for the next review. Explicit `ONAY`,
`DUZELT` and `RED` retain their existing behavior.

## Durable review flow

- Write the delivery file and atomically checkpoint its pending state, sanitized
  content and evidence snapshot before invoking the reviewer. An interrupted
  review therefore does not trigger content regeneration on restart.
- A later `yurut` run reviews that snapshot, keeping the task ID, work ID, delivery
  path, original delivery timestamp and owner-proposal key (`teslim.<task-id>`).
  Review retries do not increment `deneme` or `duzeltme.tur`.
- Pending deliveries are not expired/replanned as unstarted work, do not satisfy
  dependencies, and cannot reach the owner queue or the application ledger.
  Only explicit `ONAY` enters the existing completion/handoff path. Explicit
  `DUZELT` or `RED` resumes the existing correction/rejection path.
- Pending routines block duplicate routines; pending non-routine work counts
  toward the open-work ceiling. Daily and dashboard completion counts exclude
  pending deliveries. The Markdown artifact remains unchanged during re-review;
  current review status and reasons live in the task record and review history.
- `IS_URETICI_YONETICI=false` now pauses review calls while keeping deliveries
  pending. It no longer bypasses approval. Dry runs do not re-review saved work.

## Verification

New regression cases reproduced failures on the original PR head before the fix.
They cover missing/unknown decisions, provider failure, malformed and truncated
JSON, exhausted review budget, disabled review, deterministic findings, repeated
pending reviews, interruption/restart, stable content/evidence/identity, dependent
work, owner handoff, correction/rejection, queue ceilings and completion counts.

Local Python 3.12 verification with `requirements-test.txt` dependencies:
1,635 core tests (1,583 passed, 52 skipped), 576 web tests (551 passed, 25 skipped),
and 15 Node tests passed. `git diff --check` passed. External services and the
production database were not used.

## Scope and remaining limits

No database migration, service/timer change, deployment or merge is included.
Historical deliveries already marked approved are not reclassified. This patch
requires a valid manager decision; it does not establish distinct reviewer model
identity or resolve reviewer-routing independence. Pending retries remain bounded
by the existing batch/time/model budgets; dedicated review backoff, escalation and
operator resolution remain separate work.
