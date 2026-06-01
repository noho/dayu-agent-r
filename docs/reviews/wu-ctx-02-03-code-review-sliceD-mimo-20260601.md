# WU-CTX-02 + WU-CTX-03 Slice D Code Review — AgentMiMo

- **Reviewer**: AgentMiMo
- **Date**: 2026-06-01
- **Gate**: WU-CTX-02 + WU-CTX-03 implementation Slice D
- **Approved plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- **Accepted Slice C commit**: `2d2ed5a`
- **Reviewed diff**: uncommitted workspace changes on `feat/host-ctx-compact-failure-overflow`

## 审查范围

Slice D 目标：reactive compact final failure 后按 deterministic recent-window fallback policy 决定创建新 recovery Attempt 或 fail closed。

审查文件：

| 文件 | 变更类型 |
|---|---|
| `dayu/host/engine_ingest.py` | 生产代码：reactive fallback 决策、recovery 路径、failed payload 字段扩展 |
| `tests/host/test_engine_ingest_mapping.py` | 测试：reactive fallback dispatch 与 over-budget fail closed |
| `tests/host/test_dispatch_scheduler.py` | 测试：scheduler 组合路径 fallback dispatch |
| `dayu/host/README.md` | 文档：reactive fallback 语义同步 |
| `tests/README.md` | 文档：测试覆盖矩阵同步 |

## 验证命令及结果

```
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q
# 100 passed in 1.24s

source .venv/bin/activate && python -m pyright dayu/host/engine_ingest.py dayu/host/context_fallback.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py
# 0 errors, 0 warnings, 0 informations
```

## 审查发现

### Finding 1 — INFO: docstring 缩进不一致

- **文件**: `dayu/host/engine_ingest.py:3305-3308`
- **severity**: INFO
- **描述**: `_fallback_selection_failure_reason` 函数 docstring 的 `:param` 行使用 8 空格缩进（双层缩进），而函数体使用 4 空格缩进。PEP 257 建议 docstring body 与函数体同级缩进。
- **影响**: 不影响功能，pyright 不报错。属于代码风格一致性问题。
- **建议**: 将 docstring param 行缩进从 8 空格改为 4 空格。

### 无 Blocking Findings

其余所有审查维度均通过，详见下文逐项验证。

## 逐项审查验证

### 1. reactive compact final failure 复用 Slice C helper

**通过。**

- `engine_ingest.py:3234-3297` — `_reactive_fallback_decision` 正确调用 Slice C 的 `build_recent_window_fallback_selection` 和 `estimate_recent_window_fallback_budget`。
- 使用 `pending.frozen_material_blocks`（overflow 时冻结的 ordinary material blocks）作为 selection 输入。
- 使用 `pending.policy`（同一 ContextBudgetPolicy）和 `pending.recent_raw_turns_floor`。
- budget result 使用 `RecentWindowFallbackBudgetResult.to_payload()` 构造结构化诊断。
- fallback window 使用 `RecentWindowFallbackSelection.to_window_payload()` 构造结构化诊断。

### 2. fallback_action=dispatch 路径

**通过。**

- `engine_ingest.py:1620-1639` — `fallback.action == FALLBACK_ACTION_DISPATCH` 时返回 `_ReactiveRecoveryAccepted`：
  - `compacted_event_id=None`、`compacted_event_sequence=None` — 不伪造 compact success。
  - 包含 `CONTEXT_COMPACTION_FAILED` event 但不包含 `CONTEXT_COMPACTED`。
  - `terminal_closeout=False` — Run 不关闭。
- `engine_ingest.py:1969-1995` — `_complete_reactive_recovery` 在 `accepted.compacted_event_sequence is not None` 时才执行 memory projection catchup；fallback 时为 `None`，跳过 catchup。
- `engine_ingest.py:447-518` — `_StartReactiveRecoveryOperation` 生成新的 `attempt_id`、`execution_id`、`dispatch_record_id`，调用 `start_recovery_run_with_starting_attempt_in_transaction`。
- `StartRecoveryRunInput.context_compacted_event_id` 类型为 `str | None`，docstring 明确说 "startup recovery 未发生 compact 时为 ``None``"（`run_transition.py:514-517`），`None` 是合法语义。
- `run_transition.py:3201-3206` — payload 只在 `context_compacted_event_id is not None` 时才写入该字段，`None` 时跳过，不伪造。

