# WU-CTX-02 + WU-CTX-03 Slice D code review artifact

## 审查范围

- **Gate**: WU-CTX-02 + WU-CTX-03 implementation Slice D
- **Approved plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md` 第 7 节 Slice D
- **设计真源**: `docs/host/design.md` 第 1 节、第 25 节
- **总控文档**: `docs/host/host-core-followup-implementation-control.md`
- **Accepted Slice C commit**: `2d2ed5a`
- **审查对象**: 当前工作区未提交 diff, 覆盖以下文件:
  - `dayu/host/engine_ingest.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `dayu/host/README.md`
  - `tests/README.md`
- **Implementation artifact**: `docs/reviews/wu-ctx-02-03-implementation-sliceD-codex-20260601.md`

## 验证命令及结果

### 测试

```bash
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q
```

结果: `100 passed in 1.23s`

### 类型检查

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果: `0 errors, 0 warnings, 0 informations`

## Findings

### Finding 1 (LOW) — `_fallback_selection_failure_reason` 函数 docstring 缩进不一致

- **文件**: `dayu/host/engine_ingest.py`
- **位置**: 行 338-346 (diff 行号), 对应函数 `_fallback_selection_failure_reason`
- **描述**: 该函数 docstring 内 `:param` / `:returns` 字段比同一模块中其他函数（如 `_complete_reactive_recovery`、`_reactive_fallback_decision`）多缩进 4 空格（从 4 空格变为 8 空格），与项目 docstring 风格不一致。
- **严重性**: LOW。不影响功能、类型检查或可读性；仅格式化偏差。
- **建议**: 将 `:param` / `:returns` 行缩进调整为与模块其他函数一致（4 空格）。

### Finding 2 (INFO) — `_FALLBACK_ACTION_NOT_APPLICABLE` 常量在 `engine_ingest.py` 与 `context_events.py` 各自独立定义

- **文件**: `dayu/host/engine_ingest.py` (行 167) 与 `dayu/host/context_events.py` (行 196)
- **描述**: 两个模块各自定义了值为 `"not_applicable"` 的私有常量。`context_events.py` 的常量为 `_FALLBACK_ACTION_NOT_APPLICABLE`（在 `validate_context_compaction_failed_payload` 验证逻辑中使用），`engine_ingest.py` 的常量为 `_FALLBACK_ACTION_NOT_APPLICABLE`（在 `_append_reactive_compaction_failed_event` 默认参数中使用）。两者是同一语义值的两个副本。
- **严重性**: INFO。不构成逻辑错误或类型错误；值相同，互不影响。但若未来 `fallback_action` 的合法值集合变更，需要同时修改两处，增加维护风险。
- **评估**: 此模式在 Slice B/C 即已存在（`context_events.py` 的 `_FALLBACK_ACTION_NOT_APPLICABLE` 为 private 常量），Slice D 只是在 `engine_ingest.py` 中按同一模式定义私有默认值。不阻塞合入，但建议后续统一引用 `context_fallback.py` 中的公共常量或保持现状。

## 设计 / AGENTS 合规性逐项检查

### 1. reactive compact final failure 正确复用 Slice C fallback helper

**通过。** `_reactive_fallback_decision` (engine_ingest.py:3234) 直接调用 Slice C 的 `build_recent_window_fallback_selection` 与 `estimate_recent_window_fallback_budget` (context_fallback.py:331, 413)，使用 `pending.frozen_material_blocks`（overflow 时冻结的 ordinary material blocks）、`pending.policy`（同一 context budget policy）和 `pending.recent_raw_turns_floor`。failed payload 的 `fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`、`fallback_action` 字段通过 `_append_reactive_compaction_failed_event` 写入 EventLog。

### 2. fallback_action=dispatch 路径写 CONTEXT_COMPACTION_FAILED 后创建新 recovery Attempt

**通过。** engine_ingest.py:1620-1639: 当 `fallback.action == FALLBACK_ACTION_DISPATCH` 时，返回 `_ReactiveRecoveryAccepted(compacted_event_id=None, compacted_event_sequence=None)`。该对象通过 `_complete_reactive_recovery` (line 1969) 调用 `_StartReactiveRecoveryOperation` (line 447-506)，后者使用 `start_recovery_run_with_starting_attempt_in_transaction` 创建新 `attempt_id`（前缀 `attempt-recovery`）、新 `execution_id`（前缀 `execution-recovery`），且 `context_compacted_event_id=None`。

- 不写 `CONTEXT_COMPACTED`: `_ReactiveRecoveryAccepted.compacted_event_id=None`
- 不写 compact artifact: fallback 路径不调用 `_append_reactive_compacted_event`
- 不触发 memory projection materialization: `_complete_reactive_recovery` (line 1981) 仅在 `accepted.compacted_event_sequence is not None` 时才调用 `catch_up_conversation_memory_projection`；fallback 时 `compacted_event_sequence=None`，跳过

