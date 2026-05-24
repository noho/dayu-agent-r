# P12.6 Slice 3 Code Review — AgentDS

**Reviewer**: AgentDS  
**Date**: 2026-05-24  
**Base**: 2f3b5ac (P12.6 Slice 2 accepted)  
**Scope**: Workspace diff for Slice 3 implementation  
**Excluded**: `docs/host/implementation-control.md` (controller-only, dirty before task)

---

## Verdict: PASS

动机成立，实现符合 design.md §24/§25 约束。Selected evidence reader 正确收敛到 digest-checked payload/descriptor 路径，accepted envelope 仅作为 provenance anchor 不再作为 content 容器，`result_preview` 完全拒绝，evidence chunk 确定性与 `PromptLocalEvidenceMap` evidence-only view 均已硬化。测试覆盖 plan 指定 5 项，负面测试真实验证 fail closed。无新增 pyright 错误。无架构违规。README 不更新合理。

---

## Findings

### F1 (Medium) — `_provenance_from_evidence_blocks` 硬编码 `artifact_refs=()` / `source_locator_refs=()`

- **文件**: `dayu/host/compact_material.py`, 行 1610–1611
- **证据**:

```python
# _provenance_from_evidence_blocks (run_input 路径)
payload_refs=source.payload_refs,
artifact_refs=(),          # ← 硬编码空
source_locator_refs=(),    # ← 硬编码空
```

- **影响**: `RunInputMaterialBlock` 当前没有 `artifact_refs` / `source_locator_refs` 字段。run_input 路径（来自 `RunInputBuilder` / ordinary input）构造的 `PromptLocalProvenanceEntry` 无法携带 artifact/locator provenance。若后续 `prompt_local_evidence_map()` 校验该 entry 且 `payload_refs` 也为空，会触发 `"PromptLocalEvidenceMap requires payload or artifact refs"` — fail closed 正确，但缺少 artifact 语义保真度。
- **根因**: `RunInputMaterialBlock` 设计先于 evidence envelope artifact/locator 扩展，`artifact_refs` / `source_locator_refs` 字段尚未加入。
- **建议**: 在 Slice 6 (`RunInputBuilder` 渲染) 或更晚的 `RunInputMaterialBlock` 扩展中补齐，当前不阻塞 Slice 3。
- **严重度**：Medium — 不影响当前正确性，但是已知设计债务，应在后续 slice 闭合。

---

### F2 (Low) — `_require_non_empty_text` 跨模块重复定义

- **文件**: `dayu/host/compaction_evidence.py` (行 562–575), `dayu/host/compact_material.py` (已有)
- **证据**: 两个模块各自定义语义相同的 `_require_non_empty_text` 私有函数，签名与行为一致。
- **影响**: 轻微 DRY 违规。两函数均为模块级私有，不破坏公共契约，无运行时冲突。
- **建议**: 可提取到 `dayu.runtime` 或其他共享位置，但不紧急。
- **严重度**: Low。

---

### F3 (Info) — 旧 range-based collector 静默获得 digest-checked 行为

- **文件**: `dayu/host/compaction_evidence.py`, `collect_compaction_request_evidence_inputs` (行 152–205)
- **证据**: 旧 range-based collector 仍调用 `_tool_result_evidence_materials` → `_accepted_tool_result_payload` → `event_payload_object_for_result_ref`，现在强制执行 payload_ref/digest 校验。此前该路径仅读取 payload 不做 cross-check。
- **影响**: 旧路径的 descriptor payload 事件现在如果 `envelope.result_ref.payload_ref` / `payload_digest` 与 EventLog 不一致会 fail closed。这是正确的强化行为，不是回归。内联 payload（无 descriptor）事件不受影响。该函数计划在 Slice 5 被移除。
- **严重度**: Info — 行为变化，但方向正确，无已知风险。

---

### F4 (Info) — `InitialEvidenceMaterial.artifact_refs` 声明但未填充

- **文件**: `dayu/host/compact_material.py` (行 325), `dayu/host/compaction_evidence.py` (行 258–276)
- **证据**: `InitialEvidenceMaterial` 新增 `artifact_refs: tuple[str, ...] = ()` 字段，但 `_tool_result_evidence_materials` 构造时始终使用默认值 `()`，仅设置 `payload_refs` 和 `source_locator_refs`。
- **影响**: `artifact_refs` 是未来 artifact descriptor 路径的占位字段，当前无数据源填充。不影响当前功能。`prompt_local_evidence_map` 校验要求 `payload_refs` 或 `artifact_refs` 至少一个非空（行 692），当前 `payload_refs` 可满足。
- **严重度**: Info — 计划占位，后续 slice 填充。

