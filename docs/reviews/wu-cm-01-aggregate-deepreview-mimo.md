# WU-CM-01 Aggregate DeepReview

## Review Metadata

- **work unit**: WU-CM-01 Conversation Memory overall optimization
- **review type**: aggregate deepreview (cross-slice)
- **reviewer**: mimo
- **date**: 2026-06-04
- **branch**: phaseflow/wu-cm-01
- **accepted commits**: b2b57c18..7ff96ce6
- **design source**: `docs/host/design.md` 第 24-25 章
- **plan source**: `docs/host/wu-cm-01-conversation-memory-plan.md`

## Verification Summary

| 验证项 | 结果 |
|--------|------|
| pyright | 0 errors, 0 warnings, 0 informations |
| 核心 contract/projection 测试 | 171 passed |
| operation/dispatch/smoke 测试 | 118 passed, 1 skipped |
| durable/schema 测试 | 51 passed |
| Service/Runtime 配置测试 | 67 passed |
| public smoke 测试 | 10 passed, 1 skipped |
| Host 全量测试 | 1100 passed, 1 skipped, 5 deselected |

## Findings

### Severity: INFO

#### INFO-1: context_events.py 保留旧字段常量用于 fail-closed 校验

**文件**: `dayu/host/context_events.py:56-59`

**证据**:
```python
_FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"
_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = "minimum_preserve_item_candidates"
```

**说明**: 这两个旧字段常量保留在 `context_events.py` 中，但仅用于 `validate_context_compacted_payload()` 的 fail-closed 校验。测试 `tests/host/test_context_compact_events.py:176-213` 明确验证旧字段会被拒绝：

```python
def test_compacted_payload_rejects_patch_without_preservation_evidence() -> None:
    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {}
    with pytest.raises(ValueError, match="pinned_state_patch_candidate is not supported"):
        validate_context_compacted_payload(payload)
```

**判定**: 符合预期。旧字段常量用于防御性校验，不是兼容 wrapper 或 re-export。当旧字段出现在 payload 中时，validator 会 fail closed。

---

#### INFO-2: tests 中保留旧字段 fail-closed 测试用例

**文件**: `tests/host/test_context_compact_events.py:176-213`, `tests/host/test_llm_compaction.py:181`

**说明**: 测试文件中保留了对旧字段 `pinned_state_patch_candidate`、`episode_summary_candidate` 的 fail-closed 测试用例。这些测试验证 vNext contract 会拒绝旧字段，符合 plan 要求的"旧字段 fail closed"行为。

**判定**: 符合预期。测试覆盖了旧字段的拒绝路径，不是兼容读取。

---

### Severity: PASS

#### PASS-1: MemoryProjectionPolicy 字段与 design source 一致

**证据来源**: `docs/host/design.md:95`, `dayu/host/memory.py:756-800`, `dayu/runtime/config_loader.py:236-280`, `dayu/config/execution_profiles.json`

**验证**: design.md 第 3 章要求的 `memory_projection_policy` 字段清单：

```
context_window_size, selected_recent_window_item_cap, selected_recent_window_char_cap,
selected_recent_window_turn_floor, fallback_selected_recent_window_item_cap,
fallback_selected_recent_window_char_cap, evidence_fact_item_cap, evidence_fact_char_cap,
evidence_fact_floor, session_summary_char_cap, answer_anchor_item_cap, answer_anchor_char_cap,
forward_intent_item_cap, forward_intent_char_cap, reference_continuity_item_cap,
reference_continuity_char_cap, reference_continuity_item_floor, max_lag_events_for_inline_delta,
max_delta_repair_events, policy_ref
```

与实现完全一致：
- `dayu/host/memory.py:781-800` 的 `MemoryProjectionPolicy` 字段 ✓
- `dayu/runtime/config_loader.py:261-280` 的 `MemoryProjectionConfig` 字段 ✓
- `dayu/config/execution_profiles.json` 的 JSON key ✓
- `dayu/service/host_assembly.py` 的显式映射 ✓

**判定**: 通过。字段名、类型、默认值与 design source 完全对齐，无旧字段 alias 或兼容 wrapper。

---

#### PASS-2: ConversationMemorySnapshotVNext 字段与 design source 一致

**证据来源**: `docs/host/design.md:2744-2772`, `dayu/host/memory.py:891-921`

**验证**: design.md 第 24.4 章要求的 `ConversationMemorySnapshotVNext` 字段：

