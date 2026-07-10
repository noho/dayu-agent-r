# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Code Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-mimo.md`
- Included scope: P3-C S3 allowed production/test/docs files
- Excluded scope: `tool_trace.py`（S3 不改）、UI/Service/Engine 层、P3-E/P3-J residual

## Review 范围与对齐

按 9 项 review 重点逐项走读：

1. typed mismatch exception 是否替代 string constant / str(exc) 协议；cause chain 是否保留。
2. `evidence.py` 作为 leaf contract 放置 `AcceptedToolEvidenceLLMMaterial`、`render_accepted_tool_evidence_for_llm`、`AcceptedEvidenceProducerEventRefMismatchError` 是否符合 owner boundary。
3. `accepted_result_projection` 是否仍是 accepted result projection producer；strict optional payload accessor；`llm_material` / `tool_call_requested_event_ref` / `source_locator_refs` 是否同源。
4. memory、durable memory、compact material、compact pipeline、run input 是否不再自行 parse accepted evidence envelope，而是消费同一个 projection/material contract。
5. `MemoryProjectionEvent` 与 `RunInputMaterialBlock` 是否有完整 evidence contract；非 evidence message 是否不带 evidence fields/provenance。
6. LLM-facing renderer 是否只输出业务可读四行：工具名称、查询语义、业务来源、工具结果；不得泄漏内部治理信息。
7. `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 是否无重命名 mapping；`result_text` 只保留在 `raw_result_text` / `response_text` 语义中。
8. Tool Trace 本轮应保持不变；README/test decision 是否符合 AGENTS.md。
9. controller validation 中的测试、pyright、coverage、source scan 是否足以支撑结论。

---

## Findings

未发现实质性问题。

逐项 evidence-based 裁决如下：

### 1. Typed mismatch exception 替代 string constant / str(exc) 协议

**Evidence**: `evidence.py:102-121` 新增 `AcceptedEvidenceProducerEventRefMismatchError(ValueError)`，携带 `expected_event_ref` / `observed_event_ref` 两个 typed 字段。`accepted_evidence_envelope_from_payload()` 在 mismatch 时抛该类型（`evidence.py:420-424`），删除旧 `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` string constant。`accepted_result_projection.py:290-294` 的 `_accepted_envelope()` 先 catch `AcceptedEvidenceProducerEventRefMismatchError` 再 catch `ValueError`，以 `from exc` 保留完整 cause chain。

**Verification**: `test_accepted_result_projection.py:354` (`test_accepted_evidence_producer_mismatch_is_typed_exception`) 同时断言 direct exception 的 `expected_event_ref` / `observed_event_ref` 字段，以及 projection 包装后 `HostDurableError.__cause__` 是 `AcceptedEvidenceProducerEventRefMismatchError` 实例。Source scan `rg -n 'str(.*exc).*ACCEPTED_EVIDENCE' dayu/host` 零匹配。`rg -n 'ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host` 零匹配。

**裁决**: PASS。typed exception 正确替代 string constant；cause chain 保留；source scan 无残留。

### 2. evidence.py 作为 leaf contract 的 owner boundary

**Evidence**: `AcceptedToolEvidenceLLMMaterial`（frozen dataclass，四字段全 non-empty text）、`render_accepted_tool_evidence_for_llm()`（唯一四行 renderer）、`AcceptedEvidenceProducerEventRefMismatchError`、三个 unavailable 常量均定义在 `evidence.py`。`evidence.py` 只 import 标准库和 `dayu.host.evidence` 内部 helper（`_require_non_empty_text` 等），不 import `durable`、`accepted_result_projection`、`memory`、`compact_material`、`run_input` 或任何上层模块。

`accepted_result_projection.py` import 并 re-export `AcceptedToolEvidenceLLMMaterial`、`render_accepted_tool_evidence_for_llm`、三个 unavailable 常量到其 `__all__`，作为 producer public API surface 的一部分。这不是兼容性 re-export，而是 producer 把 leaf contract value 纳入自身稳定接口。

