# WU-SEMANTIC-OWNERSHIP-01 P3-C Aggregate Deep Review — AgentDS

## 结论

**PASS**

P3-C 三个 slice（S1/S2/S3）的 aggregate 语义链路闭合完整。所有 plan accepted findings 已关闭，S1/S2/S3 review findings 已全部 resolution 或认定为低严重度 non-blocking 观察。无新增回归，无语义所有权漂移。

---

## Scope

- **Mode**: Aggregate deep review（跨 S1/S2/S3 accepted commits）
- **Branch**: `phaseflow/host-issues-control`
- **Accepted commits**:
  - Plan: `0dcef803`
  - S1 implementation: `4df676f6`
  - S2 implementation: `9f266e4b`
  - S3 implementation: `4a2f9823`
  - S3 bookkeeping: `4c945391`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-c-aggregate-deepreview-ds.md`
- **Included scope**: `dayu/host/` 下所有 P3-C 实际变更的生产文件及其测试；P3-C plan 及 S1/S2/S3 review artifacts
- **Excluded scope**:
  - Untracked 文件：`docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/code-review-20260710-135625.md`、`docs/reviews/code-review-20260710-141049.md`
  - P3-E status fallback/raw outcome（assigned to P3-E）
  - P3-J schema/taxonomy/DDL（assigned to P3-J）
  - `dayu/host/tool_trace.py`（P3-C plan explicitly excludes）
- **Parallel review coverage**: 无（单人逐链路 aggregate deep review）

---

## Review Dimension 1: 跨 S1/S2/S3 语义链路审计

### 1.1 Compact semantic parser（S1 + S2 扩展消费）

**PASS。**

| 链路阶段 | 文件:行号 | 操作 | 状态 |
|---|---|---|---|
| LLM proposal → typed candidate | `llm_compaction.py` | `ConversationCompactOutputVNext` strict construction | ✓ S1 未改 |
| → persist | `context_events.py` | `build_context_compacted_payload` → `accepted_candidate.to_json()` + digest | ✓ |
| → persist validate | `compact_payload.py` | `parse_context_compacted_semantic_payload` 委托自 `validate_context_compacted_payload` | ✓ S1 |
| → memory event adapter | `durable/memory.py:400-401` | `_memory_projection_payload_view` → `parse_context_compacted_semantic_payload` | ✓ S1 |
| → inline repair adapter | `run_input.py:3202-3206` | `_memory_projection_event_from_row` → `parse_context_compacted_semantic_payload` | ✓ S1 |
| → memory projection | `memory.py:1268` | `compacted_semantics.accepted_candidate` → 五个 typed helper | ✓ S1 |
| → previous compacted view | `compact_material.py:2038,2073` | `_previous_compacted_view_pair_from_compacted_event` → typed pair projector | ✓ S2 |
| → tier2/tier3 degrade | `compact_material.py:975` | `transform_previous_compacted_view_pair_for_recovery` | ✓ S2 |
| → budget estimator | `compaction_operation.py:740` | `accepted_compact_business_texts(candidate)` → `estimate_post_compact_budget` | ✓ S2 |

**Audit 结论**：
- `parse_context_compacted_semantic_payload` 是所有下游消费者读取 persisted accepted candidate 的唯一入口。
- Enum 迁移（`ForwardIntentTypeVNext`/`ForwardIntentStatusVNext`/`ReferenceContinuityReasonVNext`）覆盖所有消费者：memory model（`memory.py:590-667`）、durable table 序列化（`durable/memory.py:1726,1730,1746`）、snapshot codec（`memory.py:2626,2760,2764,2644,2779,2781`）、LLM-facing 消息（`run_input.py:2390-2394,2411-2413`）。
- Old string round-trip helpers 全部删除，source scan 零匹配确认。
- `compact_material.py` / `run_input.py` 不再独立 parse accepted candidate。S2 删除了所有 `_candidate_*_texts()` helper、`_vnext_compact_candidate_semantic_lines()`、`_compact_artifact_message_content()`、以及重复的 `_PAYLOAD_FIELD_*` 常量族。

### 1.2 Compact material budget overhead（S2）

**PASS。**

- `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT = 2` 是唯一 ordinary post-compact owner（`context_budget.py:42`），带 one-system-envelope + current-input-user-message 推导注释。
- `estimate_post_compact_budget()`（`context_budget.py:494`）只接受纯文本参数（`compacted_business_texts` + `current_input_text`），无 caller override。
- `accepted_compact_business_texts()`（`compact_payload.py:161`）只返回五类业务文本，不含 diagnostics/code/labels/refs/digests。
- `compaction_operation.py` 不再定义 `_budget_after_compact_candidate()`、`_candidate_text_fragments()`、`_POST_COMPACT_BASE_MESSAGE_COUNT`。
- `llm_compaction.py` 中三个 `_POST_COMPACT_*` dead constants 已原地删除，零匹配 scan 确认。`llm_compaction.py` 不 import/re-export `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`。

### 1.3 Accepted evidence typed material / renderer（S3）

**PASS。**

- `AcceptedToolEvidenceLLMMaterial`（`evidence.py:131-165`）是唯一 typed LLM material。
- `render_accepted_tool_evidence_for_llm()`（`evidence.py:168-186`）是唯一 renderer，输出固定四行业务可读中文文本。
- `AcceptedEvidenceProducerEventRefMismatchError`（`evidence.py:105-128`）替代旧字符串常量协议。
- `AcceptedToolResultProjection` 新增 `llm_material`/`tool_call_requested_event_ref`/`source_locator_refs`（`accepted_result_projection.py:150-160`）。
- `_optional_payload_text()`（`accepted_result_projection.py:809`）strict accessor：字段存在但类型错误/空白 → `HostDurableError` fail closed。

---

## Review Dimension 2: 语义所有权漂移审计

### 2.1 Durable state → trace → memory → compact material → RunInput → LLM-facing text 同源链

**PASS。** 所有关键语义从同一真源派生：

| 语义事实 | First producer | Validator owner | Persistence owner | Projection owner | Consumers | 漂移？ |
|---|---|---|---|---|---|---|
| compact candidate 五类语义 | LLM compactor → `ConversationCompactOutputVNext` | `parse_context_compacted_semantic_payload` | `CONTEXT_COMPACTED.accepted_candidate` + digest | `ContextCompactedSemanticPayload` | memory / previous view / RunInput provenance / budget | 无 |
| forward intent type/status、reference reason | LLM candidate | `ForwardIntent*VNext` / `ReferenceContinuityReasonVNext` constructor | accepted candidate JSON enum → snapshot `.value` | 同一 parser → enum 恢复 | memory view / compact readable view / RunInput section | 无 |
| accepted compact LLM material | accepted candidate | memory policy cap/floor + snapshot codec | Conversation Memory snapshot (read model) | memory section renderer | ordinary RunInputBuilder (compact artifact provider 不再渲染第二份) | 无 |
| post-compact budget | accepted candidate business texts | `context_budget` pure estimator | EventLog diagnostic (派生记录) | candidate business text helper + budget estimator | compaction operation budget gate | 无 |
| accepted evidence durable facts | ToolRuntime accept barrier | `evidence.py` envelope codec + `accepted_result_projection` | `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` | `AcceptedToolEvidenceLLMMaterial` | memory / compact material / RunInput / Tool Trace (own display caps) | 无 |
| accepted evidence LLM 文本 | typed LLM material | material dataclass non-empty check + unique renderer | memory / runner input projection (派生记录) | `render_accepted_tool_evidence_for_llm` | memory recent evidence / ordinary protected tail / fallback RunInput | 无 |

**关键审计项**：

- **无下游二次 parse**：`compact_material.py` / `durable/memory.py` / `run_input.py` / `memory.py` 中 `accepted_evidence_envelope_from_payload` 调用零匹配。
- **无字符串协议**：`ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 字符串常量零匹配；`str(exc)` 比较代码零匹配。
- **无旧 loose fields**：`MemoryProjectionEvent` 以 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None` 替代 `evidence_query_text`/`evidence_tool_name`/`evidence_result_text`/`evidence_source_text` 四个 loose field。`RunInputMaterialBlock` 同理。
- **无兼容 facade**：无 re-export wrapper、无旧 shape compatibility 字段、无 `UNKNOWN` enum fallback。
- **无 dual renderer**：`_accepted_tool_evidence_content` / `_accepted_evidence_readable_text` 零匹配 — 三套旧 private renderers 已完全删除。
- **compact artifact provider 不再生成 LLM material**：`CompactArtifactView` 无 `messages` 字段；`DurableCompactArtifactProvider._load_compact_artifact_tx()` 不构造 `SystemMessage`。ordinary RunInput 中 accepted compact 语义只来自 memory projection。
- **显示正确 + 持久化正确 + trace 正确**：memory snapshot、compact material pack、RunInput LLM messages 都从同一个 `accepted_candidate` 或 `AcceptedToolEvidenceLLMMaterial` 派生。block text 逐字等于 `render_accepted_tool_evidence_for_llm(material)`。

### 2.2 未检测到的漂移

无。全 host 源代码扫描未发现绕过 typed contract 的裸 JSON 访问、二次 renderer、兼容 shim 或 loose parsing。

---

## Review Dimension 3: Plan accepted findings 关闭状态

| Plan Finding | 裁决 | S1 关闭？ | S2 关闭？ | S3 关闭？ | 最终状态 |
|---|---|---|---|---|---|
| AgentDS 6 (三套 LLM renderer) | accepted | — | — | ✓ memory/compact/run_input → 唯一 renderer | CLOSED |
| AgentDS 14 (budget estimator misplaced) | accepted | — | ✓ budget → `context_budget`；operation 只编排 | — | CLOSED |
| AgentDS 16 (enum read side weak) | accepted | ✓ typed enum in parser + snapshot codec + all consumers | — | — | CLOSED |
| AgentDS 22 (USER_INPUT_TEXT_UNAVAILABLE) | rejected-with-reason | — | — | — | N/A |
| AgentMiMo DS-1 (candidate parser missing) | accepted | ✓ `parse_context_compacted_semantic_payload` | ✓ all consumers migrated | — | CLOSED |
| AgentMiMo DS-5 (evidence text assembly dups) | accepted | — | — | ✓ `render_accepted_tool_evidence_for_llm` sole renderer | CLOSED |
| AgentMiMo DS-6 (string exc protocol) | accepted | — | — | ✓ `AcceptedEvidenceProducerEventRefMismatchError` typed | CLOSED |
| AgentMiMo DS-7 (lenient `_optional_text`) | accepted | — | — | ✓ `_optional_payload_text` strict accessor | CLOSED |
| AgentMiMo DS-8 (Tool Trace helper similarity) | rejected-with-reason | — | — | — | N/A |

**7 个 accepted findings 全部关闭。** 2 个 rejected 按 plan 裁决不纳入 P3-C。

### Plan fix closure 确认

| Plan Fix | 描述 | 关闭状态 |
|---|---|---|
| P3-C-PF-01 | 6.3 compact material pack exact invariant + tier2/tier3 pair transform | CLOSED (S2) |
| P3-C-PF-02 | 6.4 event-id equality + MemoryProjectionRepairRequired + compact.messages 删除 | CLOSED (S2) |
| P3-C-PF-03 | 6.6 RunInputMaterialBlock evidence contract + no-rename mapping | CLOSED (S3) |
| P3-C-PF-04 | 6.5 POST_COMPACT_BASE_MESSAGE_COUNT = 2 推导 + owner constant + drift test | CLOSED (S2) |
| P3-C-PF-05 | 7.1 / S2 / 9 节 no-compact/equal/三种 mismatch 命名测试 | CLOSED (S2) |
| P3-C-PF-06 | S3 删除 envelope 二次解析和 str(exc) catch | CLOSED (S3) |
| P3-C-RR-PF-01 | CompactPipelineCompactArtifactView.messages 删除 | CLOSED (S2) |
| P3-C-RR-PF-02 | build_run_input_material_blocks compact.messages loop 删除 | CLOSED (S2) |
| P3-C-RR-PF-03 | typed material → CompactEvidenceBlock / EvidenceReadableItemVNext no-rename mapping | CLOSED (S3) |
| P3-C-RR-PF-04 | _previous_compacted_*_vnext 零匹配 scan | CLOSED (S2) |
| P3-C-RR-PF-05 | llm_compaction.py 三个 dead constants 仅原地删除 | CLOSED (S2) |
| P3-C-RR2-PF-01 | _compact_material_source_ref 随 loop 删除 + __run_input_message_content 保留 | CLOSED (S2) |

**12 个 plan fix items 全部关闭。**

---

## Review Dimension 4: S1/S2/S3 review finding 关闭状态

### S1 DS Review Findings

| Finding | Severity | 当前状态 |
|---|---|---|
| 1-未修复-中: `_parse_fact` 的 evidence_labels 唯一性校验延迟到 typed constructor | 中 | **OPEN（非阻塞）** — 错误消息路径精度问题仍存在。`compact_payload.py:272` 调用 `_required_text_list` 不校验唯一性，唯一性校验延迟到 `EvidenceBackedFactCandidateVNext.__post_init__`（`compaction.py:1203`）。正常 producer 路径不产生重复标签，仅影响 operator 排障效率。 |
| 2-未修复-低: `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 无生产者 | 低 | **CLOSED** — 枚举值已从 `MemoryDiagnosticReason` 中完整移除。当前 `MemoryDiagnosticReason`（`memory.py:161-175`）不包含该值。 |
| 3-未修复-低: `accepted_compact_business_texts` 无生产消费者 | 低 | **CLOSED** — S2 中 `compaction_operation.py:740` 接入该函数作为 budget estimator 的唯一业务文本来源。 |

