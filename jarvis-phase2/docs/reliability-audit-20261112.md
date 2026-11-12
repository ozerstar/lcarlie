# Jarvis reliability audit — 2026-11-12

## Source and scope

Reviewed and repaired `codex/jarvis-quality-20261105` at
`e47e1d94593240b9d0e027055a4fcfc3db3ddeec` in an isolated checkout.
No production deployment, migrations, live model calls, outbound messages or
business mutations were performed.

Do not equate `main` with production: `main` and the quality branch diverge
(9 main-only commits, 100 quality-only commits). The quality branch contains
image/cari modules absent from main. `claude/bold-wozniak-p5imms` also has one
separate cari UI change while lacking ten quality-branch commits. This patch
targets the quality branch, not a blind merge of all branches.

## Fixed behavior

- A dependent task no longer runs when its prerequisite is missing, rejected,
  expired, tool-blocked, or lacks an accepted delivery.
- Task attempts and results checkpoint individually. Interrupting a later task
  no longer loses a preceding completed delivery.
- Owner-review handoff is stored before submission and retried with a stable
  key without regenerating the delivery. A missing ID is not success; duplicate
  proposals are read back with matching content and acceptable state.
- Recovery does not reopen applied/measured or rejected/expired ledger work.
- WhatsApp text and template paths respect both the global and channel switch.
  A durable pre-send audit record is required. Post-send audit failure is
  reported separately instead of falsely claiming that delivery did not occur.
- The creative cliché gate handles a narrow set of Turkish inflections without
  the optional morphology package. Reputation scanning resolves its helper
  relative to the checkout rather than assuming a production directory.
- Pure GEO helpers no longer import the optional PostgreSQL driver. Actual DB
  operations still require it; DB integration is not claimed as tested.
- Tests use disposable auth/image/push state and label production-only checks
  as skipped rather than touching production paths.

## Verification

- Before: core discovery 1,571 tests, 3 failures, 4 errors, 50 skipped.
- After: core discovery 1,606 tests, 1,554 passed, 52 skipped.
- Web console: 575 tests, 550 passed, 25 skipped.
- JavaScript logic: 8 passed.
- `git diff --check`: passed.

Python 3.12; existing pywebpush 2.5.0 and pillow-heif 1.8.1 were installed in an
isolated test environment. Node tests used the existing locked Three.js runtime.
Skipped checks include unavailable production integrations, real DB/model
services and Hunspell. Local results are not production or remote CI evidence.
A GitHub Actions workflow now covers core, web console and JavaScript checks
without production credentials or deployment steps.

## Architecture / repository decision

Keep the existing scheduler, task tree, improvement ledger, Research Controller
and adapter boundaries for this repair. Adding another orchestration framework
would not fix the observed dependency, persistence or handoff defects. Existing
repository research already distinguishes evaluated components from installed
ones; do not mass-install that candidate inventory. Further upstream selection
requires a measured capability gap and isolated license/dependency review.

## Remaining production acceptance

1. Obtain authorized server access; compare deployed hashes and active source
   branch, including uncommitted work, before merging/deploying.
2. Confirm backups and isolated restore, active timer/service units, current
   task queue, disk headroom, database/data freshness and catalog sync behavior.
3. Validate owner-proposal readback against the real schema, interrupted-worker
   replay, and pending/rejected/expired proposal behavior in staging.
4. Review intended WhatsApp switch values before deployment. This change does
   not enable either switch or authorize any automatic communication.
5. Run the final production smoke with real business evidence and explicit
   action boundaries. Deployment, real external actions and autonomous live
   operation are not claimed complete by this report.
