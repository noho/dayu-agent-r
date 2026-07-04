# WU-WAIT-03 Slice 1 Implementation

## Scope

- Work unit: WU-WAIT-03 / GitHub issue-92.
- Gate executed: implementation only.
- Slice: Slice 1 - Host Lifecycle Contract And Poller Diagnostics.
- Objective: make Host wait poller cancelled-wait lifecycle explicit, typed, retryable on transient failure, and terminal on applied / unsupported / noop lifecycle results.
- Non-goals preserved: no Engine / Service / UI / runtime / config / prompt / tool schema changes; no Fins Slice 2 implementation; no public Host API change; no new durable table or column; no provider registry; no second watchdog.

## Changed Files

- `dayu/host/wait_adapter.py`
  - Added `WaitExternalJobLifecycleAction`.
  - Added `WaitExternalJobLifecycleApplied`, `WaitExternalJobLifecycleUnsupported`, `WaitExternalJobLifecycleNoop`, and `WaitExternalJobLifecycleResult`.
  - Changed `WaitPollAdapter.abandon_wait(...)` to return `WaitExternalJobLifecycleResult`.
  - Mapped applied / unsupported / noop lifecycle results to durable poll outcomes.
- `dayu/host/durable/state.py`
  - Added `WaitPollLastOutcome.ABANDON_UNSUPPORTED`.
  - Added `WaitPollLastOutcome.ABANDON_NOOP`.
  - Added keyword-only-compatible defaulted `last_outcome` parameter to `mark_wait_record_poll_abandoned(...)`.
- `dayu/host/durable/schema.py`
  - Added the two new `poll_last_outcome` values to the existing CHECK allowlist.
  - Bumped fresh schema version to 19.
  - Reason for touching outside the initial core file list: real DB writes failed on the old CHECK constraint; accepting the new enum values requires schema truth to match state truth. This did not add a table or column.
- `tests/host/test_wait_adapter_polling.py`
  - Updated fake adapters to return typed lifecycle results.
  - Added applied / unsupported / noop terminal diagnostics coverage.
  - Added unsupported / noop CAS conflict coverage.
- `tests/host/test_wait_poller_runtime.py`
  - Updated fake adapters for the typed protocol.
- `tests/host/test_wait_record_state.py`
  - Added enum codec roundtrip coverage.
  - Parameterized abandoned marker row validation for `ABANDONED`, `ABANDON_UNSUPPORTED`, and `ABANDON_NOOP`.
- `tests/host/test_durable_schema.py`
  - Updated schema version assertion and CHECK allowlist assertions.
- `tests/host/test_open_host_runtime.py`
  - Updated one fake adapter return type for pyright compatibility only; behavior unchanged.
- `docs/reviews/wu-wait-03-slice1-implementation-codex.md`
  - This implementation artifact.

## Behavior Changes

- Cancelled wait lifecycle adapter results are now explicit:
  - `WaitExternalJobLifecycleApplied` writes `poll_last_outcome=ABANDONED`.
  - `WaitExternalJobLifecycleUnsupported` writes `poll_last_outcome=ABANDON_UNSUPPORTED`.
  - `WaitExternalJobLifecycleNoop` writes `poll_last_outcome=ABANDON_NOOP`.
- All three terminal lifecycle results set `poll_abandoned_at`, clear the poll claim, stop re-observation, and increment `WaitPollOnceResult.abandoned` only after the CAS marker write succeeds.
- Adapter exceptions still write `ABANDON_ERROR` backoff and remain retryable without setting `poll_abandoned_at`.
- Missing adapter remains retryable through existing `MISSING_ADAPTER` backoff.
- CAS conflict after adapter returns does not re-run adapter in the same poll round, does not increment `abandoned`, reports `claim_conflicts`, and leaves the wait retryable.
- Cancelled wait lifecycle path does not call `resolve_wait(...)`.
- Host command cancellation state machine is unchanged.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q`
  - Passed: 34 tests.
- `source .venv/bin/activate && pytest tests/host/test_wait_record_state.py tests/host/test_durable_schema.py -q`
  - Passed: 60 tests.
- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py -q`
  - Passed: 17 tests.
- `source .venv/bin/activate && pyright`
  - Passed: 0 errors.
- `git diff --check`
  - Passed.

## Docs Decision

- `dayu/host/README.md` was read before Host changes.
- `tests/README.md` was read before test changes.
- No README update was made. The change is an internal Host adapter/poller diagnostic contract and test maintenance update; it does not alter the stable public Host API, user workflow, setup, commands, or README-level development interface.

## Residual Risks / Owners

- Fins adapter mapping is intentionally not implemented in this slice. It remains covered by Slice 2 of the accepted plan.
- Existing databases with schema version 18 are not compatibility-migrated in this slice. Per project schema rules, this work treats the current schema as fresh truth unless a compatibility migration is explicitly requested.
- Provider-specific lifecycle semantics remain adapter-owned. Host records only applied / unsupported / noop diagnostic categories.

## Completion Status

- Slice 1 implementation complete.
- Stopped before code review and all later gates, as requested.