### S2 DS Review Findings

| Finding | 状态 |
|---|---|
| 无 findings | **PASS** |

### S3 DS Review Findings

| Finding | Severity | 当前状态 |
|---|---|---|
| F-01: evidence material/renderer import 路径不一致 | 低 | **CLOSED** — 当前所有消费者均从 `dayu.host.evidence` 直接 import。`durable/memory.py:46`、`compact_material.py:59-60`、`compact_pipeline.py:36`、`run_input.py:129` 全部统一。`accepted_result_projection.py` 以私有名 `_AcceptedToolEvidenceLLMMaterial` import 供内部使用，不外露为 re-export。 |
| F-02: `_pack_evidence_blocks` 中 `size_units` 统计口径变更 | 低 | **OPEN（非阻塞）** — `size_units=len(material.result_text)`（`compact_material.py:2759`）替代旧 `size_units=len(block.text)`。语义从"完整四行 renderer 长度"变为"结果正文长度"。变更方向正确（size_units 表示内容尺寸，result_text 是主体），且未被 plan 显式记录。下游消费者需确认适配；当前无已知错误。 |

### S1/S2/S3 Rereview Findings

所有 rereview 均 PASS 或 accepted，无残留阻塞性 finding。

---

## Review Dimension 5: AGENTS.md 合规性

