# WU-SEMANTIC-OWNERSHIP-01 P3-A S2 implementation review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S2 - Migrate terminal status/event consumers
- Agent: AgentMiMo
- Base commit: `b9e318a0`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-controller-validation.md`
- Changed files:
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/admission.py`
  - `dayu/host/durable/read_model.py`
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/purge.py`
  - `tests/host/test_run_attempt_transitions.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_public_run_api.py`
  - `tests/host/test_state_schema.py`

## Verdict

pass

## Findings

未发现实质性问题。

## Required Checks Verification

### 1. Producer terminal event type string duplicates removed

**Status: verified**

`run_transition.py` 和 `engine_ingest.py` 中原有的 8 个 terminal 常量已删除：

- `_EVENT_TYPE_ATTEMPT_SUCCEEDED` / `_EVENT_TYPE_RUN_SUCCEEDED`
- `_EVENT_TYPE_ATTEMPT_FAILED` / `_EVENT_TYPE_RUN_FAILED`
- `_EVENT_TYPE_ATTEMPT_CANCELLED` / `_EVENT_TYPE_RUN_CANCELLED`
- `_EVENT_TYPE_ATTEMPT_LOST` / `_EVENT_TYPE_RUN_LOST`

Producer scan 确认无残留：

```text
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED/LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
<no output>
```

全量 scan 中剩余匹配均为下游 projection / memory consumers（`outbox.py`、`memory.py`、`compact_material.py`、`run_input.py`、`durable/memory.py`），不在 S2 scope，作为 residual 记录。

### 2. Closeout Attempt subset excludes SUSPENDED/STEERED with fail-fast

**Status: verified**

- `lifecycle_events.CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` 只包含 `SUCCEEDED / FAILED / CANCELLED / LOST`（`lifecycle_events.py:69-75`）。
- `closeout_attempt_terminal_event_type_for_status` 对 `SUSPENDED / STEERED` 抛出 `ValueError`（`lifecycle_events.py:215-232`）。
- `run_transition._attempt_terminal_event_type` 和 `engine_ingest._closeout_attempt_event_type` 都委托给 `closeout_attempt_terminal_event_type_for_status`，保留 fail-fast 行为。
- 测试 `test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner`（`test_run_attempt_transitions.py:417-455`）显式验证 `SUSPENDED / STEERED` 不进入 `_TERMINAL_STATUS_PAIRS` 且 `_terminal_status_pair_is_compatible` 返回 `False`。

### 3. _TERMINAL_STATUS_PAIRS derivation is deterministic and semantically correct

**Status: verified**

`_derive_terminal_status_pairs()`（`run_transition.py:5553-5582`）的派生逻辑：

1. 遍历所有 `AttemptStatus` 成员
2. 跳过非终态（`not in TERMINAL_ATTEMPT_STATUSES`）
3. 跳过非 closeout-supported（`_attempt_terminal_event_type` 抛 `ValueError`，排除 `SUSPENDED / STEERED`）
4. 查找同名 `RunStatus`（`RunStatus(attempt_status.value)`）
5. 验证 RunStatus 是 terminal（`in TERMINAL_RUN_STATUSES`）
6. 验证 RunStatus event type 可派生（`_run_terminal_event_type` 不抛异常）

结果：`(SUCCEEDED, SUCCEEDED)`、`(FAILED, FAILED)`、`(CANCELLED, CANCELLED)`、`(LOST, LOST)`。

派生失败时 `raise RuntimeError`，模块加载时立即 fail-fast，不会产生 silent incorrect state。

### 4. SQL status filter migration preserves behavior and query parameter order

**Status: verified**

`state.py` 三个 read helper 现在使用 `run_status_in_clause(...)`：

| Helper | 原来 | 现在 |
|--------|------|------|
| `read_active_run_for_session` | 手写 5 个 `ACCEPTED/RUNNING/WAITING/CANCELLING/RECOVERING` | `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` |
| `read_non_terminal_runs_for_session` | 手写 6 个 non-terminal | `run_status_in_clause(NON_TERMINAL_RUN_STATUSES)` |
| `read_non_terminal_runs` | 手写 6 个 non-terminal | `run_status_in_clause(NON_TERMINAL_RUN_STATUSES)` |

`run_status_in_clause` 对 frozenset 输入按 `RunStatus` 定义顺序输出，与原手写顺序一致。参数展开 `(session_id, *status_params)` / `status_params` 保持 session_id 在首位。

测试 `test_run_status_in_clause_matches_durable_read_queries`（`test_state_schema.py:258-423`）验证：
- Helper SQL 与 durable read helper 查询结果等价
- `EXPLAIN QUERY PLAN` 确认 planner 对三条查询形状都返回行（索引可用）

### 5. Tests cover migrated owner boundaries

**Status: verified**

新增/更新测试：

- `test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner`：验证 `_TERMINAL_STATUS_PAIRS` 由 lifecycle owner 派生，`SUSPENDED / STEERED` 不进入 closeout。
- `test_terminal_plans_use_lifecycle_event_owner_helpers`：验证 `_final_answer_plan`、`_run_failed_plan`、`_lost_lifecycle_plan` 的 event type 来自 lifecycle helper。
- `test_run_status_in_clause_matches_durable_read_queries`：验证 SQL helper 与 durable read helper 等价。
- `test_public_run_api.py`：移除本地 `_TERMINAL_RUN_STATUSES`，改用 `state.TERMINAL_RUN_STATUSES`。
- Error message 更新：`"unsupported Attempt terminal status"` → `"unsupported closeout Attempt terminal status"`。

Focused tests: `203 passed in 1.72s`。

### 6. Import cycle validation

**Status: verified**

```text
python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok
```

Import graph符合 plan 设计：
- `lifecycle_events` → `api`（单向）
- `durable.state` → `api` + `_row_rules`（单向）
- `run_transition` → `lifecycle_events` + `durable.state`（允许）
- `engine_ingest` → `lifecycle_events` + `durable.state`（允许）

### 7. Pyright

**Status: verified**

```text
pyright: 0 errors, 0 warnings, 0 informations
```

## S3 Residuals Correctly Scoped

以下代码未被 S2 修改，作为 S3 scope 正确保留：

- `_close_worker_lifecycle`（`engine_ingest.py:2424`）：仍构造 `EngineEvent(type=EngineEventType.RUN_FAILED)`，S3 改为 Host lifecycle candidate。
- `_late_rejection_reason`（`engine_ingest.py:3312`）：仍使用 `terminal_event_id is not None` 判断 terminal closed，S3 改用 `state.is_terminal_run_status`。
- Active cancel routing（`engine_ingest.py:3327-3332`）：仍使用 `candidate.engine_event.type` 判断 cancel late terminal，S3 扩展为 decision table。
- Dispatch pre-worker direct cancel predicate：S3 scope。

## Open Questions

无。

## Residual Risk

- 下游 projection / memory consumers（`outbox.py`、`memory.py`、`compact_material.py`、`run_input.py`、`durable/memory.py`）仍各自定义 terminal event string 常量。这些不在 S2 producer boundary 内，但未来 EventLog / projection source-of-truth hardening 应收敛。
- 非 terminal EventLog 常量（`RUN_ACCEPTED`、`RUN_QUEUED` 等）仍在 `run_transition.py` 和 `engine_ingest.py` 中保留，作为 P3-J / future EventLog schema hardening 输入。

## Completion Report

- status: completed
- artifact: docs/reviews/wu-semantic-ownership-01-p3-a-s2-code-review-mimo.md
- verdict: pass
- blocking findings count: 0
- nonblocking findings count: 0
- blockers: none