---

## Validation Summary

### 1. 动机 — PASS

design.md §24/§25 明确要求 accepted evidence envelope 是 provenance anchor，不得作为 evidence content 容器。raw evidence 必须来自 `TOOL_RESULT_ACCEPTED` canonical fact 引用的 payload/descriptor 并做 digest 校验。`result_preview` 不得读取、生成或回退。本 Slice 完全实现这些约束。

### 2. Correctness — PASS

| 检查项 | 结果 | 证据 |
|---|---|---|
| Collector 不再从 Session 起点 range 扫描 | PASS | `collect_selected_compaction_request_evidence_inputs` 用 `read_event_by_id` 精确读取每个 selected ref，非 `read_events_after(start=1)` |
| raw text 不来自 accepted envelope preview | PASS | `_tool_result_evidence_materials` → `_accepted_tool_result_payload` → `event_payload_object_for_result_ref` 走 descriptor 路径；envelope 仅用于 evidence_id / tool_call_id / locator_refs metadata |
| payload_ref mismatch fail closed | PASS | `event_payload_object_for_result_ref` 行 61–62: `event.payload_ref != expected_payload_ref` → `HostDurableError` |
| payload digest mismatch fail closed | PASS | `event_payload_object_for_result_ref` 行 63–65: `event.payload_digest != expected_payload_digest` → `HostDurableError` |
| producer_event_ref mismatch fail closed | PASS | `_accepted_evidence_envelope_from_event` 行 231–232: `envelope.producer_event_ref != row.event_id` → `HostDurableError` |
| session mismatch fail closed | PASS | `_required_event_row` 行 465–466: `row.session_id != session_id` → `HostDurableError` |
| event class 校验 fail closed | PASS | `_required_event_row` 行 467–468: `row.event_class is not EventClass.CANONICAL_FACT` → `HostDurableError` |
| event type 校验 fail closed | PASS | `_required_event_row` 行 469–470: `row.event_type != expected_event_type` → `HostDurableError` |
| raw_tool_outcome 缺失 fail closed | PASS | `_tool_result_evidence_materials` 行 255–256: `raw_outcome is None` → `HostDurableError` |

### 3. result_preview — PASS

- `_reject_result_preview` (行 302–311): payload 含 `result_preview` key 时 `raise HostDurableError`
- 全量 `result_preview` 引用搜索: 仅出现在 `compaction_evidence.py` 的字段常量定义 (行 41) 与 `_reject_result_preview` 调用 (行 253) 及函数定义 (行 302–311) — 无读取、无渲染、无 fallback
- 测试验证: `test_toolruntime_accept_barrier.py` 行 1230: `assert "result_preview" not in payload`
- 测试验证: `test_no_result_preview_field_is_read_or_rendered` 验证 payload 含 `result_preview` 时 `HostDurableError` 抛出

### 4. Prompt-local Evidence Map / Chunking — PASS

| 检查项 | 结果 | 证据 |
|---|---|---|
| Label 确定性 | PASS | `E1` → `material_label(EVIDENCE_INPUT, 1)`; `E1.1`/`E1.2` → `evidence_chunk_label(1, ordinal)` |
| Chunk provenance 指向同一 canonical evidence id | PASS | 所有 chunk 的 `accepted_evidence_id` 统一来自 `material.accepted_evidence_id` |
| Ordinal 可靠 | PASS | `_evidence_chunks` 行 1647: `chunk_ordinal = _FIRST_ORDINAL` (=1), 每 chunk +1 |
| Chunk parent_label 设置 | PASS | `parent_label = material_label(EVIDENCE_INPUT, evidence_ordinal)` — 未 chunk 时为 `None`, chunk 时指向父 label (如 `E1`) |
| Evidence-only view 校验 | PASS | `prompt_local_evidence_map` 校验 section= `EVIDENCE_INPUT`, 拒绝非 evidence entry; 要求 `accepted_evidence_id`, `tool_result_event_ref`, `tool_call_event_ref` 非空; 要求至少一个 payload 或 artifact ref |

### 5. Architecture — PASS

- 无 `dayu.fins` / 业务工具 import
- 不解析财报 locator semantics（`source_locator_refs` 作为 `OpaqueEvidenceRef` 传递）
- 不修改 public Host/Engine/Service/Fins API
- 无 `Any` / `object`（代码级）/ `getattr` / `hasattr` 使用
- 无 lazy import seam
- 分层方向正确（Host 内部 evidence reader → payload_resolution → durable store）

