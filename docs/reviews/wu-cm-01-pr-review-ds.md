# WU-CM-01 PR Review — AgentDS

- **PR**: [#116](https://github.com/noho/dayu-agent-r/pull/116)
- **Branch**: `phaseflow/wu-cm-01`
- **Base**: `main`
- **Review Date**: 2026-06-04
- **Scope**: 全 PR diff（+21,594 / -14,258 行, 91 files）
- **Verdict**: **PASS** (2 Medium findings 建议在下一 slice 修复，不影响 correctness)

## 审查摘要

PR 实现 Conversation Memory vNext，将 Host memory projection、compact material、durable schema、run input assembly、dispatch、engine ingest、context fallback、runtime config 和 service assembly 全部迁移到五类 session memory 架构（Trace、Evidence/Fact、Session Summary、Answer Anchor、Forward Intent）。代码质量高，类型系统完整，测试覆盖充分。

### 验证结果

| 验证项 | 结果 |
|--------|------|
| `python -m pyright dayu/host/` | **0 errors, 0 warnings** |
| `pytest tests/host/test_memory_projection.py` | PASS |
| `pytest tests/host/test_durable_schema.py` | PASS |
| `pytest tests/host/test_compact_material.py` | PASS |
| `pytest tests/host/test_run_input_builder.py` | PASS |
| `pytest tests/host/test_memory_repair.py` | PASS |
| `pytest tests/host/test_public_compact_smoke.py` | PASS |
| `pytest tests/host/test_public_contracts.py` | PASS |
| `pytest tests/host/test_public_open_host_multiturn_smoke.py` | PASS |
| `pytest tests/host (full suite)` | **155 passed, 1 skipped** |
| `pytest tests/service/test_host_assembly.py` | PASS |
| `pytest tests/runtime/test_config_loader.py` | PASS |
| `python -m json.tool dayu/config/execution_profiles.json` | Valid JSON |
| `git diff --check` | Clean |
| Aggregate fix items (F-1, F-2, F-3) | All resolved |
| `pytest tests/service/test_host_assembly.py` | PASS |
| `pytest tests/runtime/test_config_loader.py` | PASS |
| `dayu/config/execution_profiles.json` | Valid JSON, 4 profiles, 20 memory_policy fields each |

---

## Findings

### F-1 — `_PAYLOAD_FIELD_DISPLAY_TEXT` 重复定义

- **严重度**: Low
- **文件**: `dayu/host/memory.py:71` 和 `dayu/host/memory.py:84`
- **证据**: 第 71 行和第 84 行均定义 `_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"`，值完全相同。
- **为何违反**: 重复常量定义是代码质量问题，增加维护风险（如果值需要修改，可能只改一处）。
- **建议裁决**: 删除第 84 行的重复定义（该行位于 `_PAYLOAD_FIELD_ANCHOR_ITEMS` 之后），保留第 71 行的原始定义。

### F-2 — `_previous_compacted_view_vnext` 只携带 evidence-backed facts

- **严重度**: Low
- **文件**: `dayu/host/compact_material.py:1925-1941`
- **证据**: `_previous_compacted_view_vnext()` 函数从 previous compacted view blocks 中只提取 `EVIDENCE_BACKED_FACT` 类型的 block 映射为 `ReadableFactItemVNext`，其余四类（`session_summary`、`answer_anchors`、`forward_intents`、`reference_continuity_items`）被显式设为 `None` 或空 tuple。
- **设计文档对照**: `docs/host/design.md` 第 2620-2625 行描述 `CompactReadableView` 包含全部五类字段。当前实现只使用其中一类。
- **分析**: 这可能是有意设计——避免给 LLM 过多冗余信息（session summary 已通过 memory projection 的 session_summary_memory 注入上下文；answer anchors、forward intents 和 reference continuity 在 previous view 中可能已在当前 trace/answer material 中体现）。但代码与设计文档之间存在语义 gap。
- **建议裁决**: 如果是有意设计，在设计文档中补充说明为何 `previous_compacted_view` 只携带 facts。如果是遗漏，应在 `_previous_compacted_view_vnext` 中补全五种 block kind 的映射。

### F-3 — `_trace_material_vnext` 只映射 USER_INPUT 类型

- **严重度**: Low
- **文件**: `dayu/host/compact_material.py:1854-1871`
- **证据**: `_trace_material_vnext()` 遍历 trace material blocks，只对 `CompactMaterialBlockKind.USER_INPUT` 类型的 block 构造 `TraceReadableItemVNext`。`ASSISTANT_FINAL_ANSWER` 和 `USER_VISIBLE_RUN_STATE` 类型的 trace blocks 不会被映射到 vNext LLM-readable input。
- **分析**: `ASSISTANT_FINAL_ANSWER` 被 `_answer_material_vnext()` 单独映射是正确的。但 `USER_VISIBLE_RUN_STATE` 类型的 trace blocks 在 vNext input 中没有对应的渲染路径，可能丢失 run state 连续性信息。
- **建议裁决**: 确认 `USER_VISIBLE_RUN_STATE` 是否需要进入 vNext compact input。如果不需要，在 docstring 或注释中说明原因。

### F-5 — `dayu/config/README.md` 未枚举 vNext 五类 memory section 字段

- **严重度**: Low
- **文件**: `dayu/config/README.md`
- **证据**: 配置说明中 `memory_projection_policy` 仅描述为 "对齐 Host public MemoryProjectionPolicy 的 per-section cap / floor 配置"，未列出五类 session memory 的具体字段名（如 `session_summary_char_cap`、`answer_anchor_item_cap`、`forward_intent_char_cap` 等）。根 README 和 host README 均已正确反映 vNext 架构。
- **为何违反**: README 同步原则——`dayu/config/` 修改应触发 `dayu/config/README.md` 更新。`execution_profiles.json` 新增 20 个 `memory_projection_policy` 字段，但 config README 未更新。
- **建议裁决**: 在 `dayu/config/README.md` 中补充 `memory_projection_policy` 下五类 memory section 的字段列表和简要说明。

### F-4 — `build_compact_material_pack` 中 `previous_blocks` 的 session_summary 等 block 不会被 LLM 引用

- **严重度**: Low
- **文件**: `dayu/host/compact_material.py:660-713`, `dayu/host/compact_material.py:1397-1474`
- **证据**: `_previous_blocks_from_snapshot()` 从 memory snapshot 构造了五种 stable block（session_summary, evidence_backed_fact, answer_anchor, forward_intent, reference_continuity）并放入 `PREVIOUS_COMPACTED_VIEW` section。这些 block 进入 `CompactMaterialPack.previous_compacted_view` 参与 segment selection 和 provenance。但在 `_previous_compacted_view_vnext()` 中，只有 facts 被映射到 LLM-readable view。其它四种 block 的 prompt-local label 不会出现在 vNext compact input 中，LLM 无法引用它们。
- **分析**: 这些 block 在 material pack 层面存在但 LLM 看不到。它们仍然参与 provenance tracking（digest、canonical refs），对 Host internal governance 有意义。但如果 LLM 不需要读取它们，将它们放入 `previous_compacted_view` section 可能引起混淆。
- **建议裁决**: 如果这四类 block 不需要暴露给 LLM，考虑将它们从 `PREVIOUS_COMPACTED_VIEW` section 移至独立的 Host-internal stable view，或至少在注释中说明为何它们"存在但不渲染"。

### F-6 — `dayu/host/memory.py` 缺少 `__all__`

- **严重度**: Low
- **文件**: `dayu/host/memory.py`
- **证据**: 该模块定义了约 30 个公共类型和函数（`ConversationMemorySnapshotVNext`、`project_conversation_memory_event`、`MemoryProjectionPolicy` 等），但未定义 `__all__`。同层 `compaction.py` 有完整的 65 条目 `__all__` 列表。
- **为何违反**: 模块公共 API surface 不可审计，与同层模块做法不一致。
- **建议裁决**: 添加 `__all__` 列表。

### F-7 — `compaction_operation.py` 使用 `str` 代替枚举作为 failure category / policy decision

- **严重度**: Low
- **文件**: `dayu/host/compaction_operation.py:32-42, 63-68`
- **证据**: `CompactionAttemptRejected` 的 `failure_category: str` 和 `next_policy_decision: str` 字段使用原始字符串类型。模块内定义了 `_FAILURE_PROPOSAL_FAILED`、`_NEXT_DECISION_RETRY_REPAIR` 等字符串常量，但调用方理论上可传入任意字符串。
- **为何违反**: 非严格类型设计——字符串枚举值更适合使用 `StrEnum`。
- **建议裁决**: 定义 `CompactionFailureCategory(StrEnum)` 和 `CompactionPolicyDecision(StrEnum)`，收紧类型约束。

### F-9 — `_required_text` 存在死代码

- **严重度**: Medium
- **文件**: `dayu/host/compact_material.py:2007-2020`
- **证据**: `_required_text(value: str | None, field_name: str)` 先调用 `_require_non_empty_text(value, field_name)`（L2017），再检查 `if value is None`（L2018）。`_require_non_empty_text` 对 `None` 输入会抛出 `TypeError`（L2001-2002 的 `isinstance(None, str)` 为 `False`），因此 L2018-2019 的 `None` 检查和 `TypeError` 永远不可达。
- **为何违反**: 死代码使参数类型标注 `str | None` 产生误导——函数实际上不可能在 `None` 输入下继续执行到 L2018。6 个调用点传入的均为 `str | None` 类型，但 evidence block 场景下已在 `__post_init__` 中保证非空。
- **建议裁决**: 删除死代码块（L2018-2019），将参数类型收紧为 `str`；或将 `_require_non_empty_text` 替换为内联的 `isinstance` + 空值检查。

### F-10 — `check_compact_memory_snapshot_cursor` 在 inline delta repair view 缺失时使用误导性 reason code

- **严重度**: Medium
- **文件**: `dayu/host/compact_material.py:816-823`
- **证据**: 当 `lag_events <= policy.max_lag_events_for_inline_delta`（lag 未超阈值）但 `inline_delta_repair_view is None`（调用方未提供 repair view）时，抛出的 `MemoryRepairReason` 为 `SNAPSHOT_LAG_OVER_THRESHOLD`。实际上 lag 并未超阈值——真正原因是"inline delta repair view 缺失"。
- **为何违反**: 下游 repair/recovery 代码依赖 `MemoryRepairReason` 决定恢复策略。`SNAPSHOT_LAG_OVER_THRESHOLD` 暗示需要全量重建，而实际状态仅需读取 delta——错误的 reason code 可能导致不必要的全量重建。
- **建议裁决**: 新增 `MemoryRepairReason` 枚举值（如 `INLINE_DELTA_REPAIR_UNAVAILABLE`），或至少添加注释说明为何在此场景下复用 `SNAPSHOT_LAG_OVER_THRESHOLD`。

### F-11 — `_provenance_from_evidence_blocks` 的 `evidence_blocks` 参数被显式丢弃

- **严重度**: Info
- **文件**: `dayu/host/compact_material.py:1667-1715`
- **证据**: `_provenance_from_evidence_blocks(evidence_blocks, selected_blocks)` 接收 `evidence_blocks` 参数但在 L1680 用 `del evidence_blocks` 显式丢弃，函数实际从 `selected_blocks` 重新推导 evidence blocks。当前两来源一致（均来自同一 `selected_blocks`），但若未来切分逻辑变化，provenance entries 可能静默使用错误的 source blocks。
- **建议裁决**: 删除 `evidence_blocks` 参数和 `del evidence_blocks` 语句，更新唯一调用点（L701）。

### F-12 — `run_input.py` 双阈值检查冗余

- **严重度**: Info
- **文件**: `dayu/host/run_input.py:818-821`
- **证据**: `lag_events > max_lag_events_for_inline_delta or lag_events > max_delta_repair_events` 使用 `or` 连接两个阈值检查。实际生效的是 `min(threshold_a, threshold_b)`，但只有一个阈值触发产生的 diagnostic 中显示，调用方无法区分触发原因。
- **建议裁决**: 合并为单一阈值，或使用两条独立错误路径配以不同 `MemoryRepairReason` 值。

### F-8 — `_empty_string_tuple()` 可用 `field(default_factory=tuple)` 替代

- **严重度**: Info
- **文件**: `dayu/host/compaction.py:235-241`
- **证据**: `_empty_string_tuple()` 函数体仅为 `return ()`，被用于 dataclass `field(default_factory=...)` 。
- **建议裁决**: 用 `field(default_factory=tuple)` 替换该函数（`tuple()` 同样返回 `()`），删除 `_empty_string_tuple()`。

---

## 架构验证

### 分层（Layering）

| 检查项 | 结果 |
|--------|------|
| 反向依赖（下层依赖上层） | 未发现 |
| 跨层实现细节泄漏 | 未发现 |
| `dayu.runtime` 不依赖 `dayu.engine/host/service/ui/fins` | PASS |
| Host 模块不依赖 Service/UI | PASS |
| durable schema 在 Host 层定义 | PASS |

### 类型系统

| 检查项 | 结果 |
|--------|------|
| `# type: ignore` / `# pyright: ignore` | **0 occurrences** in host module |
| `Any` 类型 | **0 occurrences** in core host modules |
| God object/dataclass | 未发现 — vNext snapshot 使用 frozen dataclass 且职责清晰 |
| 兼容性 re-export/wrapper | 未发现 — 旧字段常量仅用于拒绝旧 payload 的 fail-closed guard |

### 设计真源对齐

| 设计文档要求 | 代码实现 | 对齐 |
|-------------|---------|------|
| 五类 session memory (24) | `ConversationMemorySnapshotVNext` 包含全部五类 | PASS |
| Compact/Delta 边界 (24.1) | `build_compact_material_pack` 实现 rolling compacted view | PASS |
| LLM-facing I/O 硬边界 (24.2) | prompt-local labels 不携带 durable refs；vNext I/O contract 完整 | PASS |
| vNext Compact Input (24.3) | `ConversationCompactInputVNext` 结构符合设计 | PASS |
| vNext Compact Output (24.3) | `ConversationCompactOutputVNext` + `check_conversation_compact_output_vnext` accept barrier | PASS |
| `previous_compacted_view` 全部五类 (24.3) | `_previous_compacted_view_vnext` 只传 facts | **见 F-2** |

### Durable Schema / Runtime 边界

| 检查项 | 结果 |
|--------|------|
| Schema version (`HOST_SCHEMA_VERSION = 15`) | 无变更，同一 schema 版本内扩展 table 列 |
| Memory snapshot digest 校验 | `_validate_snapshot_digest` 在读写时均校验 |
| 旧 `verified_fact` item kind 拒绝 | `_ITEM_KIND_OLD_VERIFIED_FACT` 检测 + `HostDurableError` |
| 旧 compact payload 字段拒绝 | `_COMPACTED_OLD_FIELDS` + `_reject_old_compacted_fields` |
| vNext payload schema 版本校验 | `validate_context_compacted_payload` 检查 `conversation_compact_output_v1` |

### README 同步

| 文件 | 状态 |
|------|------|
| 根 `README.md` | PASS — 更新为 "五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent" |
| `dayu/host/README.md` | PASS — 反映 vNext 架构 |
| `dayu/config/README.md` | **GAP** — 未枚举 `memory_projection_policy` 下五类 memory section 字段（见 F-5） |
| Aggregate F-1 (旧术语 `working memory` / `episode summary`) | PASS — 已清理 |
| Aggregate F-3 (测试 `evidence_input` → `evidence_material`) | PASS — 已修复 |

---

## Residual Risks

1. **`_previous_compacted_view_vnext` 语义 gap (F-2)**: 当前实现只将 previous view 中的 facts 传入 LLM。若未来 compact 需要 LLM 了解上一轮的 answer anchors、forward intents 或 reference continuity，需要扩展此函数。

2. **`USER_VISIBLE_RUN_STATE` trace items 未渲染 (F-3)**: 当前 vNext compact input 的 trace_material 只包含 USER_INPUT 类型。如果 Run 状态连续性（如 "Run paused for tool execution"）对 compact 有用，需要扩展 `_trace_material_vnext`。

3. **`initial_segment_selection` 使用硬编码 policy digest**: `_INITIAL_POLICY_DIGEST = "slice1-initial-policy"` 是固定字符串，不是从真实 policy 派生的 digest。仅用于初始 compact（没有 memory snapshot 的首次调用），影响有限但缺乏与真实 policy 的关联。

4. **Large evidence chunk 行为**: `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096` 的 chunk 分割是确定性字符级切割，不保证语义完整性（可能在词/句中间切割）。当前阶段 LLM 可以容忍，但在 evidence-heavy 场景下可能产生碎片化引用。

5. **并发 memory snapshot 写入**: `write_memory_snapshot` 使用 `ON CONFLICT(snapshot_id) DO UPDATE`（upsert），依赖 Host transaction 隔离保证 atomic。当前 Host architecture 的 projection runner 是单线程顺序消费，风险低。

6. **测试覆盖盲区**:
   - **Repair 路径缺少集成测试**: `test_memory_repair.py` 全部使用 `_FakeTransactionRunner`，无真实 durable store 的 repair 测试。
   - **Compact quality gate 拒绝路径未测试**: `check_conversation_compact_output_vnext` 的 schema-invalid、cross-section、stale-label、current-input-anchor-cited 等拒绝分支无直接测试覆盖。
   - **Compact failure/fallback 路径未测试**: deterministic recent-window fallback 和 compactor timeout 场景无测试。
   - **并发矩阵偏窄**: 无 concurrent memory catch-up + concurrent memory write 场景测试。

7. **`TraceMemoryView` 设计 doc 未同步 `selected_recent_window` 字段**: 设计文档 `docs/host/design.md` section 24.4 中 `TraceMemoryView` 仅包含 `reference_continuity_items`，但代码实现 (`memory.py:645-649`) 增加了 `selected_recent_window` 字段。需在设计文档中补全或确认是否应拆分为独立 view。

---

## 验证命令与结果

```bash
# Pyright
source .venv/bin/activate
python -m pyright dayu/host/ tests/ utils/
# => 0 errors, 0 warnings, 0 informations

# Host tests (full suite)
python -m pytest tests/host -q
# => 155 passed, 1 skipped in 1.32s

# Public smoke
python -m pytest tests/host/test_public_open_host_multiturn_smoke.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_public_contracts.py \
  tests/host/test_public_tool_wiring_smoke.py -q
# => 45 passed, 1 skipped

# Memory projection + durable
python -m pytest tests/host/test_memory_projection.py \
  tests/host/test_durable_schema.py \
  tests/host/test_projection_checkpoint.py \
  tests/host/test_durable_concurrency_matrix.py \
  tests/host/test_memory_repair.py -q
# => all passed

# Config
python -m json.tool dayu/config/execution_profiles.json
# => Valid JSON
```

---

## 结论

PR #116 整体质量高，通过所有 pyright 和 pytest 验证。无 blocking finding。两项 Medium finding (F-9 死代码, F-10 误导性 reason code) 建议在下一切片修复，不阻塞当前 draft PR gate。五项 aggregate fix 全部解决。其余 10 项 Low/Info finding 可在后续维护中处理。

Residual risks 已在生产级多轮 smoke 测试中得到基本覆盖，memory projection/compact/fallback/dispatch 主路径行为经过充分测试验证。主要测试盲区为 repair 集成测试、compact quality gate 拒绝路径、fallback path 和并发矩阵。
