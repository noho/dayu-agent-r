# WU-WAIT-02 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub Issue #90
- Gate: Slice 2 code review
- Slice: Backoff-aware poller supervisor and lifecycle
- Baseline: accepted Slice 1 commit `b7447316`
- Implementation artifact: `docs/reviews/wu-wait-02-slice2-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260701-150341.md`
  - `docs/reviews/code-review-20260701-150525.md`

## Controller Decision

Decision: fix required.

The core supervisor direction is acceptable: a typed `WaitPollerFactory` is justified by the direct SQLite thread-affinity failure observed during implementation, runtime diagnostics remain in-memory, shutdown-skipped is persisted as retry metadata, and focused validation passed.

However, both reviewers identified the same material defect: the default `_DirectWaitPollerFactory` allows `WaitPollerSupervisor.open()` to start a background thread that reuses a `HostTransactionRunner` created on the caller thread. That path is unsafe for SQLite and must fail fast or be removed before the slice can be accepted.

## Finding Adjudication

### S2-CR-F01 default direct factory reuses caller-thread transaction runner in background thread

- Sources:
  - `docs/reviews/code-review-20260701-150341.md` finding 01
  - `docs/reviews/code-review-20260701-150525.md` finding 01
- Severity: high
- Controller verdict: accepted
- Required action:
  - Remove the unsafe default background factory path from `WaitPollerSupervisor`.
  - Make `poller_factory` an explicit required typed dependency for supervisor construction, or otherwise make `open()` fail fast before any background thread can use a caller-thread `HostTransactionRunner`.
  - Remove or isolate `_DirectWaitPollerFactory` so it cannot be selected implicitly by production `open()`.
  - Update tests so every background supervisor path supplies a thread-local factory.
  - Add a regression test that constructing without an explicit safe factory fails fast, or that the unsafe default path no longer exists.

### S2-CR-F02 supervisor constructor dead parameters when factory is provided

- Source: `docs/reviews/code-review-20260701-150341.md` finding 02
- Severity: low
- Controller verdict: accepted
- Required action:
  - Resolve as part of S2-CR-F01 by trimming `WaitPollerSupervisor` construction to dependencies that are actually consumed when an explicit factory is required.
  - Do not leave required parameters that are only stored for the removed implicit direct-factory path.

### S2-CR-F03 close self-call branch returns before stopped state

- Source: `docs/reviews/code-review-20260701-150525.md` finding 02
- Severity: medium
- Controller verdict: accepted
- Required action:
  - Make the poller-thread self-close branch explicit and fail-fast or clearly non-public with a warning and comment.
  - Preferred fix: raise `RuntimeError` if `close()` is called from the supervisor thread, because the documented close contract cannot wait for the current thread to stop.
  - Add or update a focused test for the chosen behavior.

### S2-CR-F04 double-close transient CLOSING state

- Sources:
  - `docs/reviews/code-review-20260701-150341.md` finding 03
  - `docs/reviews/code-review-20260701-150525.md` finding 03
- Severity: low
- Controller verdict: accepted
- Required action:
  - Add an early return for already stopped / failed supervisor or clear `self._thread` after close, so repeated close cannot move diagnostics from `STOPPED` back to `CLOSING`.
  - Keep close idempotent and covered by tests.

### S2-CR-F05 close_drain_timeout_seconds does not support None despite accepted plan

- Source: `docs/reviews/code-review-20260701-150341.md` finding 04
- Severity: low
- Controller verdict: accepted
- Required action:
  - Support `close_drain_timeout_seconds: float | None`.
  - `None` must mean no first-timeout diagnostic threshold and a direct wait until the in-flight poll path stops.
  - Positive floats retain current timeout diagnostic behavior.
  - Add policy validation tests for `None` and non-positive non-None values.

## Non-Blocking Notes

- `WaitPollerFactory` itself is accepted as a necessary typed port because background threads need a thread-local durable runner / connection boundary.
- Using `threading.Thread` rather than an async task is accepted for Slice 2 because the current adapter protocol is synchronous and implementation evidence showed thread-local runner construction is the real safety boundary. Slice 3 must still integrate this safely with `open_host`.
- `shutdown_skipped` using normal bounded durable backoff is accepted as a low-risk retry behavior.

## Required Fix Validation

After fix, rerun:

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q
source .venv/bin/activate && pyright
git diff --check
```

Then return to two-agent code re-review before any accepted Slice 2 commit.
