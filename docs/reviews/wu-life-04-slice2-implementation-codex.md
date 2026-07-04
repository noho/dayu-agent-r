# WU-LIFE-04 Slice 2 Implementation Artifact

## Scope

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: implementation
- Slice: Slice 2 - Watchdog No-Extra-Budget Closeout
- Implementer: AgentCodex

## Changed Files

Slice 2 touched:

- `dayu/host/dispatch.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_open_host_options.py`

Pre-existing Slice 1 / controller changes remain in the worktree and were not reverted. `docs/host/issues-implementation-control.md` was not modified by this slice.

## Exact Changes

- Converted the active cancel watchdog from a timeout scanner into an accepted-cancel closeout supervisor:
  - `wake_active_cancel_watchdog()` no longer returns based on a timeout option.
  - `_start_active_cancel_watchdog_loop()` is no longer gated by timeout seconds.
  - `tick_active_cancel_watchdog(now)` still validates `now`, but no longer compares `cancel_requested_at + timeout_seconds`.
  - Each strict candidate is eligible on the first tick after accepted cancel.
- Preserved strict watchdog candidate preconditions in `dispatch.py`: only `CANCELLING` Run, current `RUNNING` Attempt, worker-accepted dispatch, and a linked accepted cancel fact are considered.
- Renamed durable closeout helper semantics:
  - `ActiveCancelTimeoutCloseoutInput` -> `ActiveCancelWatchdogCloseoutInput`
  - `active_cancel_timeout_closeout_in_transaction()` -> `active_cancel_watchdog_closeout_in_transaction()`
  - Internal replay / precondition / validation / payload helper names now use watchdog closeout terminology.
- Changed active cancel watchdog terminal fact semantics:
  - reason is now `active_cancel_watchdog_closeout`.
  - worker lifecycle signal is now `active_cancel_watchdog_closeout`.
  - payload no longer includes `timeout_seconds` or `timed_out_at`.
  - payload includes `cancel_requested_at` and `closed_out_at`.
- Updated tests:
  - Replaced the before-timeout no-op test with first-tick closeout after cancel.
  - Removed active cancel timeout construction parameters from active cancel dispatch helpers.
  - Updated transition and Engine ingest tests for renamed helper/imports and new payload fields.
  - Updated open-host runtime startup recovery expectations: reopened accepted-cancel `CANCELLING` runs close as `CANCELLED` via watchdog and do not become `LOST`.
  - Updated scheduler close test setup to stop the unrelated watchdog background task before asserting active consumer cleanup behavior.
  - Renamed the public options negative test so repository search no longer exposes the old timeout semantic phrase.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py -q
```

Result: passed, `44 passed in 0.18s`.

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_run_attempt_transitions.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_effective_execution_config.py tests/host/test_public_open_host_options.py -q
```

Result: passed, `250 passed in 3.25s`.

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

Command:

```bash
git diff --check
```

Result: passed.

Command:

```bash
rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md
```

Result: no matches.

Command:

```bash
rg "active_cancel_timeout|timeout_seconds.*active" dayu/host tests/host docs/host/design.md dayu/host/README.md
```

Result: no matches.

## README Decision

`tests/README.md` was checked because this slice modified `tests/`. No update was made: the slice changed existing Host test assertions and helper names, but did not add a new test layer, new test command, or changed maintenance rule.

No Host README update was made in Slice 2. The Host public construction contract and design text updates were handled by Slice 1, and this slice did not add a new public option or user-facing workflow.

## Stop Condition Status

- No active production/test code computes active cancel closeout eligibility from `cancel_requested_at + timeout_seconds`: met.
- Active cancel closeout payload no longer describes post-cancel timeout: met.
- `rg "active_cancel_timeout" ...` and `rg "timeout_seconds.*active" ...` leave no live reason string, worker lifecycle signal, helper name, payload assertion, or design text: met.
- `rg "active_cancel_timeout_seconds" ...` has no live usage: met.
- Startup recovery is consistent with the new watchdog logic: met. Slice 1's unconditional defer now routes accepted-cancel `CANCELLING` runs to the always-enabled watchdog closeout path.
- Orphan `CANCELLING -> LOST` coverage does not depend on disabling the watchdog: met. The watchdog only sees candidates with linked accepted cancel facts; tests now rely on fixture state rather than a timeout disable path.

## Residual Risks / Owners

- Physical interruption of tool/provider work remains out of scope and belongs to WU-TOOLS-CANCEL-01 / Issue #87 follow-up.
- The watchdog still scans non-terminal runs and filters in process. Query optimization remains an Issue #87 performance follow-up.
- Closeout proves Host durable cancellation state, not provider/tool physical stop. Late worker events remain governed by existing identity, state, and first-committer-wins rules.
