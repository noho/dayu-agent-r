# WU-SEMANTIC-OWNERSHIP-01 P3-C Aggregate Deepreview

## Scope

- Mode: aggregate deepreview（跨 S1/S2/S3 语义链路审计）
- Branch: `phaseflow/host-issues-control`
- Base: `0dcef803`（accepted plan commit）
- Head: `4c945391`（S3 bookkeeping commit）
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-aggregate-deepreview-mimo.md`
- Included scope: P3-C 全部 5 个 committed gates 的生产代码、测试与文档变更
- Excluded scope: `docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/code-review-20260710-135625.md`、`docs/reviews/code-review-20260710-141049.md`（未归属 untracked 文件）
- Parallel review coverage: 4 个 subagent 并行收集 S1/S2/S3 review artifacts、生产文件语义分析、消费者/适配器文件分析、测试覆盖分析

## Plan Finding Closure Audit

### P3-C Plan Accepted Findings（7 项）

| Finding | Plan 裁决 | S1/S2/S3 实现 | Aggregate 状态 |
|---|---|---|---|
| AgentDS 6 | accepted，scope corrected | S3 新增唯一 `AcceptedToolEvidenceLLMMaterial` + `render_accepted_tool_evidence_for_llm`；memory/compact_material/run_input 三路径统一消费 | **closed** |
| AgentDS 14 | accepted | S2 `estimate_post_compact_budget()` 归 `context_budget`；`compaction_operation` 删除 `_budget_after_compact_candidate` | **closed** |
| AgentDS 16 | accepted，scope corrected | S1 `compact_payload._parse_persisted_candidate` 严格构造 enum；snapshot JSON 写 `.value`、read 用 enum constructor | **closed** |
| AgentMiMo DS-1 | accepted | S1 `ContextCompactedSemanticPayload` + `parse_context_compacted_semantic_payload` 成为唯一 persisted payload read contract | **closed** |
| AgentMiMo DS-5 | accepted，partially fixed by P1-A | S3 统一 renderer；memory/compact_material/run_input 全部调用 `render_accepted_tool_evidence_for_llm` | **closed** |
| AgentMiMo DS-6 | accepted，scope expanded | S3 `AcceptedEvidenceProducerEventRefMismatchError` 替代 `str(exc)` 比较；compact_material 不再二次打开 envelope | **closed** |
| AgentMiMo DS-7 | accepted only for P3-C typed evidence boundary | S3 `accepted_result_projection` 改用 strict shared payload accessor | **closed** |

### P3-C Plan Rejected Findings（2 项）

| Finding | 裁决 | 理由 | 状态 |
|---|---|---|---|
| AgentDS 22 | rejected-with-reason | `_USER_INPUT_TEXT_UNAVAILABLE` 与 accepted evidence query unavailable 是不同业务事实 | **保持 rejected** |
| AgentMiMo DS-8 | rejected-with-reason for P3-C | Tool Trace 与 accepted projection 各自 bounded display 是不同 projection 层 | **保持 rejected** |

### Plan Re-Review Fix Closure（P3-C-RR-PF-01 至 P3-C-RR-PF-05）

| Fix | 内容 | Aggregate 验证 |
|---|---|---|
| P3-C-RR-PF-01 | `CompactPipelineCompactArtifactView` 删除 `messages`，只保留 ref/digest | `compact_pipeline.py` protocol 只有 `compact_artifact_ref` / `compact_artifact_digest` 两个 property |
| P3-C-RR-PF-02 | `build_run_input_material_blocks()` 删除 compact.messages loop | source scan `_compact_material_source_ref` 零匹配；`compact.messages` 零匹配 |
| P3-C-RR-PF-03 | typed material 到 `CompactEvidenceBlock` / `EvidenceReadableItemVNext` exact no-rename mapping | 测试 `test_accepted_result_projection.py` 覆盖四字段 mapping |
| P3-C-RR-PF-04 | `_previous_compacted_*_vnext` 零匹配 scan | source scan 零匹配 |
| P3-C-RR-PF-05 | `llm_compaction.py` 三个 dead constants 删除 | source scan `_POST_COMPACT_*` 零匹配 |

### Final Plan Micro-Fix Closure（P3-C-RR2-PF-01）

| Fix | 内容 | Aggregate 验证 |
|---|---|---|
| P3-C-RR2-PF-01 | `_compact_material_source_ref()` 随 compact.messages loop 同一变更删除 | source scan 零匹配 |

## S1/S2/S3 Review Accepted Findings Closure

### S1 Review Findings

S1 code review（AgentMiMo）识别 3 项 findings，controller 裁决全部 accepted。S1 fix（Codex）修复后 re-review（AgentMiMo）确认全部 closed。S1 controller validation 确认 closure。

Aggregate 验证：
- S1 核心变更：`compact_payload.py` 新增 `ContextCompactedSemanticPayload` parser；`memory.py` / `durable/memory.py` 消费 typed candidate；ForwardIntent/Reference enum 字段收紧
- source scan：无残留 `_accepted_candidate_mapping`、candidate 字段常量或 mapping accessors
- 测试：`test_context_compact_events.py`、`test_memory_projection.py` 覆盖 roundtrip、invalid enum、digest mismatch

### S2 Review Findings

S2 code review（AgentMiMo）识别 2 项 findings，controller 裁决全部 accepted。S2 实现修复后 controller validation 确认 closure。

Aggregate 验证：
- S2 核心变更：compact material pair projector、`CompactArtifactView` 删除 `messages`、`RunInputBuilder.build()` 删除 `*compact.messages`、`estimate_post_compact_budget` 归 `context_budget`、`llm_compaction.py` dead constants 删除
- source scan：`_parse_previous_forward_intent_text`、`_parse_previous_reference_continuity_text`、`_previous_blocks_from_snapshot`、`_snapshot_*_texts`、`_candidate_*_texts`、`_PAYLOAD_FIELD_*`、`compact.messages`、`_compact_material_source_ref` 全部零匹配
- 测试：`test_run_input_builder.py` 覆盖 5 个命名 event-ref 安全测试；`test_context_budget.py` 覆盖 post-compact estimator；`test_llm_compaction.py` 覆盖 dead constant 零匹配

### S3 Review Findings

S3 code review（AgentMiMo）识别 2 项 findings，controller 裁决全部 accepted。S3 fix（Codex）修复后 re-review（AgentMiMo）确认全部 closed。S3 controller validation 确认 closure。

Aggregate 验证：
- S3 核心变更：`AcceptedToolEvidenceLLMMaterial` + `render_accepted_tool_evidence_for_llm` 统一 evidence renderer；`AcceptedEvidenceProducerEventRefMismatchError` 替代字符串协议；`RunInputMaterialBlock` 原子迁移到完整 evidence contract
- source scan：`accepted_evidence_envelope_from_payload` 在 `compact_material.py` 零匹配；`str(exc)` 在 `compact_material.py` 零匹配；`def _accepted_tool_evidence_content` / `def _accepted_evidence_readable_text` 全局零匹配
- 测试：`test_accepted_result_projection.py` 覆盖 llm_material、typed mismatch exception、strict accessor

## Cross-Slice Semantic Chain Audit

### 1. Compact Semantic Payload Chain

```
CONTEXT_COMPACTED persisted JSON
  -> compact_payload.parse_context_compacted_semantic_payload()  [唯一 parser]
     -> ContextCompactedSemanticPayload (typed view)
        -> durable/memory.py: MemoryProjectionEvent.compacted_semantics
           -> memory.py: project_conversation_memory_event() 消费 typed candidate
              -> snapshot JSON 写 enum .value
              -> RunInput memory sections
        -> compact_material.py: _load_accepted_compact_semantic_payload()
           -> pair projector 产生 blocks + CompactReadableViewVNext
           -> CompactMaterialPack.__post_init__ 校验 pair invariant
        -> run_input.py: inline repair adapter 调用唯一 parser
        -> context_events.py: validate_context_compacted_payload() 委托 parser