### 3. fallback_action=fail_closed / over-budget 路径

**通过。**

- `engine_ingest.py:1640-1658` — `fallback.action != FALLBACK_ACTION_DISPATCH` 时调用 `_fail_recovering_run`，Run 收口为 `FAILED`。
- `terminal_closeout=True` — Run 关闭。
- 不写 `RUN_LOST`（由 `_fail_recovering_run` 内部保证，写 `RUN_FAILED`）。
- 不创建新 Attempt。

### 4. 未修改禁止文件

**通过。**

- diff 不包含 `dayu/host/durable/run_transition.py`。
- diff 不包含 SQLite durable schema 变更。
- diff 不包含 `RUN_STARTED` required payload 新增字段。
- diff 不包含 Service-facing API、EngineEvent schema、ContextBudgetPolicy public field 或 execution profile schema 变更。

### 5. StartRecoveryRunInput(context_compacted_event_id=None) 语义

**通过。**

- `run_transition.py:514-517` — docstring 明确说明 `context_compacted_event_id` 在 "startup recovery 未发生 compact 时为 ``None``"。
- `run_transition.py:5369-5378` — validation 要求 `context_compacted_event_id` 和 `context_compacted_event_sequence` 同时为 `None` 或同时非 `None`。Slice D 两者都传 `None`，通过校验。
- `run_transition.py:3201-3206` — `RUN_STARTED` payload 只在非 `None` 时才写入 `context_compacted_event_id`，`None` 时 payload 不含该字段。
- 这是既有 durable transition 的合法语义，不是伪造 compact success。

### 6. EventLogContextFallbackProvider 读取 failed fallback view

**通过（Slice C 已实现，Slice D 正确接线）。**

- `context_fallback.py:235-328` — `EventLogContextFallbackProvider.load_context_fallback` 从 EventLog 读取当前 Run started 之前最近的 `CONTEXT_COMPACTION_FAILED` event，校验 `fallback_action == "dispatch"`、`current_input_ref` 匹配后返回 `ActiveRecentWindowFallback`。
- `current_input_ref` 绑定校验（`context_fallback.py:319`）确保 fallback view 只对匹配的输入生效。
- Slice D 的 `_ReactiveRecoveryAccepted` 将 `compacted_event_id=None` 传入 `_StartReactiveRecoveryOperation`，recovery Attempt 的 `RUN_STARTED` event 不含 `context_compacted_event_id`，RunInputBuilder 的 fallback provider 可从该 `RUN_STARTED` 之前的 `CONTEXT_COMPACTION_FAILED` event 读取 fallback view。

### 7. reactive count limit / unreadable count / precondition failure 仍 fail closed

**通过。**

- Slice D 未修改 `_fail_reactive_recovery_without_request`、reactive count limit 检查或 precondition 失败路径。
- 这些路径仍走既有 fail-closed 逻辑，不进入 `_reactive_fallback_decision`。
- `_reactive_fallback_decision` 只在 compaction operation final failure 分支调用（`engine_ingest.py:1593`），该分支在 request 已写入、旧 Attempt 已进入 `RECOVERING` 后才到达。
- `max_reactive_compactions_per_run` 上限由 ingest 层既有逻辑保证，Slice D 不突破。

### 8. 测试覆盖

**通过。**

- `test_engine_ingest_mapping.py:620-666` — `test_reactive_compactor_missing_fallback_dispatches_recovery_attempt`：
  - 断言事件序列为 `REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> COMPACTION_FAILED -> RUN_STARTED -> ATTEMPT_STARTED`。
  - 断言 `fallback_action == "dispatch"`、`fallback_policy_decision == "deterministic_recent_window"`。
  - 断言 `CONTEXT_COMPACTED` 为 0、`RUN_FAILED` 为 0、`RUN_LOST` 为 0。
  - 断言 2 个 Attempt、新 attempt_id != 旧 attempt_id。
  - 断言 fallback window 和 budget result 为结构化 Mapping。
