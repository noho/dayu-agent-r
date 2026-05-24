# Code Review — Phase 12.6 Slice 1

## Scope

- **Mode**: current changes (workspace diff against HEAD)
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Base**: HEAD (8749be9 gateflow: accept plan fix for P12.6 slice 1)
- **Plan commits**: 728904a (accept plan), 8749be9 (accept plan fix for slice 1)
- **Output file**: docs/reviews/p12-6-slice1-code-review-ds-20260524.md
- **Included scope**: workspace uncommitted diff on 18 files — `dayu/host/compaction.py`, `dayu/host/compact_material.py` (new), `dayu/host/compaction_evidence.py`, `dayu/host/llm_compaction.py`, `dayu/host/context_governance.py`, `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py`, `dayu/host/context_events.py`, `dayu/host/compact_artifact.py`, `dayu/config/prompts/scenes/conversation_compaction_user.md`, plus 8 test files
- **Excluded scope**: Committed changes before HEAD; `dayu/host/run_input.py` (not in Slice 1 allowed files per plan §3.2)
- **Review targets**: correctness, contract safety, strict typing, old `CompactionRequest` field removal, prompt-local label/provenance mapping correctness, event/artifact payload safety, tests adequacy, no Engine/Fins/Service/UI/public API drift
- **Truth sources**: `docs/host/design.md` §24/§25, `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` Slice 1, `docs/reviews/p12-6-slice1-implementation-codex-r2-20260524.md`

## Findings

### 1-PENDING-中-run_input.py 与 context_events.py 的 preserved_fact_refs payload 字段名不一致

- **入口/函数**: `_preserved_fact_refs_text` → `run_input.py:2160`；`build_context_compacted_payload` → `context_events.py:293`
- **文件(行号)**: `dayu/host/run_input.py:115` vs `dayu/host/context_events.py:85`
- **输入场景**: 新的 `CONTEXT_COMPACTED` 事件被 Slice 1 代码写入后，RunInputBuilder 在后续 Run 中读取该事件的 `preserved_fact_refs`。
- **实际分支**: `context_events.py:85` 将 payload key 从 `"accepted_evidence_refs"` 改为 `"canonical_evidence_refs"`；`run_input.py:115` 仍然使用 `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_REFS = "accepted_evidence_refs"`；`run_input.py:2160` 用旧 key 读取 `_optional_text_list`。
- **预期行为**: RunInputBuilder 应能正确读取新格式 `CONTEXT_COMPACTED` 事件中的 preserved evidence refs。
- **实际行为**: `_optional_text_list` 找不到 `"accepted_evidence_refs"` key 时返回空 tuple，导致 `_preserved_fact_refs_text` 的 `accepted_evidence_refs` 部分静默为空。
- **直接证据**: `context_events.py:85` 写入 `"canonical_evidence_refs"`；`run_input.py:115` 读取 `"accepted_evidence_refs"` —— 两条路径使用不同的 payload key。
- **影响**: RunInputBuilder 读取 Slice 1 产生的 `CONTEXT_COMPACTED` 事件时静默丢失 evidence refs，影响 memory projection 和后续 compact 的 evidence 覆盖判断。
- **建议改法和验证点**: 这属于 Slice 6（V1 consolidation owner）的已知延期项。Codex 报告明确记录 "Existing `dayu/host/run_input.py` still contains historical payload field names outside Slice 1 allowed files; not touched because this slice did not authorize RunInputBuilder migration." Slice 6 必须统一 `run_input.py` 的 payload field name 与 `context_events.py` 一致，并补充跨版本 payload 兼容读取测试。
- **修复风险（中）**: RunInputBuilder 迁移涉及 memory projection 全链路，需要 Slice 6 完整测试覆盖。
- **严重程度（中）**: 已知延期项，当前 Slice 1 不引入新写入的 `CONTEXT_COMPACTED` 事件被立即消费的路径（proactive compact 发生在 dispatch 前，不经过 RunInputBuilder 读取），但若后续 Slice 提前消费新格式事件会触发此问题。

### 2-PENDING-低-_range_tuple 对空 canonical_source_refs 的隐式 IndexError 风险

