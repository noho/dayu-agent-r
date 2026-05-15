# Gateflow Implementation Artifact: Host P5-S5 Active Cancel And Session-scope Cancel

## Gate

- Current gate: Host Phase 5 P5-S5 Active Cancel And Session-scope Cancel implementation
- Role: implementation worker
- Approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S5
- Design source: `docs/host/design.md` §22 Cancel、§17 Local EngineWorker、§9 Admission

## Scope And Non-goals

- 只实现 per-run active worker cancel 与 `cancel_session_runs` dispatching / active worker 子集。
- 未实现 WAITING cancel、RECOVERING cancel、RemoteProxy、ToolRuntime、active cancel watchdog。
- 未修改 durable schema、Engine code 或 lane token release ownership。

## Changed Files

- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_session_runs.py`

## Implemented Items

- `cancel_run`
  - 支持 `pending` / `waiting_for_lane` / pre-accept `dispatching` 的 STARTING Attempt direct cancel。
  - 支持 active Attempt `RUNNING`：追加 `CANCEL_REQUESTED`，首次从 Run `RUNNING` 推进到 `CANCELLING` 并追加 `RUN_CANCELLING`。
  - 已处于 `CANCELLING` 时不重复追加 `RUN_CANCELLING`，但返回 active cancel target 用于 best-effort 重新传播。
  - terminal 已先提交时返回当前 terminal Run，不改写终态。
- `cancel_session_runs`
  - 在同一 write transaction 内先分类全部 non-terminal Run。
  - 遇到 `WAITING` / `RECOVERING` 返回 `UNSUPPORTED_OPERATION`，无 partial mutation。
  - queued / pre-worker Run 直接 `CANCELLED`；active worker Run 进入或保持 `CANCELLING`。
  - 幂等 replay 返回当前 Session snapshot，不取消首次后新 Run，不追加 cancel facts；仍 active `CANCELLING` 时返回 target 供 best-effort 重新传播。
- active registry / dispatch
  - 新增进程内 `ActiveWorkerRegistry`，以 `(attempt_id, execution_id)` 注册 worker handle。
  - cancel message 携带 `run_id`、`attempt_id`、`execution_id`、`reason`。
  - dispatch worker accept durable commit 后注册 active handle，worker finally 注销。
  - cancel path 只设置 Host cancellation token 并调用 handle best-effort cancel，不释放 lane token。
  - worker event stream 接入 `EngineEventIngestor`，支持 `run_cancelled` 后关闭 Run 为 `CANCELLED`。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`
  - Result: passed, 21 tests.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: passed, 0 errors.
- `git diff --check`
  - Result: passed.

## Stop Conditions Checked

- 未实现 wait record 取消或 recovery dispatch。
- cancel path 未直接释放 lane token；lane release 仍在 scheduler / worker finally。
- 未修改 durable schema 或 Engine code。

## Residual Risks

- `HostCommandHandleOptions.local_execution` 的完整 command-handle 自动启动 dispatch scheduler 不在本 slice 范围内；本实现通过进程内 default active registry 连接已运行 scheduler 与 public cancel facade。
- active cancel watchdog 仍未实现；若 worker 收到 cancel 后长期不产出 terminal，Run 会停留在 `CANCELLING`，按计划留给后续 owner。
- README 未更新，因为本 worker handoff 的 allowed files 不包含 README；当前代码行为变化已由测试覆盖并在本 artifact 记录。
