# WU-LIFE-03 Slice 2 Implementation - Codex

## Changed Files

- `dayu/host/api.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/recovery.py`
- `dayu/host/README.md`
- `docs/host/design.md`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_recovery_scan.py`

## Implemented Behavior

- Added construction-time `OpenHostOptions.active_cancel_timeout_seconds` with `None` or positive finite seconds validation. `OpenHostOptions` defaults to enabled; low-level `HostLocalExecutionOptions` defaults to disabled unless explicitly wired by `open_host`.
- Added Host-owned active cancel watchdog in `HostDispatchScheduler`:
  - deterministic `tick_active_cancel_watchdog(now)` entry point;
  - durable scan over current `CANCELLING` runs, current `RUNNING` Attempt, worker-accepted dispatch record, and linked `CANCEL_REQUESTED` fact;
  - timeout closeout through Slice 1 `active_cancel_timeout_closeout_in_transaction(...)`;
  - queue promotion wakeup and projection catch-up after successful timeout terminal closeout;
  - cancel-commit wakeup plus periodic fallback scan under scheduler lifecycle.
- Wired `cancel_run` / `cancel_session_runs` active cancel propagation to wake the watchdog when a durable active cancel target is produced or replayed.
- Wired `open_host` startup ordering so an enabled watchdog performs one startup tick before `StartupRecoveryScanner.scan()`.
- Added recovery deferral for accepted-cancel `CANCELLING` runs when watchdog is enabled; disabled watchdog keeps existing recovery orphan behavior.
- Preserved scheduler / Host close boundary: close cancels local runtime and active tasks but does not run timeout closeout.
- Public watch/get_run observe the existing `CANCELLED` terminal shape after timeout closeout; timeout fields remain additive EventLog diagnostics.

## Tests Added Or Updated

- `tests/host/test_active_cancel_dispatch.py`
  - non-cooperative worker timeout closes Run/Attempt as `CANCELLED`;
  - before-timeout tick noops;
  - zero `CANCELLING` scan noops;
  - multiple `CANCELLING` scan closes eligible runs;
  - timeout closeout promotes queued Run;
  - cancel_session replay after timeout does not append or propagate;
  - scheduler close writes no timeout terminal.
- `tests/host/test_open_host_runtime.py`
  - public watcher sees `HostEventKind.CANCELLED` and `get_run` returns `CANCELLED`;
  - clean-close/reopen after timeout closes accepted cancel as `CANCELLED`, not `LOST`;
  - clean-close/reopen before timeout defers to watchdog and writes no `RUN_LOST`.
- `tests/host/test_recovery_scan.py`
  - enabled watchdog defers accepted-cancel `CANCELLING`;
  - disabled watchdog preserves existing `CANCELLING` orphan `LOST` policy.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q`
  - Passed: `140 passed in 2.48s`.
  - Note: this repository does not contain `tests/host/test_startup_recovery.py`; `tests/host/test_recovery_scan.py` is the existing `StartupRecoveryScanner` owner module allowed by the slice instructions.
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q`
  - Passed: `123 passed in 1.33s`.
- `source .venv/bin/activate && pyright`
  - Passed: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && git diff --check`
  - Passed.

## Docs / README Decision

- Updated `docs/host/design.md` because Slice 2 introduces the active cancel timeout option, watchdog terminal policy, and recovery deferral behavior.
- Updated `dayu/host/README.md` because `dayu/host` public opener behavior and lifecycle semantics changed for developers.
- Read `tests/README.md`; no update needed because the test layer organization and documented common commands did not change.
- Root `README.md` not updated because there is no user-visible CLI/Web/WeChat workflow, installation, logging, or workspace path change.

## Residual Risks

- Provider/tool work is not physically killed by Host timeout closeout. Owner/destination: WU-TOOLS-CANCEL-01.
- Timeout default may need production tuning by backend/provider. Owner/destination: Host lifecycle watchdog runtime tuning under GitHub Issue #87.
- Reopen timeout compares durable UTC event time with current Host UTC time; cross-instance clock skew can shift detection. Owner/destination: Host lifecycle watchdog runtime tuning under GitHub Issue #87.
- `active_cancel_timeout_seconds=None` remains an explicit special/test opt-out where recovery orphan policy can still mark `CANCELLING` as `LOST`. Owner/destination: Host runtime assembly policy under GitHub Issue #87.

## Stop Conditions

- No second independent watchdog runtime was introduced; the watchdog is owned by `HostDispatchScheduler` / `open_host` lifecycle.
- Deterministic tests use direct `tick_active_cancel_watchdog(now)` or durable timestamp adjustment; no long real sleep is required.
- No provider/tool kill API was added.
- No production files outside the allowed Slice 2 scope were modified.
