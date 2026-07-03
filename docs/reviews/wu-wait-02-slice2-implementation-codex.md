# WU-WAIT-02 Slice 2 Implementation - Codex

## Slice

- Work unit: `WU-WAIT-02` / GitHub Issue #90
- Slice: Slice 2 - Backoff-Aware Poller Supervisor And Lifecycle
- Status: implementation complete; no code review / fix / commit / push / PR performed.

## Changed Files

- `dayu/host/wait_adapter.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_durable_schema.py`
- `tests/README.md`
- `docs/reviews/wu-wait-02-slice2-implementation-codex.md`

Pre-existing controller update in `docs/host/issues-implementation-control.md` was preserved and not edited by this implementation.

## Behavior Implemented

- Added `WaitPollerRuntimePolicy` with centralized defaults and positive-value validation for poll interval, claim TTL, claim batch size, backoff initial delay, multiplier, max delay, and close drain timeout.
- Moved poll backoff calculation to policy-backed centralized helper.
- Added `WaitPollerSupervisor` with `open()`, `close()`, `drain_once_for_test()`, and `diagnostics_snapshot()`.
- Added runtime diagnostics dataclasses and loop status enum. Diagnostics remain in-memory only and do not write EventLog.
- Added cancellable background sleep through a close event.
- Made `close()` idempotent and made close drain timeout record/log diagnostics while still waiting for the in-flight poll path to stop.
- Added lifecycle close gate checks before claim, before adapter call, before `resolve_wait`, before `abandon_wait`, after `abandon_wait` before durable abandon marking, and before loop sleep.
- Added `WaitPollerFactory` because `HostTransactionRunner` holds a SQLite connection with thread affinity; background supervisor threads must receive a thread-local poller/runner from Slice 3 wiring rather than reusing an opener-thread runner.
- Added `shutdown_skipped` durable poll outcome and schema check support, bumping fresh `HOST_SCHEMA_VERSION` to 18. Close after adapter result but before resolve/abandon releases claim with `shutdown_skipped` backoff, leaving the wait retryable.
- Unexpected loop-level exceptions are logged and move diagnostics to `failed`.

## Validation

Required command:

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q
```

Result:

```text
20 passed in 0.56s
```

Additional schema-focused command, because this slice had to extend the Slice 1 durable enum:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q
```

Result:

```text
57 passed in 0.67s
```

Required command:

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Required command:

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

Read `dayu/host/README.md` and `tests/README.md` Agent update constraints.

- `dayu/host/README.md` was not updated because Slice 2 adds an internal supervisor primitive only; it does not change `open_host`, public Host handle methods, Service-facing construction options, or user workflow.
- `tests/README.md` was updated because a new Host test file, `tests/host/test_wait_poller_runtime.py`, was added and the README explicitly tracks current test structure.

## Residual Risks

- Background supervisor cannot safely reuse an opener-thread `HostTransactionRunner`; it must receive a thread-local poller factory in Slice 3 open_host wiring. Classification: current slice design constraint. Owner: WU-WAIT-02 Slice 3. Destination: `open_host` integration must construct the factory with a durable runner/connection valid in the background execution boundary.
- Synchronous adapter calls still cannot be forcibly interrupted. Classification: accepted plan residual. Owner: WU-WAIT-02 Slice 2 / future adapter contract owners. Destination: close waits for in-flight adapter calls; operators see close-drain timeout diagnostics.
- `shutdown_skipped` uses normal durable backoff, so repeated close-during-result races can increase shared backoff. Classification: bounded retry behavior. Owner: Host wait poller runtime. Destination: policy tuning remains centralized in `WaitPollerRuntimePolicy`.

## Stop Conditions

- Synchronous adapter calls did not require changing the adapter protocol; close drain waits and records timeout diagnostics. No stop.
- Supervisor did not need private `open_host` internals; no stop.
- Runtime diagnostics did not require EventLog changes; no stop.