| 检查项 | 状态 | 证据 |
|---|---|---|
| 函数 docstring（中文，含参数/返回/异常） | ✓ | `parse_context_compacted_semantic_payload`、`render_accepted_tool_evidence_for_llm`、`estimate_post_compact_budget` 等关键函数均含完整中文 docstring |
| 类/模块中文概览 docstring | ✓ | `ContextCompactedSemanticPayload`、`AcceptedToolEvidenceLLMMaterial`、`CompactArtifactView` 等均含中文 docstring |
| 无 `Any`/`object`/无类型参数/无类型返回值 | ✓ | Key P3-C 文件无 `Any` import；`object` 仅在 docstring 中作为 "JSON object" 说明使用 |
| 无 `hasattr`/`getattr` 逃避 | ✓ | `compact_payload.py`、`evidence.py`、`accepted_result_projection.py` 零匹配 |
| 无反向依赖 | ✓ | `evidence.py`、`accepted_result_projection.py`、`compact_payload.py`、`context_budget.py` 均不 import `dayu.service`/`dayu.ui`/`dayu.engine` |
| 无 God object/function/dataclass | ✓ | 只新增两个窄 typed value（`ContextCompactedSemanticPayload`、`AcceptedToolEvidenceLLMMaterial`）和一个专用异常 |
| 无兼容性代码 | ✓ | 无兼容 re-export、wrapper、facade；旧 field/enum/renderer 已删除不保留 alias |
| 无 business rule fragile branch | ✓ | 五格 repair matrix 由单一 `_require_compact_memory_event_ref_consistency` 实现；tier degradation 只走 `transform_previous_compacted_view_pair_for_recovery`；无 hardcoded 特殊值分支 |
| pyright | ✓ | `0 errors, 0 warnings, 0 informations` |
| 单文件 coverage ≥ 80% | ✓ | evidence 92%、accepted_result_projection 94%、compact_payload 91%、compact_material 86%、compact_pipeline 94%、compaction_operation 94%、context_budget 93%、llm_compaction 90%、memory 92%、durable/memory 85%、run_input 88% |
| README trigger | ✓ | `dayu/host/README.md` 已更新（Conversation Memory、RunInputBuilder、accepted result、context budget 条目）；`tests/README.md` 按需更新；根 README/`dayu/README.md` 未触发 |

