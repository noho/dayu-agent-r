# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-C S1

## Scope

- **Mode**: current changes（workspace diff）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: HEAD（当前未提交 workspace changes）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-code-review-ds.md`
- **Included scope**（仅 P3-C S1 生产/测试/README）:
  - `dayu/host/compact_payload.py` — 新增 512 行严格 parser、`ContextCompactedSemanticPayload`、`accepted_compact_business_texts`
  - `dayu/host/context_events.py` — `validate_context_compacted_payload` 委托到 parser，废除 `_validate_vnext_candidate_payload` / `_validate_mapping_list`
  - `dayu/host/durable/memory.py` — `_MemoryProjectionPayloadView` 新增 `compacted_semantics` 字段；`_forward_intent_item_json_value` / `_reference_continuity_item_json_value` enum `.value` 序列化
  - `dayu/host/memory.py` — `ForwardIntent.intent_type/status` 从 `str` → `ForwardIntentTypeVNext`/`ForwardIntentStatusVNext`；`ReferenceContinuityItem.reason` 从 `str` → `ReferenceContinuityReasonVNext`；`MemoryProjectionEvent` 新增 `compacted_semantics` 字段与 pairing invariant；compact 五类 helper 改为消费 typed candidate；移除 `_fact_candidate_invalid_diagnostic` helper 与 23 个 `_PAYLOAD_FIELD_*` 常量
  - `dayu/host/run_input.py` — `_memory_projection_event_from_row` 对 CONTEXT_COMPACTED 调用 parser；LLM-facing `forward_intent`/`reference_continuity` 消息改用 `.value`
  - `dayu/host/README.md` — 一行 compact read boundary 描述更新
  - `tests/host/test_context_compact_events.py` — 新增 7 个 parser 测试（roundtrip、enum 拒绝、shape 拒绝、ordinal 拒绝、未知字段拒绝、digest mismatch）
  - `tests/host/test_memory_projection.py` — 测试工厂从裸 dict 迁到 typed constructor；新增 snapshot codec enum 拒绝测试；新增 `test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint`
  - `tests/host/test_run_input_builder.py` — `_compact_payload` helper 从裸 dict 迁到 `build_context_compacted_payload`；LLM-facing 断言适配 `.value`
  - `tests/host/memory_snapshot_factories.py` — enum 字面量 → typed enum
  - `tests/host/test_compact_material.py` — enum 字面量 → typed enum
- **Excluded scope**:
  - 未跟踪文件：`docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、既有 code-review artifacts
  - `compact_material.py`（不在当前 diff，属 P3-C 后续 slice）
  - `context_budget.py` / `compaction_operation.py` budget estimator 迁移（属 P3-C 后续 slice）
  - 非 S1 范围的 design docs、control doc 修改