- **入口/函数**: `_range_tuple` → `llm_compaction.py`
- **文件(行号)**: `dayu/host/llm_compaction.py`（`_range_tuple` 函数内 `start_refs[0]` 与 `end_refs[0]` 访问）
- **输入场景**: LLM proposal 中的 `dropped_ranges` 或 `summarized_ranges` 引用了 `canonical_source_refs` 为空的 material label。
- **实际分支**: `_canonical_refs_for_labels` 展开 label 对应的 `entry.canonical_source_refs`，若为空 tuple 则返回空 tuple；随后 `start_refs[0]` 触发 `IndexError`。
- **预期行为**: 应明确校验 range 端点 label 必须有至少一个 canonical source ref，否则给出明确错误信息。
- **实际行为**: `IndexError` 无明确上下文信息。
- **直接证据**: `_require_string_tuple`（`compaction.py`）允许空 tuple；`_canonical_refs_for_labels` 对空 canonical_source_refs 无特殊处理；`_range_tuple` 直接索引 `[0]`。
- **影响**: 仅在异常输入（provenance entry 构造错误）时触发，正常路径不受影响。错误信息不够明确，增加调试难度。
- **建议改法和验证点**: 在 `_range_tuple` 中获取 refs 后检查非空，或让 `_canonical_refs_for_labels` 对空结果抛出明确 `ValueError`。也可在 `CompactMaterialBlock.__post_init__` 中要求 `canonical_source_refs` 非空。
- **修复风险（低）**: 仅增加防御性校验。
- **严重程度（低）**: 当前所有构造路径均提供非空 canonical_source_refs，实际不会触发。

### 3-PENDING-低-context_events.py 字段常量命名与值不一致

- **入口/函数**: `context_events.py` 模块级常量
- **文件(行号)**: `dayu/host/context_events.py:85, 111, 116`
- **输入场景**: 阅读代码时理解 payload 字段名。
- **实际分支**: `_FIELD_ACCEPTED_EVIDENCE_REFS = "canonical_evidence_refs"` —— 常量名含 `ACCEPTED`，值含 `canonical`。同问题影响 `_FIELD_ACCEPTED_EVIDENCE_REFS_RETAINED = "canonical_evidence_refs_retained"` 和 `_FIELD_RETAINED_ACCEPTED_EVIDENCE_REFS = "retained_canonical_evidence_refs"`。
- **预期行为**: 常量名应与值一致（如 `_FIELD_CANONICAL_EVIDENCE_REFS = "canonical_evidence_refs"`），或至少名实相符。
- **实际行为**: 常量名残留 "ACCEPTED" 但值已改为 "canonical"。
- **直接证据**: `context_events.py:85, 111, 116` 三处。
- **影响**: 降低代码可读性，但不影响运行时正确性（模块内部使用一致）。
- **建议改法和验证点**: 将常量名中的 `ACCEPTED` 改为 `CANONICAL`。纯重命名，无行为变更，`rg` 确认模块内引用即可。
- **修复风险（低）**: 纯重命名。
- **严重程度（低）**: 仅影响可读性。

## 正面确认项

以下审查点均通过，无发现：

- **旧 `CompactionRequest` 字段删除**: `input_event_refs`, `current_message_summary`, `accepted_evidence_envelopes`, `compact_raw_context_items` 已从 `CompactionRequest` dataclass 中完全移除。`rg` 搜索确认生产代码与测试中均无残留引用。
- **旧类型删除**: `CompactRawContextItem`, `CompactRawContextKind`, `CurrentMessageSummary` 已从 `compaction.py` 的 `__all__` 和定义中移除。全仓搜索确认无残留引用。
- **无兼容别名或 wrapper**: 未发现 deprecated alias、compat re-export 或 test-only compatibility 过渡代码。
- **无 EventLog ledger dump**: `_compaction_request_prompt_block` 不再渲染 `input_event_refs`、`accepted_evidence_envelopes` metadata（payload_ref、digest、event_id 等）、`compact_raw_context` event ref 列表。LLM-facing prompt 只包含 `trigger_source` 和 `material_pack` JSON。
- **无 `result_preview` 路径**: `CompactEvidenceBlock.raw_result_text` 承载 raw tool outcome（JSON-encoded），不经过 lossy preview。
- **无 Host provenance 语义输入**: `llm_json()` 方法排除 `canonical_source_refs`, `content_digest`, `canonical_source_refs` 等内部字段。LLM 只看到 `label`, `kind`, `text`, `source_labels` 等 prompt-local 信息。
- **Prompt-local label 正确性**: `material_label` 和 `evidence_chunk_label` 使用模块级常量生成确定性的 label 格式（`C1`, `H1`-`Hn`, `E1`-`En`, `E1.1`-`En.m`, `S1`-`Sn`）。`validate_material_label` 正确校验 section membership。
- **Label → canonical provenance 映射**: `_canonical_refs_for_labels` 和 `_canonical_evidence_refs_for_labels` 通过 `provenance_map` 将 LLM 输出的 prompt-local labels 映射为 canonical refs。未知 label、非 evidence label 引用 evidence 字段、evidence label 无 accepted_evidence_id 均 fail closed（抛 `ValueError`）。
- **Material pack section 一对一映射**: `_require_one_section_per_canonical_content` 通过 `(sorted(canonical_source_refs), content_digest)` 去重 key 防止同一 content 进入两个 section。
- **Prompt-local label owner 集中**: `compact_material.py` 是 label 生成和校验的唯一 owner。parser（`llm_compaction.py`）复用 `CompactMaterialSection` 枚举和 `provenance_map` 做校验，没有另写不一致的 regex。
- **Evidence provenance entry 强制字段**: `PromptLocalProvenanceEntry.__post_init__` 对 `EVIDENCE_INPUT` section 强制要求非空 `accepted_evidence_id`。
- **Event/artifact payload 安全**: `context_events.py` 中 `validate_context_compacted_payload` 正确使用 `canonical_evidence_refs` 校验 fact candidates 的 evidence refs 和 quality check result 的 retained refs。
- **无 Engine/Fins/Service/UI drift**: `dayu/host/compaction.py` 不再 import `AcceptedEvidenceEnvelope` 或 `accepted_evidence_envelope_to_json_value`；仅 import `OpaqueEvidenceRef`（已有底层类型）。未修改 `dayu/host/api.py` public handle、`OpenHostOptions`、`SubmitFollowupRequest` 或 Engine public contracts。
- **测试更新**: `fake_compaction.py` 完全使用 `material_pack` / `segment_selection` 构造 candidate。`test_compaction_contract.py`, `test_compaction_operation.py`, `test_llm_compaction.py`, `test_compact_artifact_store.py`, `test_context_compact_events.py` 均已迁移到新 contract。Codex 报告确认 `pytest` 260 测试通过、`pyright` 0 errors。