```
schema_version, session_id, source_event_cursor, latest_compaction_event_ref,
trace_memory, evidence_fact_memory, session_summary_memory, answer_anchor_memory,
forward_intent_memory, diagnostics
```

实现与 design source 一致：
- `schema_version` ✓
- `snapshot_id` (额外字段，用于 stable id) ✓
- `session_id` ✓
- `cursor` (对应 `source_event_cursor`) ✓
- `policy_digest` ✓
- `latest_compaction_event_ref` ✓
- `trace_memory: TraceMemoryView` ✓
- `evidence_fact_memory: EvidenceFactMemoryView` ✓
- `session_summary_memory: SessionSummaryMemoryView` ✓
- `answer_anchor_memory: AnswerAnchorMemoryView` ✓
- `forward_intent_memory: ForwardIntentMemoryView` ✓
- `diagnostics` ✓

**判定**: 通过。五类 session semantic memory view 完整实现，无旧 `pinned_state`、`working_assumptions`、`conversation_continuity` 字段。

---

#### PASS-3: Compact I/O vNext contract 完整实现

**证据来源**: `docs/host/design.md:2600-2735`, `dayu/host/compaction.py:1-200`

**验证**: design.md 第 24.3 章要求的 `ConversationCompactInputVNext` 和 `ConversationCompactOutputVNext`：

**Input vNext**:
- `schema_version: "conversation_compact_input_v1"` ✓
- `previous_compacted_view` ✓
- `trace_material` ✓
- `evidence_material` ✓
- `answer_material` ✓
- `current_input_anchor` ✓
- `instruction` ✓

**Output vNext**:
- `schema_version: "conversation_compact_output_v1"` ✓
- `session_summary` ✓
- `evidence_backed_facts` ✓
- `answer_anchors` ✓
- `forward_intents` ✓
- `reference_continuity_items` ✓
- `diagnostics` ✓

**CompactMaterialSection**:
- `PREVIOUS_COMPACTED_VIEW` ✓
- `TRACE_MATERIAL` ✓
- `EVIDENCE_MATERIAL` ✓
- `ANSWER_MATERIAL` ✓
- `CURRENT_INPUT_ANCHOR` ✓

**CompactMaterialBlockKind** (vNext):
- `SESSION_SUMMARY` ✓
- `EVIDENCE_BACKED_FACT` ✓
- `ANSWER_ANCHOR` ✓
- `FORWARD_INTENT` ✓
- `REFERENCE_CONTINUITY` ✓
- `USER_INPUT` ✓
- `ASSISTANT_FINAL_ANSWER` ✓
- `USER_VISIBLE_RUN_STATE` ✓
- `ACCEPTED_TOOL_EVIDENCE` ✓
- `CURRENT_INPUT_ANCHOR` ✓

**判定**: 通过。旧 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 已删除，vNext section 完整实现。

---

#### PASS-4: Durable schema fresh-start 策略一致

**证据来源**: `dayu/host/durable/schema.py:34`, `tests/host/test_public_compact_smoke.py`

**验证**:
- `HOST_SCHEMA_VERSION = 15`，全新 schema 起库
- public smoke 使用 fresh workspace，不依赖旧库数据
- `tests/host/test_durable_schema.py` 覆盖 fresh-start 行为

**判定**: 通过。durable schema 按全新设计处理，不写旧库兼容读取。

---

#### PASS-5: Prompt assembly 固定顺序实现

**证据来源**: `docs/host/design.md:2809-2848`, `dayu/host/run_input.py`

**验证**: design.md 第 24.6 章要求的固定顺序：

1. Host / Service system messages 与场景约束 ✓
2. Session Summary Memory ✓
3. Evidence / Fact Memory ✓
4. Answer Anchor Memory ✓
5. Forward Intent Memory ✓
6. Trace Memory 的 reference continuity items ✓
7. selected recent window ✓
8. current input ✓
9. replay / retry / steer / resume guidance ✓
10. tool schema snapshot 与运行 policy ✓

RunInputBuilder 实现了三种渲染模式：
- no accepted compacted view: selected recent window + current input ✓
- compact failed fallback: fallback selected recent window + current input ✓
- accepted compacted view: 五类 memory section + selected recent window + current input ✓

**判定**: 通过。fallback 不生成高阶语义，不写 `CONTEXT_COMPACTED`。