### 6. Tests — PASS

plan 指定 5 项测试全部覆盖：

| 测试 | 文件 | 行 | 验证内容 |
|---|---|---|---|
| `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` | `test_compaction_operation.py` | 886–968 | raw text 来自 descriptor，readable_query 来自 envelope metadata，不泄露 result content |
| `test_missing_or_digest_mismatch_raw_evidence_fails_closed` | `test_compaction_operation.py` | 971–1052 | 缺 raw_tool_outcome → `HostDurableError("raw_tool_outcome")`；digest mismatch → `HostDurableError("payload digest mismatch")` |
| `test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence` | `test_compact_material.py` | 749–782 | `E1` label 映射到 canonical evidence id / tool result / tool call / payload refs |
| `test_single_large_evidence_block_is_chunked_under_same_provenance` | `test_compact_material.py` | 785–822 | 超大 evidence → `E1.1`/`E1.2`；同一 `accepted_evidence_id`；`chunk_parent_label="E1"`；`chunk_ordinal` 递增 |
| `test_no_result_preview_field_is_read_or_rendered` | `test_compaction_operation.py` | 1055–1083 | payload 含 `result_preview` → `HostDurableError("result_preview")` |

全部 48 测试通过（Codex 已验证）。

负面测试真实性:
- Digest mismatch 测试: envelope 声明的 `payload_digest=_DIGEST` (fake) vs EventLog 记录的 `descriptor.payload_digest` (real) → 真实 cross-check
- Missing raw 测试: 内联 payload 无 `raw_tool_outcome` 字段 → 真实字段缺失
- result_preview 测试: payload 含 `result_preview: "legacy preview must not be used"` → 真实旧字段注入

### 7. README — PASS (无需更新)

已检查 `dayu/host/README.md` 与 `tests/README.md`:
- 本次变更是 Host 内部 compaction evidence reader / material provenance 强化与既有 Host 测试覆盖增强
- 不改变 public contract、运行命令、测试层级
- README 中的稳定说明未过期

---

## Residual Risks

1. **`artifact_refs` 占位字段无数据源**: 当前 `_tool_result_evidence_materials` 不填充 `artifact_refs`，仅设置默认 `()`。若后续 Slice 4/5 expect artifact provenance 可用，需先补齐 artifact descriptor 读取路径。

2. **旧 range-based collector 仍存在**: `collect_compaction_request_evidence_inputs` 虽未在本 Slice 修改主流程但已静默获得 digest-checked 强化行为。Slate 5 移除该函数前，若旧调用路径（`dispatch.py` / `engine_ingest.py`）产生未预料的 digest mismatch，会以 `HostDurableError` fail closed — 方向正确，但需在 Slice 5 接线时验证。

3. **`RunInputMaterialBlock` 缺少 `artifact_refs` / `source_locator_refs` 字段**: 见 F1。`_provenance_from_evidence_blocks` 硬编码空值。当 run_input 路径的 evidence block 需要 artifact provenance 时需扩展该 dataclass。

4. **Chunk content_digest 是 chunk 级而非 material 级**: `_evidence_chunks` 每个 chunk 独立计算 `_text_digest(chunk_text)`，不是整个 material 的 digest。`evidence_map` 中的 `content_digest` 是 chunk 级 digest。这是正确的设计（chunk 是 LLM 实际看到的单元），但需确保 accept barrier 侧也按 chunk digest 校验。

5. **`_require_non_empty_text` 重复**: 见 F2。后续若有更多模块需要此 helper，提取为共享工具可减少维护成本。

---

## Review Checklist

- [x] 动机成立（design §24/§25 vs 实现）
- [x] Selected ref → EventLog 精确读取（非 range scan）
- [x] Raw evidence 来自 descriptor 而非 envelope preview
- [x] payload_ref / digest / producer / session / event type 全链路 fail closed
- [x] `result_preview` 全拒绝（无读取、无渲染、无 fallback）
- [x] E1/E1.1/E1.2 label 确定性
- [x] Chunk provenance 指向同一 canonical evidence id
- [x] Chunk ordinal 确定性递增
- [x] `PromptLocalEvidenceMap` evidence-only 校验
- [x] 无 Fins / 业务工具 import
- [x] 不解析财报 locator semantics
- [x] 不改 public API
- [x] 无 Any/object/getattr/hasattr/lazy seam
- [x] 测试覆盖 plan 5 项
- [x] 负面测试真实 digest mismatch / missing raw / fail closed
- [x] 48/48 测试通过, 0 pyright errors
- [x] README 不更新合理
