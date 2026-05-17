# P9.5 S4 Host Durable Helper API Tightening — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S4 Host Durable Helper API Tightening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S4.
- Implementation artifact: `docs/reviews/p9-5-s4-host-durable-helper-tightening-implementation-20260517.md`.
- Reviewed files: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/dispatch.py`, `tests/host/test_run_attempt_transitions.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_public_cancel_session_runs.py`, `tests/host/test_phase6_toolruntime_integration.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_run_input_builder.py`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. mark_dispatching_after_lane_row 是否确实收窄为 production WAITING_FOR_LANE -> DISPATCHING，且前置覆盖 run/attempt/dispatch/execution/owner/lane/cancel/worker refs

**结论：通过。**

**SQL 收窄验证**（`state.py:3158-3198`）：
- `WHERE status = ?` 绑定 `WAITING_FOR_LANE`（原为 `IN (PENDING, WAITING_FOR_LANE)`）。
- 新增 `AND owner_host_instance_id = ?`、`AND waiting_for_lane_at IS NOT NULL`、`AND lane_name = ?`。
- 新增 `AND worker_accepted_at IS NULL`、`AND worker_accept_event_sequence IS NULL`、`AND cancelled_event_sequence IS NULL`。
- 移除 `COALESCE(waiting_for_lane_at, ?)` — 不再为 PENDING 行补齐 waiting timestamp。

**Python 前置检查验证**（`_invalid_dispatching_after_lane_precondition`，`state.py:4147-4213`）：
- 读取 dispatch record / attempt / run 三行做完整状态校验。
- 校验项：`dispatch_record.status == WAITING_FOR_LANE`、`owner_host_instance_id` 匹配、`waiting_for_lane_at IS NOT NULL`、`lane_name` 匹配、`run.status == RUNNING`、`run.current_attempt_id == attempt_id`、`attempt.status == STARTING`、`execution_id` 一致、`run_id`/`attempt_id` 交叉一致、`lane_claim_id/lane_owner_id/lane_acquired_at/dispatching_at` 全部 `IS NULL`、`worker_accepted_at/worker_accept_event_id/worker_accept_event_sequence` 全部 `IS NULL`、`cancelled_event_id/cancelled_event_sequence` 全部 `IS NULL`。
- 前置失败返回 `INVALID_STATE`（非 `NOT_FOUND`），dispatch record 行保持不变。

**调度器 recheck 验证**（`dispatch.py:1205-1237`）：
- `_is_dispatchable_recheck` 现在要求 `dispatch_record.status == WAITING_FOR_LANE`（原为 `IN (PENDING, WAITING_FOR_LANE)`）。
- 新增 `dispatch_record.owner_host_instance_id is not None`、`waiting_for_lane_at is not None`、`lane_name is not None`。

**调度器流程验证**（`dispatch.py:511-549`）：
- `_dispatch_one` 先调用 `_mark_waiting_for_lane(record)` → 再 acquire lane → 再调用 `_mark_dispatching_after_recheck(record, token)`。
- 流程为 `PENDING → WAITING_FOR_LANE → DISPATCHING`，无 bypass 路径。

**测试验证**：
- `test_dispatching_rejects_pending_direct_lane_bypass`：PENDING dispatch 直接调用 `mark_dispatching_after_lane_row` → `INVALID_STATE`，dispatch 保持 PENDING。
- `test_pending_dispatch_recheck_without_waiting_is_skipped`：scheduler recheck 时 dispatch 未进入 `WAITING_FOR_LANE` → `None`（skip）。
- `test_dispatching_after_recheck_requires_waiting_for_lane`：先进入 `WAITING_FOR_LANE` 再 dispatching → 成功。

### 2. accept_worker_running_in_transaction 是否 fail-closed 且 ATTEMPT_RUNNING payload 补齐诊断但不变 public contract

**结论：通过。**

**fail-closed 验证**（`run_transition.py:3278-3306`）：
- `_invalid_accept_worker_precondition` 校验完整链：`run.status == RUNNING`、`run.current_attempt_id == attempt_id`、`attempt.status == STARTING`、`attempt.execution_id == dispatch_record.execution_id`、`dispatch_record.run_id == run.run_id`、`dispatch_record.attempt_id == attempt.attempt_id`、`dispatch_record.status == DISPATCHING`、`owner_host_instance_id/waiting_for_lane_at/lane_name/lane_claim_id/lane_owner_id/lane_acquired_at/dispatching_at` 全部 `IS NOT NULL`、`worker_accepted_at/worker_accept_event_id/worker_accept_event_sequence` 全部 `IS NULL`、`cancelled_event_id/cancelled_event_sequence` 全部 `IS NULL`。
- 任一前置失败 → `INVALID_STATE`，不写 EventLog、不更新 dispatch record、不推进 Attempt。

**ATTEMPT_RUNNING payload 补齐验证**（`run_transition.py:2291-2302`）：
- 新增 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id` 四个诊断字段。
- 这些是 EventLog payload 内部字段，不影响 public facade（`RunSnapshot`、`HostApiError` 等）。