### 3. fallback_action=fail_closed / selection failure / over-budget 路径 RUN_FAILED 收口

**通过。** engine_ingest.py:1640-1658: 当 `fallback.action != FALLBACK_ACTION_DISPATCH`（即 fail_closed）时，调用 `_fail_recovering_run` 将 Run 置为 `FAILED`。

- `_fail_recovering_run` (line 1920-1967) 写入 `RUN_FAILED` fact 并执行 `fail_recovering_run_in_transaction`
- 不写 `RUN_LOST`: Slice D 新增代码未引入 `RUN_LOST` 写入；engine_ingest.py 中仅有的 `RUN_LOST` 引用在 `_EVENT_TYPE_RUN_LOST` 常量（line 205）和其他无关注入点（line 3714, 3994）保持不变
- selection/estimate 异常路径 (line 3304-3323): `_reactive_fallback_decision` 的 `except Exception` 分支返回 `action=FALLBACK_ACTION_FAIL_CLOSED`，诊断字段使用 `build_selection_failure_window_payload` / `build_selection_failure_budget_payload`
- over-budget 路径: `_reactive_fallback_decision` 中 `budget.hard_budget_passed == False` 时返回 `action=FALLBACK_ACTION_FAIL_CLOSED`

### 4. 未修改 durable schema、未修改 run_transition.py、未新增 required payload

**通过。** diff 不包含对以下任何文件的修改:
- `dayu/host/durable/run_transition.py`
- SQLite DDL 文件
- `RUN_STARTED` required payload 集合
- `ContextBudgetPolicy` public fields
- `execution_profiles.json` schema
- Engine `AgentRunRequest` 或 `EngineEvent` schema
- Service-facing public API

### 5. StartRecoveryRunInput(context_compacted_event_id=None) 使用合法

**通过。** `_StartReactiveRecoveryOperation.__call__` (line 469-486) 将 `self.accepted.compacted_event_id`（fallback 时为 `None`）传入 `StartRecoveryRunInput.context_compacted_event_id`。该字段类型为 `str | None`，在 Slice C 即已支持 `None`。`start_recovery_run_with_starting_attempt_in_transaction` 内部处理 `None` 为"无 compact event 关联"的合法语义。此用法不伪造 compact success，不绕过 transition precondition。

### 6. EventLogContextFallbackProvider 为 recovery Attempt 读取 fallback view

**通过。** `EventLogContextFallbackProvider._load_context_fallback_tx` (context_fallback.py:272-328):
- 查询 `run_started_event_sequence` 之前最新的 `CONTEXT_COMPACTION_FAILED` event
- 校验 `fallback_action == "dispatch"`
- 读取 `fallback_input_window` 中的 `selected_block_ids` 和 `current_input_ref`
- 校验 `window_current_ref == current_input_ref`（即 fallback 绑定的 current input ref 与当前 Run 的用户输入 ref 一致）
- 返回 `ActiveRecentWindowFallback`

`RunInputBuilder.build` (run_input.py:1618-1650) 在 fallback is not None 时调用 `_fallback_context_messages`，基于 `ActiveRecentWindowFallback.selected_block_ids` 从 ordinary material blocks 中过滤消息，不包含 compact artifact 消息。