各 consumer（`memory.py`、`compact_material.py`、`compact_pipeline.py`、`run_input.py`）直接从 `evidence.py` import。`durable/memory.py` 从 `accepted_result_projection` import `AcceptedToolEvidenceLLMMaterial`，因其已 import `project_accepted_tool_result`，属同模块 natural import。

**Verification**: import boundary test（`test_import_boundary.py` + `test_weak_typing_guard.py`，25 passed）证明无 cycle。`pyright` 0 errors。`evidence.py` 无 lazy import、facade 或胶水代码。

**裁决**: PASS。leaf contract 放置正确，无 import cycle、lazy import、facade 或兼容 re-export 问题。

### 3. accepted_result_projection 作为 producer 的同源性

**Evidence**: `AcceptedToolResultProjection` 新增三个字段：`llm_material: AcceptedToolEvidenceLLMMaterial | None`、`tool_call_requested_event_ref: str | None`、`source_locator_refs: tuple[OpaqueEvidenceRef, ...]`。三者均在 `project_accepted_tool_result()` 内从同一 projection 上下文构造：

- `llm_material` 由 `_llm_material()` 从已校验的 `tool_name`、`query.text`、`source.text`、`result_text` 构造（`accepted_result_projection.py:688-718`）。
- `tool_call_requested_event_ref` 从 `envelope.tool_query.tool_call_requested_event_ref` 取值（`accepted_result_projection.py:224-228`）。
- `source_locator_refs` 从 `envelope.locator_refs` 取值（`accepted_result_projection.py:238-240`）。

`_optional_payload_text()` 替代旧 `_optional_text()`，字段缺失/null 返回 `None`，字段存在但类型错误或空白 raise `HostDurableError`（`accepted_result_projection.py:803-823`）。这比旧 lenient accessor 更严格，符合 plan 的 AgentMiMo DS-7 finding disposition。

**Verification**: `test_projection_malformed_optional_payload_text_fails_closed` 覆盖 tool_name 为 int、resolution_kind 为空白、tool_name 为 null 三种场景。`test_projection_missing_envelope_returns_shared_unavailable_source_text` 断言 `projection.llm_material` 非空且 renderer 输出正确四行。

**裁决**: PASS。`llm_material` / `tool_call_requested_event_ref` / `source_locator_refs` 均从同一 projection 上下文产生；strict accessor 正确替代 lenient accessor。

### 4. 消费者不再自行 parse envelope

**Evidence**:

- `durable/memory.py`: `_tool_result_memory_payload_view()` 删除 `accepted_evidence_envelope_from_payload()` 调用和 `event_payload_object_for_result_ref()` 调用，直接用 `projection.llm_material`（`durable/memory.py:425-433`）。
- `compact_material.py`: `_accepted_tool_evidence_delta_blocks()` 删除 `accepted_evidence_envelope_from_payload()` 调用和 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block，改用 `project_accepted_tool_result()` 的 `projection.llm_material`（`compact_material.py:2557-2588`）。
- `run_input.py`: `_tool_result_memory_payload()` 函数整体删除；`_memory_projection_event_from_row()` 改用 `project_accepted_tool_result().llm_material`（`run_input.py:3136-3151`）。

**Verification**: `rg -n 'accepted_evidence_envelope_from_payload' dayu/host/compact_material.py dayu/host/durable/memory.py dayu/host/run_input.py` 零匹配。`rg -n 'str(.*exc)' dayu/host/compact_material.py dayu/host/durable/memory.py dayu/host/run_input.py` 零匹配。

**裁决**: PASS。三个消费者均不再二次打开 envelope，统一消费 projection。

### 5. MemoryProjectionEvent 与 RunInputMaterialBlock 的 evidence contract