**AcceptWorkerRunningInput 变更验证**（`run_transition.py:380-400`）：
- 新增 `local_worker_id: str | None = None`，默认 `None`，向后兼容。
- `_validate_accept_worker_running_input` 增加 `_require_optional_non_empty_text` 校验。
- 非本地或旧白盒调用可为 `None`，生产 scheduler 路径已补齐。

**测试验证**：
- `test_dispatch_record_waiting_dispatching_and_worker_accept_refs`：验证 `ATTEMPT_RUNNING` payload 包含 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id`。
- `test_active_cancel_appends_run_cancelling_once`：补齐 `local_worker_id`。
- `test_phase6_toolruntime_integration`、`test_toolruntime_accept_barrier`、`test_resolve_wait_command`、`test_public_cancel_session_runs`：补齐 `local_worker_id`。

### 3. dispatch scheduler recheck 是否不再依赖 pending direct path

**结论：通过。**

- `_is_dispatchable_recheck`（`dispatch.py:1229`）：`dispatch_record.status == DispatchRecordStatus.WAITING_FOR_LANE`（移除 `PENDING`）。
- `_mark_dispatching_after_recheck`（`dispatch.py:627-654`）：先 `_is_dispatchable_recheck` 再 `mark_dispatching_after_lane_row`。
- `_mark_waiting_for_lane`（`dispatch.py:587-615`）：PENDING → WAITING_FOR_LANE 的唯一入口。
- `_dispatch_one`（`dispatch.py:511-549`）：先 `_mark_waiting_for_lane` → acquire lane → `_mark_dispatching_after_recheck`。
- `test_pending_dispatch_recheck_without_waiting_is_skipped`：验证未 waiting 时 recheck 返回 `None`。

### 4. test_run_input_builder 等白盒 fixture 是否迁移为 production-like 状态而不是绕过 schema/helper

**结论：通过。**

- `test_run_input_builder._seed_current_run`（`test_run_input_builder.py:1661-1673`）：新增 `mark_dispatch_waiting_for_lane_row` 调用，使 dispatch record 先进入 `WAITING_FOR_LANE` 再调用 `mark_dispatching_after_lane_row`。
- `test_run_input_builder._force_dispatch_snapshot_state`（`test_run_input_builder.py:1790-1840`）：
  - `PENDING` 分支：显式清空所有诊断字段（`owner_host_instance_id=NULL, waiting_for_lane_at=NULL, ...`）。
  - `WAITING_FOR_LANE` 分支：显式设置 `owner_host_instance_id`、`waiting_for_lane_at`、`lane_name`，清空 claim/owner/acquired/dispatching/worker/cancel 字段。
  - 其它状态分支：显式设置全部 `WAITING_FOR_LANE` + `DISPATCHING` 诊断字段。
- `test_run_attempt_transitions._mark_waiting_tx`：调用 production `mark_dispatch_waiting_for_lane_row`。
- `test_run_attempt_transitions._mark_dispatching_tx`：先调用 `_mark_waiting_tx` 再调用 production `mark_dispatching_after_lane_row`。
- 所有 fixture 使用 production helper 而非 raw SQL bypass。

### 5. 是否违反 docs/host/design.md、S4 plan、AGENTS 硬约束

**结论：通过。无硬约束违反。**

| 约束 | 验证 |
|---|---|
| 不新增状态 | ✅ 只收紧前置检查，不添加 `DispatchRecordStatus` 或 `AttemptStatus` |
| 不新增 schema | ✅ 无 DDL 变更 |
| 不新增 public facade | ✅ `AcceptWorkerRunningInput.local_worker_id` 是内部字段 |
| 不暴露 helper | ✅ `mark_dispatching_after_lane_row` / `accept_worker_running_in_transaction` 保持内部 |
| 不加兼容 wrapper | ✅ 无新 wrapper |
| 不引入 RECOVERING / Phase 11 | ✅ |
| 不引入 `Any`/`object`/无类型签名 | ✅ |
| 函数有完整中文 docstring | ✅ |
| 不破坏 Host 分层 | ✅ |

## Findings

### F1 [Info] Python 前置检查与 SQL WHERE 双重校验

- **File/line**: `state.py:4147-4213`（`_invalid_dispatching_after_lane_precondition`）+ `state.py:3158-3198`（SQL UPDATE WHERE）
- **Evidence**: Python 前置读取 dispatch/attempt/run 三行做完整状态校验；SQL UPDATE WHERE 子句重复 `status`、`owner_host_instance_id`、`waiting_for_lane_at`、`lane_name`、各 `IS NULL` 检查。两者在同一 SQLite 事务内，Python 校验先执行。
- **Impact**: 防御性纵深。Python 层提供 fail-fast 结构化错误返回（`INVALID_STATE` + row）；SQL WHERE 保证原子 CAS。标准 CAS 模式，非冗余。
- **Blocking**: No.

### F2 [Info] `_is_dispatchable_recheck` 与 `_invalid_dispatching_after_lane_precondition` 校验范围重叠

- **File/line**: `dispatch.py:1205-1237` vs `state.py:4147-4213`
- **Evidence**: `dispatch.py` 的 `_is_dispatchable_recheck` 在调用 `mark_dispatching_after_lane_row` 前做了 run/attempt/dispatch 状态检查；`state.py` 的 `_invalid_dispatching_after_lane_precondition` 在 SQL UPDATE 前做了更完整的同类检查。
- **Impact**: 调度器 recheck 是快速路径过滤（避免不必要的 write transaction）；state.py 前置是 transaction 内 fail-closed 保障。两层职责不同，非重复。
- **Blocking**: No.

### F3 [Info] `AcceptWorkerRunningInput.local_worker_id` 默认 `None` 允许旧调用方不传

- **File/line**: `run_transition.py:400`
- **Evidence**: `local_worker_id: str | None = None`。旧白盒测试或非本地 worker 路径可不传。生产 scheduler 路径已补齐（`dispatch.py` 中 `_start_worker` 构造 `AcceptWorkerRunningInput` 时传入 `local_worker_id`）。
- **Impact**: 向后兼容，非本地 worker 路径 `local_worker_id` 为 `None` 时 payload 该字段也为 `None`。实现 artifact 已记录此残余风险。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`state.py`、`run_transition.py`、`dispatch.py`、9 个测试文件。
- 未修改 public facade（`api.py`、`command.py`、`read_api.py`）。
- 未新增 status / schema / public error code。
- 未引入兼容 wrapper / re-export。

### Confirmed: no prohibited semantics introduced

- No P10+ semantics (RECOVERING, ToolsDiscovery, etc.)
- No new state-machine states or transitions
- No compatibility re-export/wrapper
- No `Any`/`object`/untyped signatures
- No extra payload bag

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| New state-machine states | Not introduced |
| Schema changes | Not introduced |
| Public facade changes | Not introduced |
| RECOVERING / Phase 11 | Not introduced |
| Compatibility wrapper | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |
| Extra payload bag | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 3 (F1–F3)

S4 实现正确达成计划目标：`mark_dispatching_after_lane_row` 收窄为 `WAITING_FOR_LANE → DISPATCHING`，前置覆盖 run/attempt/dispatch/execution/owner/lane/cancel/worker refs；`accept_worker_running_in_transaction` fail-closed 且 ATTEMPT_RUNNING payload 补齐诊断字段；dispatch scheduler recheck 不再依赖 pending direct path；白盒 fixture 迁移为 production-like 状态。无硬约束违反。