---

#### PASS-6: Source label fail-closed 校验完整

**证据来源**: `dayu/host/compaction.py`, `tests/host/test_compaction_contract.py`

**验证**: vNext contract 要求：
- 未知 label 拒绝 ✓
- stale label 拒绝 ✓
- 跨 section label 拒绝 ✓
- 缺 source label 拒绝 ✓
- current input anchor 被引用拒绝 ✓
- 空文本拒绝 ✓
- 非法枚举拒绝 ✓

`CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT` 只允许 `EVIDENCE_MATERIAL` ✓
`CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT` 只允许 `ANSWER_MATERIAL` ✓

**判定**: 通过。fail-closed 行为由测试覆盖。

---

#### PASS-7: Whole-candidate repair 实现

**证据来源**: `dayu/host/compaction_operation.py`, `tests/host/test_compaction_operation.py`

**验证**:
- repair 是 whole-candidate re-proposal ✓
- 不合并旧 proposal 的 valid fields ✓
- 不 partial materialize rejected candidate ✓
- retry budget 耗尽只写 `CONTEXT_COMPACTION_FAILED` ✓
- 不写 `CONTEXT_COMPACTED` ✓

**判定**: 通过。

---

#### PASS-8: Fallback 不生成高阶语义

**证据来源**: `dayu/host/context_fallback.py`, `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`

**验证**:
- fallback 不写 `CONTEXT_COMPACTED` ✓
- fallback 不写 compact artifact ✓
- fallback 不 materialize memory snapshot ✓
- fallback 不生成 summary / fact / anchor / intent / reference continuity ✓
- fallback 只渲染 bounded recent window 和 current input ✓

**判定**: 通过。

---

#### PASS-9: execution_profiles.json 字段迁移完整

**证据来源**: `dayu/config/execution_profiles.json`

**验证**: 旧字段已全部删除：
- `max_pinned_items` ✗ (已删除)
- `max_evidence_backed_facts` ✗ (已删除)
- `max_working_assumptions` ✗ (已删除)
- `recent_raw_turns_floor` ✗ (已删除)
- `raw_turn_context_ratio` ✗ (已删除)
- `raw_turn_size_floor` ✗ (已删除)
- `raw_turn_size_cap` ✗ (已删除)
- `history_pool_context_ratio` ✗ (已删除)
- `history_pool_size_floor` ✗ (已删除)
- `history_pool_size_cap` ✗ (已删除)
- `stable_layer_context_ratio` ✗ (已删除)
- `stable_layer_size_floor` ✗ (已删除)
- `stable_layer_size_cap` ✗ (已删除)

新字段已全部添加：
- `context_window_size` ✓
- `selected_recent_window_item_cap` ✓
- `selected_recent_window_char_cap` ✓
- `selected_recent_window_turn_floor` ✓
- `fallback_selected_recent_window_item_cap` ✓
- `fallback_selected_recent_window_char_cap` ✓
- `evidence_fact_item_cap` ✓
- `evidence_fact_char_cap` ✓
- `evidence_fact_floor` ✓
- `session_summary_char_cap` ✓
- `answer_anchor_item_cap` ✓
- `answer_anchor_char_cap` ✓
- `forward_intent_item_cap` ✓
- `forward_intent_char_cap` ✓
- `reference_continuity_item_cap` ✓
- `reference_continuity_char_cap` ✓
- `reference_continuity_item_floor` ✓
- `max_lag_events_for_inline_delta` ✓
- `max_delta_repair_events` ✓
- `policy_ref` ✓

**判定**: 通过。config_loader 会 fail fast 旧字段。

---

#### PASS-10: README 同步完整

**证据来源**: `dayu/host/README.md`, `tests/README.md`, `dayu/config/README.md`

**验证**:
- Host README 已更新为 vNext 术语：`trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory` ✓
- 旧术语已清理：`stable layer`、`history pool`、`working_assumptions`、`pinned_state`、`minimum_preserve` ✓
- tests README 已更新测试命令 ✓
- config README 已检查 ✓

**判定**: 通过。

---

#### PASS-11: Residual risk owners 完整

**证据来源**: `docs/host/wu-cm-01-conversation-memory-plan.md:666-671`

**验证**: deferred residual owners：

