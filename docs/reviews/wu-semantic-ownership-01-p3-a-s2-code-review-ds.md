# WU-SEMANTIC-OWNERSHIP-01 P3-A S2 code review - AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S2 — Migrate terminal status/event consumers to S1 lifecycle/state owner helpers
- Base commit: `b9e318a0` (S1 acceptance)
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

## Required Checks Verification

### 1. Producer terminal event type duplicates removed

**要求**: `run_transition.py` 与 `engine_ingest.py` 中不再有自行维护的 `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` 常量。

**验证**:

- `rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py` → **无输出**。
- `run_transition.py:99-109` 移除了全部 8 个 terminal event type 常量（`_EVENT_TYPE_ATTEMPT_CANCELLED`、`_EVENT_TYPE_RUN_CANCELLED`、`_EVENT_TYPE_ATTEMPT_SUCCEEDED`、`_EVENT_TYPE_ATTEMPT_FAILED`、`_EVENT_TYPE_ATTEMPT_LOST`、`_EVENT_TYPE_RUN_SUCCEEDED`、`_EVENT_TYPE_RUN_FAILED`、`_EVENT_TYPE_RUN_LOST`）。
- `engine_ingest.py:232-237` 移除了全部 8 个 terminal event type 常量。
- 替换为 `run_transition.py` 中 `_attempt_terminal_event_type(status).value` 和 `_run_terminal_event_type(status).value`，以及 `engine_ingest.py` 中 `_closeout_attempt_event_type(status).value` 和 `_run_terminal_event_type(status).value`，均委托到 `lifecycle_events.py` owner helper。
- `_EVENT_TYPE_ATTEMPT_SUSPENDED` 在 `engine_ingest.py` 中保留，属于 S3 scope 的 worker lifecycle synthetic event 路径，已明确记录为非目标。

**判决**: 通过。

### 2. Closeout Attempt subset 排除 SUSPENDED/STEERED

**要求**: closeout Attempt 子集不包含 `SUSPENDED` / `STEERED`，fail-fast 行为保留。

**验证**:

- `run_transition.py:_attempt_terminal_event_type` (`run_transition.py:5530-5539`) 委托到 `closeout_attempt_terminal_event_type_for_status(status).value`。`closeout_attempt_terminal_event_type_for_status` 对 `SUSPENDED` / `STEERED` 抛出 `ValueError("unsupported closeout Attempt terminal status")`。
- `engine_ingest.py:_closeout_attempt_event_type` (`engine_ingest.py:4139-4147`) 同样委托到 `closeout_attempt_terminal_event_type_for_status`。
- `_derive_terminal_status_pairs` (`run_transition.py:5553-5582`) 在迭代 `AttemptStatus` 时通过 `try: _attempt_terminal_event_type(attempt_status) except ValueError: continue` 正确跳过 `SUSPENDED` / `STEERED`。
- 测试 `test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner` (`test_run_attempt_transitions.py:420-441`) 显式断言 `(SUSPENDED, SUCCEEDED)` 和 `(STEERED, SUCCEEDED)` 不被 `_terminal_status_pair_is_compatible` 接受。
- 测试 `test_terminal_closeout_accepts_attempt_running_in_phase5` (`test_run_attempt_transitions.py:816-819`) 的 parametrize 错误消息从 `"unsupported Attempt terminal status"` 更新为 `"unsupported closeout Attempt terminal status"`，与新 helper 的错误消息一致。

**判决**: 通过。

### 3. `_TERMINAL_STATUS_PAIRS` 派生确定性与语义正确性

**要求**: `_TERMINAL_STATUS_PAIRS` 的派生是确定性的且在语义上正确。

**验证**:

- `_derive_terminal_status_pairs` (`run_transition.py:5553-5582`) 的执行路径分析：
  1. 按 `AttemptStatus` 定义顺序迭代（Python `StrEnum` 迭代顺序确定：`STARTING → RUNNING → SUCCEEDED → FAILED → CANCELLED → SUSPENDED → STEERED → LOST`）。
  2. 过滤非终态：`STARTING` / `RUNNING` 被 `TERMINAL_ATTEMPT_STATUSES` 过滤。
  3. 过滤非 closeout：`SUSPENDED` / `STEERED` 被 `_attempt_terminal_event_type` 的 `ValueError` 捕获后跳过。
  4. 通过 `RunStatus(attempt_status.value)` 构造同名 Run 终态，并验证其为 `TERMINAL_RUN_STATUSES` 成员。
  5. 通过 `_run_terminal_event_type(run_status)` 验证 Run terminal event type 映射存在。
  6. 结果：`((SUCCEEDED, SUCCEEDED), (FAILED, FAILED), (CANCELLED, CANCELLED), (LOST, LOST))`，按 `AttemptStatus` 定义顺序排列。