- **Design 真源**: `docs/host/design.md` 第 23-25 节；`docs/engine/design.md` 第 1、4、14、15 节
- **Accepted plan commit**: `0dcef803`
- **Controller artifacts**: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-controller-validation.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-s1-implementation-codex.md`
- **Parallel review coverage**: 无（单人 deep review，全链路走读）

## Adversarial Propagation Audit

以下按语义从产生到消费逐段审计。

### 1. `ConversationCompactOutputVNext` 产生 → 持久化 → 恢复 → 消费

| 阶段 | 文件:行号 | 操作 |
|------|-----------|------|
| 产生 | `compaction.py:1480-1494` | `ConversationCompactOutputVNext.to_json()` 输出七字段 JSON |
| 持久化写入 | `context_events.py:314` | `build_context_compacted_payload` 将 `accepted_candidate.to_json()` 存入 `accepted_candidate` 字段，`accepted_candidate.digest()` 存入 `accepted_candidate_digest` |
| 写入校验 | `context_events.py:348` | `validate_context_compacted_payload` → `parse_context_compacted_semantic_payload(payload)` |
| 持久化读取（projection runner） | `durable/memory.py:400-401` | `_memory_projection_payload_view` → `parse_context_compacted_semantic_payload(event.payload)` |
| 持久化读取（inline repair） | `run_input.py:3202-3206` | `_memory_projection_event_from_row` → `parse_context_compacted_semantic_payload(payload)` |
| Memory projection 消费 | `memory.py:1268` | `compacted_semantics.accepted_candidate` → 五个 typed helper |
| RunInput LLM 消息 | `run_input.py:2390-2394` | `intent.intent_type.value` / `intent.status.value` |
| RunInput LLM 消息 | `run_input.py:2411-2413` | `item.reason.value` |
| Durable table 序列化 | `durable/memory.py:1726,1730,1746` | `item.intent_type.value` / `item.status.value` / `item.reason.value` |
| Snapshot JSON 序列化 | `memory.py:2626,2760,2764` | `item.reason.value` / `item.intent_type.value` / `item.status.value` |
| Snapshot JSON 反序列化 | `memory.py:2644,2779,2781` | `ReferenceContinuityReasonVNext(str)` / `ForwardIntentTypeVNext(str)` / `ForwardIntentStatusVNext(str)` |

**审计结论**：
- Parser 与 `to_json()` 字段名精确对应。`ConversationCompactOutputVNext.to_json()` 的七字段集合 `{schema_version, session_summary, evidence_backed_facts, answer_anchors, forward_intents, reference_continuity_items, diagnostics}` 与 `_CANDIDATE_FIELDS` frozenset 完全一致。每个子类型的 field set 与对应 `to_json()` 返回 key 集合完全一致。
- Enum 值在产生侧由 `StrEnum.value` 写入，在 parser 侧由 `StrEnum(str_value)` 恢复。StrEnum 的构造对非法值 fail-closed（抛出 `ValueError`），不会产生 `UNKNOWN` fallback。
- Digest 校验链完整：`accepted_candidate_digest` 在 build 时由 `candidate.digest()` 计算，parser 在 `ContextCompactedSemanticPayload.__post_init__` 中与 `accepted_candidate.digest()`（同一算法 `sha256_digest_json(to_json())`）比对。Roundtrip 保真度依赖 `parse → typed → to_json()` 与原始 JSON 的 canonical form 一致性。经逐字段验证，parser 读取的字段值与 `to_json()` 写入的字段值类型一致，不存在 int/float、None/null、bool/int 歧义。
- `_require_exact_fields` 同时拒绝 missing 和 unknown 字段，确保旧 schema alias 不会静默通过。
- No second schema truth：所有 consumer 的 candidate 字段读取路径最终追溯到 `parse_context_compacted_semantic_payload` → `_parse_persisted_candidate`，没有绕过它的裸 JSON 字段访问。

### 2. `ForwardIntent` / `ReferenceContinuityItem` enum 迁移

| 阶段 | 旧类型 | 新类型 |
|------|--------|--------|
| `ForwardIntent.intent_type` | `str` | `ForwardIntentTypeVNext` |
| `ForwardIntent.status` | `str` | `ForwardIntentStatusVNext` |
| `ReferenceContinuityItem.reason` | `str` | `ReferenceContinuityReasonVNext` |

- 生产写入侧（`_forward_intents_from_accepted_event`、`_reference_continuity_from_accepted_event`）从 typed `ForwardIntentCandidateVNext.intent_type`（已是 StrEnum）直接赋值 → 类型一致。
- Durable table 序列化（`durable/memory.py`）从 `item.intent_type` → `item.intent_type.value`，输出不变（StrEnum.value 等于旧 str 值）。
- Snapshot JSON 序列化/反序列化（`memory.py`）同样 `.value` 写入、`StrEnum(str)` 恢复 → consistent。
- LLM-facing 消息（`run_input.py`）从 `intent.intent_type` → `intent.intent_type.value`，输出不变。
- Memory snapshot factory（test）从裸字符串 `"follow_up"` → `ForwardIntentTypeVNext.NEXT_STEP_NOTE`，因为 `"follow_up"` 从未是合法 enum 值——旧测试 factory 绕过了 enum 契约，生产数据始终使用合法 enum 值。

**审计结论**：enum 迁移完整覆盖所有消费者（memory model、durable table、snapshot codec、LLM message、test factories）。不存在混合 `str`/`StrEnum` 使用。

### 3. `MemoryProjectionEvent.compacted_semantics` pairing invariant

- `MemoryProjectionEvent.__post_init__` 强制：`event_type == CONTEXT_COMPACTED` → `compacted_semantics is not None`；其他 event_type → `compacted_semantics is None`。
- Durable adapter（`durable/memory.py:_memory_projection_event_from_view`）对所有 event_type 显式设置 `compacted_semantics`，不使用默认值。
- Inline repair adapter（`run_input.py:_memory_projection_event_from_row`）对 CONTEXT_COMPACTED 调用 parser，其他 event_type 传 `None`。
- `project_conversation_memory_event` 在处理 CONTEXT_COMPACTED 分支前二次检查 `compacted_semantics is None` → raise。

**审计结论**：invariant 在生产路径与测试路径一致执行，不存在默认值绕过的路径。

### 4. Anchor children / ordinal 完整链

- 产生：`AnswerAnchorCandidateVNext.to_json()` → `anchor_items` 数组中每个 child 含 `display_text` 与可选 `ordinal`。
- Parser：`_parse_answer_anchor_child` → `_required_optional_non_negative_int(child, "ordinal")` 允许 None 或非负整数，拒绝 bool 和负数。
- Memory projection：`_answer_anchors_from_accepted_event` → `AnswerAnchorChild(display_text=child.display_text, ordinal=child.ordinal)` 逐 child 传递。
- 旧 `compact_material.py` 的 previous view 只保留 anchor title 并合成单一同名 child（丢原 children）——这个问题**不在 S1 diff 范围内**，`compact_material.py` 本次未修改。

**审计结论**：S1 parser 正确恢复完整 children 与 ordinal。下游消费者（memory projection）正确传递。`compact_material.py` 的 child 丢失问题是已知 P3-C 后续 slice 的工作。

## Findings

### 1-未修复-中-`_parse_fact` 的 `evidence_labels`/`source_labels` 唯一性校验延迟到 typed constructor，错误消息丢失 fact 索引路径上下文

- **入口/函数**: `_parse_fact()` → `EvidenceBackedFactCandidateVNext.__post_init__`
- **文件(行号)**: `compact_payload.py:269-277`（parser 侧）、`compaction.py:1194-1212`（constructor 侧）
- **输入场景**: 持久化的 fact candidate JSON 中 `evidence_labels` 或 `source_labels` 列表包含重复字符串（例如 `["e1", "e1"]`）。正常 producer 路径不会产生此数据（`EvidenceBackedFactCandidateVNext.__post_init__` 自身已做唯一性校验），但直接 DB 操作、旧版本 bug 或手工修复可能产生。
- **实际分支**: `_parse_fact` 调用 `_required_text_list(fact, _FIELD_EVIDENCE_LABELS)` 返回保留重复的 tuple → 传给 `EvidenceBackedFactCandidateVNext(...)` → `__post_init__` 调用 `_require_non_empty_unique_string_tuple(self.evidence_labels, ...)` → `ValueError("EvidenceBackedFactCandidateVNext.evidence_labels must be unique")`。
- **预期行为**: parser 应在构造 typed object 之前校验唯一性，并在错误消息中包含 `evidence_backed_facts[{index}]` 路径前缀（与其他 parser 校验的错误消息风格一致，参见 `_require_exact_fields` 的 `path` 参数用法）。
- **实际行为**: `ValueError` 从 typed constructor 抛出，消息不含 fact index 或 JSON path。操作员排查时只知道 "某个 fact 的 evidence_labels 有重复"，不知道是第几个 fact。
- **直接证据**: 
  - `compact_payload.py:272`: `_required_text_list(fact, _FIELD_EVIDENCE_LABELS)` — 不检查唯一性（行 778-797，只检查 `isinstance(item, str) or item.strip() == ""`）。
  - `compaction.py:1203-1206`: `_require_non_empty_unique_string_tuple(self.evidence_labels, ...)` — 唯一性检查在此处，消息固定不含路径。
  - 对比同文件 `_parse_answer_anchor_child`（行 340-342）在调用 typed constructor 前已用 `_require_exact_fields(child, _ANCHOR_CHILD_FIELDS, path=path)` 带上完整路径。`_parse_fact` 只构造了 `path`（行 268）但未在证据标签校验中使用。
- **影响**: 数据损坏排查时错误定位精度下降；不影响正常路径（正常 producer 不产生重复标签）。仅影响 operator 排障效率。
- **建议改法和验证点**:
  1. 在 `_parse_fact` 中，`_required_text_list` 后增加显式唯一性检查，或在 `_required_text_list` 内部加入 `unique: bool = False` 参数。
  2. 错误消息格式统一为 `f"{path}.evidence_labels must be unique non-empty text list"`。
  3. 同样适用于 `source_labels`（`_require_unique_string_tuple` 在 typed constructor 中的校验，但 parser 未前置检查）。
  4. 新增单测：构造含重复 evidence_labels 的 fact JSON，断言 `ValueError` 消息包含 `evidence_backed_facts[0]` 路径。
- **修复风险（低）**: 仅改进错误消息，不改动通过/拒绝逻辑。
- **严重程度（中）**: 正常路径不受影响，但 operator 排障效率下降，与 parser 其他校验的错误消息质量不一致。

### 2-未修复-低-`MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 枚举值无生产者

