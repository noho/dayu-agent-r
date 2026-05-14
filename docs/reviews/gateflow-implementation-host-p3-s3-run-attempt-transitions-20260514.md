# Gateflow Implementation Artifact: Host P3-S3 Run / Attempt Transitions

- **gate**: implementation
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S3 Run / Attempt Transition Primitives
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **implementation date**: 2026-05-14
- **status**: completed, pending review

## Scope And Non-goals

本次实现严格限制在 P3-S3：

- 允许修改：
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_run_attempt_transitions.py`
- 额外交付本 implementation artifact。

未实现且未触碰：

- admission / queue scanning orchestration
- WorkerProxy / LocalProxy / RemoteProxy
- Engine dispatch / EngineEvent ingest
- lane / scheduler / after-commit callback
- `ATTEMPT_RUNNING`
- public facade
- Engine / Fins / Service / UI / runtime

## Changed Files

- `dayu/host/durable/state.py`
  - 新增 Run / Attempt / dispatch record read helpers。
  - 新增 Run / Attempt / dispatch record insert helpers。
  - 新增低层 CAS mutation result 类型，区分 `updated`、`cas_lost`、`not_found`、`invalid_state`。
  - 新增 queued promotion、queued cancel、pre-dispatch cancel、terminal closeout 所需的 CAS update helper。

- `dayu/host/durable/run_transition.py`
  - 新增 P3-S3 transition primitive module。
  - 实现 `create_queued_run_in_transaction`。
  - 实现 `create_running_run_with_starting_attempt_in_transaction`。
  - 实现 `promote_queued_run_in_transaction`。
  - 实现 `terminal_closeout_in_transaction`。
  - 实现 `cancel_queued_in_transaction`。
  - 实现 `cancel_predispatch_starting_in_transaction`。
  - 所有 helper 接收 `HostTransaction`，不自行开启事务，不注册 after-commit。
  - EventLog append 与 state row update 均发生在调用方同一 transaction 内。
  - terminal closeout append 具体 terminal event type：`ATTEMPT_SUCCEEDED` / `ATTEMPT_FAILED` / `ATTEMPT_LOST` 与 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_LOST`，未使用 `RUN_TERMINAL`。

- `tests/host/test_run_attempt_transitions.py`
  - 覆盖 running Run 创建、queued Run 创建、FIFO promotion、terminal closeout、CAS loser、pre-dispatch cancel、terminal cancel invalid state、rollback 原子性。

## Implemented Plan Items

- 低层 Run / Attempt / dispatch read/insert/CAS helper 已实现。
- running creation 会 append `RUN_ACCEPTED`、`RUN_STARTED`、`ATTEMPT_STARTED` 并创建 Run `RUNNING`、Attempt `STARTING`、dispatch `pending`。
- queued creation 会 append `RUN_ACCEPTED`、`RUN_QUEUED` 并创建 Run `QUEUED`，不创建 Attempt 或 dispatch。
- promotion 按 `accepted_event_sequence` 读取最早 queued Run，成功时创建 STARTING Attempt 与 pending dispatch。
- terminal closeout 会同事务写 Attempt terminal event、Run terminal event、Attempt terminal row、Run terminal row。
- pre-dispatch cancel 会同事务写 `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，并 CAS 更新 dispatch、Attempt、Run。
- queued cancel 会写 `CANCEL_REQUESTED`、`RUN_CANCELLED` 并 CAS 更新 queued Run。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py -q
```

结果：8 passed。

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q
```

结果：17 passed。

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：0 errors, 0 warnings, 0 informations。

`git diff --check` 将在最终验证 gate 运行。

## Docs Decision

按项目 README 触发规则，`dayu/host/` 与 `tests/host/` 变更会触发 `dayu/host/README.md` 与 `tests/README.md` 检查。

本次用户明确限定允许修改文件为：

- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_run_attempt_transitions.py`
- 本 implementation artifact

因此本 slice 未修改 README。该 README 同步事项应由 controller 在允许文档 scope 的后续 gate 处理。

## Residual Risks

- P3-S3 只提供低层 transaction primitive；admission idempotency、public command facade、after-commit promotion/wakeup 与 dispatch scheduler 仍由 P3-S4/P3-S5 负责。
- CAS loser 在真实并发下依赖调用方使用 `BEGIN IMMEDIATE` transaction runner；本 slice 不引入额外 lease/fencing。
- terminal closeout helper当前覆盖 STARTING/RUNNING Attempt 到 succeeded/failed/lost 的低层路径；EngineEvent 到 terminal 状态的生产映射仍是后续 phase 范围。
