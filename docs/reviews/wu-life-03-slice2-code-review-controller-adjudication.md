# WU-LIFE-03 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-LIFE-03`
- Gate: Slice 2 code review
- Implementation artifact: `docs/reviews/wu-life-03-slice2-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-life-03-slice2-code-review-mimo.md`
  - `docs/reviews/wu-life-03-slice2-code-review-ds.md`
- Reviewed changes: current uncommitted Slice 2 workspace changes after accepted Slice 1 commit `ef2d3644`.

## Controller Decision

Current gate does not pass. A focused fix is required before re-review.

## Accepted Findings

### S2-CR-F01 malformed RUN_CANCELLING payload can crash startup recovery

- Source: MiMo Finding 1, DS F01.
- Status: accepted-current-fix.
- Location: `dayu/host/recovery.py::_has_accepted_cancel_fact`.
- Reasoning: `event_payload_object(...)` can raise `HostDurableError` for malformed or missing payload material. The dispatch-side helper already treats the same condition as "not an accepted cancel candidate"; recovery should do the same. Letting one corrupt `RUN_CANCELLING` payload abort the whole startup recovery scan is not acceptable for a Host lifecycle path.
- Required fix: catch `HostDurableError` in `_has_accepted_cancel_fact` and return `False`.
- Required test: add focused recovery coverage proving a malformed `RUN_CANCELLING` payload does not crash `StartupRecoveryScanner.scan()` and does not classify the Run as `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`.

### S2-CR-F02 watchdog loop exits permanently after a transient tick exception

- Source: MiMo Finding 2.
- Status: accepted-current-fix.
- Location: `dayu/host/dispatch.py::_active_cancel_watchdog_loop`.
- Reasoning: Slice 2 explicitly adds periodic fallback scan to cover lost wakeups and reopen leftovers. If one tick raises a retry-exhausted or payload/storage exception and the background task exits, existing `CANCELLING` Runs may hang until another cancel command or Host reopen. This is a low-cost fix and belongs to the watchdog runtime integration slice.
- Required fix: contain non-cancel exceptions at the per-tick level so the loop logs the failure and continues future periodic scans while preserving scheduler-close `CancelledError` behavior.
- Required test: add focused scheduler/watchdog coverage showing a transient tick exception does not permanently kill the watchdog loop, or document why direct deterministic unit coverage is not practical and cover the helper-level behavior that prevents loop exit.

## Non-blocking Findings / Notes

- DS F02 (`ActiveCancelWatchdogWakeupPort` location) is rejected as current fix. The Protocol is intentionally a narrow command dependency port, `open_host` is the only production assembler, and moving it now would be churn without a current behavior defect.
- DS F03 (overlapping candidate / transition precondition checks) is accepted as a non-blocking maintenance note only. The overlap is intentional: candidate scan filters obvious non-candidates, while transition helper remains the CAS truth. No current code change required.
- MiMo residual notes about all non-terminal Run scan, loop clock injection, and test SQLite helpers are deferred to #87 runtime tuning or accepted test implementation tradeoffs.

## Required Validation After Fix

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
source .venv/bin/activate && pyright
source .venv/bin/activate && git diff --check
```
