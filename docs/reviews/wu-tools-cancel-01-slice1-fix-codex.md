# WU-TOOLS-CANCEL-01 Slice S1 Fix Report

## Scope

- Work unit: `WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`
- Slice: `WU-TOOLS-CANCEL-01-S1 interrupt capsule + local worker cleanup`
- Gate: fix
- Agent: AgentCodex
- Base accepted plan commit: `4723ec61`
- Controller adjudication: `docs/reviews/wu-tools-cancel-01-slice1-code-review-controller-adjudication.md`

## Findings Fixed

| Finding | Status | Fix |
|---|---|---|
| DS F01 outer `CancelledError` can leak capsule/capsule task | fixed | `ToolRuntimeExecutor._dispatch_tool_call_with_bounds(...)` now catches outer `asyncio.CancelledError`, interrupts and closes the capsule via `_interrupt_capsule_after_wait(...)`, then re-raises cancellation. Added executor-level test that cancels the outer `execute()` task while an ignored-SIGTERM process-backed target is running and asserts terminate failed, kill completed, and capsule close ran. |
| MiMo 01 executor-level terminate -> kill escalation test missing | fixed | Added ToolRuntime executor integration test using a process target that ignores SIGTERM. The test asserts terminate is supported but incomplete and kill is supported and completed under ToolRuntime cancellation. |
| DS F02 `_DefaultLocalWorkerHandle.on_cancel(...)` background close task exception is not logged | fixed | `on_cancel(...)` now attaches a done callback to the background close task. The callback logs close failures with `local_worker_id`, cancel `reason`, and `error_type`. Added focused log assertion test. |
| DS F03 `_interrupt_capsule_after_wait(...)` close failure can hide governed outcome | fixed | `_interrupt_capsule_after_wait(...)` now catches and logs `capsule.close()` failures at warning level, without preventing governed cancel/timeout outcome return. Added focused test proving cancel still returns governed failure when close raises. |
| MiMo 02 `_run_process_target` catches `BaseException` | fixed | Changed `_run_process_target(...)` to catch `Exception`, allowing `SystemExit` and `KeyboardInterrupt` to terminate the child process naturally. |

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py -q`
  - Result: `61 passed in 3.79s`
- `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py -q`
  - Result: `3 passed in 0.86s`
- `source .venv/bin/activate && pytest tests/host/test_local_proxy_engine_ingest.py -q`
  - Result: `8 passed in 0.28s`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/host/test_import_boundary.py tests/host/test_package_exports.py -q`
  - Result: `39 passed in 2.22s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed a version availability notice for `v1.1.411`; no type errors or warnings.
- `git diff --check`
  - Result: passed

## README Decision

- Read `dayu/host/README.md`: no update required. The fix changes internal ToolRuntime cleanup behavior and LocalProxy diagnostic logging; it does not change Host public API, public cancel semantics, stable worker interfaces, or developer-facing architecture.
- Read `tests/README.md`: no update required. The added tests are focused regressions inside existing Host ToolRuntime / LocalProxy and Runtime helper test layers; they do not introduce a new test layer, command category, or maintenance rule.

## Residual Risks

- S1 still does not migrate production Doc / Fins / Web tools to process-backed or request-abort-capable adapters; that remains S2 scope.
- `thread_backed` still does not provide OS thread hard interruption. Tests continue to assert it only cancels the wrapper awaitable.
- The new executor hard-kill tests wait for the spawned process to install its SIGTERM ignore handler before cancellation. This is intentionally bounded but still depends on local process spawn performance.
