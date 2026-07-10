# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: main (commit `0dcef803` — accepted P3-C plan)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-code-review-mimo.md`
- Included scope: S1 production code (`dayu/host/compact_payload.py`, `dayu/host/context_events.py`, `dayu/host/memory.py`, `dayu/host/durable/memory.py`, `dayu/host/run_input.py`), tests (`tests/host/test_context_compact_events.py`, `tests/host/test_memory_projection.py`, `tests/host/test_compact_material.py`, `tests/host/test_run_input_builder.py`, `tests/host/memory_snapshot_factories.py`), README (`dayu/host/README.md`), control (`docs/host/issues-implementation-control.md`).
- Excluded scope: untracked `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-*` files.
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对用户攻击清单中每一项的 adversarial 验证结论：

### 1. compact_payload parser 是否与 ConversationCompactOutputVNext.to_json 精确同源

**结论：PASS。** parser 不是第二 schema truth，而是 `to_json()` 的精确对称反序列化。

逐层核对：
- `_CANDIDATE_FIELDS` = `{schema_version, session_summary, evidence_backed_facts, answer_anchors, forward_intents, reference_continuity_items, diagnostics}` → 与 `ConversationCompactOutputVNext.to_json()` 输出字段完全一致（`compaction.py:1486-1494`）。
- `_SUMMARY_FIELDS` = `{summary_text, source_labels}` → 与 `SessionSummaryCandidateVNext.to_json()`（`compaction.py:1173-1176`）完全一致。
- `_FACT_FIELDS` = `{claim_text, evidence_labels, evidence_kind, source_labels}` → 与 `EvidenceBackedFactCandidateVNext.to_json()`（`compaction.py:1220-1225`）完全一致。
- `_ANCHOR_FIELDS` = `{anchor_title, anchor_items, answer_source_labels}` → 与 `AnswerAnchorCandidateVNext.to_json()`（`compaction.py:1297-1301`）完全一致。
- `_ANCHOR_CHILD_FIELDS` = `{display_text, ordinal}` → 与 `AnswerAnchorChildVNext.to_json()`（`compaction.py:1256`）完全一致。
- `_FORWARD_INTENT_FIELDS` = `{intent_type, text, status, source_labels}` → 与 `ForwardIntentCandidateVNext.to_json()`（`compaction.py:1343-1348`）完全一致。
- `_REFERENCE_FIELDS` = `{text, reason, source_labels}` → 与 `ReferenceContinuityCandidateVNext.to_json()`（`compaction.py:1386-1390`）完全一致。
- `_DIAGNOSTIC_FIELDS` = `{code, text, source_labels}` → 与 `CompactCandidateDiagnosticVNext.to_json()`（`compaction.py:1426-1430`）完全一致。

`ContextCompactedSemanticPayload.__post_init__`（`compact_payload.py:124`）通过 `accepted_candidate_digest != accepted_candidate.digest()` 做 roundtrip digest 校验：parser 恢复的 typed candidate 的 `digest()` 必须与 persisted digest 一致。如果 parser 的字段集与 `to_json()` 不一致，digest 不匹配，会 fail closed。

### 2. unknown/exact-field/digest/evidence_kind/ordinal 校验

**结论：PASS。** 校验严格且完备。

- `_require_exact_fields`（`compact_payload.py:696-717`）：拒绝缺字段和未知字段。旧字段 alias（如 `episode_summary`）会被 `"is not supported"` 拒绝。测试 `test_compacted_semantic_parser_rejects_unknown_old_candidate_field` 覆盖。
- digest：`ContextCompactedSemanticPayload.__post_init__`（`compact_payload.py:122-125`）校验 `accepted_candidate_digest` 是 sha256 且与 candidate.digest() 一致。测试 `test_compacted_semantic_parser_rejects_candidate_digest_mismatch` 覆盖。
- evidence_kind：`_parse_fact`（`compact_payload.py:273-274`）通过 `FactEvidenceKindVNext(text)` 构造，Python 3.11 StrEnum 对未知值 raise ValueError。测试 `test_compacted_semantic_parser_rejects_missing_host_evidence_kind` 覆盖。
- ordinal：`_required_optional_non_negative_int`（`compact_payload.py:676-693`）允许 `None` 或 `>= 0`，拒绝 bool 和负数。测试 `test_compacted_semantic_parser_rejects_negative_anchor_ordinal` 覆盖。
- forward intent enum：`ForwardIntentTypeVNext(text)` 和 `ForwardIntentStatusVNext(text)` 对未知值 fail closed。测试 `test_compacted_semantic_parser_rejects_invalid_forward_intent_enum` 覆盖。
- reference reason：`ReferenceContinuityReasonVNext(text)` 对未知值 fail closed。测试 `test_compacted_semantic_parser_rejects_invalid_reference_reason` 覆盖。