```

**审计结论**：链路闭环。唯一 parser 在 `compact_payload.py`；所有消费者通过 `ContextCompactedSemanticPayload` 消费 typed candidate；无下游二次 parse、无字符串 round-trip、无重复 candidate 字段常量。

### 2. Accepted Evidence LLM Material Chain

```
TOOL_RESULT_ACCEPTED envelope + raw outcome
  -> accepted_result_projection.project_accepted_tool_result()
     -> AcceptedToolResultProjection.llm_material: AcceptedToolEvidenceLLMMaterial | None
        -> durable/memory.py: MemoryProjectionEvent.accepted_tool_evidence
           -> memory.py: render_accepted_tool_evidence_for_llm(event.accepted_tool_evidence)
        -> compact_material.py: _accepted_tool_evidence_delta_blocks()
           -> RunInputMaterialBlock(accepted_tool_evidence=projection.llm_material)
              -> __post_init__ 校验 text == render_accepted_tool_evidence_for_llm(material)
        -> run_input.py: DurableAcceptedToolEvidenceMaterialProvider
           -> fallback RunInput material blocks
              -> render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)
  -> evidence.render_accepted_tool_evidence_for_llm()  [唯一 renderer]
     -> 四行固定文本：工具名称/查询语义/业务来源/工具结果
