# WU-SEMANTIC-OWNERSHIP-01 P3-C S2 Code Review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s2-code-review-ds.md`
- Included scope: S2 allowed production files（`compaction.py`、`compact_payload.py`、`compact_material.py`、`compact_pipeline.py`、`run_input.py`、`context_budget.py`、`compaction_operation.py`、`llm_compaction.py`）及其对应测试与 README
- Excluded scope: S3 deferred（accepted evidence typed LLM material、唯一 evidence renderer、typed mismatch exception）；未跟踪 `docs/cli_ci*` 文件
- Review date: 2026-07-10

## 真源对齐

本 review 以以下真源为基准：

- design: `docs/host/design.md`（第 23-25 节）、`docs/engine/design.md`
- control: `docs/host/issues-implementation-control.md`
- accepted plan: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- S2 implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s2-implementation-codex.md`
- controller validation: `docs/reviews/wu-semantic-ownership-01-p3-c-s2-controller-validation.md`

## 审查看法

### 1. previous compacted view 只由 ContextCompactedSemanticPayload.accepted_candidate 产生 typed blocks + CompactReadableViewVNext pair

**PASS。**

证据链：

- `_previous_compacted_view_pair_from_compacted_event()`（`compact_material.py:2038`）通过 `parse_context_compacted_semantic_payload(payload).accepted_candidate` 获取 typed candidate，再调用 `_previous_compacted_view_pair_from_candidate()`（`compact_material.py:2073`）。
- `_previous_compacted_view_pair_from_candidate()` 在一次遍历中从 `ConversationCompactOutputVNext` 的五个 typed section 同时生成 `CompactMaterialBlock` tuple 与 `CompactReadableViewVNext`，并在返回前调用 `validate_previous_compacted_view_pair()` 校验 plan 6.3 全部 invariant（presence、kind、label、数量、文本逐项一致、anchor children 保留完整）。
- `CompactMaterialPack.__post_init__()`（`compaction.py:1641`）通过 `_require_previous_compacted_view_pair()` 在 pack 构造时校验 exact pair。
- `PreDispatchCompactMaterialView.__post_init__()`（`compact_material.py:393`）同样调用 `validate_previous_compacted_view_pair()`。
- `CompactPipelineSourceSnapshot.__post_init__()`（`compact_pipeline.py:201`）调用 `validate_previous_compacted_view_pair()`。
- 所有 consumer 路径均只通过验证后的 pair，不存在绕过 typed parser 直接读 raw JSON candidate 的代码路径。
- source scan 确认 `_candidate_session_summary_text`、`_candidate_facts_texts`、`_candidate_answer_anchor_texts`、`_candidate_forward_intent_texts`、`_candidate_reference_continuity_texts` 在 `dayu/host/` 下零匹配。

### 2. tier2/tier3 只通过 transform_previous_compacted_view_pair_for_recovery 同步过滤

**PASS。**

证据链：

- `compact_pipeline.py:532`（tier2）与 `compact_pipeline.py:556`（tier3）均调用 `transform_previous_compacted_view_pair_for_recovery()`。
- `transform_previous_compacted_view_pair_for_recovery()`（`compact_material.py:975`）在一次遍历中同时过滤 blocks 和 typed readable view 的五个 section（summary、facts、anchors、intents、references），过滤后重新执行 `validate_previous_compacted_view_pair()`。
- tier2 先通过 `retained_previous_compacted_view_labels_for_recovery()` 计算需要保留的 labels，再传入 pair transform；tier3 传空 `frozenset()`。
- 不存在分别过滤 blocks/readable view 的独立函数；旧 `degrade_previous_compacted_view_for_recovery()` 已替换为 label selection helper。
- tier1 原样传递已验证 pair（`compact_pipeline.py:475`）。

### 3. compact_material.py / run_input.py 删除旧 string round-trip、raw candidate duplicate parser

**PASS。**

source scan 零匹配确认：

| 扫描目标 | 结果 |
|---|---|
| `_compact_material_source_ref` | 零匹配 |
| `_parse_previous_forward_intent_text` | 零匹配 |
| `_parse_previous_reference_continuity_text` | 零匹配 |
| `def _previous_compacted_(view\|session_summary\|fact_material\|answer_anchors\|forward_intents\|references)_vnext` | 零匹配 |
| `_previous_blocks_from_snapshot` | 零匹配 |
| `_snapshot_(summary_text\|fact_texts\|answer_anchor_texts\|forward_intent_texts\|reference_continuity_texts)` | 零匹配 |
| `compact.messages`（生产代码） | 零匹配 |
| `_compact_artifact_message_content` | 零匹配 |
| `_vnext_compact_candidate_semantic_lines` | 零匹配 |
| `_candidate_(session_summary_text\|facts_texts\|answer_anchor_texts\|forward_intent_texts\|reference_continuity_texts)` | 零匹配 |
| `_available_previous_compacted_view` | 零匹配 |

`run_input.py` 中 `_PAYLOAD_FIELD_ACCEPTED_CANDIDATE` 及其 21 个 nested candidate 字段常量、`_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS`、`_PAYLOAD_FIELD_ANSWER_ANCHORS`、`_PAYLOAD_FIELD_FORWARD_INTENTS`、`_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS` 已从 diff 中删除。

ordinary RunInput 路径验证：
- `RunInputBuilder.build()`（`run_input.py:1916`）的 `bounded_context_messages` 仅拼装 `*memory.messages + *protected_recent_raw_tail.messages + *continuity.messages`，不含 `*compact.messages`。
- `build_run_input_material_blocks()`（`run_input.py:2468`）签名已删除 `compact: CompactArtifactView` 参数及整个 `compact.messages` loop body。
- `_compact_artifact_message_content()`、`_vnext_compact_candidate_semantic_lines()` 及其所有 nested candidate mapping/list parser 已删除。
- `_run_input_message_content()` 保留（`run_input.py:2985`），其调用者仍为 memory（line 2487）、continuity（line 2505）、material-kind（line 3025）路径，不受影响。

### 4. CompactArtifactView / CompactPipelineCompactArtifactView protocol 符合 S2

**PASS。**

- `CompactArtifactView`（`run_input.py:407`）仅有 `compaction_event_ref`、`compact_artifact_ref`、`compact_artifact_digest`、`represented_evidence_refs` 四个字段，无 `messages`。
- `CompactPipelineCompactArtifactView` protocol（`compact_pipeline.py:150`）仅声明 `compact_artifact_ref` 和 `compact_artifact_digest` 两个 property，无 `messages`、无 `represented_evidence_refs`。
- protocol scoped scan 确认只有 `def compact_artifact_ref` 和 `def compact_artifact_digest` 两个 property。
- `CompactArtifactView` 以 structural subtyping 满足该窄 protocol（拥有 `compact_artifact_ref`、`compact_artifact_digest` 同名字段，额外字段不影响 protocol 匹配），pyright 未报 protocol 不匹配错误。
- `DurableCompactArtifactProvider._load_compact_artifact_tx()`（`run_input.py:1587`）不再调用 `_compact_artifact_message_content()`、不构造 `SystemMessage`、不设置 `messages=`。

### 5. RunInputBuilder compact event ref 与 memory latest compaction ref repair matrix

**PASS。**

- `MemorySnapshotView` 新增 `latest_compaction_event_ref: str | None`（`run_input.py:339`），由 `_memory_snapshot_view()`（`run_input.py:2240`）从 `snapshot.latest_compaction_event_ref` 直传。
- `CompactArtifactView` 新增 `compaction_event_ref: str | None`（`run_input.py:417`），由 `DurableCompactArtifactProvider` 设为 `row.event_id` 或 `None`。
- `_require_compact_memory_event_ref_consistency()`（`run_input.py:3084`）实现 plan 6.4 的完整五格矩阵：

| compact ref | memory latest ref | 行为 |
|---|---|---|
| `None` | `None` | 正常继续 |
| 非 `None` | 同一 event-id | 正常继续 |
| 非 `None` | `None` | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)` |
| `None` | 非 `None` | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)` |
| 非 `None` | 不同非 `None` | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)` |