---

## Review Dimension 6: Residual 分类确认

| 项目 | 归属 | P3-C 阻塞？ |
|---|---|---|
| P3-E accepted tool status fallback/raw outcome reconstruction | P3-E | 否 — P3-C 不改变 status owner |
| P3-J 全局 EventLog schema/taxonomy/DDL | P3-J | 否 — P3-C 不触及 DDL |
| `tool_trace.py` truncation/display 与 accepted projection 的 helper 相似 | rejected (plan AgentMiMo DS-8) | 否 |
| S1 Finding 1: fact label uniqueness 错误路径精度 | P3-C deferred low-severity | 否 — 正常路径不受影响 |
| S3 F-02: size_units 口径变更 | P3-E follow-up | 否 — 语义方向正确 |
| `durable/memory.py` 85% / `compact_material.py` 86% coverage gap | P3-E/P3-J | 否 — 均在 ≥80% 阈值以上，gap 来自 integrity scan 路径（非 S3 引入） |

无 P3-C blocking residual。

---

## Findings

### 1-未修复-低-`_parse_fact` 中 evidence_labels/source_labels 唯一性校验延迟到 typed constructor 导致错误消息丢失路径上下文

- **入口/函数**: `_parse_fact()` → `EvidenceBackedFactCandidateVNext.__post_init__`
- **文件(行号)**: `compact_payload.py:269-277`（parser）、`compaction.py:1194-1212`（constructor）
- **输入场景**: 持久化 fact candidate JSON 的 `evidence_labels` 或 `source_labels` 包含重复字符串（正常 producer 不产生，但手工修复/旧版本 bug/DB 直接写入可能产生）
- **实际分支**: `_parse_fact` → `_required_text_list` 不校验唯一性 → 传给 `EvidenceBackedFactCandidateVNext(...)` → `__post_init__` 中 `_require_non_empty_unique_string_tuple` → `ValueError` 不含 fact index 路径
- **预期行为**: parser 在构造 typed object 前校验唯一性，错误消息包含 `evidence_backed_facts[{index}]` 路径前缀，与同 parser 其他校验的错误消息风格一致
- **直接证据**: `compact_payload.py:272` 的 `_required_text_list` 只检查类型/空值不检查唯一性；`compaction.py:1203-1206` 的唯一性检查消息固定无路径；对比同文件 `_parse_answer_anchor_child`（line 340-342）在 typed constructor 前已带路径校验
- **影响**: operator 排障效率下降——不知道错误发生在第几个 fact。正常路径不受影响
- **建议改法和验证点**: 在 `_parse_fact` 中 `_required_text_list` 后增加显式唯一性检查，错误消息格式统一为 `f"{path}.evidence_labels must be unique non-empty text list"`。新增单测：构造含重复 evidence_labels 的 fact JSON，断言 `ValueError` 消息包含 `evidence_backed_facts[0]` 路径
- **修复风险（低）**: 仅改进错误消息，不改通过/拒绝逻辑
- **严重程度（低）**: 正常路径不受影响；仅 operator 排障精度下降

