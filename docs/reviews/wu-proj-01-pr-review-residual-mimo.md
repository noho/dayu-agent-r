# WU-PROJ-01 PR Review — AgentMiMo Residual Gate

## 审查范围

- PR #136 diff: `wu-proj-01` branch vs `main`
- 本地未提交变更: `docs/host/issues-implementation-control.md` gate 状态更新
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 控制文档: `docs/host/issues-implementation-control.md`

## PR 概述

PR #136 实现 WU-PROJ-01 的全部 scope，包括：

1. **EventLog-backed pre-dispatch compact material source** (Slice 1): `build_pre_dispatch_compact_material_view()` 从 EventLog durable truth 构造 compact material，不依赖 Conversation Memory projection。
2. **Proactive Context Governance 同源 material view** (Slice 2): Context Governance 消费 builder 输出做预算估算、segment selection 与 compact operation 编排。
3. **Bounded memory projection catch-up / rebuild** (Slice 3): `MemoryProjectionCatchupBudget`、`MemoryProjectionRepairStopReason`、`target_reached` / `budget_exhausted` 诊断字段。
4. **Accepted compact -> Conversation Memory -> ordinary RunInput 回归覆盖** (Slice 4): 验证 accepted compact 后 memory projection 消费并物化 read model。
5. **CAP-R1**: 删除 `_READABLE_QUERY_TEXT_MAX_CHARS` 固定截断、删除 `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS` / `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS` 固定上限；compact material source 读取完整 canonical EventLog delta。
6. **S3-R1**: dispatch before-worker catch-up happy-path 覆盖，required cursor 已覆盖时 ordinary RunInput 继续。
7. **S4-R1**: 稳定 lane-timeout flaky dispatch scheduler 测试。
8. **Aggregate fix**: 关闭 deepreview 发现。

## 审查结论

### 总结: PASS

PR 136 完整关闭 WU-PROJ-01 CAP-R1 / S3-R1 / S4-R1，无 blocking findings，无 active residual risk 无 owner。

---

## 审查维度

### 1. PR diff 是否完整关闭 WU-PROJ-01 CAP-R1 / S3-R1 / S4-R1

**结论: PASS**

| Residual | 状态 | 关闭依据 |
|---|---|---|
| CAP-R1 | closed | `448b70ba`: 删除 `_READABLE_QUERY_TEXT_MAX_CHARS`、`_READABLE_QUERY_TRUNCATED_MARKER`、`_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS`、`_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS`；`_bounded_query_text()` 替换为 `_normalized_query_text()`；dispatch 路径 `budget=None` 表示 required catch-up 无固定上限 |
| S3-R1 | closed | `3baeef53`: dispatch before-worker catch-up happy-path 测试覆盖，required cursor 已覆盖时 ordinary RunInput 继续；`_raise_if_memory_projection_target_not_reached()` 确认 target_reached |
| S4-R1 | closed | `3baeef53`: lane-timeout flaky 测试通过 timing fixture 调整稳定 |

无 active residual risk 无 owner。控制文档 Residual Risk 表中无 WU-PROJ-01 相关 open 项。

### 2. CAP-R1: 无固定 query truncation / delta/evidence caps / required/rebuild correctness budgets 复发

**结论: PASS**

- `_readable_query_text_from_envelope()` 调用 `_normalized_query_text()` 而非旧 `_bounded_query_text()`，不再截断到 `_READABLE_QUERY_TEXT_MAX_CHARS=1200`。
- `compaction_evidence.py` 中同名函数也已更新为 `_normalized_query_text()`，通过 `normalized_material_text()` 规范化但保留完整内容。
- `_post_compact_delta_rows()` 不限制行数，读取 start_sequence 到 end_sequence 的全部 canonical facts。
- `_accepted_tool_evidence_delta_blocks()` 不限制 evidence blocks 数量。
- `MemoryProjectionCatchupBudget` 只用于 after-commit / after-compact opportunistic 路径 (`BEST_EFFORT_AFTER_COMMIT`)。
- Dispatch 前 required catch-up / rebuild 路径传 `budget=None`，不设固定上限，追到 required cursor、idle 或 failure。
- `MemoryProjectionRepairStopReason` 包含 `TARGET_REACHED`，正确区分 "已覆盖 required cursor" 与 "idle"。
- opportunistic one-batch (`_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT=1` / `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT=1`) 明确标注为 "非 correctness"，purpose 为 `BEST_EFFORT_AFTER_COMMIT`。

### 3. S3/S4 测试稳定性与意义

**结论: PASS**

- Controller 复验 CAP/S3/S4 focused set 174 passed。
- S3/S4 test_dispatch_scheduler 68 passed。
- S4-R1 通过 timing fixture 调整稳定，不再 flaky。
- S3-R1 happy-path 测试验证 required cursor 已覆盖时 catch-up 不重复执行、ordinary RunInput 继续。
- `_raise_if_memory_projection_target_not_reached()` 在 target 未达到时抛出 `_MemoryProjectionDispatchDiagnosticError`，dispatch 路径捕获并走 timeout closeout，不误触发 recovery。

