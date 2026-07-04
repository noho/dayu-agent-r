# WU-LIFE-03 Slice 2 Code Re-Review Controller Adjudication

## Scope

- Work unit: `WU-LIFE-03`
- Gate: Slice 2 code re-review
- Fix artifact: `docs/reviews/wu-life-03-slice2-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-life-03-slice2-code-rereview-mimo.md`
  - `docs/reviews/wu-life-03-slice2-code-rereview-ds.md`

## Controller Decision

Slice 2 code re-review passes. Both accepted findings are closed and no new material defect was reported.

## Finding Closure

### S2-CR-F01 malformed RUN_CANCELLING payload can crash startup recovery

- Status: closed.
- Evidence: `_has_accepted_cancel_fact` now catches `HostDurableError` from `event_payload_object(...)` and returns `False`.
- Test evidence: `tests/host/test_recovery_scan.py::test_scan_malformed_cancelling_payload_uses_orphan_policy` proves malformed `RUN_CANCELLING` payload material does not crash startup recovery and does not defer to the watchdog.

### S2-CR-F02 watchdog loop exits permanently after a transient tick exception

- Status: closed.
- Evidence: `_active_cancel_watchdog_loop` now isolates per-tick non-cancel exceptions, logs `dispatch.active_cancel_watchdog.tick_failed`, and continues the loop while preserving `asyncio.CancelledError` propagation.
- Test evidence: `tests/host/test_dispatch_scheduler.py::test_active_cancel_watchdog_loop_continues_after_transient_tick_failure` proves a transient tick failure does not terminate the watchdog loop.

## Non-blocking Items

- DS F02 (`ActiveCancelWatchdogWakeupPort` location) remains non-blocking architecture debt and is not part of the current fix.
- DS F03 (overlapping candidate and transition precondition checks) remains a non-blocking maintenance note.
- Watchdog loop transient-failure test uses a deterministic scheduler subclass rather than injecting a real durable storage failure. This is accepted because the current risk is the loop control flow, not durable storage behavior.

## Validation

Controller validation after fix:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
```

Result: `142 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
```

Result: `123 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate && git diff --check
```

Result: passed.

## Next Gate

Proceed to accepted Slice 2 commit, then update control state for the next WU-LIFE-03 gate.