- 后三类复用既有 `MemoryProjectionRepairRequired` + `MemoryRepairReason.SNAPSHOT_DAMAGED`，由既有 required catch-up/rebuild path 处理。
- 未新增异常类型、direct compact renderer 或 fallback message。
- 测试覆盖：`test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`、`test_matching_compact_and_memory_compaction_event_refs_build_once`、`test_compact_event_without_memory_compaction_ref_requires_repair`、`test_memory_compaction_ref_without_compact_event_requires_repair`、`test_mismatched_compact_and_memory_compaction_event_refs_require_repair` — 五个命名测试完全匹配 plan 9 节要求。
- `_latest_compacted_event_before_attempt()`（`run_input.py:3265`）的 SQL 已从 `session_id + run_id` 改为仅 `session_id`，匹配 plan 语义（latest compact 是 session-scoped）。

### 6. post-compact budget 归 context_budget owner

**PASS。**

- `context_budget.py:42`：`POST_COMPACT_BASE_MESSAGE_COUNT = 2`，带 plan 6.5 要求的 one-system-envelope + current-input-user-message 推导注释。
- `context_budget.py:494`：`estimate_post_compact_budget()` 只接受 `compacted_business_texts: tuple[str, ...]` 和 `current_input_text: str`，逐文本调用 `estimate_budget_text_tokens()` 加固定 message overhead。无 caller override 参数。
- `compaction_operation.py:739`：`last_budget = estimate_post_compact_budget(compacted_business_texts=accepted_compact_business_texts(candidate), current_input_text=compact_input.current_input_anchor.text)`。
- `compact_payload.py:161`：`accepted_compact_business_texts()` 只返回五类业务文本（summary text、fact claim texts、anchor titles + child display texts、intent texts、reference texts），不含 diagnostics、code、labels、refs、digests。
- `compaction_operation.py` 不再定义 `_POST_COMPACT_BASE_MESSAGE_COUNT`、`_budget_after_compact_candidate()`、`_candidate_text_fragments()`。
- `llm_compaction.py` 中 `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、`_POST_COMPACT_BASE_MESSAGE_COUNT`、`_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 三个 dead constants 已原地删除，source scan 零匹配。`llm_compaction.py` 不 import/re-export `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`。
- `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT` 是唯一有消费语义的 ordinary post-compact owner。

