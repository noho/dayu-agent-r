# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 re-review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S1 - Lifecycle/status owner helpers
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`
- Fix validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-rereview-ds.md`

## Verdict

Accepted. P3-A S1 is ready for accepted slice commit.

Both re-reviewers reported:

- verdict: pass
- blocking findings count: 0
- nonblocking findings count: 0
- blockers: none

## Controller Findings

- S1-F01 through S1-F04 are closed.
- `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` and `closeout_attempt_terminal_event_type_for_status` distinguish durable Attempt terminal status from Run / Attempt joint closeout support.
- `SUSPENDED` and `STEERED` remain durable Attempt terminal statuses but fail fast through the closeout helper.
- Predicate tests and frozenset serialization tests now explicitly protect the intended owner helper behavior.
- Lifecycle docstrings now describe Attempt terminal ownership and closeout-supported subset ownership.

## Validation

Controller validation after fix passed:

- Focused tests: `59 passed`
- Import-cycle validation: `import-ok`
- Pyright: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

## Residual Risk / Next Slice Handoff

- S2 must migrate terminal event consumers in `run_transition.py` and `engine_ingest.py`.
- S2 must use `closeout_attempt_terminal_event_type_for_status` for Run / Attempt joint terminal closeout paths and keep `SUSPENDED` / `STEERED` on waiting / steer-specific routes.
- S2 must migrate SQL/status consumers to the durable state helpers and run the mandatory terminal event source scan.

## Next Gate

Proceed to accepted S1 commit, then P3-A S2 implementation.