**MemoryProjectionEvent**: 删除 `evidence_query_text`、`evidence_tool_name`、`evidence_result_text`、`evidence_source_text` 四个 loose 字段，新增 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None`。`__post_init__` 校验类型（`memory.py:999-1009`）。非 compact event 必须 `compacted_semantics is None`（`memory.py:1001-1003`）。

**RunInputMaterialBlock**: 删除 `readable_tool_name`、`readable_query_text`、`readable_source_text`，新增 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None`。`__post_init__` 的 evidence invariant 双向校验（`compact_material.py:277-316`）：

- evidence block：section 和 kind 必须同时匹配；`accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref` 必须非空；`payload_refs` 或 `artifact_refs` 至少一条；`accepted_tool_evidence` 必须非空；`text` 必须等于 `render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`。
- non-evidence block：所有 evidence identity ref、provenance、`accepted_tool_evidence` 必须为空/None。

**Verification**: `test_accepted_result_projection.py` 中 evidence block 构造均传入 `accepted_tool_evidence`。`test_compact_material.py` 中 `_evidence_block()` helper 已迁移到 typed material。`test_memory_projection.py` 中 `_event()` helper 已迁移到 `accepted_tool_evidence`。所有 non-evidence block 构造不传入 evidence fields。

**裁决**: PASS。完整 evidence contract 原子迁移；non-evidence block 不携带 evidence fields。

### 6. LLM-facing renderer 输出格式

**Evidence**: `render_accepted_tool_evidence_for_llm()` 输出固定四行中文格式（`evidence.py:153-165`）：

```
工具名称：<tool_name>
查询语义：<query_text>
业务来源：<source_text>
工具结果：<result_text>
```

`material is None` 时返回 `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT`（`evidence.py:157-158`）。三个 unavailable 常量均不含 event_id / ref / digest / cursor / tool_call_id / wait / poll / runtime 术语。

`compact_pipeline.py:1110-1113` 和 `run_input.py:2935-2938` 各自在 renderer 前加 `_ACCEPTED_TOOL_EVIDENCE_PREFIX` section header，正文来自同一 renderer。`memory.py:1705-1709` 的 `_selected_evidence_text()` 直接调用 `render_accepted_tool_evidence_for_llm(event.accepted_tool_evidence)`。

**Verification**: `test_accepted_result_projection.py:265-268` 断言四行格式。`test_memory_projection.py:1496` 断言 fallback text 等于 `render_accepted_tool_evidence_for_llm(None)`。`test_compact_pipeline.py:375` 断言 `业务来源：filing page 12` 出现在 content 中。Source scan `rg -n 'def _accepted_tool_evidence_content|def _accepted_evidence_readable_text' dayu/host` 零匹配。

**裁决**: PASS。唯一 renderer 只输出业务可读四行；无内部治理信息泄漏。

### 7. CompactEvidenceBlock / EvidenceReadableItemVNext 的 no-rename mapping

**Evidence**: `_pack_evidence_blocks()` 从 `material` 字段直接构造 `CompactEvidenceBlock`（`compact_material.py:2753-2762`）：

| Target field | Source |
|---|---|
| `readable_tool_name` | `material.tool_name` |
| `readable_query_text` | `material.query_text` |
| `raw_result_text` | `material.result_text` |
| `readable_source_text` | `material.source_text` |

`_evidence_material_vnext()` 从 `CompactEvidenceBlock` 字段构造 `EvidenceReadableItemVNext`（`compact_material.py:3166-3175`）：

| Target field | Source |
|---|---|
| `tool_name` | `block.readable_tool_name` |
| `query_text` | `block.readable_query_text` |
| `response_text` | `block.raw_result_text` |
| `source_note` | `block.readable_source_text` |

`result_text` 只进入 `CompactEvidenceBlock.raw_result_text` 和 `EvidenceReadableItemVNext.response_text`。`block.text` 是完整四字段 renderer 输出，不被 parse。`content_digest` 使用 `_text_digest(material.result_text)` 而非 `_text_digest(block.text)`，只对 result 分量做 digest。

**Verification**: `test_accepted_result_projection.py:896-903` 断言 `block.text` 包含完整四行 renderer，且 `material.result_text` 在其中。`test_compact_material.py:1814-1822` 断言 `block.text == render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)` 且 `accepted_tool_evidence.result_text` 等于 raw outcome JSON。