- **入口/函数**: `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`
- **文件(行号)**: `memory.py:160`（定义）、`memory.py:2873-2904`（已删除的 `_fact_candidate_invalid_diagnostic` helper）
- **输入场景**: 任何触发 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` diagnostic 的代码路径。
- **实际分支**: 该 diagnostic reason 的唯一生产者 `_fact_candidate_invalid_diagnostic()` 已被删除。空 `evidence_labels` 现在由 parser 在边界处以 `ValueError` 拒绝，不再进入 memory projection。其他所有 `MemoryDiagnosticReason` 枚举值（`BUDGET_LIMIT_REACHED`、`ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE`、`UNSUPPORTED_EVENT_TYPE` 等）均有活跃生产者。
- **预期行为**: 枚举值要么有至少一个生产者，要么明确标注为 `# reserved, no longer produced since P3-C S1`。
- **实际行为**: 枚举值定义存在但永远不会被实例化。如果有代码按枚举值做 switch/dispatch，该分支永久不可达——当前没有这种代码，但未来维护者可能误用。
- **直接证据**:
  - `memory.py:160`: 枚举值定义。
  - `git diff`: `_fact_candidate_invalid_diagnostic` 函数（旧 `memory.py:2898-2924`）被完整删除。
  - `rg EVIDENCE_BACKED_FACT_CANDIDATE_INVALID dayu/` 仅在枚举定义处命中。
