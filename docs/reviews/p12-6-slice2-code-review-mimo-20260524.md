# P12.6 Slice 2 Code Review — AgentMiMo

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Reviewer: AgentMiMo
- Review base: `c0a5b18` (gateflow: accept P12.6 slice 1)
- Review scope: workspace diff for P12.6 Slice 2 (excluding `docs/host/implementation-control.md`)
- Date: 2026-05-24

## Verdict: PASS (with 1 low-severity accepted finding)

Slice 2 实现正确、完整地完成了 plan 指定的所有目标。deterministic segment selection、material pack builder、snapshot cursor validation 和 current input anchor 去重均按 design §25 要求实现。没有发现 blocker。

## 动机判断

动机成立，没有被高估。Slice 2 直接修复 plan §6.3/§6.4/§6.6 指定的 material selection / source 同源问题：RunInputBuilder 与 compact builder 共用同一 `RunInputMaterialBlock` view，segment selection 确定性输出 block ids，material pack builder 强制 one-to-one section mapping。没有引入过度复杂或偏离设计的路径。

## Findings

### F1 [LOW] `_memory_material_kind` 使用 content-prefix 匹配判断 material kind

- 文件: `dayu/host/run_input.py:2065-2083`
- 证据: 函数通过 `content.startswith("Memory evidence-backed facts:")` 等硬编码前缀判断 material kind。这些前缀必须与 memory projection renderer 的输出完全一致。
- 影响: 若 memory projection renderer 的前缀格式变更，kind 分类会静默降级为 `PINNED_STATE` 或 `RAW_USER_TURN`，不会抛错。当前代码正确，但脆弱。
- 建议: 可接受为 V1 实现；后续 Slice 6 做 Memory Projection Consolidation 时，可考虑让 memory message 携带 structured metadata 而非依赖 content prefix。
- 决策: **Accepted** — 不阻塞本 slice，记录为后续 slice 的改进点。

### F2 [LOW] `excluded_reason_codes` 类型注解语义不精确

- 文件: `dayu/host/compaction.py:600`
- 证据: `excluded_reason_codes: Mapping[PromptLocalMaterialLabel, str]`，但 key 实际是 block ID（如 `"history-old"`），不是 prompt-local label（如 `"H1"`）。`PromptLocalMaterialLabel = str` 使类型检查通过，但注解语义误导。
- 影响: 不影响运行时正确性；对后续阅读者可能造成理解偏差。
- 建议: 将类型改为 `Mapping[str, str]` 或新增 `MaterialBlockId = str` type alias。
- 决策: **Accepted** — 低优先级，可在后续 slice 统一清理。

## Correctness 详细审查

### Deterministic segment selection (`select_compact_segment`)

- 排序键 `(event_sequence, event_sub_index, block_kind_order, block_id)` 与 plan §6.3 一致。
- Stable block 缺少 `event_sequence` 时使用 `memory_snapshot_cursor` 作为 fallback，无 cursor 时用 `_NO_EVENT_SEQUENCE=0`，确定性成立。
- 相同输入不论 block 顺序均输出相同 `selected_block_ids` 和 `selection_digest`。测试 `test_segment_selection_is_deterministic_for_same_inputs` 验证了这一点。

### Proactive exclusion 规则

- `CURRENT_INPUT_ANCHOR` section → `protected_current_input` ✓
- Protected recent raw floor → `protected_recent_raw_floor` ✓
- `already_represented=True` → `already_represented` ✓
- `STABLE_INPUT` section → `stable_input_not_selected` ✓
- 非 `HISTORY_INPUT` / `EVIDENCE_INPUT` section → `not_in_segment` ✓

### Reactive path

- Reactive selection 消费传入的 frozen overflow material list，不从 EventLog 重新扫描。测试 `test_reactive_segment_uses_frozen_overflow_material_list` 验证。

### Material pack builder

- `_is_current_input_history_duplicate` 同时检查 source ref 包含和 content digest 相等，防止同一 current input 重复进入 history。
- `_raise_on_duplicate_section_owner` 使用 `(sorted(canonical_source_refs), content_digest)` 作为 dedupe key，跨 section 重复时抛 `DuplicateMaterialSectionOwnerError`。
- current input anchor 超过 `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS=1200` 时截断并标记，完整 digest 保留。符合 plan §6.4。

