# WU-CTX-02 + WU-CTX-03 Draft PR Review

- **Reviewer**: AgentMiMo
- **Date**: 2026-06-01
- **PR**: #105 `feat/host-ctx-compact-failure-overflow`
- **Base**: `main`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`

## 结论: Accepted

PR #105 可保持 draft-PR-pass。所有发现均为非阻塞观察项，无 correctness / durability / state machine / schema 级别缺陷。

## PR 概要

64 files changed, +8099 / -106。5 个 implementation slices 覆盖：

- **Slice A**: 默认 attempts 对齐为 5，compactor scene model 对齐为 `deepseek-v4-flash`。
- **Slice B**: `CONTEXT_COMPACTION_FAILED` payload 增补 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted` 与 fallback 诊断字段。
- **Slice C**: proactive deterministic recent-window fallback：预算通过则 dispatch，预算失败则 fail closed。
- **Slice D**: reactive deterministic recent-window fallback：旧 Attempt 关闭后创建新 recovery Attempt 或 fail closed。
- **Slice E**: 连续 reactive overflow dispatch-loop E2E，达上限 fail closed，不写 `RUN_LOST`。

## Findings

### F-01 [INFO] `dayu/config/README.md` 未更新

- **文件**: `dayu/config/README.md`（未出现在 diff 中）
- **影响**: plan §9 将 `config/README.md` 列为允许更新的文档；默认 attempts 从 2 变为 5、compactor scene model 从 `mimo-v2.5-pro-thinking-plan` 变为 `deepseek-v4-flash`。若 README 含旧默认值示例，会与实现漂移。
- **建议**: 检查 `dayu/config/README.md` 是否包含默认 attempts 或默认 compactor model 的硬编码示例；若有则更新，若无则记录"检查后无需修改"。
- **阻塞 draft-PR-pass**: 否。README 漂移是文档级风险，不影响 correctness。

### F-02 [INFO] `_ProactiveCompactionExecutionResult` 数据类冗余 `None` 字段

- **文件**: `dayu/host/dispatch.py:347-358`
- **影响**: `compacted_event_sequence: int | None` 和 `pending_dispatch: PendingDispatchRecord | None` 的组合实际上是三态（compacted / fallback dispatch / neither）。当前用 `None` 表示"未发生"语义清晰，但两个 `None` 字段同时为 `None` 时表示"compactor 缺失或 stale result"，调用方需同时检查两个字段。
- **建议**: 可考虑用 `StrEnum` 三态 result type 替代，但当前实现正确且调用方逻辑清晰，不强制修改。
- **阻塞 draft-PR-pass**: 否。

### F-03 [INFO] proactive fallback 不写 `CONTEXT_COMPACTED` 但写了 `CONTEXT_COMPACTION_REQUESTED`

- **文件**: `dayu/host/dispatch.py`（`_prepare_compact_before_dispatch` 写 request fact）
- **影响**: proactive fallback 路径先写 `CONTEXT_COMPACTION_REQUESTED`，再写 `CONTEXT_COMPACTION_FAILED(fallback_action=dispatch)`。这是正确的：request fact 记录了触发 compaction 的意图，failed fact 记录了 compaction 失败和 fallback 决策。但 EventLog 中会出现 `REQUESTED -> FAILED` 而无 `COMPACTED` 的序列，消费者需理解 fallback 语义。
- **建议**: 无需修改。设计真源明确 fallback 不是 compact success，`REQUESTED -> FAILED` 是正确序列。
- **阻塞 draft-PR-pass**: 否。

### F-04 [INFO] reactive fallback 不进入 `RECOVERING` 状态

- **文件**: `dayu/host/engine_ingest.py`（`_execute_reactive_compaction` fallback dispatch 路径）
- **影响**: reactive compact failure fallback dispatch 时，Run 保持 `RUNNING` 状态，直接在同一 Run 上创建新 Attempt。测试 `test_reactive_compactor_missing_fallback_dispatches_recovery_attempt` 断言 `run_status == RunStatus.RUNNING` 且 `_event_count("RUN_RECOVERING") == 0`。这与 plan §5 状态机描述的 `RUN_RECOVERING` 路径不同。
- **分析**: plan §5 描述 reactive fallback success 为 `RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED`。但实现中 `_execute_reactive_compaction` 在 fallback dispatch 时直接返回 `_ReactiveRecoveryAccepted(compacted_event_id=None, compacted_event_sequence=None)`，不调用 `_fail_recovering_run`。`_complete_reactive_recovery` 在 `compacted_event_sequence is None` 时跳过 memory catch-up，直接创建新 Attempt。Run 保持 `RUNNING` 是因为 fallback 不需要关闭 Run 再重新打开。
- **建议**: 无需修改。实现行为优于 plan 描述——避免了不必要的 `RECOVERING` 状态转换，减少了 durable write 和状态机复杂度。plan 描述可视为保守预期，实现选择了更优路径。
- **阻塞 draft-PR-pass**: 否。行为正确且更优。

### F-05 [INFO] `EventLogContextFallbackProvider` 在 `run_input.py` 中 re-export

- **文件**: `dayu/host/run_input.py:46-48`，`dayu/host/run_input.py:__all__`
- **影响**: `EventLogContextFallbackProvider` 定义在 `context_fallback.py`，通过 `run_input.py` 的 import 和 `__all__` re-export。这使得 `run_input.py` 的消费者可以直接 `from dayu.host.run_input import EventLogContextFallbackProvider`。
- **建议**: 这是合理的公共 API 设计——`run_input.py` 作为 RunInputBuilder 的组装入口，re-export 其依赖的 provider 类型便于上层使用。
- **阻塞 draft-PR-pass**: 否。

### F-06 [INFO] `context_fallback.py` 不在 `dayu/host/__init__.py` 的 `__all__` 中