- **影响**: 低——当前无消费者依赖此枚举值。但如果后续 slice 重新引入 fact candidate 校验（例如空 claim_text 校验），开发者可能复用此枚举值而不知道其 helper 已被删除，导致重复造轮子或行为不一致。
- **建议改法和验证点**:
  1. 在枚举值上方加注释 `# reserved — produced by _fact_candidate_invalid_diagnostic prior to P3-C S1; now rejected at parser boundary`。
  2. 或将枚举值标记为 deprecated 并在下一个 major schema version 移除。
- **修复风险（低）**: 仅注释变更。
- **严重程度（低）**: 不影响正确性，仅影响代码可维护性。

### 3-未修复-低-`accepted_compact_business_texts` 定义后无生产消费者

- **入口/函数**: `accepted_compact_business_texts()`
- **文件(行号)**: `compact_payload.py:171-192`
- **输入场景**: 任何需要从 accepted candidate 提取纯业务文本用于 budget 估算或 LLM 上下文的场景。
- **实际分支**: 函数仅在测试中被调用（`test_context_compact_events.py:168`）。生产代码中无人调用它。
- **预期行为**: P3-C plan 成功信号要求 "post-compact budget helper...只统计后续真正投影给 LLM 的 candidate 业务文本"。`accepted_compact_business_texts` 的文本顺序（summary → facts → anchor titles → anchor children → intents → reference texts）与 `_budget_after_compact_candidate` 当前在 `compaction_operation.py` 中的遍历逻辑应一致。但在 S1 scope 内该函数尚未接入 budget estimator。
- **实际行为**: 函数作为 public API 存在但无消费者。text ordering 仅被 roundtrip 测试覆盖，未被实际的 budget 计算验证。如果后续 slice 修改了 text ordering 或内容选择逻辑，现有的 roundtrip 测试不会检测到与 budget computation 的语义不对齐。
- **直接证据**:
  - `rg accepted_compact_business_texts dayu/` 仅在 `compact_payload.py:171`（定义）命中，生产代码零引用。
  - `compaction_operation.py` 中 `_budget_after_compact_candidate` 直接遍历 `candidate.evidence_backed_facts` 等字段，绕过此函数。
