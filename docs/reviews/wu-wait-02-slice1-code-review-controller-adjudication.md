# WU-WAIT-02 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub Issue #90
- Gate: Slice 1 code review
- Slice: Durable poll claim and backoff primitive
- Reviewed implementation artifact: `docs/reviews/wu-wait-02-slice1-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260701-143921.md`
  - `docs/reviews/code-review-20260701-144036.md`
- Implementation baseline: current uncommitted workspace changes relative to accepted plan commit `8568467c`

## Controller Decision

Decision: pass.

Both reviewers found the Slice 1 implementation satisfies the accepted plan and preserves the Host design boundary: poller observation is fenced by durable wait-row claim fields, terminal progression remains owned by the shared `resolve_wait` pipeline, and adapter / abandon side effects happen outside Host durable transactions.

Controller accepts the gate as passed with no required fix before accepted Slice 1 commit.

## Finding Adjudication

### DS-CR-F01 claim candidate SELECT vs atomic UPDATE

- Source: `docs/reviews/code-review-20260701-143921.md`
- Severity: low
- Controller verdict: rejected-with-reason
- Reason: direct evidence shows the candidate `SELECT` and `UPDATE` run in one write transaction, and the `UPDATE ... WHERE` repeats the full eligibility predicate and rowcount is the authoritative claim decision. The implementation report and docstring already state that the candidate read is not an authorization source. This is a plan wording mismatch, not a correctness defect.
- Required action: none.

### DS-CR-F02 release CAS conflict integration test gap

- Source: `docs/reviews/code-review-20260701-143921.md`
- Severity: low
- Controller verdict: deferred-with-owner
- Owner / destination: WU-WAIT-02 Slice 2 integration tests if supervisor loop introduces a natural stale-release path.
- Reason: state-helper tests already cover stale release rejection by `poll_claim_id` CAS, and `WaitPoller._release_with_backoff` maps CAS_LOST to `claim_conflicts`. Slice 1 has no production loop or concurrent supervisor path that would naturally trigger a double-release integration scenario. Adding a synthetic adapter mutation test is optional and not required for Slice 1 correctness.
- Required action: none before accepted Slice 1 commit.

## Residual Risk

- `_backoff_delay_seconds` has no dedicated pure-unit test. Current integration tests cover persisted backoff scheduling for not-ready, missing adapter, adapter failure, resolve failure, and abandon failure paths. Risk is low and non-blocking.
- `shutdown_skipped` is intentionally not in `WaitPollLastOutcome` or schema CHECK in Slice 1. If Slice 2 needs shutdown-specific durable outcome metadata, it must extend enum and schema CHECK in that slice.
- `poll_backoff_attempt` uses singular naming while the plan text used plural in places. This is non-functional and should not be changed solely for naming churn.

## Validation Considered

- AgentCodex reported focused Host durable / wait adapter tests: 102 passed.
- AgentCodex reported pyright: 0 errors.
- AgentCodex reported `git diff --check`: passed.
- Controller reran focused Host durable / wait adapter tests: 102 passed.
- Controller reran pyright: 0 errors.
- Controller reran `git diff --check`: passed.
- AgentMiMo reran focused tests during review: 102 passed.
- AgentDS reported pyright remained clean.

## Next Gate

Update `docs/host/issues-implementation-control.md` to `accepted-slice`, rerun final lightweight validation, then create the accepted Slice 1 commit. Slice 2 may start from the accepted Slice 1 commit.