**裁决**: PASS。no-rename mapping 正确；result_text 只保留在 raw_result_text / response_text 语义中。

### 8. Tool Trace 不变与 README decision

**Evidence**: `git diff -- dayu/host/tool_trace.py` 为空（source scan 通过）。`tool_trace.py` 不在 S3 allowed production files 中。

`dayu/host/README.md` 更新了两处（`README.md` diff）：

- accepted 工具结果描述段：新增 typed evidence material 和唯一 renderer 的说明。
- RunInputBuilder 段：新增 accepted tool evidence 的 ordinary raw tail 和 fallback 渲染只调用 typed material renderer 的说明。
- Memory `TOOL_RESULT_ACCEPTED` 段：更新为 typed LLM evidence material 和唯一 renderer 的描述。

`tests/README.md` 未变更：S3 只扩展现有 Host test 覆盖，未新增测试分层或命令族。根 README / `dayu/README.md` 未变更：无用户入口、安装/CLI/分层变化。

**Verification**: source scan `git diff -- dayu/host/tool_trace.py` 为空。README 变更内容与实际 implementation 一致。

**裁决**: PASS。Tool Trace 未变；README decision 符合 AGENTS.md 触发规则。

### 9. Controller validation 的验证充分性

**Evidence**:

- 测试：449 passed, 1 skipped（aggregate affected matrix）。
- Import boundary：25 passed。
- pyright：0 errors, 0 warnings, 0 informations。
- Coverage：逐文件 >= 80%（evidence.py 92%、accepted_result_projection.py 94%、memory.py 92%、durable/memory.py 85%、compact_material.py 86%、compact_pipeline.py 94%、run_input.py 88%）。
- Source scans：所有 hard scan 零匹配（旧 string constant、str(exc)、envelope re-parse、旧 private renderer、旧 payload field constants）。
- `git diff --check` pass。

**不足之处**: 未发现明确的测试缺口。controller validation 的测试矩阵、pyright、coverage 和 source scan 均足以支撑 PASS 结论。

**裁决**: PASS。验证充分。

---

## Open Questions

无。

## Residual Risk

- P3-E 仍为 accepted tool status fallback / raw outcome reconstruction 的 owner。S3 不触及 status 投影逻辑，`_accepted_status()` 仍按 P1-A 规则处理。
- P3-J 仍为全局 EventLog schema / taxonomy / DDL closed-set 的 owner。S3 不改 schema。
- `_optional_payload_text` 的 strict fail-closed 行为比旧 `_optional_text` 更严格，但这是 plan 中 AgentMiMo DS-7 的 accepted finding，有测试覆盖。若 production payload 存在历史上写入的 malformed optional 字段，该路径会 raise `HostDurableError` 而非静默降级——这是预期行为，不是 regression。

---

## 验证记录

本次 review 基于以下证据：

- **已运行**: git diff（各 production/test 文件）、source scans（`rg` / `grep` 验证旧符号零匹配）、`git diff -- dayu/host/tool_trace.py`（确认为空）、`git diff --check`。
- **未运行**: pytest、pyright、coverage（controller validation artifact 已报告 449 passed / 0 errors / 逐文件 >= 80%，reviewer 未独立重跑；若需独立验证，应运行 controller validation 中的完整命令）。
- **已阅读**: `evidence.py`、`accepted_result_projection.py`、`memory.py`、`durable/memory.py`、`compact_material.py`、`compact_pipeline.py`、`run_input.py` 的完整 diff；`test_accepted_result_projection.py`、`test_memory_projection.py`、`test_compact_material.py`、`test_compact_pipeline.py`、`test_run_input_builder.py` 的 diff；`dayu/host/README.md` 的 diff；`docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md` S3 section；`docs/reviews/wu-semantic-ownership-01-p3-c-s3-implementation-codex.md`；`docs/reviews/wu-semantic-ownership-01-p3-c-s3-controller-validation.md`。