```

**审计结论**：链路闭环。唯一 renderer 在 `evidence.py`；memory/compact_material/run_input 三路径全部调用同一 renderer；`RunInputMaterialBlock.__post_init__` 强制 `text == renderer(material)` invariant；无重复 private renderer、无 envelope 二次解析。

### 3. Previous Compacted View Pair Chain

```
ContextCompactedSemanticPayload.accepted_candidate
  -> compact_material pair projector
     -> (blocks, CompactReadableViewVNext) 原子产生
     -> CompactMaterialPack.__post_init__ 校验 pair invariant
        -> _require_previous_compacted_view_pair()
           -> presence/count/kind/label/text/anchor-children 全部一一对应
  -> transform_previous_compacted_view_pair_for_recovery()
     -> 同步过滤 blocks + typed view
     -> 过滤后重新校验 pair invariant
  -> conversation_compact_input_vnext_from_material_pack()
     -> 直接使用 previous_compacted_readable_view
```

**审计结论**：链路闭环。blocks 与 typed view 从同一 `accepted_candidate` 原子派生；pair invariant 在 `CompactMaterialPack.__post_init__` 强制校验；tier2/tier3 只能通过唯一 `transform_previous_compacted_view_pair_for_recovery()` 过滤；无 string round-trip、无独立重建。

### 4. Event-Ref Equality Matrix

```
CompactArtifactView.compaction_event_ref
  + MemorySnapshotView.latest_compaction_event_ref
  -> _assert_compact_and_memory_compaction_refs_consistent()
     -> None/None: no-compact, 继续
     -> non-None/same: 继续
     -> non-None/None: MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)
     -> None/non-None: MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)
     -> non-None/different: MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)
```

**审计结论**：五格矩阵完整实现。测试 `test_run_input_builder.py` 覆盖全部 5 个命名测试。

### 5. Post-Compact Budget Chain

```
ContextCompactedSemanticPayload.accepted_candidate
  -> compact_payload.accepted_compact_business_texts(candidate)
     -> tuple[str, ...]（summary/fact/anchor title+child/intent/reference 文本）
  -> context_budget.estimate_post_compact_budget(
       compacted_business_texts=business_texts,
       current_input_text=current_input,
     )
     -> POST_COMPACT_BASE_MESSAGE_COUNT = 2（one-system envelope + current user message）
     -> 逐文本估算 + 固定 overhead
  -> compaction_operation 只调用上述函数，不持有纯估算实现
