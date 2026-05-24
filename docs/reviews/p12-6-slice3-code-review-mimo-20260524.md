# P12.6 Slice 3 Code Review — AgentMiMo

**Review date**: 2026-05-24
**Reviewer**: AgentMiMo
**Base**: HEAD = 2f3b5ac (gateflow: accept P12.6 slice 2)
**Scope**: workspace diff for P12.6 Slice 3 implementation; excludes `docs/host/implementation-control.md`
**Plan reference**: `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` Slice 3

---

## Verdict: PASS

---

## 1. 动机判断

Slice 3 动机成立，严重性未被高估。`docs/host/design.md` §24 / §25 已明确 accepted evidence envelope 只是 provenance anchor，不得作为 evidence 内容容器；raw evidence 必须来自 `TOOL_RESULT_ACCEPTED` canonical fact 引用的 payload / descriptor，并做 digest / descriptor 校验。Slice 1/2 已建立 material pack 与 segment selection，但 evidence reader 仍需 selected block ref 读取、raw payload 校验、chunk provenance 与 evidence-only map 的硬化。当前实现正确响应了这些需求。

---

## 2. Correctness 验证

### 2.1 Collector 不再从 Session 起点 range 扫描

**PASS**。新增 `collect_selected_compaction_request_evidence_inputs(...)` 按 `SelectedEvidenceBlockRef` 精确读取，每个 ref 通过 `_required_event_row(...)` 校验 event id、session_id、event_class（`CANONICAL_FACT`）、event_type（`TOOL_RESULT_ACCEPTED` / `RUN_SUCCEEDED` / `CONTEXT_COMPACTED`）。不使用 `start_event_sequence=1` range scan。

旧 `collect_compaction_request_evidence_inputs(...)` 仍保留，由 `dispatch.py` / `engine_ingest.py` 使用，按 plan 由 Slice 5 迁移。Slice 3 不负责删除旧 collector。

### 2.2 Raw text 不来自 accepted envelope preview

**PASS**。`_tool_result_evidence_materials(...)` 调用 `_accepted_tool_result_payload(...)` -> `event_payload_object_for_result_ref(...)` 从 EventLog payload descriptor 读取 JSON object，再从中提取 `raw_tool_outcome` 序列化为 `raw_text`。`readable_query_text` 和 `readable_source_text` 只使用 envelope metadata（tool_call_id、source_refs、locator_refs），不包含 result content。

### 2.3 payload_ref / digest / producer / session / event type 校验 fail closed

**PASS**。校验链：
- `_required_event_row(...)`：event 缺失 -> `HostDurableError("selected evidence event is missing")`；session mismatch -> `HostDurableError("selected evidence event session mismatch")`；非 canonical fact -> `HostDurableError("selected evidence event is not canonical fact")`；type mismatch -> `HostDurableError("selected evidence event type mismatch")`。
- `event_payload_object_for_result_ref(...)`：`event.payload_ref != expected_payload_ref` -> `HostDurableError("... payload ref mismatch")`；`event.payload_digest != expected_payload_digest` -> `HostDurableError("... payload digest mismatch")`。
- `_accepted_evidence_envelope_from_event(...)`：`envelope.producer_event_ref != row.event_id` -> `HostDurableError("accepted evidence producer_event_ref mismatch")`。

### 2.4 result_preview 不读取、不生成、不回退

**PASS**。`_reject_result_preview(payload)` 在 `_tool_result_evidence_materials(...)` 中调用，检测 `result_preview` 字段存在时抛出 `HostDurableError("TOOL_RESULT_ACCEPTED result_preview is not allowed")`。`test_toolruntime_accept_barrier.py` 第 202 行新增断言 `assert "result_preview" not in payload`，确认 accept barrier 写入 payload 时也不包含该字段。

---

## 3. Prompt-local Evidence Map / Chunking

### 3.1 E1 / E1.1 / E1.2 labels 确定性