### 2-未修复-低-`_pack_evidence_blocks` 中 `size_units` 统计口径从完整四行 renderer 变为纯 result_text

- **入口/函数**: `_pack_evidence_blocks()`
- **文件(行号)**: `compact_material.py:2759`
- **输入场景**: 任意 accepted tool evidence block 被 pack 为 `CompactEvidenceBlock`
- **实际分支**: `size_units=len(material.result_text)` — 仅结果文本长度
- **预期行为**: 旧代码使用 `size_units=len(block.text)` — 完整四行 renderer（工具名称 + 查询语义 + 业务来源 + 工具结果）长度
- **直接证据**: diff 中 `size_units=len(block.text)` → `size_units=len(material.result_text)`（`compact_material.py:2759`）。对应 field mapping 中 `raw_result_text = material.result_text`
- **影响**: `size_units` 值比旧值小约三行标签固定字符，语义从"完整 evidence block 文本长度"变为"结果正文长度"。变更方向正确（result_text 是 evidence 内容主体），但未被 plan section 显式记录。下游 budget estimation 若依赖该值可能出现微小偏移
- **建议改法和验证点**: 不需要回退。在 P3-E 中确认 `CompactEvidenceBlock.size_units` 所有消费者已适配新口径（或无需适配）。验证：rg `CompactEvidenceBlock` 所有消费者的 `size_units` 使用
- **修复风险（低）**: 无需回退，仅需确认下游消费者
- **严重程度（低）**: 无已知错误，纯 documentation/verification gap

---

## Open Questions

无。

---

## Residual Risk