### Snapshot cursor validation

- `check_compact_memory_snapshot_cursor` 正确处理：snapshot 缺失（`SNAPSHOT_MISSING`）、session 不匹配（`SNAPSHOT_DAMAGED`）、cursor 超前（`SNAPSHOT_AHEAD_OF_REQUIRED`）、lag 超阈值（`SNAPSHOT_LAG_OVER_THRESHOLD`）、lag 在阈值内可用 inline repair（`INLINE_DELTA_REPAIR`）。
- `CompactMemorySnapshotRepairRequired.requests_run_recovery` 硬编码为 `False`，符合 design §25 "memory projection lag 不得把 Run 推入 RECOVERING"。
- 测试 `test_snapshot_lag_failure_does_not_request_run_recovery` 验证。

### Architecture 合规

- 不修改 Engine / Service / Fins / Host public API ✓
- 不引入 `Any` / `object` / `getattr` / `hasattr` / lazy seam ✓
- 不反向依赖：`compact_material.py` 只 import `compaction.py`（同层 contracts）和 `memory.py`（下层） ✓
- 所有函数有完整中文 docstring ✓
- 所有新增签名严格类型化 ✓

## Tests 审查

### Plan 要求的 8 个测试覆盖

| Plan 测试 | 实现 | 状态 |
|---|---|---|
| `test_segment_selection_is_deterministic_for_same_inputs` | ✓ | PASS |
| `test_proactive_segment_excludes_current_anchor_and_recent_raw_floor` | ✓ | PASS |
| `test_reactive_segment_uses_frozen_overflow_material_list` | ✓ | PASS |
| `test_already_represented_blocks_are_not_reexpanded` | ✓ | PASS |
| `test_material_pack_one_to_one_section_mapping_rejects_duplicate_content` | ✓ | PASS |
| `test_current_input_anchor_does_not_duplicate_history_raw_turn` | ✓ | PASS |
| `test_snapshot_cursor_lag_requires_catchup_or_inline_delta` | ✓ | PASS |
| `test_snapshot_lag_failure_does_not_request_run_recovery` | ✓ | PASS |

8/8 全覆盖。

### 测试质量评估

- 测试覆盖了 critical positive 和 negative cases。
- 辅助函数 `_history_block` / `_evidence_block` / `_current_block` / `_policy` / `_empty_snapshot` 构造清晰，便于维护。
- `test_run_input_builder.py` 新增 `test_run_input_builder_exposes_shared_material_block_source` 覆盖 `build_material_blocks` 入口。

### 测试缺口（non-blocking）

- `max_selected_size_units` 预算限制路径无专门测试（手动验证通过）。
- 空 material blocks 列表输入无测试（手动验证通过，返回空 selection）。
- `normalized_material_text` 空白输入无测试（代码有显式校验）。

## README 审查

### `dayu/host/README.md`

- 新增内容描述了 compact material 同源 view、deterministic segment selection、protected exclusion 和 material pack builder 的稳定语义。
- 没有过程状态、未来计划或实现细节。
- 术语与 design §25 一致。

### `tests/README.md`

- 新增 `test_compact_material.py` 的测试职责描述和 focused command。
- 与代码实际测试范围一致。

## Open Questions / Residual Risks

1. **Dispatch / engine-ingest 接线**: Slice 2 的 `select_compact_segment` 和 `build_compact_material_pack` 尚未接入 proactive / reactive production path。该接线属于 Slice 5。
2. **Raw evidence descriptor digest 校验**: Slice 2 的 `RunInputMaterialBlock` 支持 evidence block 的 `accepted_evidence_id` / `tool_result_event_ref` 等字段，但实际 digest-checked raw payload 读取属于 Slice 3。
3. **`_memory_material_kind` content-prefix 脆弱性**: 已记录为 F1，可在 Slice 6 统一改进。

## Validation Summary

```bash
# Tests
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
# 结果: 92 passed

# Pyright
source .venv/bin/activate && python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
# 结果: 0 errors, 0 warnings, 0 informations

# Git diff check
git diff --check
# 结果: passed
```