### 4. Aggregate fix 删除 enum 值的兼容/类型/测试风险

**结论: PASS**

- 删除的常量 (`_READABLE_QUERY_TEXT_MAX_CHARS` 等) 是模块级私有常量，非 enum 值，无跨模块兼容风险。
- `_bounded_query_text()` 是模块级私有函数，已替换为 `_normalized_query_text()`。
- 删除的旧 helper (`_latest_session_compacted_event_before_input`、`_proactive_material_blocks`、`_proactive_represented_evidence_refs`) 是 `dispatch.py` 模块级私有函数，无外部引用。
- `__all__` 导出已更新：新增 `CompactMaterialSourceBoundary`、`PreDispatchCompactMaterialView`、`build_pre_dispatch_compact_material_view`。
- pyright 0 errors，无类型扩散。

### 5. 控制文档 gate 状态、Issue 86/PR 后续动作一致性

**结论: PASS**

- 本地未提交变更正确更新 WU-PROJ-01 状态为 `PR-review`。
- 已记录 residual commits: CAP-R1 `448b70ba`, S3/S4 `3baeef53`, aggregate fix `bd6488df`。
- 已记录 aggregate deepreview artifacts 和 controller 复验结果。
- Next gate: PR review。
- Issue #86 通过 PR body `Closes #86` 关联，merge 后自动关闭。
- Residual Risk 表中无 WU-PROJ-01 相关 open 项。

### 6. README / 测试 / pyright / hardcoding / overdesign 风险

**结论: PASS**

- `dayu/host/README.md` 已更新 Memory 与 compact 关系描述，明确 ordinary RunInput 读 memory snapshot 作为 read model，pre-dispatch compact material 由 EventLog / payload / artifact truth 构造。
- `docs/host/design.md` 新增 compact material truth 段落、Context Governance 职责边界、material source cursor 校验、ordinary RunInput bounded memory catch-up 说明。
- `tests/README.md` 已按触发规则更新。
- pyright 0 errors。
- `git diff --check` passed。
- 无 hardcoding 风险：`_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT` 和 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT` 是模块级常量，purpose 为 `BEST_EFFORT_AFTER_COMMIT`，语义清晰。
- 无 overdesign 风险：`MemoryProjectionCatchupBudget` 只有 3 个字段 (`max_batches`、`max_scanned_events`、`purpose`)；`MemoryProjectionRepairStopReason` 只有 4 个值；新增数据类遵循 frozen=True, slots=True 模式。

---

## Non-blocking Findings

### NF1 (Low): `budget=None` 生产路径文档措辞

`memory_repair.py` 中 `catch_up_conversation_memory_projection()` 和 `rebuild_conversation_memory_projection()` 的 `budget` 参数 docstring 写：

> ``None`` 仅供显式审阅的 close-only 或 test-only 调用。

但 `dispatch.py` 中 `_catch_up_memory_projection_before_worker()` 和 `_build_run_input_with_lag_repair()` 在 production dispatch 路径传 `budget=None`，用于 required cursor catch-up。这是正确的设计选择（required catch-up 不应有固定上限），但 docstring 措辞与实际使用不一致。

**建议**: 改为 "``None`` 表示不设固定上限，追到 required cursor、idle 或 failure；仅用于 correctness-required 路径。"

**严重度**: Low — 不影响正确性，仅文档准确性。

### NF2 (Low): reactive compact path 广泛 Exception 捕获

`engine_ingest.py` 中 `_start_reactive_context_recovery()` 对 `build_pre_dispatch_compact_material_view()` 使用 `except Exception` 广泛捕获。这与 proactive path 的 `except Exception` 模式一致，且 `build_pre_dispatch_compact_material_view` 已通过 `HostDurableError` 表达可预期的 durable 错误。广泛捕获可以防止 unexpected 异常破坏 reactive recovery 流程，符合 fail-closed 语义。

**严重度**: Low — 当前模式可接受，但后续可考虑收窄为 `(HostDurableError, TypeError, ValueError)`。

---

## Remaining Residual Risks

无 active residual risk。WU-PROJ-01-S3-R1、WU-PROJ-01-S4-R1、WU-PROJ-01-CAP-R1 均已在本 PR 关闭。

---

## 验证记录

| 验证项 | 结果 |
|---|---|
| CAP/S3/S4 focused set | 174 passed |
| S3/S4 test_dispatch_scheduler | 68 passed |
| Aggregate fix focused | 91 passed |
| Full affected Host test files | 185 passed |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| PR state | draft/open |
| CI checks | 当前为空 |