### 3. context_events 委托是否重复解析或改变异常 taxonomy

**结论：PASS。** 无重复解析，异常 taxonomy 未改变。

- `validate_context_compacted_payload`（`context_events.py:348`）调用 `parse_context_compacted_semantic_payload(payload)` 替代了已删除的 `_validate_vnext_candidate_payload`。外层字段（`operation_id`、`accepted_attempt_number`、`compact_artifact_digest` 等）仍在 `validate_context_compacted_payload` 中校验，与 candidate 解析无重叠。
- 旧 `_validate_vnext_candidate_payload` 做浅层 shape 校验（`_validate_mapping_list`），新 parser 做完整 typed 恢复 + exact field + enum + digest。新 parser 是旧 validator 的严格超集。
- 异常类型：parser 内部均 raise `ValueError`（shape/enum/digest），与旧 `_validate_vnext_candidate_payload` 的 `ValueError` 一致。外部调用方（durable memory、run_input）的异常处理链未改变。

### 4. durable memory 与 inline repair adapters 是否解析一次、错误是否被正确分类并阻止 checkpoint

**结论：PASS。** 解析一次，错误阻止 checkpoint。

- `durable/memory.py:_memory_projection_payload_view`（行 390-400）对 `CONTEXT_COMPACTED` 事件调用 `parse_context_compacted_semantic_payload(event.payload)` 一次，结果存入 `_MemoryProjectionPayloadView.compacted_semantics`，传递到 `MemoryProjectionEvent.compacted_semantics`。
- `run_input.py:_memory_projection_event_from_row`（行 3199-3204）对 `CONTEXT_COMPACTED` 行调用 `parse_context_compacted_semantic_payload(payload)` 一次。
- 两处调用均只执行一次 parse，无重复解析。
- 测试 `test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint`（`test_memory_projection.py`）验证：非法 persisted enum → `result.failures == 1`、`result.events_applied == 0`、`latest is None`、checkpoint 不推进。

### 5. MemoryProjectionEvent pairing/invariants

**结论：PASS。**

- `MemoryProjectionEvent.__post_init__`（`memory.py:1002-1007`）强制：
  - `CONTEXT_COMPACTED` 事件必须携带 `compacted_semantics`。
  - 非 compact 事件不得携带 `compacted_semantics`。
- `project_conversation_memory_event`（`memory.py:1265-1267`）在 `CONTEXT_COMPACTED` 分支再次断言 `compacted_semantics is not None`。
- 所有 `MemoryProjectionEvent` 构造点（durable/memory.py、run_input.py、测试 helpers）均正确设置 pairing。

### 6. enum snapshot/table roundtrip 和所有消费者

**结论：PASS。**

- `ForwardIntent.intent_type`、`ForwardIntent.status`、`ReferenceContinuityItem.reason` 从 `str` 改为 typed enum。
- 序列化：`_forward_intent_to_json_value`（`memory.py:2760-2761`）使用 `.value`；`_reference_item_to_json_value`（`memory.py:2626`）使用 `.value`；`durable/memory.py` 中对应函数同步。
- 反序列化：`_forward_intent_from_json_value`（`memory.py:2779-2780`）使用 `ForwardIntentTypeVNext(str)`；`_reference_item_from_json_value`（`memory.py:2644`）使用 `ReferenceContinuityReasonVNext(str)`。
- LLM-facing 投影：`run_input.py:_memory_forward_intent_message`（行 2390-2393）使用 `.value`；`_memory_reference_continuity_message`（行 2410-2412）使用 `.value`。
- 测试 `test_snapshot_json_roundtrip_preserves_vnext_sections` 验证 roundtrip 后 enum 值正确。
- 测试 `test_snapshot_json_rejects_invalid_compact_enum` 验证非法 enum 在反序列化时 fail closed。

