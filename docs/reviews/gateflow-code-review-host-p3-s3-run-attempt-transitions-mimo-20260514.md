# Gateflow Code Review: Host P3-S3 Run / Attempt Transition Primitives

- **gate**: code review
- **reviewer**: AgentMiMo
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S3 Run / Attempt Transition Primitives
- **review date**: 2026-05-14
- **baseline commit**: 9cfb0f7 (P3-S2 accepted)
- **reviewed files**:
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_run_attempt_transitions.py`
- **status**: approved, no blocking findings

## Review Scope

本次审查对照以下文档与代码：

- `docs/host/design.md` §9.1 (state transition contract)、§22 (cancel semantics)
- `docs/host/implementation-control.md` (phase orchestration)
- `docs/host/phase3-session-run-attempt-admission-plan.md` P3-S3 section
- `docs/reviews/gateflow-implementation-host-p3-s3-run-attempt-transitions-20260514.md` (implementation artifact)
- `dayu/host/durable/state.py` (CAS helpers)
- `dayu/host/durable/run_transition.py` (transition primitives)
- `tests/host/test_run_attempt_transitions.py` (tests)

## Findings

### No Blocking Findings

本次审查未发现阻塞级问题。

### Observations (non-blocking)

#### O-1: terminal_closeout 测试只覆盖 SUCCEEDED 路径

**severity**: info

`test_terminal_closeout_appends_concrete_terminal_events` 只验证 `AttemptStatus.SUCCEEDED` / `RunStatus.SUCCEEDED`。`FAILED` 和 `LOST` 终态路径未被测试直接覆盖。

**分析**: `_attempt_terminal_event_type` 和 `_run_terminal_event_type` 都是简单的 if-chain 映射，`_validate_terminal_input` 通过调用这两个函数间接验证了 status 枚举值合法性。`_invalid_terminal_precondition` 的前置检查与终态类型无关。P3-S3 作为低层 primitive，SUCCEEDED 路径已验证核心 CAS + event append 逻辑；FAILED/LOST 路径的代码路径完全对称，风险可控。

**建议**: 后续 phase 补充 FAILED/LOST 路径测试即可，不阻塞 P3-S3 merge。

#### O-2: cancel_predispatch_starting 未测试 dispatch 非 pending 状态的 INVALID_STATE 路径

**severity**: info

`cancel_predispatch_starting_in_transaction` 在 dispatch status 不是 `PENDING` 时返回 `INVALID_STATE`（run_transition.py:714），但测试未覆盖此分支。

**分析**: 该分支的 guard 逻辑是简单的 `dispatch_record.status != DispatchRecordStatus.PENDING` 检查，属于 §22 "dispatch 已进入 dispatching 或 Attempt 已 RUNNING 时走 RUN_CANCELLING 路径" 的边界。P3-S3 只负责 pre-dispatch cancel；dispatching/active 路径由后续 phase 实现。

**建议**: 后续 phase 实现 `cancel_dispatching_running_in_transaction` 时一并补充。

#### O-3: promote_queued_run 在 CAS 失败时已 append 的 EventLog 事件会被 rollback

**severity**: info (by design)

`promote_queued_run_in_transaction` 在 `promote_queued_run_row` CAS 失败时（run_transition.py:511-518），已 append 的 `RUN_STARTED` event 会随 transaction rollback 消失。

**分析**: 这是 by design 的行为——所有 helper 都接收调用方的 `HostTransaction`，在同一事务内完成 event append + state update。CAS 失败时调用方应 rollback 事务，不会留下脏事件。如果调用方不 rollback 而直接 commit，会留下一个无对应 Run 状态变更的孤立 `RUN_STARTED` event。但这是调用方的责任，不是 P3-S3 helper 的问题。

**确认**: rollback 测试 `test_rollback_prevents_partial_event_and_state_persistence` 已验证事务回滚不会留下痕迹。

## Review Area Summary

### 1. Scope Compliance (严格限于 P3-S3)

**结论**: PASS

- `run_transition.py` 只实现 6 个 public helper：`create_queued_run_in_transaction`、`create_running_run_with_starting_attempt_in_transaction`、`promote_queued_run_in_transaction`、`terminal_closeout_in_transaction`、`cancel_queued_in_transaction`、`cancel_predispatch_starting_in_transaction`
- 未触碰 admission orchestration、queue scanning、Engine dispatch、WorkerProxy/LocalProxy/RemoteProxy、`ATTEMPT_RUNNING`、public facade
- 所有 helper 接收调用方 `HostTransaction`，不自行开启事务，不注册 after-commit callback
- 实现 artifact 声明的 non-goals 与代码一致

### 2. Transaction Atomicity (EventLog append 与 state row 同事务)

**结论**: PASS

- 所有 6 个 helper 使用同一个 `transaction` 参数完成 EventLog append 和 state row insert/update
- `test_rollback_prevents_partial_event_and_state_persistence` 验证 rollback 后无 Run row、无 RUN_ACCEPTED event 残留
- `cancel_predispatch_starting_in_transaction` 的 3 步 CAS（dispatch → attempt → run）在同一事务内，任一步失败全部回滚

### 3. Plan / Design §9.1 / §22 Compliance

**结论**: PASS

| helper | plan 要求 | §9.1/§22 要求 | 实现 |
|--------|----------|--------------|------|
| create_queued_run | append RUN_ACCEPTED + RUN_QUEUED，创建 QUEUED Run，无 Attempt/dispatch | §22: "QUEUED 且尚未创建 Attempt 的 Run 被取消时直接进入 CANCELLED" | 一致 |
| create_running_run | append RUN_ACCEPTED + RUN_STARTED + ATTEMPT_STARTED，创建 RUNNING Run + STARTING Attempt + pending dispatch | §9.1: direct start path | 一致 |
| promote_queued_run | 按 accepted_event_sequence 读最早 queued，CAS QUEUED→RUNNING，创建 STARTING Attempt + pending dispatch | §9.1: queue promotion | 一致 |
| terminal_closeout | 同事务写 Attempt terminal event + Run terminal event + Attempt terminal row + Run terminal row | §22: "terminal fact 已提交后 cancel 不能改写 terminal" | 一致 |
| cancel_queued | 写 CANCEL_REQUESTED + RUN_CANCELLED，CAS QUEUED→CANCELLED，无 Attempt | §22: "QUEUED → CANCELLED，不创建 Attempt" | 一致 |
| cancel_predispatch_starting | 写 CANCEL_REQUESTED + ATTEMPT_CANCELLED + RUN_CANCELLED，CAS dispatch/attempt/run → cancelled | §22: "STARTING + pending dispatch → direct close" | 一致 |

### 4. CAS Classification

**结论**: PASS

- `StateMutationStatus` 区分 `UPDATED`、`CAS_LOST`、`NOT_FOUND`、`INVALID_STATE`
- `_run_mutation_result` / `_attempt_mutation_result` 分类逻辑：rowcount=1 → UPDATED；row 不存在 → NOT_FOUND；row 仍在期望源状态且 `cas_lost_when_expected=True` → CAS_LOST；否则 → INVALID_STATE
- `promote_queued_run_row` 使用 NOT EXISTS 子查询保证 active Run 存在时 CAS 失败，返回 CAS_LOST
- `cancel_running_run_row` 使用 `current_attempt_id` 条件防止误取消已切换 Attempt 的 Run
- 所有 CAS 失败路径不会写脏 EventLog 事件（事件 append 发生在 precondition check 之后，CAS 之前；CAS 失败时事务应由调用方 rollback）

### 5. Terminal Event Types

**结论**: PASS

- 使用具体 event type：`ATTEMPT_SUCCEEDED`、`ATTEMPT_FAILED`、`ATTEMPT_LOST`、`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_LOST`
- 未使用 `RUN_TERMINAL` 等泛化类型
- `_attempt_terminal_event_type` / `_run_terminal_event_type` 在 validation 阶段即验证 status 枚举合法性
- `_validate_terminal_input` 通过调用映射函数间接验证 terminal status

### 6. Active Run Partial Index & Queue FIFO

**结论**: PASS

- `promote_queued_run_row` 的 WHERE 子句包含 `NOT EXISTS (SELECT 1 FROM host_runs active_run WHERE active_run.session_id = ? AND active_run.run_id <> ? AND active_run.status IN ('running', 'waiting', 'cancelling', 'recovering'))`，与 partial unique index `idx_host_runs_one_active_per_session` 语义一致
- `read_earliest_queued_run` 按 `accepted_event_sequence ASC` 排序，保证 FIFO
- 低层 helper 不会破坏这两个不变量

### 7. Typing, Docstrings, Over-design

**结论**: PASS

- 所有输入通过 frozen dataclass + slots 定义，字段类型明确
- 所有 public 函数与 private helper 均有中文 docstring，包含 `:param`、`:returns`、`:raises`
- 无 `object`、`Any`、无类型参数
- 无 God helper：每个 helper 职责单一，validator 分层（common + specific）
- `_attempt_terminal_event_type` / `_run_terminal_event_type` 是简单映射，非过度抽象

### 8. Test Coverage

**结论**: PASS (8 tests, 覆盖核心成功/失败路径)

| test | 路径 | 类型 |
|------|------|------|
| test_create_running_run_creates_attempt_and_pending_dispatch | running 创建 | success |
| test_create_queued_run_creates_no_attempt_or_dispatch | queued 创建 | success |
| test_promote_queued_run_uses_earliest_accepted_sequence | FIFO promotion | success |
| test_terminal_closeout_appends_concrete_terminal_events | terminal closeout + 具体事件类型 | success |
| test_promote_cas_loser_keeps_queued_state | CAS_LOST (active run 存在) | failure |
| test_cancel_predispatch_starting_updates_dispatch_attempt_and_run | pre-dispatch cancel 3 步 CAS | success |
| test_cancel_queued_terminal_run_returns_invalid_state | terminal Run 不能被 cancel | failure |
| test_rollback_prevents_partial_event_and_state_persistence | rollback 原子性 | failure |

**未覆盖但可接受的路径** (info, 不阻塞):
- terminal closeout 的 FAILED/LOST 终态 (O-1)
- cancel_predispatch_starting 的 dispatch 非 pending 状态 (O-2)
- WAITING Run 的 terminal closeout

## Validation Results

```bash
# pytest
$ source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q
17 passed in 0.38s

# pyright
$ source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations
```

## Decision

**APPROVED**。P3-S3 实现严格符合 plan、design §9.1/§22 要求，CAS 分类正确，事务原子性有保障，具体终态事件类型使用正确，index/FIFO 不变量未被破坏。3 个 info 级 observation 不阻塞 merge，建议后续 phase 补充。