- **文件**: `dayu/host/__init__.py`
- **影响**: `context_fallback.py` 是 Host 内部模块，不需要对外暴露。其公共符号通过 `run_input.py` 和 `dispatch.py` 消费，不需要从 `dayu.host` 包级别 re-export。
- **建议**: 无需修改。内部模块不暴露是正确选择。
- **阻塞 draft-PR-pass**: 否。

### F-07 [INFO] `_fallback_context_messages` 排除 current input anchor

- **文件**: `dayu/host/run_input.py:2389-2446`
- **影响**: fallback rendering 排除 current input anchor block，因为 `RunInputBuilder.build` 会在 messages 末尾单独添加当前用户输入。若 fallback selected blocks 中没有 current input anchor（理论上不会，因为 `_current_input_block` 强制要求），`current_blocks` 会为空导致 `HostDurableError`。
- **建议**: 防御性逻辑正确。`build_recent_window_fallback_selection` 强制保留 current input anchor，`_fallback_context_messages` 再次校验确保 exactly one，双重保险。
- **阻塞 draft-PR-pass**: 否。

## 架构边界检查

### 分层边界

| 检查项 | 结果 |
|---|---|
| `context_fallback.py` 不 import `dayu.engine` / `dayu.service` / `dayu.ui` | 通过 |
| `context_fallback.py` 只依赖 `dayu.host.*` 和 `dayu.contracts` | 通过 |
| `dispatch.py` 新增 import 只来自 `dayu.host.context_fallback` | 通过 |
| `engine_ingest.py` 新增 import 只来自 `dayu.host.context_fallback` | 通过 |
| `run_input.py` 新增 import 只来自 `dayu.host.context_fallback` | 通过 |
| 无反向依赖 | 通过 |
| `dayu.runtime` 未被修改 | 通过 |

### 编码硬约束

| 检查项 | 结果 |
|---|---|
| 中文 docstring 完整 | 通过。所有新增函数、类、方法均有中文 docstring，包含参数、返回值、异常。 |
| 类型签名无 `Any` / `object` / 无类型参数 | 通过。`context_fallback.py` 和 `context_events.py` 新增代码无 `Any` / `object` 使用。 |
| 禁止魔法数字 / 魔法字符串 | 通过。常量用 `_FIELD_*` / `FALLBACK_*` 模块级常量定义。 |
| 无兼容性代码 | 通过。全新 schema，无旧兼容读取。 |
| 无 God object / God function | 通过。每个函数职责单一。 |

### EventLog Schema

| 检查项 | 结果 |
|---|---|
| `CONTEXT_COMPACTION_FAILED` payload 新字段完整 | 通过。所有 append 路径传入 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`。 |
| `fallback_action` 枚举值正确 | 通过。`dispatch` / `fail_closed` / `not_applicable` 三种。 |
| fallback 字段一致性校验 | 通过。`_validate_failed_fallback_fields` 校验 `not_applicable` 时必须全 null，`dispatch` / `fail_closed` 时必须非 null。 |
| 无敏感 raw payload 泄漏 | 通过。`fallback_input_window` 只含 `selected_block_ids`、`source_refs` 等结构化诊断。 |

### State Machine

| 检查项 | 结果 |
|---|---|
| Proactive fallback success 不进入 `RECOVERING` | 通过。Run 从 `ACCEPTED/QUEUED` 直接 dispatch。 |
| Proactive fallback fail closed 不创建 Attempt | 通过。测试断言 `attempt_count == 0`。 |
| Reactive fallback dispatch 创建新 Attempt / execution id | 通过。测试断言 `attempt_id != seeded.attempt_id`。 |
| Reactive fallback fail closed 不写 `RUN_LOST` | 通过。测试断言 `RUN_LOST count == 0`。 |
| 连续 overflow 达上限 fail closed | 通过。E2E 测试断言 Attempt 数 bounded。 |
| Fallback 不写 `CONTEXT_COMPACTED` | 通过。所有 fallback 测试断言 `CONTEXT_COMPACTED count == 0`。 |

### 测试覆盖

| Slice | 测试文件 | 新增 / 修改测试 |
|---|---|---|
| A | `test_context_policy.py`, `test_config_loader.py`, `test_scene_assets_migration.py`, `test_host_assembly.py` | 断言默认 attempts 为 5；断言 scene model 与 profile compactor model 一致 |
| B | `test_context_compact_events.py` | 6 个新增测试覆盖 no-fallback / fallback-dispatch / fallback-fail-closed / 负数 attempt / 非法 action / not_applicable-with-fields / dispatch-missing / fail_closed-missing |
| C | `test_dispatch_scheduler.py`, `test_run_input_builder.py` | proactive fallback dispatch / fail closed / fallback selection stability / budget estimate / RunInputBuilder rendering |
| D | `test_engine_ingest_mapping.py` | reactive fallback dispatch / over-budget fail closed / stale result / count limit |
| E | `test_dispatch_scheduler.py` | 连续 reactive overflow dispatch-loop E2E |

## 验证命令

```bash
source .venv/bin/activate

# 全量受影响测试
pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q

# pyright
python -m pyright dayu/ tests/ utils/
```

## 残余风险

| Risk | 状态 | Owner |
|---|---|---|
| F-01 `config/README.md` 可能含旧默认值 | 需检查 | implementation owner |
| F-04 reactive fallback 不进入 `RECOVERING` 与 plan 描述不完全一致 | 已分析，实现行为更优 | 无需处理 |
| fallback message rendering 降级语义 | current WU risk，通过 selected block ids / digest / budget result 约束 | implementation + review |
| EventLog failed payload 字段增补影响现有 read model / outbox | current WU risk，只增不删 | implementation + aggregate review |
