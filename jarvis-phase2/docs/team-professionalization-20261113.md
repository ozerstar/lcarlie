# Professional team contracts: scope and acceptance

This review concerns software roles, not employee appraisal. A role title or an
animated office avatar is not evidence of autonomous work.

## Existing foundations

- `roster.Member` defines role, responsibility and named Company Memory inputs;
  missing data, missing implementation and execution errors are distinct states.
- `hr_team.review` reports unstaffed departments, missing responsible members and
  incomplete sources without changing authority or pretending to test live APIs.
- `team_lead.build_brief` rejects stale activity snapshots and does not label a
  role worked when its evidence references are absent.
- `agency` restricts role selection by task and reports concrete contribution
  fields. This layer is deterministic and proposal-only, not eight independently
  executing agents.
- `is_uretici` validates delivery and manager acceptance before dependencies run.
- `kurul` supplies reviewer, challenge and decision stages followed by internal
  task assignment or owner-review proposal, not direct platform writes.

The current isolated role/brief/agency regression group passes 80 tests. This
checks code contracts; it does not verify production staffing, API health or
model judgement.

## Acceptance required before a role is called operational

For each role record: responsible department and member; allowed data/tools;
input freshness and provenance; expected artifact and acceptance criteria;
independent reviewer; stable delivery identity and acknowledgement; retry limit
and escalation owner; human approval boundaries for external effects. Source
read, draft generated, approval requested, action applied and outcome measured
must remain distinct.

Prioritize end-to-end cases before expanding headcount: unanswered-conversation
triage with a draft only, catalog completeness analysis, and evidence-based
content briefs. Real external communication requires a separately defined
recipient/data/action scope. A missing integration must report blocked, not be
substituted with invented output.

## Production acceptance remains outstanding

Authorized server access, deployed hash reconciliation, timer/service health,
backup restore, data freshness and live integration scopes must be established
before any always-on or all-systems-connected claim. No deployment or permission
expansion is included in these repository changes. Neither feedback retrieval
nor accumulated outcome records constitutes model-weight training.

## Concrete remaining design gaps

- `yonetici.karar_ayikla` currently falls back to deterministic checks when model
  review is missing. With no deterministic finding it returns ONAY. This is not
  evidence that an independent model reviewer accepted the delivery. A future
  review-pending state should retain the artifact and re-review it without
  regenerating it or consuming content-correction attempts.
- Kurul chooses the first listed department member for generated work. A tested
  role/capability matching policy and explicit rejection when no qualified member
  exists are preferable to cosmetic role expansion.
- Reviewer routing can fall back to the producing department when the designated
  reviewer and EXEC are absent. Independent-review availability must be checked
  explicitly before claiming separation of responsibilities.

These gaps are recorded, not claimed fixed by the current batch.

## Implemented role-accountability corrections

- Competitor research status labels no longer count as produced research. This
  deterministic agency path has no actual source-backed research deliverable;
  it now reports no output rather than inventing a contribution.
- Roster speakers and their shared row cache reject noncanonical/unattributed
  Company Memory results before calculation. Missing/untrusted inputs remain
  visible instead of producing unsupported numerical opinions.
- Instagram direction reports revision requests as requested and unverified,
  not completed corrections without revised-artifact evidence.

These safeguards do not grant new tools, promote a role to live operation or
resolve the remaining review-independence and assignment-policy gaps above.

## Implemented team handoff contract

Kurul now requires explicit KABUL for each proposal. Missing review, SORGULA
and RED cannot dispatch; SORGULA intentionally stays pending even for an owner
review recommendation. Audited sources/proposals are checkpointed before
handoff, with source-bound IDs and an exact owner-proposal payload reused after
interruption or a date change. Only positive integer proposal acknowledgements
or exact internal-task lineage count as successful handoff. Source consumption
waits for every proposal's acknowledged dispatch or explicit rejection/cancel.
The processing batch is bounded while retaining pending entries.

Fourteen isolated Kurul tests cover partial review, rejection, deferred/capped
work, source-window expiry after audit, interrupted callbacks, stable payloads,
legacy acknowledgement recovery and retained queue limits. Remaining limits:
first-stage unaudited sources still have the existing age window; indefinitely
disputed or duplicate-blocked entries need backoff/escalation and an operator
resolution interface. A blocked bounded backlog can delay fresh intake. No
unbounded self-healing or complete live autonomy is claimed.

Final local suite: 1,628 core tests (1,576 passed, 52 skipped), 575 web tests
(550 passed, 25 skipped), 15 Node tests passed. Python used a fresh isolated venv
with requirements-test.txt. Diff and JavaScript syntax checks passed. Browser
visual acceptance and real-model accuracy/latency were not tested.