**PASS**。`_evidence_chunks(evidence_ordinal, text)` 使用模块级常量 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096` 作为 chunk 上限。未超限时返回单个 `E1` label（通过 `material_label(EVIDENCE_INPUT, ordinal)`）。超限时生成 `E1.1`、`E1.2`（通过 `evidence_chunk_label(ordinal, chunk_ordinal)`）。`chunk_ordinal` 从 `_FIRST_ORDINAL` 开始递增。label 生成 owner 固定在 `compact_material.py` 模块级私有 helper。

### 3.2 Chunk provenance 指向同一 canonical evidence id

**PASS**。`_evidence_provenance(...)` 和 `_provenance_from_evidence_blocks(...)` 中，所有 chunk 共享同一个 `material.accepted_evidence_id` / `source.accepted_evidence_id`。chunk 的 `chunk_parent_label` 指向非 chunk 的 parent label（如 `E1`），`chunk_ordinal` 记录 chunk 在 parent 内的位置。

### 3.3 ordinal 可靠性

**注意**（不阻塞）。`_evidence_provenance(...)` 接收 `blocks` 参数后立即 `del blocks`，ordinal 从 `enumerate(materials, start=_FIRST_ORDINAL)` 推导而非从 block label 解析。`_provenance_from_evidence_blocks(...)` 同样 `del evidence_blocks`。ordinal 一致性依赖于 blocks 和 materials 的 enumerate 起始值与顺序相同——当前代码满足，但函数签名具有误导性。

### 3.4 PromptLocalEvidenceMap 校验

**PASS**。`prompt_local_evidence_map(...)` 从 `CompactMaterialPack.evidence_map()` 派生，校验每个 entry：
- section 必须为 `EVIDENCE_INPUT`。
- `accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref` 非空。
- `payload_refs` 或 `artifact_refs` 至少有一个非空。
- label 格式通过 `validate_material_label(label, EVIDENCE_INPUT)` 校验。

---

## 4. Architecture 验证

| 约束 | 状态 |
|------|------|
| 不 import Fins / 业务工具 | PASS |
| 不解析财报 locator semantics | PASS |
| 不改 public Host / Engine / Service / Fins API | PASS |
| 不引入 `Any` / `object` / `getattr` / `hasattr` / lazy seam | PASS |
| 函数完整中文 docstring | PASS |
| 类型签名严格 | PASS |
| 不把 event id / payload ref / digest / cursor 当 LLM semantic input | PASS |

---

## 5. Tests 验证

### 5.1 Plan 指定 5 项测试覆盖

| Plan 要求 | 测试函数 | 文件 | 状态 |
|-----------|---------|------|------|
| `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` | 同名 | `test_compaction_operation.py` | PASS |
| `test_missing_or_digest_mismatch_raw_evidence_fails_closed` | 同名 | `test_compaction_operation.py` | PASS |
| `test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence` | 同名 | `test_compact_material.py` | PASS |
| `test_single_large_evidence_block_is_chunked_under_same_provenance` | 同名 | `test_compact_material.py` | PASS |
| `test_no_result_preview_field_is_read_or_rendered` | 同名 | `test_compaction_operation.py` | PASS |

### 5.2 负面测试质量

**PASS**。
- `test_missing_or_digest_mismatch_raw_evidence_fails_closed`：两个子场景——(1) payload 无 `raw_tool_outcome` 字段，assert `pytest.raises(HostDurableError, match="raw_tool_outcome")`；(2) EventLog payload descriptor 的 digest 与 envelope 声明不一致，assert `pytest.raises(HostDurableError, match="payload digest mismatch")`。
- `test_no_result_preview_field_is_read_or_rendered`：payload 包含 `result_preview` 字段时 assert `pytest.raises(HostDurableError, match="result_preview")`。
- `test_toolruntime_accept_barrier.py` 第 202 行：`assert "result_preview" not in payload` 确认 accept barrier 上游也不写入该字段。

### 5.3 测试结果

Implementation artifact 报告 48 passed、0 pyright errors、git diff --check pass。与 plan Slice 3 验证命令一致。

---

## 6. README 合理性

**PASS**。Implementation artifact 说明未更新 README，理由是：变更为 Host 内部 compaction evidence reader、material provenance 与测试覆盖增强，不改变 public contract、运行命令、测试层级或 README 中的稳定说明。按 AGENTS.md README 触发规则，`dayu/host/` 修改应检查 `dayu/host/README.md`，本次变更确实不改变 public contract，不更新合理。

---

## 7. Findings

### F1. `del blocks` / `del evidence_blocks` 参数误导 [Quality / Low]

**文件**: `compact_material.py:980`, `compact_material.py:1581`
**证据**: `_evidence_provenance(blocks, materials, ...)` 接收 `blocks` 参数后立即 `del blocks`；`_provenance_from_evidence_blocks(evidence_blocks, source_blocks)` 同理。
**影响**: 函数签名暗示 blocks 参数有意义，实际 ordinal 完全由 `enumerate(materials / source_blocks)` 推导。不导致正确性问题，但增加阅读者理解成本。
**建议**: 后续 slice 考虑移除 dead 参数或在签名中标注 `_blocks: object`（仅用于向后兼容时）。

### F2. `_provenance_from_evidence_blocks` 硬编码 `artifact_refs=()` / `source_locator_refs=()` [Quality / Low]

**文件**: `compact_material.py:1610-1611`
**证据**: `RunInputMaterialBlock` 没有 `artifact_refs` 和 `source_locator_refs` 字段，因此 provenance entry 中这两个字段硬编码为空。而 `_evidence_provenance(...)` 使用 `InitialEvidenceMaterial` 时会传播 `material.artifact_refs` 和 `material.source_locator_refs`。
**影响**: 当 evidence 走 `RunInputMaterialBlock` 路径时，`artifact_refs` 和 `source_locator_refs` 丢失。当前 `RunInputMaterialBlock` 确实不携带这些字段，所以硬编码正确；但若后续 `RunInputMaterialBlock` 扩展这些字段，此处会成为 silent data loss。
**建议**: 若 `RunInputMaterialBlock` 后续扩展 `artifact_refs` / `source_locator_refs` 字段，需同步更新 `_provenance_from_evidence_blocks`。

### F3. `_evidence_chunks` 在三条路径中重复调用 [Quality / Low]

**文件**: `compact_material.py` `_evidence_blocks`（~第 897 行）、`_evidence_provenance`（~第 980 行）、`_pack_evidence_blocks`（~第 1508 行）
**证据**: 同一 evidence text 在构建 blocks、构建 provenance 和 packing 时各调用一次 `_evidence_chunks`，产生相同的 chunk tuple。
**影响**: 不影响正确性（deterministic 函数，相同输入相同输出），但存在冗余计算。
**建议**: 可在 `_evidence_provenance` 等函数中缓存 chunk 结果；不阻塞当前 slice。

---

## 8. Validation Summary

| 检查项 | 结果 |
|--------|------|
| Collector 按 selected refs 读取，不从 Session 起点扫描 | PASS |
| Raw text 来自 digest-checked payload descriptor | PASS |
| payload_ref / digest / producer / session / event type fail closed | PASS |
| result_preview 不读取、不生成、不回退 | PASS |
| E1 / E1.1 / E1.2 label 确定性，chunk provenance 指向同一 canonical id | PASS |
| PromptLocalEvidenceMap 校验完整 | PASS |
| 不 import Fins / 业务工具 | PASS |
| 不解析财报 locator semantics | PASS |
| 不改 public API | PASS |
| 不引入 Any / object / getattr / hasattr / lazy seam | PASS |
| 类型签名严格，中文 docstring 完整 | PASS |
| Plan 指定 5 项测试全部覆盖 | PASS |
| 负面测试真实验证 digest mismatch / missing raw / fail closed | PASS |
| README 未更新，理由合理 | PASS |
| pytest 48 passed / pyright 0 errors / git diff --check pass | PASS |

---

## 9. Residual Risks

1. **旧 range collector 仍保留**：`collect_compaction_request_evidence_inputs(...)` 仍由 `dispatch.py` / `engine_ingest.py` 使用，按 plan 由 Slice 5 迁移。不阻塞 Slice 3。
2. **`RunInputMaterialBlock` 路径丢失 artifact_refs / source_locator_refs**：当前 `RunInputMaterialBlock` 不携带这些字段，硬编码 `()` 正确。若后续扩展需同步更新。
3. **`del blocks` dead parameter**：函数签名误导，不影响运行期正确性。后续 slice 可清理。
