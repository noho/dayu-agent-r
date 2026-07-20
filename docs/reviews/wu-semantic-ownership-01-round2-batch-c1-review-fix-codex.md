# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Review Fix

## scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1`.
- Gate: `review-fix`.
- Fixing agent: `AgentCodex`.
- Scope boundary: Host wait boundary rejection outcome/counter, wait callback status contract, wait poller supervisor diagnostics, focused tests and README updates required by those changes.
- Explicit non-scope: Batch C2 dispatch, promotion, cancel predispatch, tool accept duplicate index, Engine retry, PR/commit/push/merge.

## owner decisions

- Host wait poll adapter owns pre-adapter boundary rejection diagnostics. Durable `poll_last_outcome` now uses `boundary_rejected`, while concrete reason remains in `poll_last_error_code` / `poll_last_error_message`.
- `WaitPollOnceResult.boundary_rejections` owns the poll-round counter for Host boundary rejection. `adapter_errors` no longer counts waits rejected before provider adapter observation.
- Callback adapter status contract no longer contains `STALE_CALLBACK`; stale/expired boundary decisions are owned by `resolve_wait` / Host wait boundary owner.
- Supervisor self-close is represented by an internal typed exception, not a `RuntimeError` message comparison.
- `WaitPollerDiagnosticsSnapshot.round_errors` owns recoverable round exceptions. `fatal_errors` is reserved for terminal supervisor failure.

## fixed review findings

- `DS-C1-01`: fixed. Added durable `WaitPollLastOutcome.BOUNDARY_REJECTED`, schema CHECK value, poll result `boundary_rejections`, and updated boundary rejection tests to assert `adapter_errors == 0`.
- `C1-REVIEW-01`: fixed. Removed `WaitCallbackAdapterStatus.STALE_CALLBACK` and removed the Service HTTP mapping/test case for that unreachable status.
- `DS-C1-02`: fixed. Replaced self-close string matching with `_WaitPollerSelfCloseError`.
- `C1-REVIEW-02` / `DS-C1-03`: fixed. Added `round_errors`; recoverable poll round exceptions increment it while leaving `fatal_errors == 0` and supervisor status `RUNNING`.

## changed files

- `dayu/host/durable/state.py`
- `dayu/host/durable/schema.py`
- `dayu/host/wait_adapter.py`
- `dayu/host/wait_callback.py`
- `dayu/service/wait_callback_endpoint.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_wait_record_state.py`
- `tests/service/test_wait_callback_endpoint.py`
- `dayu/host/README.md`
- `tests/README.md`

## validation

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_record_state.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/service/test_wait_callback_endpoint.py -q`
  - Result: `288 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## README decision

- Updated `dayu/host/README.md` because Host callback and production wait poller contract text mentioned stale callback ownership and needed to reflect the current owner boundary.
- Updated `tests/README.md` because the Host test coverage summary still described stale deadline as callback-adapter behavior.
- No root README update required: no user-visible installation, CLI/Web/WeChat workflow, workspace path, or troubleshooting flow changed.

## residual risk

- Existing third-party `edgar` deprecation warnings remain unrelated.
- Expired waits still remain `WAITING` with retry/backoff after Host boundary rejection; any future terminal expired policy remains a separate Host wait policy decision.
- Batch C2 findings remain untouched.

## stop status

- Batch C1 review-fix is complete locally.
- No commit, push, PR, or merge was performed.
