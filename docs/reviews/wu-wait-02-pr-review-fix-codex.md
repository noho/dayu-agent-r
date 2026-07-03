# WU-WAIT-02 / PR 165 PR Review Fix — AgentCodex

## Scope

- Work unit: WU-WAIT-02 / GitHub issue #90
- PR: https://github.com/noho/dayu-agent-r/pull/165
- Gate: PR review fix
- Accepted finding fixed: DS Finding 01, `_abandon_cancelled_wait` could externally abandon a cancelled wait, then skip durable `poll_abandoned_at` marking if the lifecycle gate closed before the mark transaction.

## Root Cause

`WaitPoller._abandon_cancelled_wait(...)` treated the post-adapter shutdown gate the same way for ready/lost resolve and cancelled abandon.

That was correct for `poll_wait(...)` results because no Host durable terminal fact had been written yet and retrying later is safe. It was not correct after `adapter.abandon_wait(record)` returned successfully, because the external side effect had already happened. Releasing the claim as `SHUTDOWN_SKIPPED` left the cancelled wait retryable with `poll_abandoned_at IS NULL`, so a later poller could call `abandon_wait(...)` again.

## Fix

- Removed the lifecycle-gate skip after successful `adapter.abandon_wait(record)`.
- Kept the pre-adapter lifecycle-gate check, so shutdown before any external side effect still releases the claim as `SHUTDOWN_SKIPPED`.
- Kept adapter calls outside Host transactions.
- Kept durable abandoned marking as the existing claim-based CAS (`mark_wait_record_poll_abandoned`), preserving stale-claim conflict behavior.

## Tests Added

- `tests/host/test_wait_adapter_polling.py::test_cancelled_abandon_success_marks_abandoned_when_close_gate_closes`

The test simulates `abandon_wait(...)` closing the lifecycle gate before returning. It verifies the first poll writes `poll_abandoned_at`, reports `abandoned == 1`, does not report `shutdown_skipped`, clears the claim, and a later poller does not observe or abandon the same wait again.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q`
  - Result: `25 passed in 0.65s`
- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py tests/host/test_open_host_runtime.py tests/host/test_resolve_wait_command.py tests/host/test_public_lifecycle_smoke.py -q`
  - Result: `86 passed in 1.06s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed a new-version notice only.
- `git diff --check`
  - Result: passed with no output.

## README Decision

No README update required. The change is an internal ordering fix inside the existing Host wait poller and an added case in an existing test file. It does not change public Host interfaces, developer-facing stable behavior, test layering, test commands, or documented runtime assembly.

## Residual Risks / Open Questions

- DS Finding 02 remains intentionally deferred/rejected as a maintainability note per controller instruction; no code change was made for schema v17 skip.
- CAS conflict after external abandon success still preserves existing stale-claim behavior: if the claim is no longer current, durable mark is not forced. This is intentionally unchanged to preserve the wait poller CAS invariant.
- No GitHub comments, commits, staging, pushes, ready-for-review changes, merges, issue updates, or re-review/final closeout actions were performed.
