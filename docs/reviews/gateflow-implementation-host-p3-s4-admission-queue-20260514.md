# Gateflow Implementation: Host P3-S4 Admission And Queue Promotion

- **gate**: Phase 3 implementation
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S4 Admission And Queue Promotion
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **implementation date**: 2026-05-14
- **implementation agent**: AgentCodex
- **status**: completed

## Scope

本 slice 只实现内部 admission service：

- `start_run`
- `submit_followup_queue`
- `promote_next_queued_run`
- no-op/test wakeup port
- start/follow-up idempotency
- P3-S4 admission queue tests

显式未实现：

- public facade
- scheduler / lane / WorkerProxy / Engine dispatch
- Service / UI / Fins / Engine / runtime 修改
- steer / retry / replay / wait / recovery
- cancel / terminal closeout orchestration

## Changed Files

- `dayu/host/admission.py`
- `tests/host/test_admission_queue.py`
- `docs/reviews/gateflow-implementation-host-p3-s4-admission-queue-20260514.md`

未修改 `dayu/host/durable/session_lifecycle.py`；本 slice 不需要复用或迁移 snapshot helper。

## Implemented Plan Items

- 新增 `HostAdmissionService` 与默认装配 helper。
- 新增 `AdmissionPolicy`，只允许 `queue`、`reject`、`attach_active`；未知值在事务前抛出 `ValueError`。
- 新增 `SubmitFollowupQueueAdmissionInput`，强制接收非空 `resolved_execution_target`。
- 新增 `AdmissionWakeupPort`、`NoopAdmissionWakeupPort` 与测试 spy；只记录/触发 pending dispatch wakeup，不做真实 dispatch。
- `start_run`：
  - 同事务校验 Session open。
  - 无 active Run 时追加 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(initial)`、`ATTEMPT_STARTED`，创建 running Run、starting Attempt、pending dispatch record。
  - active + `queue` 时创建 queued Run。
  - active + `reject` 时抛出 `HostApiErrorCode.CONFLICT`，不写 EventLog，不写 idempotency。
  - active + `attach_active` 时不写 EventLog，写 null event ref idempotency，返回 active Run。
- `submit_followup_queue`：
  - 同事务吸收 active Run 竞态。
  - active 存在时创建 queued Run 且不创建 Attempt。
  - active 不存在时直接创建 running Run、starting Attempt、pending dispatch record。
  - 始终把显式 `resolved_execution_target` 写入 `host_runs.execution_target`。
  - semantic digest 排除 `resolved_execution_target`；同 key 重试返回首次 persisted Run，且不改 target。
- `promote_next_queued_run`：
  - active Run 存在时返回 skipped。
  - 无 active 时复用 P3-S3 transition helper，按 queued Run 的 `accepted_event_sequence` FIFO promotion 一个 Run。
  - promotion 后复用 queued Run 已持久化 execution target。

## Validation

已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
```

结果：

```text
20 passed
```

已通过：

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

`git diff --check` 将在 artifact 写入后执行。

## Docs Decision

本 slice 按用户指定文件边界只允许修改 `dayu/host/admission.py`、必要 durable helper、`tests/host/test_admission_queue.py` 和本 implementation artifact。虽然新增了 Host admission 模块和测试文件，README 更新属于更宽的 Phase 3 文档同步触发项；本次 P3-S4 指令未授权修改 README，因此记录为本 slice 不修改 README。

## Plan Gaps

- P3-S4 plan 要求 promotion CAS loser 返回 skipped；当前可达路径中 SQLite `BEGIN IMMEDIATE` 串行化 promotion，第二个竞争者会在提交后重读 active 并 skipped。低层 P3-S3 helper 对“append 后 CAS lost”仍保持已接受的 rollback 行为，未在本 slice 改写，以避免破坏 P3-S3 测试和既有 controller adjudication。
- `wake_queue_promotion` 端口已定义为 no-op/test spy，但本 slice 未接入 terminal/cancel 后 promotion trigger；该部分属于 P3-S5。

## Residual Risk Classification

- **covered by later slice**: terminal / cancel release 后自动触发 promotion，由 P3-S5 拥有。
- **covered by later phase**: public facade、policy provider integration、真实 dispatch、lane acquire、WorkerProxy，由 Phase 4/5 拥有。
- **accepted in current slice**: P3-S4 多进程 promotion 测试用多连接线程模拟 SQLite 竞争；更完整的多进程 admission race 覆盖属于 P3-S6。

## Completion Signal

P3-S4 已实现 direct start、follow-up queue、idempotency、closed Session rejection、reject/attach active side effects、FIFO promotion 与 concurrent promotion at-most-one 覆盖；指定测试与 pyright 均通过。