- 确定性仅依赖 Python enum 迭代顺序和模块级常量，不受外部输入影响。
- 测试 `test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner` (`test_run_attempt_transitions.py:420-441`) 显式构建期望配对并逐项断言每个 status 的 event type 与 `lifecycle_events` owner helper 一致。

**潜在边界**: `_derive_terminal_status_pairs` 中的 `RunStatus(attempt_status.value)` 构造在遇到 closeout-supported Attempt 终态没有同名 Run 终态时会抛出 `RuntimeError`。当前所有 closeout-supported Attempt 终态（`SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST`）都有同名 Run 终态，不会触发。此 RuntimeError 是防御性编程，合理。

**判决**: 通过。

### 4. SQL status filter 迁移保留行为与参数顺序

**要求**: `state.py` 中 SQL status filter 迁移到 `run_status_in_clause` 后行为不变，查询参数顺序正确。

**验证**:

- `read_active_run_for_session` (`state.py:1636-1637`): 使用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。`START_BLOCKING_RUN_STATUSES` = `{ACCEPTED, RUNNING, WAITING, CANCELLING, RECOVERING}`。旧代码手动序列化相同 5 个状态。新代码生成 `IN (?, ?, ?, ?, ?)` + 相同 5 个参数。行为等价。
- `read_non_terminal_runs_for_session` (`state.py:1785-1786`): 使用 `run_status_in_clause(NON_TERMINAL_RUN_STATUSES)`。`NON_TERMINAL_RUN_STATUSES` = `{ACCEPTED, QUEUED, RUNNING, WAITING, CANCELLING, RECOVERING}`。旧代码手动序列化相同 6 个状态。新代码生成 `IN (?, ?, ?, ?, ?, ?)` + 相同 6 个参数。行为等价。
- `read_non_terminal_runs` (`state.py:1831-1832`): 同上，使用 `NON_TERMINAL_RUN_STATUSES`。
- `serialized_run_status_values` 对 frozenset 输入按 `RunStatus` 定义顺序输出，保证 SQL 参数顺序稳定。
- 测试 `test_run_status_in_clause_matches_durable_read_queries` (`test_state_schema.py:261-423`) 是本次新增的最重要测试：
  - 种子数据覆盖 accepted / queued / succeeded / running 四种 Run。
  - 对三个受影响的查询（active / session_non_terminal / all_non_terminal）分别执行 `EXPLAIN QUERY PLAN`，验证生成的 SQL 产生合法查询计划。
  - 直接用 helper 子句构建等效 SQL，将结果与 durable read helper 结果比较，断言一致。
  - 验证返回的 run_id 集合与预期匹配：session-sql-1 的 active = `run-sql-accepted`，non_terminal = `(run-sql-accepted, run-sql-queued)`，all non_terminal = 包含 session-sql-2 的 running run。

**判决**: 通过。

### 5. 测试覆盖 migrated owner boundaries

**验证迁移覆盖的测试**:

| 测试 | 验证内容 |
|------|---------|
| `test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner` | `_TERMINAL_STATUS_PAIRS` 派生 + `_attempt_terminal_event_type` / `_run_terminal_event_type` 委托 + SUSPENDED/STEERED 排除 |
| `test_terminal_plans_use_lifecycle_event_owner_helpers` | `_final_answer_plan` / `_run_failed_plan` / `_lost_lifecycle_plan` 的 event type 与 lifecycle owner helper 一致 |
| `test_run_status_in_clause_matches_durable_read_queries` | SQL clause 迁移的查询等价性与 EXPLAIN QUERY PLAN 验证 |
| `test_run_snapshot_mapping_covers_current_run_statuses` | `run_snapshot_from_row` 对 `TERMINAL_RUN_STATUSES`（owner 常量）的终态投影 |
| `test_terminal_closeout_accepts_attempt_running_in_phase5`（parametrize 更新） | SUSPENDED + SUCCEEDED 配对拒绝消息更新为 closeout helper 消息 |

**未覆盖但合理的边界**:
- `admission.py` 中 `is_terminal_run_status` 调用是谓词语义的一对一替换，旧 `_is_terminal_run_status` 与新 `is_terminal_run_status` 均检查 `status in {SUCCEEDED, FAILED, CANCELLED, LOST}`，语义完全等价。由现有 `CancelRunOperation` 事务测试间接覆盖。
- `read_model.py` 中 `is_terminal_run_status` 调用同样是谓词语义的一对一替换，由现有 `RunResult` write/read 测试覆盖。
- `purge.py` 中 `serialized_run_status_values` 调用生成与旧 `status.value for status in ...` 相同的 frozenset，由现有 purge 测试间接覆盖。