## Open Questions

1. `run_input.py` 的 payload field name 迁移是否应在 Slice 2（snapshot cursor validation）或 Slice 3（raw evidence path hardening）提前处理，而非等到 Slice 6？若 Slice 2 开始产生实际 `CONTEXT_COMPACTED` 事件并被 RunInputBuilder 消费，此问题会从"已知延期"升级为"阻塞 bug"。
2. `context_events.py` 的 `preserved_fact_refs` 子对象 key 从 `"accepted_evidence_refs"` 改为 `"canonical_evidence_refs"`，但 `compact_artifact.py:211` 的 artifact JSON 中对应 key 也是 `"canonical_evidence_refs"`。artifact 与 EventLog payload 的 key 一致性是否需要显式 contract 或共享常量？

## Residual Risk

- **run_input.py payload field divergence**: 已知延期至 Slice 6。在 RunInputBuilder 消费新格式 `CONTEXT_COMPACTED` 事件前不触发，但一旦 Slice 2-5 中的任何 slice 开始让 RunInputBuilder 读取 Slice 1 产生的事件，就会静默丢失 evidence refs。
- **Evidence raw_result_text JSON encoding**: `_tool_result_evidence_materials` 使用 `canonical_json_dumps(raw_outcome)` 作为 LLM-facing 文本，JSON 编码对 LLM 可读性不如 display text。已知延期至 Slice 3（digest-checked raw evidence path hardening）。
- **Segment selection 为占位实现**: `initial_segment_selection` 选择 material pack 中所有 labels，不做 already-represented pruning、budget-based selection 或 deterministic reason codes。按 plan 延期至 Slice 2。
- **Memory snapshot cursor 未校验**: `initial_segment_selection` 中 `memory_snapshot_cursor=None`。`CompactionRequest` 构造时 `memory_snapshot_cursor=None`。按 plan 延期至 Slice 2。
- **测试覆盖范围**: Slice 1 测试覆盖了 contract validation、fake compactor integration、quality check、context events 和 artifact store。未覆盖 dispatch.py 和 engine_ingest.py 中 `build_initial_material_pack` + `initial_segment_selection` 的实际调用路径（这些路径依赖完整的 EventLog 和 durable store，属于 Slice 2+ 集成测试范围）。

## Conclusion

**PASS**

Slice 1 正确完成了 material-pack-oriented `CompactionRequest` 契约删除边界与直接消费者迁移。旧字段和旧类型已完全移除，无兼容别名或 wrapper 残留。Prompt-local label 生成与 canonical provenance 映射正确，LLM-facing JSON 与 Host internal JSON 分离清晰。已知的 `run_input.py` payload field name 不一致和 segment selection 占位实现均属于 plan 明确的后续 slice 范围，不阻塞 Slice 1 合入。