测试 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` (test_dispatch_scheduler.py:3719) 验证第二个 recovery request 不包含 `"Accepted compact artifact is available for this run."`，且最后一条消息为 `"dispatch prompt"`。

### 7. reactive count limit / unreadable count / precondition failure 仍 fail closed

**通过。** `_start_reactive_context_recovery` (engine_ingest.py:1150-1269):
- `context_budget_policy_missing` (line 1167): `_fail_reactive_recovery_without_request` → `_fail_recovering_run` → fail closed
- `input_event_missing` (line 1178): 同上
- `reactive_compact_count_unreadable` (line 1206): 同上
- `reactive_compact_limit_reached` (line 1214): 同上

以上路径均不创建新 Request fact (operation_id 由 `_reactive_precondition_compaction_operation_id` 生成)，不进入 `_execute_reactive_compaction`，不经过 `_reactive_fallback_decision`，直接 fail closed。`failed` payload 使用 `_append_reactive_compaction_failed_event` 的默认 `fallback_action="not_applicable"`，`attempt_count=0`，`retry_repair_budget_exhausted=False`。

### 8. tests 覆盖 engine ingest 与 scheduler 组合路径

**通过。**

- `test_reactive_compactor_missing_fallback_dispatches_recovery_attempt` (test_engine_ingest_mapping.py:448): 覆盖 ingest 层 reactive compactor missing → fallback budget pass → 新 recovery Attempt，断言 7 个事件的完整序列、`CONTEXT_COMPACTION_FAILED` payload 的 `fallback_action=dispatch` / `fallback_input_window` 结构、0 `CONTEXT_COMPACTED`、0 `RUN_LOST`、0 `RUN_FAILED`、新 Attempt 数=2、新 current attempt_id 不同于 seeded。

- `test_reactive_fallback_over_budget_fails_closed_without_lost` (test_engine_ingest_mapping.py:497): 覆盖 ingest 层 reactive fallback over-budget → `RUN_FAILED`，断言 `fallback_action=fail_closed`、`fallback_budget_result.status=over_hard_budget`、0 `RUN_LOST`、0 `CONTEXT_COMPACTED`、Attempt 数=1（未创建新 recovery Attempt）。

- `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` (test_dispatch_scheduler.py:3719): 覆盖 scheduler 组合路径，使用 `_ReactiveRecoveryWorkerFactory`（第一轮 emit `CONTEXT_COMPACTION_REQUESTED`，第二轮 emit `FINAL_ANSWER`），断言 2 个 Accepted snapshots、新 attempt_id/execution_id、0 `CONTEXT_COMPACTED`、0 `RUN_LOST`、第二个 request 不包含 compact artifact 提示文本、最后消息为 `"dispatch prompt"`。

### 9. AGENTS 合规

| 检查项 | 状态 |
|---|---|
| 中文 docstring（参数、返回值、异常） | **通过**。所有新增函数/类均有完整中文 docstring |
| 无 `Any`/`object`/无类型签名 | **通过**。所有新签名均有完整类型标注 |
| 无魔法字符串扩散 | **通过**。fallback action 常量在 `context_fallback.py` 模块级定义 |
| 无兼容 wrapper/facade | **通过**。无旧接口兼容代码 |
| 无过度耦合 | **通过**。新增 `_ReactiveFallbackDecision` / `_reactive_fallback_decision` 为 engine_ingest 内部 helper，与 Slice C fallback 通过 typed 参数解耦 |
| 无反向依赖 | **通过**。`context_fallback.py` 不 import engine_ingest |
| 无 `hasattr`/`getattr` | **通过** |
| 无 God object/function/dataclass | **通过**。`_ReactiveFallbackDecision` 职责仅承载 fallback 决策诊断字段 |
| 函数级别做职责拆分 | **通过**。`_reactive_fallback_decision` 为独立 module-level helper，不在 `EngineEventIngestor` 内嵌套 |
| 无 hardcoded 业务规则为脆弱分支 | **通过**。fallback 动作选择由 `budget.hard_budget_passed` 驱动 |

**唯一偏差**: Finding 1（docstring 缩进不一致）。

### README 合规

- `dayu/host/README.md`: 更新了 reactive compact failure fallback 的当前稳定语义，明确 fallback 不是 compact success、reactive fallback dispatch 创建 recovery Attempt、fail closed 收口为 `FAILED` 不写 `RUN_LOST`。符合触发规则（`dayu/host/` 修改）。
- `tests/README.md`: 更新了测试覆盖矩阵，新增 reactive compact failure recent-window fallback dispatch / over-budget fail closed 描述。符合触发规则（`tests/` 修改）。
- 未更新根 README、`dayu/README.md`、Engine/Fins/Config README：本 Slice 未改变 public 使用方式、分层关系或配置入口。

## 最终结论

**Accepted.**

No blocking findings. 1 low-severity docstring formatting inconsistency (Finding 1). 1 informational note about private constant duplication between modules (Finding 2) — pre-existing pattern, not introduced by Slice D.

所有 9 项设计/AGENTS 合规检查通过。100 tests pass, pyright 0 errors.

### Residual risks (from implementation artifact, verified acceptable)

1. **RR-CTX-SLICEB-01**: precondition failure 路径（`context_budget_policy_missing` / `input_event_missing`）未进入 fallback dispatch，直接 fail closed。当前实现符合 Stop Condition 要求（不破坏 durable input_event invariant），但需要 aggregate review 聚合裁决。
2. **reactive frozen material 边界**: fallback selection 使用与 Slice C 相同的 `_frozen_reactive_material_blocks` 输入。当前行为正确，未来若 frozen material 构成变化，RunInputBuilder filtered-view 组合断言需要补强。
3. **fallback dispatch 后真实 provider 可能再次 overflow**: 由现有 `max_reactive_compactions_per_run` 上限与 Slice E repeated-overflow E2E 收口，不在 Slice D scope 内。