| Residual Risk | Owner | Status |
|---------------|-------|--------|
| 完整 Conversation Memory eval benchmark | WU-CM-10 / GitHub Issue #80 | deferred-with-owner ✓ |
| Cross-session User Profile Memory | WU-CM-11 / GitHub Issue #115 | deferred-with-owner ✓ |
| Deep historical recall / semantic search | GitHub Issue #39 | deferred-with-owner ✓ |
| Provider-specific tokenizer adapter | 后续 Context Governance 精确预算 work unit | deferred-with-owner ✓ |
| Fins fact grounding integration | Fins integration work unit | deferred-with-owner ✓ |
| Schema old DB upgrade | explicit non-goal | N/A ✓ |

**判定**: 通过。所有 residual risks 有明确 owner。

---

## Cross-Slice Consistency Check

### Compact vNext contract closure ↔ Memory vNext projection

**验证**:
- `ConversationCompactOutputVNext` 的 `evidence_backed_facts` 字段 → `EvidenceFactMemoryView.evidence_backed_facts` ✓
- `ConversationCompactOutputVNext` 的 `session_summary` 字段 → `SessionSummaryMemoryView.summary_text` ✓
- `ConversationCompactOutputVNext` 的 `answer_anchors` 字段 → `AnswerAnchorMemoryView.anchors` ✓
- `ConversationCompactOutputVNext` 的 `forward_intents` 字段 → `ForwardIntentMemoryView.intents` ✓
- `ConversationCompactOutputVNext` 的 `reference_continuity_items` 字段 → `TraceMemoryView.reference_continuity_items` ✓
- `CONTEXT_COMPACTED` payload 使用 vNext `accepted_candidate` ✓
- memory projection 从 vNext payload materialize 五类 memory ✓

**判定**: 通过。compact output → memory projection 的数据流无旧字段 alias、兼容 wrapper 或 snapshot bridge。

### Durable schema ↔ Public smoke

**验证**:
- durable schema 使用全新 `HOST_SCHEMA_VERSION = 15` ✓
- public smoke 使用 fresh workspace ✓
- public smoke 不依赖旧库数据 ✓
- fresh-start 策略与 fail-closed 行为一致 ✓

**判定**: 通过。

### Config-service ↔ Host policy

**验证**:
- `config_loader.py` 的 `MemoryProjectionConfig` 字段 = `memory.py` 的 `MemoryProjectionPolicy` 字段 ✓
- `host_assembly.py` 做显式一对一映射 ✓
- `execution_profiles.json` 使用 vNext 字段 ✓
- 旧字段 fail fast ✓

**判定**: 通过。

---

## Verdict

**PASS**

WU-CM-01 aggregate deepreview 未发现 blocking finding。所有 findings 均为 INFO 或 PASS 级别。

### 关键验证结论

1. **Contract consistency**: Conversation Memory vNext policy/snapshot/durable schema/run input/compact material/config-service/docs 整体一致
2. **No compatibility wrappers**: compact vNext contract closure 与 memory vNext projection 无旧字段 alias、兼容 wrapper、snapshot bridge、旧库兼容读取
3. **Fresh-start consistency**: durable schema fresh-start 策略和 public smoke fresh workspace 行为一致，不掩盖生产 fail-closed
4. **Test coverage**: full tests/pyright/smoke validation 足够可信
5. **Residual owners**: deferred residual owners 完整，所有 deferred items 有明确 owner
6. **No cross-slice drift**: docs/host/design.md 已同步、README 无旧术语、tests 覆盖完整、public smoke 不过度依赖真实 provider

### Implementation Quality

- 153 files changed, 20222 insertions(+), 14206 deletions(-)
- 5 个 slice (compact closure, Slice B, Slice C policy fix, Slice C, Slice D) 顺序实施
- 每个 slice 都经过 pyright 和测试验证
- 无旧库兼容读取、无 compatibility wrapper、无 lazy import seam

### Residual Risks (deferred, with owners)

1. **Issue #80 eval benchmark**: WU-CM-10 owner，WU-CM-01 已提供可断言入口和 smoke
2. **Issue #115 User Profile**: WU-CM-11 owner，WU-CM-01 已固定不混入 session memory 边界
3. **Issue #39 recall/search**: deferred owner，第一阶段不做 prompt-conditioned recall
4. **Tokenizer adapter**: deferred owner，WU-CM-01 保持 conservative estimator
5. **Fins integration**: deferred owner，WU-CM-01 保证 memory snapshot 不替代 accepted evidence
