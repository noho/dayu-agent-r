# Host P5-S6 Integration, Docs And Validation Closeout Implementation

## Scope

本次按 `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` 的 P5-S6 执行，目标是补齐本地 no-tool Engine 执行闭环的端到端验证、import boundary 验证和 README 同步。

实施过程中发现一个真实 production gap：`HostDispatchScheduler._consume_worker_events` 只消费显式 EngineEvent；worker event stream clean EOF 或异常时只释放 lane / close handle，不会调用 `EngineEventIngestor.close_clean_eof` / `close_worker_lost`。这会让 active Run 停留在非终态，无法满足 P5-S6 要求的 clean EOF -> `FAILED` 与 worker crash -> `LOST`。

Controller 已批准 controlled scope expansion，允许修改 `dayu/host/dispatch.py`。本次 production 修改仅限该文件，并保持 lane release owner 仍在 scheduler / worker `finally` 路径。

完整验证首次运行后暴露 4 个旧 Phase 3 测试断言仍未迁移到 Phase 5 真源：schema `user_version` 仍期望 `2`、Attempt `RUNNING` active cancel / terminal closeout 仍期望 `invalid_state`。Controller 二次批准 controlled scope expansion，允许只修改 `tests/host/test_admission_queue.py`、`tests/host/test_durable_schema.py`、`tests/host/test_run_attempt_transitions.py` 的过时断言、测试名和 docstring；本次没有为迎合旧测试修改生产代码。

## Changes

- `dayu/host/dispatch.py`
  - 在 worker event stream 消费中区分四类收口：
    - terminal EngineEvent 已 accepted / duplicate：记录 terminal seen，正常 EOF 不再追加 lifecycle closeout。
    - clean EOF 且未见 terminal：调用 `EngineEventIngestor.close_clean_eof`，收口为 `FAILED`。
    - worker stream 异常：调用 `EngineEventIngestor.close_worker_lost`，收口为 `LOST`。
    - `asyncio.CancelledError`：继续透传，由 scheduler close / task cancel 语义处理。
  - lane token release、active registry unregister 和 handle close 仍在 `finally` 中执行。

- `tests/host/test_phase5_local_execution_integration.py`
  - 新增 public `start_run` + real `HostDispatchScheduler` + runtime lane + fake local worker 端到端测试：
    - `final_answer` -> Run / Attempt `SUCCEEDED`。
    - `run_failed` -> Run / Attempt `FAILED`。
    - clean EOF without terminal -> Run / Attempt `FAILED`。
    - worker stream crash -> Run / Attempt `LOST`。
    - active fake worker cancel -> `CANCELLING` 后 `CANCELLED`。
    - terminal 与 cancel 释放 active slot 后继续 promotion queued Run，并唤醒 dispatch。
  - 保留原有低层 `EngineEventIngestor` lifecycle closeout 测试。

- `tests/host/test_import_boundary.py`
  - 补充 P5-S6 import boundary：
    - `dayu.runtime` 不 import `dayu.host` / `dayu.engine` / 上层或业务层。
    - `dayu.engine` 不 import `dayu.host`。
    - Host 只有本地执行边界模块可依赖 Engine contracts / entry。

- `tests/host/test_admission_queue.py`
  - 将 terminal Run 后 cancel 的期望迁移为返回当前 terminal result、记录幂等结果且不追加新 canonical facts。
  - 将 Attempt `RUNNING` active cancel 的期望迁移为 Run 进入 `CANCELLING`，追加 `CANCEL_REQUESTED` / `RUN_CANCELLING`，并返回 active worker cancel target。

- `tests/host/test_durable_schema.py`
  - 将 fresh schema `user_version` / `HOST_SCHEMA_VERSION` 期望迁移为 `3`。

- `tests/host/test_run_attempt_transitions.py`
  - 将 Attempt `RUNNING` terminal closeout 的期望迁移为 Phase 5 支持的 terminal closeout。

- `dayu/host/README.md`
  - 更新当前能力描述：RunInputBuilder no-tool boundary、LocalProxy / fake worker semantic baseline、dispatch record 四状态、active cancel 子集、scheduler worker stream EOF / crash closeout。
  - 清理仍把 dispatch / active cancel 接线描述为未实现的旧表述。
  - 保留 deferred owner：ToolRuntime、WAITING / wait cancellation、RemoteProxy、Recovery、policy provider set、projection / audit / outbox 等仍未实现。

- `tests/README.md`
  - 增加 Phase 5 本地执行集成测试 strata、运行命令和 fake local worker 约定。

`dayu/README.md` 已检查，当前总览没有把 RunInputBuilder / LocalProxy 全部描述成未来能力；本次未修改。根目录 `README.md` 未修改，因为没有新增 CLI、配置入口或用户运行方式。

## Validation

已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_import_boundary.py -q
# 14 passed

source .venv/bin/activate && pytest tests/host/test_admission_queue.py::test_cancel_terminal_run_returns_current_terminal_without_new_facts tests/host/test_admission_queue.py::test_cancel_attempt_running_enters_cancelling_with_cancel_facts tests/host/test_durable_schema.py::test_fresh_db_creates_foundation_and_phase5_tables tests/host/test_run_attempt_transitions.py::test_terminal_closeout_accepts_attempt_running_in_phase5 -q
# 4 passed

source .venv/bin/activate && pytest tests/host tests/runtime -q
# 334 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

## Residual Risks

- 真实 provider runner 的外部网络 / provider API smoke 不属于 Phase 5 必测；本次以 fake local worker、Engine public event contract 和 Host durable state machine 覆盖本地 no-tool 闭环。
- ToolRuntime / `fetch_more` 仍归 Phase 6；`WAITING` / `resolve_wait` 归 Phase 7；Memory 归 Phase 9；Context Governance 归 Phase 10；Recovery 归 Phase 11；Observer / Sink 归 Phase 13；RemoteProxy 归 Phase 14。

## Stop Status

P5-S6 implementation patch、integration tests、import boundary tests、Phase 5 旧断言迁移、README 同步与 artifact 已完成。指定 pytest、pyright 与 `git diff --check` 全部通过。