- **影响**: 低——S1 不包含 budget estimator 迁移，该函数为后续 slice 预留。但如果后续 slice 的开发者没有发现此函数而重复实现文本收集逻辑，就会引入 semantic ownership drift。
- **建议改法和验证点**:
  1. 在函数 docstring 中标注 `.. note:: 当前仅被 P3-C S2 budget estimator 消费；在此之前文本顺序由 roundtrip 测试锁定。`
  2. P3-C S2 接入 budget estimator 时一并增加 integration test，验证 `accepted_compact_business_texts` 的输出与 budget estimator 统计的 token 数来自同一文本集合。
- **修复风险（低）**: 仅文档/注释变更。
- **严重程度（低）**: S1 scope 内正确；仅 forward-compatibility 提醒。

## Open Questions

1. `compact_material.py` 中 `_parse_previous_forward_intent_text` / `_parse_previous_reference_continuity_text` 仍从私有字符串反解析 intent/reference（未在本次 diff 中修改）。P3-C 后续 slice 是否会将这些消费者也迁移到 typed candidate？若会，`accepted_compact_business_texts` 的 ordering 是否需要与 compact material 的 rendering 对齐？
2. `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 枚举值是否应在 P3-C 结束时统一清理，还是保留为 reserved？

## Residual Risk

1. **`compact_material.py` 独立 candidate 解析未迁移**：`compact_material.py` 仍定义自己的 candidate 字段名并独立解析 `accepted_candidate` JSON。这意味着同一 `CONTEXT_COMPACTED` payload 的语义仍有两个 read boundary（parser + compact_material）。这是 P3-C 后续 slice 的已知工作，但 S1 交付时存在窗口期风险——如果有人在 S1 和后续 slice 之间修改 `ConversationCompactOutputVNext.to_json()`，`compact_material.py` 可能产生不匹配的 previous view。
2. **`_budget_after_compact_candidate` 未使用 `accepted_compact_business_texts`**：budget estimator 与 business text collector 尚未统一。如果 estimator 的遍历逻辑与 `accepted_compact_business_texts` 的文本选择产生偏差（例如 estimator 多计了 labels 而 collector 不计），预算估算会偏离实际 LLM 消费。
3. **`run_input.py` inline repair 与 `durable/memory.py` projection runner 的 parser 调用各自独立**：两个 adapter 各自调用 `parse_context_compacted_semantic_payload`，没有共享缓存。同一次 catchup 中同一 payload 可能被解析两次（先 inline repair 后 projection runner），但这是已有的架构特征不是 S1 引入的回归。
4. **旧 snapshot durable 数据兼容性**：本次变更将 snapshot 中 `intent_type`/`status`/`reason` 的序列化从 `str` 改为 `.value`（输出相同），反序列化从 `str` 改为 `StrEnum(str)`。如果存在任何手工插入或未通过 producer 写入的 snapshot 数据包含非法 enum 值，反序列化会抛出 `ValueError` 阻止 snapshot 读取。当前无证据表明存在此类数据。