### 7. S3 scope 未提前实现

**PASS。**

S3 deferred scope 验证：

| S3 目标 | 状态 |
|---|---|
| `AcceptedToolEvidenceLLMMaterial` typed dataclass | 未实现 |
| `render_accepted_tool_evidence_for_llm()` 唯一 renderer | 未实现 |
| `AcceptedEvidenceProducerEventRefMismatchError` typed exception | 未实现 |
| `AcceptedToolResultProjection.llm_material` | 未实现 |
| `RunInputMaterialBlock` evidence contract 原子迁移 | 未实现 |
| `MemoryProjectionEvent` 四字段 → 单一 typed material | 未实现 |
| `compact_material.py` envelope 二次解析删除 | 未实现 |
| `str(exc)` 比较删除 | 未实现 |

现存 accepted evidence renderer / mismatch 旧路径（如 `compact_material.py` 中 `accepted_evidence_envelope_from_payload` 调用、`run_input.py` 中 `_accepted_tool_evidence_content`、`memory.py` 中 `_accepted_evidence_readable_text`）作为 S3 deferred scope 保留，S2 diff 未新增或破坏这些路径。`git diff -- dayu/host/tool_trace.py` 为空。

### 8. README/test updates 符合职责；coverage/pyright/source scan 证据可信

**PASS。**

- `dayu/host/README.md`：更新描述了 typed pair、ordinary single system envelope、budget owner 与 compact artifact provenance 变化，符合其 README 更新约束。
- `tests/README.md`：更新了 P12.6 测试覆盖描述，符合其 README 更新约束。
- 根 README、`dayu/README.md` 未被 S2 触发，未修改。
- 独立验证结果（与 controller validation 一致）：
  - S2 focused tests：`136 passed in 1.05s`
  - aggregate affected tests：`285 passed, 1 skipped`
  - import/weak typing guards：`25 passed`
  - pyright：`0 errors, 0 warnings, 0 informations`
  - import smoke：通过
  - `git diff --check`：通过
- 逐文件 coverage（controller validation 已验证，均 ≥80%）：
  - `compact_material.py` 86%、`compact_payload.py` 87%、`compact_pipeline.py` 94%、`compaction.py` 88%、`compaction_operation.py` 94%、`context_budget.py` 93%、`llm_compaction.py` 90%、`run_input.py` 88%
- source scans：所有 plan 9 节要求的 hard-delete scan 均零匹配（已独立执行并确认）。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- S3 仍未实现：accepted evidence typed LLM material、唯一 evidence renderer、typed mismatch exception。当前 memory/compact pipeline/run input 仍有三套独立 evidence renderer（`_accepted_evidence_readable_text`、`_accepted_tool_evidence_content`、run_input 同名函数），且 envelope mismatch 仍通过 `str(exc)` 字符串比较处理。这些是已批准的 S3 deferred scope，不作为 S2 defect。
- `conversation_compact_input_vnext_from_material_pack()` 直接使用 `material_pack.previous_compacted_readable_view`（`compact_material.py:583`），该值来自 `CompactMaterialPack`，已在构造时通过 `validate_previous_compacted_view_pair` 校验。若未来有代码路径绕过 `CompactMaterialPack` 构造直接调用此函数，需确保传入的 pack 已经过校验。
- `_latest_compacted_event_before_attempt()` 的 SQL 从 `session_id + run_id` 改为仅 `session_id`（`run_input.py:3278`），语义上正确（compact 是 session-scoped），但需确认所有调用方不依赖旧的 run-scoped 过滤行为。当前调用方仅 `DurableCompactArtifactProvider._load_compact_artifact_tx()`，其语义已对齐。