### 7. anchor children/ordinal 完整性

**结论：PASS。**

- `_parse_answer_anchor_child`（`compact_payload.py:310-333`）恢复 `display_text` 和 `ordinal`（nullable non-negative int）。
- `_ANCHOR_CHILD_FIELDS = {display_text, ordinal}` 与 `AnswerAnchorChildVNext.to_json()` 一致。
- 测试 `test_compacted_semantic_parser_roundtrips_full_typed_candidate` 验证 anchor children 含 ordinal。
- 测试 `test_accepted_compact_materializes_vnext_memory_sections` 验证 memory projection 保留 children 和 ordinal。

### 8. accepted_compact_business_texts 是否越过 S1 或文本顺序错误

**结论：PASS。** 未越过 S1，文本顺序正确。

- `accepted_compact_business_texts`（`compact_payload.py:160-181`）仅在 `compact_payload.py` 定义、`test_context_compact_events.py` 测试，无 production 调用方。它是 typed semantic payload 的公共 API，供后续 work unit 使用。S1 scope 内不调用它不影响 correctness。
- 文本顺序：summary → facts → anchor_title + anchor_children → intents → references。与 `ConversationCompactOutputVNext.to_json()` 字段顺序一致。测试 `test_compacted_semantic_parser_roundtrips_full_typed_candidate` 验证精确 tuple。

### 9. 测试 scope 扩展是否仅 enum 迁移

**结论：PASS。**

- `test_compact_material.py`：将 `ForwardIntent`、`ReferenceContinuityItem` 的 `intent_type`、`status`、`reason` 从 `str` 改为 typed enum 值。无新增测试函数，仅 enum 值迁移。
- `test_run_input_builder.py`：`_compact_payload` helper 从 dict literal 改为 typed dataclass + `build_context_compacted_payload`。`reference_reason` 从 `"needed_for_ordered_item_reference"` 改为 `ReferenceContinuityReasonVNext.ORDINAL_REFERENCE`（对应 `compaction.py` 中实际 enum value）。无新增超出 enum 迁移范围的测试。
- `test_memory_projection.py`：新增 `test_snapshot_json_rejects_invalid_compact_enum`、`test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint`。删除 `test_accepted_compact_preserves_budget_diagnostic_before_invalid_fact`、`test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels`（因 empty evidence_labels 现在在 parse boundary fail closed，不再在 memory projection 层产生 diagnostic）。
- `test_context_compact_events.py`：新增 8 个 parser 测试覆盖 roundtrip、enum、digest、shape、ordinal。`_candidate()` helper 增加 children ordinal 和 diagnostics。
- `memory_snapshot_factories.py`：enum 值迁移，无逻辑变更。

### 10. README/docstrings/strict typing/coverage

**结论：PASS。**

- README（`dayu/host/README.md`）：在架构边界 bullet 中补充 "persisted accepted compact candidate 在唯一严格 typed read boundary 恢复，非法 shape、digest 或 enum fail closed，Memory projection 不再自行解释 nested candidate JSON"。准确描述新行为，符合 README Agent更新约束。
- docstring：所有新增函数和类均有完整中文 docstring（参数、返回值、异常）。
- strict typing：pyright 0 errors, 0 warnings, 0 informations。
- 测试覆盖：255 tests passed。新增 10+ 测试覆盖 parser roundtrip、enum fail-closed、digest mismatch、shape rejection、ordinal validation、checkpoint behavior。

## Open Questions

无。

## Residual Risk

- `_required_text_list`（`compact_payload.py:778-797`）不拒绝空 list（返回 `()`）。非空约束由 VNext dataclass `__post_init__` 中的 `_require_non_empty_unique_string_tuple` 兜底。当前正确，但若未来新增不经过 dataclass 构造的消费路径，可能遗漏非空校验。风险低，因所有消费路径均经过 `parse_context_compacted_semantic_payload` → dataclass 构造。
- `_require_exact_fields` 严格拒绝未知字段。若未来 schema 演进添加新字段但未同步更新 parser frozensets，所有旧 persisted 数据将 fail closed。这是 S1 设计意图（fail closed），但 schema 演进时需同步更新 parser。当前版本无此风险。