- `test_engine_ingest_mapping.py:669-707` — `test_reactive_fallback_over_budget_fails_closed_without_lost`：
  - 断言事件序列为 `REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> COMPACTION_FAILED -> RUN_FAILED`。
  - 断言 `fallback_action == "fail_closed"`、`fallback_budget_result.status == "over_hard_budget"`。
  - 断言 `RUN_LOST` 为 0、`CONTEXT_COMPACTED` 为 0、Attempt 数为 1。
- `test_dispatch_scheduler.py:3719-3778` — `test_reactive_compact_failure_fallback_dispatch_uses_failed_view`：
  - 使用 `_ReactiveRecoveryWorkerFactory`（第一轮 overflow、第二轮 final answer），不传 `context_compactor`。
  - 断言 2 个 accepted snapshots、新 attempt_id/execution_id、`CONTEXT_COMPACTED` 为 0、`RUN_LOST` 为 0。
  - 断言第二个 request 不含 compact artifact 文本。

### 9. AGENTS 合规

**通过（除 Finding 1 INFO 外）。**

- 中文 docstring：所有新增/修改函数和 dataclass 均有完整中文 docstring，包含参数、返回值、异常。
- 签名类型：无 `Any`、`object`、无类型参数或返回值。`_ReactiveFallbackDecision` 字段使用 `str`、`Mapping[str, JsonValue]` 等具体类型。
- 魔法字符串：fallback action/policy decision 常量定义在 `context_fallback.py` 并通过 import 使用，不直接写字面量。
- 无兼容 wrapper：`_complete_reactive_recovery_after_compact` 重命名为 `_complete_reactive_recovery`，不是兼容 wrapper，是语义扩展。
- 无过度耦合：`engine_ingest.py` 通过 import `context_fallback.py` 的公共 helper 复用 Slice C 逻辑，不重复实现。

## README 合规性

- `dayu/host/README.md`：更新 reactive compaction 路径描述，明确 deterministic recent-window fallback 在 proactive 和 reactive 两条路径的语义差异，包括 reactive fallback dispatch 创建 recovery Attempt、fail closed 收口为 `FAILED` 且不写 `RUN_LOST`。描述与当前代码一致，不写未来设计。
- `tests/README.md`：在 P12.6 memory semantic smoke 段新增 reactive fallback dispatch / over-budget fail closed 覆盖描述。与当前测试一致。

## 设计 / AGENTS 合规性结论

| 维度 | 结论 |
|---|---|
| 架构边界 | 通过。Context Governance 仍在 Host 内，Engine 不参与 compact retry。 |
| 状态机 | 通过。reactive fallback dispatch: `RECOVERING -> COMPACTION_FAILED -> RUN_STARTED -> ATTEMPT_STARTED`；reactive fallback fail closed: `RECOVERING -> COMPACTION_FAILED -> RUN_FAILED`。不写 `RUN_LOST`、不写 `CONTEXT_COMPACTED`。 |
| Durable schema | 通过。未修改。 |
| Public contract | 通过。未新增。 |
| Fallback 语义 | 通过。fallback 不是 compact success，不物化 memory projection，不写 compact artifact。 |
| AGENTS 编码约束 | 通过（除 docstring 缩进 INFO）。 |

## 最终结论

**Accepted with findings（仅 INFO 级别）。**

No blocking findings. Slice D 实现正确复用 Slice C deterministic recent-window fallback helper，reactive compact failure 后 fallback dispatch 创建新 recovery Attempt（新 attempt_id/execution_id、compacted_event_id=None、不写 CONTEXT_COMPACTED、不物化 memory projection）或 fail closed（RUN_FAILED、不写 RUN_LOST）。未修改 durable schema、未修改 run_transition.py、未新增 RUN_STARTED required payload 或 public policy schema。测试覆盖 engine ingest 与 scheduler 组合路径。README 只写当前稳定行为。