**判决**: 通过。关键 owner boundary 有聚焦测试覆盖；等词语义替换由现有测试矩阵保护。

## Adversarial Pass

### 新增 blocker 检查

- **无新增 blocker**。变更严格限制在 S2 allowed files 内，未触及 S3 scope（worker lifecycle synthetic `EngineEvent`、`_late_rejection_reason` nullable terminal refs、dispatch pre-worker direct cancel predicate）。
- Import cycle 验证通过：全部 S2 changed files 可同时 import 无循环。
- Pyright: 0 errors, 0 warnings。
- 203 个 focused tests 全部通过。

### Owner boundary drift 检查

- `run_transition.py` 和 `engine_ingest.py` 的 terminal event type 生成现在统一通过 `lifecycle_events` owner helper，不再各自维护裸字符串常量。这是正确的 owner boundary 收敛。
- `admission.py` 和 `read_model.py` 的 terminal Run status 判定现在使用 `state.is_terminal_run_status`，不再各自维护独立 tuple/set。正确。
- `state.py` 的 SQL status filter 现在使用 `run_status_in_clause` 从 `START_BLOCKING_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES` 派生，不再手工内联 placeholder 和参数。正确。
- `purge.py` 的 status value 序列化现在使用 `serialized_run_status_values`，不再用 `status.value for status in ...` 自行序列化。正确。
- 所有 migrated consumer 现在从同一 source-of-truth 派生语义：`_row_rules` → `state` constants/helpers → consumer → SQL/EventLog/read model/purge。

### 过度设计检查

- `run_transition.py` 和 `engine_ingest.py` 各自定义 `_run_terminal_event_type` 私有 helper 而非抽取共享模块，因为两者需要返回 `.value`（字符串）且处于不同 import 上下文。这不是过度设计，而是合理的模块内封装。
- `engine_ingest.py` 的 helper 命名为 `_closeout_attempt_event_type` 而非 `_attempt_terminal_event_type`（与 `run_transition.py` 不同），这是因为 engine_ingest.py 中存在 S3 scope 的非 closeout Attempt event（`ATTEMPT_SUSPENDED`），命名区分是有意的。
- `_derive_terminal_status_pairs` 是模块级函数调用，结果缓存为 `_TERMINAL_STATUS_PAIRS`。无工厂模式、无额外抽象层。

### 类型问题检查

- 所有新增/修改的函数签名包含完整类型标注。
- `run_status_in_clause` 返回 `tuple[str, tuple[str, ...]]`，调用方使用解包赋值，类型安全。
- `_derive_terminal_status_pairs` 返回 `tuple[tuple[AttemptStatus, RunStatus], ...]`，类型完整。

### 边界条件检查

- `_derive_terminal_status_pairs` 的 RuntimeError 防御：当 closeout-supported Attempt 终态没有同名 Run 终态或映射到非终态 Run status 时 fail-fast。当前不会触发，但保护未来 enum 变更时的语义一致性。
- `run_status_in_clause` 对空集合的 fail-fast 在 `state.py:597-599` 保留，不受本次迁移影响。
- SUSPENDED/STEERED 在 `_terminal_status_pair_is_compatible` 中返回 `False`，在 `_attempt_terminal_event_type` 中抛出 ValueError —— 两种 fail 模式互补，分别用于查询和构造路径。

### 下游 projection/memory 常量

- 终端扫描确认 `outbox.py`、`memory.py`、`compact_material.py`、`run_input.py`、`durable/memory.py` 中仍有独立 terminal 常量。这些是 projection/memory 消费者，不在 S2 producer boundary 内。它们消费的是 EventLog 中已写入的 canonical fact event_type 字符串，不是自行产生 terminal event。属于后续 EventLog/projection source-of-truth 硬化范围，不作为 S2 blocker。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **S3 worker lifecycle path**: `engine_ingest.py` 中的 `_EVENT_TYPE_ATTEMPT_SUSPENDED` 裸字符串和 worker lifecycle synthetic `EngineEvent(type=RUN_FAILED)` 路径仍在 S3 scope，S2 未触及。
- **S3 `_late_rejection_reason` nullable terminal refs**: 仍使用 `terminal_event_id is not None` 判定 terminal closed，属于 S3 scope。
- **S3 dispatch pre-worker direct cancel predicate**: 仍在 `command.py` 中，属于 S3 scope。
- **下游 projection/memory 常量**: `outbox.py`、`memory.py`、`compact_material.py`、`run_input.py`、`durable/memory.py` 中的独立 terminal 常量属于后续 EventLog/projection source-of-truth 硬化范围。

## Completion Report

- status: completed
- artifact: docs/reviews/wu-semantic-ownership-01-p3-a-s2-code-review-ds.md
- verdict: pass
- blocking findings count: 0
- nonblocking findings count: 0
- blockers: none
