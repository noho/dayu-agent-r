# Gateflow Re-Review: Host P3-S3 Run / Attempt Transition Primitives — P3S3-C-001 Fix

- **gate**: code re-review
- **reviewer**: AgentMiMo
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S3 Run / Attempt Transition Primitives
- **re-review scope**: P3S3-C-001 fix only
- **review date**: 2026-05-14
- **baseline artifacts**:
  - `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`
  - `docs/reviews/gateflow-fix-host-p3-s3-run-attempt-transitions-20260514.md`
- **reviewed files**:
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_run_attempt_transitions.py`
  - `dayu/host/durable/state.py`（确认低层 CAS helper 结构未变）
- **status**: P3S3-C-001 fixed, no new blocking findings

## P3S3-C-001 Fix Verification

### Finding Description

EventLog 是 Host canonical fact truth。原实现允许 transition helper 在 append `RUN_STARTED` / terminal / cancel events 后，若后续 state mutation 返回 `CAS_LOST` / `NOT_FOUND` / `INVALID_STATE`，将 failure result 返回调用方，调用方可正常 commit，留下无对应 state migration 的孤立 EventLog fact。

### Fix Mechanism

引入三个类型安全的 `_require_*_mutation_updated` 断言 helper（`run_transition.py:791-846`），在 append canonical EventLog 后、每一步 state mutation 返回时立即检查：

- `_require_run_mutation_updated` — 断言 `RunMutationResult.status == UPDATED`
- `_require_attempt_mutation_updated` — 断言 `AttemptMutationResult.status == UPDATED`
- `_require_dispatch_record_mutation_updated` — 断言 `DispatchRecordMutationResult.status == UPDATED`

非 `UPDATED` 时调用 `_raise_after_event_append_mutation_failure`（`run_transition.py:848-861`）抛出 `HostDurableError`，由 `HostTransactionRunner.run_write` 自动 rollback 整个 SQLite write transaction。

### Path-by-Path Verification

#### 1. `promote_queued_run_in_transaction` (run_transition.py:469-548)

| 路径 | 行为 | 结论 |
|------|------|------|
| active Run 存在 (line 484) | 返回 `INVALID_STATE` + skip reason，**不 append EventLog** | PASS |
| 无 queued Run (line 492) | 返回 `NOT_FOUND` + skip reason，**不 append EventLog** | PASS |
| append `RUN_STARTED` 后 promotion CAS 非 UPDATED (line 514) | `_require_run_mutation_updated` 抛 `HostDurableError`，事务 rollback | PASS |
| append `ATTEMPT_STARTED` 后 (line 519-539) | `insert_attempt` / `insert_dispatch_record` 是 INSERT 不会 CAS 失败；若底层抛异常，事务 rollback | PASS |

#### 2. `terminal_closeout_in_transaction` (run_transition.py:551-613)

| 路径 | 行为 | 结论 |
|------|------|------|
| Run / Attempt 不存在或状态不匹配 (line 569) | 返回 `NOT_FOUND` / `INVALID_STATE`，**不 append EventLog** | PASS |
| append terminal events 后 Attempt CAS 非 UPDATED (line 589) | `_require_attempt_mutation_updated` 抛 `HostDurableError` | PASS |
| Attempt CAS OK 但 Run CAS 非 UPDATED (line 602) | `_require_run_mutation_updated` 抛 `HostDurableError` | PASS |

#### 3. `cancel_queued_in_transaction` (run_transition.py:616-675)

| 路径 | 行为 | 结论 |
|------|------|------|
| Run 不存在 (line 632) | 返回 `NOT_FOUND`，**不 append EventLog** | PASS |
| Run 非 QUEUED (line 639) | 返回 `INVALID_STATE`，**不 append EventLog** | PASS |
| append cancel events 后 Run CAS 非 UPDATED (line 666) | `_require_run_mutation_updated` 抛 `HostDurableError` | PASS |

#### 4. `cancel_predispatch_starting_in_transaction` (run_transition.py:678-788)

| 路径 | 行为 | 结论 |
|------|------|------|
| Run 不存在 (line 693) | 返回 `NOT_FOUND`，**不 append EventLog** | PASS |
| Run 非 RUNNING 或无 current_attempt_id (line 701) | 返回 `INVALID_STATE`，**不 append EventLog** | PASS |
| Attempt / dispatch 前置不满足 (line 712) | 返回 `INVALID_STATE`，**不 append EventLog** | PASS |
| append 3 个 cancel events 后 dispatch CAS 非 UPDATED (line 756) | `_require_dispatch_record_mutation_updated` 抛 `HostDurableError` | PASS |
| dispatch OK 但 Attempt CAS 非 UPDATED (line 767) | `_require_attempt_mutation_updated` 抛 `HostDurableError` | PASS |
| Attempt OK 但 Run CAS 非 UPDATED (line 779) | `_require_run_mutation_updated` 抛 `HostDurableError` | PASS |

### Invariant Summary

修复后代码满足 P3S3-C-001 的两个必要条件：

1. **skip / not_found / invalid_state 前置失败不会 append 新 EventLog** — 所有前置判断均在 `event_log_store.append_event()` 调用之前完成。
2. **append 后 mutation 非 UPDATED 会 rollback** — 三个 `_require_*_mutation_updated` helper 确保 `HostDurableError` 被抛出，`HostTransactionRunner.run_write` 的 `except` 分支执行 `rollback()`。

## Test Verification

### `test_promote_cas_loser_keeps_queued_state` (test_run_attempt_transitions.py:391-499)

- **修复前**: monkeypatch 令 `promote_queued_run_row` 返回 `CAS_LOST` 后，测试正常返回并 commit，留下孤立 `RUN_STARTED` event。
- **修复后**: 测试改为 `with pytest.raises(HostDurableError)` 捕获异常，随后验证 queued Run 状态仍为 `QUEUED` 且 queued Run 的 `RUN_STARTED` event 数为 0。事务 rollback 生效。

### `test_promote_active_run_skip_does_not_append_queued_started_event` (test_run_attempt_transitions.py:502-580)

- **新增测试**: 在 active Run 存在时调用 `promote_queued_run_in_transaction`，断言返回 `INVALID_STATE` + `active_run_exists`，queued Run 状态保持 `QUEUED`，queued Run 的 `RUN_STARTED` event 数为 0。验证 skip 路径不 append EventLog。

### 测试覆盖矩阵

| 测试 | 覆盖路径 | P3S3-C-001 修复相关 |
|------|---------|-------------------|
| test_create_running_run_creates_attempt_and_pending_dispatch | running 创建 happy path | 否 |
| test_create_queued_run_creates_no_attempt_or_dispatch | queued 创建 happy path | 否 |
| test_promote_queued_run_uses_earliest_accepted_sequence | FIFO promotion happy path | 否 |
| test_terminal_closeout_appends_concrete_terminal_events | terminal closeout happy path | 否 |
| test_promote_cas_loser_keeps_queued_state | CAS_LOST → rollback | **是** |
| test_promote_active_run_skip_does_not_append_queued_started_event | active skip → no append | **是** |
| test_cancel_predispatch_starting_updates_dispatch_attempt_and_run | pre-dispatch cancel happy path | 否 |
| test_cancel_queued_terminal_run_returns_invalid_state | terminal Run 不能被 cancel | 否 |
| test_rollback_prevents_partial_event_and_state_persistence | 事务 rollback 原子性 | 间接验证 |

## Scope Creep Check

| 检查项 | 结论 |
|--------|------|
| 未引入 admission orchestration / queue scanning | PASS |
| 未引入 Engine dispatch / WorkerProxy / scheduler / lane | PASS |
| 未引入 savepoint / 通用事务框架 | PASS |
| 未引入 public facade / after-commit callback | PASS |
| 低层 `state.py` CAS helper 保持结构化 mutation result，未被修改 | PASS |
| 修复范围严格限于 `run_transition.py` 的 4 个 transition helper + 内部断言 | PASS |

## New Findings

### 无新 blocking findings

### Observations (non-blocking)

#### O-1: `terminal_closeout` 和 `cancel_predispatch_starting` 的 append 后 CAS 失败路径未被测试直接覆盖

**severity**: info

`test_promote_cas_loser_keeps_queued_state` 验证了 `promote_queued_run_in_transaction` 的 append 后 CAS 失败 → `HostDurableError` 路径。但 `terminal_closeout_in_transaction`、`cancel_queued_in_transaction`、`cancel_predispatch_starting_in_transaction` 的同类路径未被测试直接覆盖。

**分析**: 修复机制 `_require_*_mutation_updated` 是统一的断言 helper，对所有 4 个 transition helper 使用完全相同的 `HostDurableError` 抛出模式。promotion 路径的测试已验证该机制有效；其余路径的代码对称性高，风险可控。后续 phase 可按需补充。

**建议**: 不阻塞 P3-S3 acceptance；后续 phase 实现 terminal closeout / cancel 的更高层集成测试时可一并覆盖。

#### O-2: O-1/O-2/O-3 原始 observation 状态不变

**severity**: info

原 MiMo review 的 O-1（FAILED/LOST terminal 路径）、O-2（dispatch 非 pending 状态）仍为 deferred。O-3 已被 P3S3-C-001 吸收——修复后 O-3 描述的 "CAS 失败时已 append 的 EventLog 随 rollback 消失" 行为不再是隐式 contract，而是显式编码的 `HostDurableError` + rollback。

## Validation Results

```bash
# pytest
$ source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q
18 passed in 0.38s

# pyright
$ source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

# git diff --check
$ git diff --check
(no output — passed)
```

## Decision

**P3S3-C-001: fixed**。修复正确实现了 "append 前完成所有前置判断 + append 后 mutation 非 UPDATED 抛 `HostDurableError`" 的双重保障。测试覆盖了 CAS 失败 rollback 和 active skip 不 append 两个关键路径。未引入 scope creep。无新 blocking findings。