1. **S1 Finding 1（低）**: `_parse_fact` evidence_labels 唯一性错误消息缺失路径上下文。operator 排障效率轻微下降。正常路径无影响。
2. **S3 F-02（低）**: `CompactEvidenceBlock.size_units` 口径变更。建议 P3-E follow-up 确认所有消费者。
3. **Coverage gap**: `durable/memory.py` 85%、`compact_material.py` 86%（偏低的两个文件），gap 来自 integrity scan 路径而非 P3-C 引入。建议 P3-E 或 P3-J 补充。
4. **P3-E scope（非 P3-C）**: accepted tool status fallback/raw outcome reconstruction。
5. **P3-J scope（非 P3-C）**: 全局 EventLog schema/taxonomy/DDL closed-set。

---

## 验证执行记录

以下由本 reviewer 在 aggregate review 期间独立运行：

| 验证项 | 命令 | 结果 |
|---|---|---|
| Aggregate affected tests | `pytest tests/host/test_*` (full affected matrix, 12 files) | **436 passed, 1 skipped** |
| Import/typing boundary | `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | **25 passed** |
| pyright | `pyright dayu/host/ tests/host/` | **0 errors, 0 warnings, 0 informations** |
| Coverage (11 changed modules) | `coverage report` (per-file, all ≥80%) | **90% aggregate** |
| evidence.py | per-file coverage | **92%** |
| accepted_result_projection.py | per-file coverage | **94%** |
| compact_payload.py | per-file coverage | **91%** |
| compact_material.py | per-file coverage | **86%** |
| compact_pipeline.py | per-file coverage | **94%** |
| compaction_operation.py | per-file coverage | **94%** |
| context_budget.py | per-file coverage | **93%** |
| llm_compaction.py | per-file coverage | **90%** |
| memory.py | per-file coverage | **92%** |
| durable/memory.py | per-file coverage | **85%** |
| run_input.py | per-file coverage | **88%** |
| Source scan: old candidate parsers | `rg '_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines' dayu/host/` | **零匹配** |
| Source scan: string round-trip helpers | `rg '_previous_blocks_from_snapshot\|_snapshot_.*_texts\|_candidate_.*_texts' dayu/host/compact_material.py` | **零匹配** |
| Source scan: dead previous_compacted helpers | `rg 'def _previous_compacted_.*_vnext' dayu/host/compact_material.py` | **零匹配** |
| Source scan: string exception protocol | `rg 'ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH\|str\(exc\).*ACCEPTED_EVIDENCE' dayu/host/` | **零匹配** |
| Source scan: dead helpers | `rg '_compact_material_source_ref' dayu/host/run_input.py` | **零匹配** |
| Source scan: compact.messages | `rg 'compact\.messages\|_compact_artifact_message_content' dayu/host/run_input.py` | **零匹配** |
| Source scan: llm_compaction dead constants | `rg '_POST_COMPACT_' dayu/host/llm_compaction.py` | **零匹配** |
| Source scan: duplicate evidence renderers | `rg 'def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text' dayu/host/` | **零匹配** |
| Source scan: payload field constants in consumers | `rg '_PAYLOAD_FIELD_*' dayu/host/memory.py dayu/host/compact_material.py dayu/host/run_input.py` | **零匹配** |
| Source scan: envelope parse in consumers | `rg 'accepted_evidence_envelope_from_payload' dayu/host/{compact_material,durable/memory,run_input,memory}.py` | **零匹配** |
| P3-C CompactPipelineCompactArtifactView protocol | scoped scan `sed` | **仅 compact_artifact_ref + compact_artifact_digest** |
| tool_trace.py unchanged | `git diff -- dayu/host/tool_trace.py` | **空** |
| Import consistency (evidence material) | `rg` all consumers | **全部从 `dayu.host.evidence` import** |
| No reverse dependencies | `ast` scan key P3-C files | **零反向依赖** |
| No hasattr/getattr in key files | `rg` compact_payload/evidence/accepted_result_projection | **零匹配** |
| No Any import in key files | `rg` compact_payload/evidence/accepted_result_projection/context_budget/compact_material | **零匹配** |
| Whitespace | `git diff --check 0dcef803^..4c945391` | **仅 1 处 trailing whitespace 在 review doc（非生产代码）** |
| Post-compact budget owner | `rg 'POST_COMPACT_BASE_MESSAGE_COUNT'` | **仅 context_budget.py（owner）** |
| accepted_compact_business_texts 消费者 | `rg 'accepted_compact_business_texts' dayu/host/` | **compaction_operation.py:740** |

以下验证未独立运行（信任 S1/S2/S3 controller validation 结果）：

- `python -c 'import dayu.host; import dayu.host.memory; ...'`（import smoke）
- `git diff --check`（S1/S2/S3 各自已通过）
