# WU-TOOLS-CANCEL-01 Slice S1 Implementation Report

## Scope

- Work unit: `WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`
- Slice: `WU-TOOLS-CANCEL-01-S1 interrupt capsule + local worker cleanup`
- Gate: implementation
- Agent: AgentCodex
- Accepted plan commit: `4723ec61`

## What Changed

- Added `dayu.runtime.interruptible_process` as a layer-neutral process helper with `start`, bounded `wait`, `terminate`, `kill`, and `close` semantics. It only depends on stdlib and `dayu.contracts.json_value`.
- Added ToolRuntime internal execution capsule types:
  - `ToolExecutionMode`: `async_direct`, `thread_backed`, `process_backed`
  - `ToolExecutionCapsule` / `ToolExecutionCapsuleFactory`
  - `AsyncDirectToolExecutionCapsule`
  - `ThreadBackedToolExecutionCapsule`
  - `ProcessBackedToolExecutionCapsule`
- Integrated capsule execution into `ToolRuntimeExecutor._dispatch_tool_call_with_bounds(...)` while preserving the existing batch deadline from `BatchToolExecutionContext.timeout_seconds`.
- Kept the default production path as `async_direct`, including the existing pre-cancel barrier that avoids starting a callable when the context token is already cancelled.
- Added process-backed test fixture path through an internal capsule factory without changing `dayu.contracts`, public Host cancel API, Engine contract, durable schema, or EventLog event types.
- Updated default local worker cancel behavior so `on_cancel(...)` schedules event stream `close()`, cancelling active `anext` and closing the underlying async generator.
- Added bounded local worker close grace in dispatch (`3.0s`) so close timeout logs a diagnostic and lane release still proceeds.
- Added tests for process terminate/kill, ToolRuntime process-backed cancellation, thread-backed non-hard-interrupt semantics, default local worker stream close on cancel, and dispatch finally/lane release under `CancelledError`.

## Direct Evidence Used

- `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` S1 required typed capsule modes, process-backed fixture path, local worker stream close, bounded cleanup grace, and accept/ingest barrier preservation.
- `dayu/host/tool_runtime.py` previously raced only the callable awaitable with token/deadline in `_dispatch_tool_call_with_bounds(...)`.
- `dayu/host/local_proxy.py` previously had a default `on_cancel(...)` no-op.
- `dayu/host/dispatch.py` already released active handle and lane token in `_consume_worker_events(...)` `finally`; S1 needed cancel-triggered stream interruption to reach that finally path.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py -q`
  - Result: `58 passed in 1.67s`
- `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py -q`
  - Result: `3 passed in 0.85s`
- Additional focused regression for touched local proxy file:
  - `source .venv/bin/activate && pytest tests/host/test_local_proxy_engine_ingest.py -q`
  - Result: `7 passed in 0.26s`
- Additional import/export boundary regression for new runtime module and ToolRuntime exports:
  - `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/host/test_import_boundary.py tests/host/test_package_exports.py -q`
  - Result: `39 passed in 2.19s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## README Decision

- Read `dayu/host/README.md`: no update required. The current README already documents the Host local execution boundary, worker handle close/cancel hook, and Host-owned ToolRuntime boundary at the stable developer level. S1 changed internal cleanup mechanics and internal capsule execution, not a new public Host interface.
- Read `tests/README.md`: no update required. Existing runtime and Host test-layer sections already cover focused runtime helper tests and Host ToolRuntime / local execution tests; this slice did not introduce a new testing layer or stable command category.

## Open Questions / Residual Risks

- S1 intentionally does not migrate production Doc/Fins/Web tools. Production blocking paths still require S2 migration to process-backed or request-abort-capable async adapters before #87 closeout.
- `thread_backed` is explicitly not production-grade hard interrupt for non-cooperative blocking work; tests assert it does not claim OS thread termination.
- Process-backed capsule currently supports S1 fixture shape with JSON-like process result. If S2 proves production providers need shared tool declaration capability in `dayu.contracts`, that must return to design/contract gate instead of adding magic tool-name branches.