```

**审计结论**：链路闭环。`POST_COMPACT_BASE_MESSAGE_COUNT = 2` 由 `context_budget` 拥有；`accepted_compact_business_texts` 不含 diagnostics/refs/digests；`compaction_operation` 删除 `_budget_after_compact_candidate`。

## AGENTS.md Compliance Audit

### Docstring

所有新增/修改的公共类、函数、方法均提供完整中文 docstring，包含参数、返回值、异常。模块级 docstring 存在。

### Typing

- 禁止 `Any`、`object`、无类型参数/返回值：**通过**。所有签名严格类型化。
- 禁止 `hasattr`/`getattr` 逃避：**通过**。source scan 无相关使用。

### README Trigger

- `dayu/host/` 修改触发 `dayu/host/README.md` 更新：**已更新**（6 处变更，覆盖 Conversation Memory、RunInputBuilder、Context governance、accepted evidence、Memory-compact 关系）
- `tests/` 修改触发 `tests/README.md` 更新：**已更新**（P12.6 memory semantic smoke 条目更新）

### Pyright

```
0 errors, 0 warnings, 0 informations
```

### Coverage（逐文件 >= 80%）

| 文件 | Coverage |
|---|---|
| `compact_payload.py` | 87% |
| `context_events.py` | 93% |
| `memory.py` | 92% |
| `durable/memory.py` | 85% |
| `compaction.py` | 85% |
| `compact_material.py` | 86% |
| `compact_pipeline.py` | 93% |
| `run_input.py` | 88% |
| `context_budget.py` | 93% |
| `compaction_operation.py` | 83% |
| `llm_compaction.py` | 90% |
| `evidence.py` | 92% |
| `accepted_result_projection.py` | 94% |

### 无反向依赖

- `compact_payload.py` 只依赖 `compaction.py`、`durable/codec.py`（向下）
- `context_budget.py` 不依赖 `compaction_operation.py`（向下）
- `evidence.py` 不依赖 `accepted_result_projection.py`（向下）
- 无 `dayu.runtime` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 导入

### 无 Business Rule Fragile Branch

- enum 严格构造：`ForwardIntentTypeVNext(value)`、`ForwardIntentStatusVNext(value)`、`ReferenceContinuityReasonVNext(value)`、`FactEvidenceKindVNext(value)` 全部在 `compact_payload.py` 唯一 parser 中执行；非法值由 enum constructor 拒绝
- digest 校验：`ContextCompactedSemanticPayload.__post_init__` 强制 `accepted_candidate_digest == candidate.digest()`
- exact fields：`_require_exact_fields()` 强制 persisted shape 与 current schema 字段集合一致

## Source Scans

| Scan | 预期 | 结果 |
|---|---|---|
| `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|_parse_previous_forward_intent_text\|_parse_previous_reference_continuity_text` | 零匹配 | **零匹配** |
| `_previous_blocks_from_snapshot\|_snapshot_*_texts\|_candidate_*_texts` in `compact_material.py` | 零匹配 | **零匹配** |
| `def _previous_compacted_*_vnext` in `compact_material.py` | 零匹配 | **零匹配** |
| `str(exc).*ACCEPTED_EVIDENCE\|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` | 零匹配 | **零匹配** |
| `def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text` | 零匹配 | **零匹配** |
| `_PAYLOAD_FIELD_*` in memory/compact_material/run_input | 零匹配 | **零匹配** |
| `compact.messages\|messages=.*CompactArtifactView\|_compact_artifact_message_content` in `run_input.py` | 零匹配 | **零匹配** |
| `_compact_material_source_ref` in `run_input.py` | 零匹配 | **零匹配** |
| `CompactPipelineCompactArtifactView` 的 `messages` / `represented_evidence_refs` | 零匹配 | **零匹配** |
| `CompactPipelineCompactArtifactView` 的 `compact_artifact_ref` / `compact_artifact_digest` | 只匹配 ref/digest | **只匹配 ref/digest** |
| `accepted_evidence_envelope_from_payload\|str(exc)` in `compact_material.py` | 零匹配 | **零匹配** |
| `_POST_COMPACT_*` in `llm_compaction.py` | 零匹配 | **零匹配** |
| `tool_trace.py` diff | 空 | **空** |

## Findings

未发现实质性问题。

P3-C 跨 S1/S2/S3 语义链路审计通过：compact semantic parser、compact material budget overhead、accepted evidence typed material/renderer 三条链路均从同一真源派生，无下游二次 parse、无字符串协议、无旧 loose fields、无兼容 facade、无显示正确但持久化/trace/memory 错误。P3-C plan 中全部 7 项 accepted findings 已关闭；2 项 rejected findings 保持 rejected。S1/S2/S3 review accepted findings 全部关闭，无新 regression。

## Open Questions

无。

## Residual Risk

以下问题不属于 P3-C scope，标注为 residual：

1. **P3-E tool status fallback/raw outcome**：accepted tool status 的 fallback 优先级与 raw outcome 重建仍由 P3-E owner 处理。P3-C 不改变 status owner。
2. **P3-J EventLog schema/taxonomy/DDL**：`durable/schema.py` 删除了 `evidence_backed_fact_candidate_invalid` CHECK constraint value（无代码引用），但全局 EventLog taxonomy 闭集仍属 P3-J scope。
3. **非 P3-C 全仓问题**：`git diff --check` 报告 `docs/reviews/wu-semantic-ownership-01-p3-c-s1-code-review-ds.md:102` 有 trailing whitespace，属 review artifact 格式问题，不影响生产代码。

## 验证清单

### 已运行

| 验证项 | 结果 |
|---|---|
| 聚合测试（436 passed, 1 skipped） | **通过** |
| pyright（0 errors, 0 warnings, 0 informations） | **通过** |
| 逐文件 coverage（全部 >= 80%） | **通过** |
| import boundary check | **通过** |
| import boundary + weak typing guard tests（25 passed） | **通过** |
| tool trace regression tests（36 passed） | **通过** |
| public compact smoke tests（13 passed, 1 skipped） | **通过** |
| 全部 13 项 source scans | **通过** |
| `tool_trace.py` diff 为空 | **通过** |
| README 更新检查 | **通过** |

### 未运行

| 验证项 | 原因 |
|---|---|
| SQLite fresh bootstrap / schema migration | P3-C 不涉及 schema migration；`durable/schema.py` 只删除无引用的 CHECK value |
| 生产环境集成测试 | 非本次 review scope |
