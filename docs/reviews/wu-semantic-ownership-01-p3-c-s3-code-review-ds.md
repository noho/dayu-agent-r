# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Code Review — AgentDS

## Scope

- Mode: current changes (workspace unstaged + staged diff)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-ds.md`
- Included scope: 当前工作树变动中的 P3-C S3 production/test/doc 文件
- Excluded scope: P3-C S1/S2 已提交变更、P3-A/P3-B 变更、`dayu/cli/` 无关变更、untracked non-S3 docs
- Review focus: P3-C S3 — accepted evidence typed LLM material / renderer / typed mismatch closure

## 结论

PASS

S3 实现正确完成了 accepted plan 要求的九项 closure，无阻塞性 finding。以下逐项审计结果及两条低严重度观察。

---

## Review Point 审计

### 1. typed mismatch exception 替代 string constant / str(exc) 协议

**PASS**

- 旧 `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 字符串常量已从 `evidence.py` 删除（`evidence.py:50` 旧址已无该常量）。
- 新增 `AcceptedEvidenceProducerEventRefMismatchError(ValueError)`，携带 `expected_event_ref` 与 `observed_event_ref`（`evidence.py:105-128`）。
- `accepted_evidence_envelope_from_payload()` 不再 `raise ValueError(string_constant)`，改为 `raise AcceptedEvidenceProducerEventRefMismatchError(expected_event_ref=..., observed_event_ref=...)`（`evidence.py:422-426`）。
- 上游 `_accepted_envelope()` 使用 `except AcceptedEvidenceProducerEventRefMismatchError as exc: raise HostDurableError(...) from exc` 保留 cause chain（`accepted_result_projection.py:293-294`）。
- 全 host 源代码扫描：
  - `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 零匹配。
  - `str(exc).*ACCEPTED_EVIDENCE` 零匹配。
  - 确认不再有 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 分支。

### 2. evidence.py 作为 leaf contract 的 owner boundary

**PASS**

- `AcceptedToolEvidenceLLMMaterial` 定义在 `evidence.py:131-165`。
- `render_accepted_tool_evidence_for_llm()` 定义在 `evidence.py:168-186`。
- `AcceptedEvidenceProducerEventRefMismatchError` 定义在 `evidence.py:105-128`。
- `evidence.py` 的 import 依赖只有 `dayu.contracts.json_value` 和 `dayu.host.durable.codec`（leaf 级别），不 import 任何 projection/durable/memory/compact 模块，不存在 import cycle。
- 无 lazy import、facade 或兼容 re-export 问题。类型和 renderer 自证为 value contract。
- `accepted_result_projection.py` import 这三者并放入 `__all__`（`accepted_result_projection.py:21-31, 838-851`），为消费者提供单一入口。

**观察 F-01（低严重度）**：`AcceptedToolEvidenceLLMMaterial` 与 `render_accepted_tool_evidence_for_llm` 的真源在 `evidence.py`，但 `accepted_result_projection.py.__all__` 将其重新导出。消费者 `durable/memory.py:45-46` 从 `accepted_result_projection` import，而 `compact_material.py:58-60` 从 `evidence` 直接 import。两条 import 路径指向同一符号，不一致但不构成 import cycle 或语义漂移。建议在 P3-E 或后续 slice 统一消费者从同一模块（建议 `accepted_result_projection` 作为公共入口）import，并记录在 README 的 import convention 中。

### 3. accepted_result_projection 仍是 accepted result projection producer

**PASS**

- `AcceptedToolResultProjection` 新增字段 `tool_call_requested_event_ref`（`accepted_result_projection.py:150`）、`llm_material`（`accepted_result_projection.py:158`）、`source_locator_refs`（`accepted_result_projection.py:160`）。
- `_optional_text` 改为 `_optional_payload_text`：字段缺失/null 返回 `None`，但类型错误或空白时 `raise HostDurableError`（`accepted_result_projection.py:803-823`）。这是 **strict optional payload accessor**——不再把 malformed 值当成缺失字段。
- `tool_call_requested_event_ref`、`source_locator_refs`、`llm_material` 均从同一 `envelope`/`projection` 派生，同源不变：
  - `tool_call_requested_event_ref` ← `envelope.tool_query.tool_call_requested_event_ref`（`accepted_result_projection.py:225-229`）
  - `source_locator_refs` ← `envelope.locator_refs`（`accepted_result_projection.py:241-243`）
  - `llm_material` ← `_llm_material(tool_name, query, source, result_text)`（`accepted_result_projection.py:209-214`）
- `_llm_material()` 在 `tool_name` 或 `result_text` 缺失时返回 `None`（`accepted_result_projection.py:707-708`），其余字段来自已校验 `query.text` 和 `source.text`。

### 4. memory / durable memory / compact material / compact pipeline / run input 不再自行 parse accepted evidence envelope

**PASS**

- Source scan 确认 `accepted_evidence_envelope_from_payload` 在以下文件零匹配：`compact_material.py`、`durable/memory.py`、`run_input.py`、`memory.py`。
- 各消费者改用 typed material/renderer：
  - `memory.py:_selected_evidence_text()` 改为 `return render_accepted_tool_evidence_for_llm(event.accepted_tool_evidence)`（`memory.py:1710`）。
  - `durable/memory.py:_tool_result_memory_payload_view()` 删除整段 envelope 二次解析；直接使用 `projection.llm_material`（`durable/memory.py:425-431`）。
  - `compact_material.py:_accepted_tool_evidence_delta_blocks()` 改为先调 `project_accepted_tool_result()`，再取 `projection.llm_material`；删除 `accepted_evidence_envelope_from_payload()` 调用和 `str(exc)` catch（`compact_material.py:2557-2586`）。
  - `run_input.py:_memory_projection_payload()` 删除 `_tool_result_memory_payload()` 及其 envelope 解析（`run_input.py:3179-3193`）。

### 5. MemoryProjectionEvent 与 RunInputMaterialBlock 的 evidence contract

**PASS**

- `MemoryProjectionEvent` 以单一 typed field `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None` 取代旧四个 loose text fields（`evidence_query_text`、`evidence_tool_name`、`evidence_result_text`、`evidence_source_text`）（`memory.py:973`）。
- `__post_init__` 校验非 evidence 事件不携带 evidence fields：只验证类型合法性（`memory.py:1002-1011`），不强制 evidence event 必须携带 material（fallback 由 renderer 处理）。
- `RunInputMaterialBlock` 同样以 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None` 取代三个 loose fields（`readable_tool_name`、`readable_query_text`、`readable_source_text`）（`compact_material.py:220`）。
- evidence block invariant 严格校验（`compact_material.py:264-316`）：
  - evidence block 要求 `accepted_tool_evidence is not None`。
  - `block.text` 必须等于 `render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence)`。
  - non-evidence block 禁止携带 `accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref`、payload/artifact refs、`accepted_tool_evidence`。
- 非 evidence 消息（compact event、user input、assistant answer 等）在 durable memory 路径中 `accepted_tool_evidence=None`（`durable/memory.py:382-437`），在 run input 路径中也只在 `TOOL_RESULT_ACCEPTED` 时设置 material（`run_input.py:3139-3175`）。

### 6. LLM-facing renderer 只输出业务可读四行

**PASS**

- `render_accepted_tool_evidence_for_llm()` 输出（`evidence.py:179-186`）：

```text
工具名称：{material.tool_name}
查询语义：{material.query_text}
业务来源：{material.source_text}
工具结果：{material.result_text}
```

- material 为 `None` 时返回整体 fallback: `"工具证据不可用；缺少可安全展示的工具名称或工具结果。"`（`evidence.py:177`）。
- 不包含 event_id、ref、digest、cursor、tool_call_id、wait、poll、runtime 或任何 Host/Engine 内部治理标识。
- 三个 fallback 常量均为业务可读中文，无内部技术术语：
  - `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` = `"查询语义不可用；参数未安全展开。"`
  - `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` = `"业务来源不可用；工具结果未提供可安全展示的来源。"`
  - `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` = `"工具证据不可用；缺少可安全展示的工具名称或工具结果。"`

### 7. CompactEvidenceBlock / EvidenceReadableItemVNext no-rename mapping

**PASS**

- `_pack_evidence_blocks()` 中 component 字段取值（`compact_material.py:2751-2762`）：
  - `readable_tool_name = material.tool_name`（值直接取自 typed material，无重命名/变换）
  - `readable_query_text = material.query_text`
  - `raw_result_text = material.result_text`
  - `readable_source_text = material.source_text`
- `EvidenceReadableItemVNext` 映射（`compact_material.py:3168-3174`）：
  - `response_text = block.raw_result_text`（= `material.result_text`）
- `block.text`（`RunInputMaterialBlock.text`）保持为完整四行 renderer 输出，不反向解析为 component 字段。
- `result_text` 分量只在 `raw_result_text`/`response_text` 语义中，不在 `block.text` 被当作结果正文使用。

### 8. Tool Trace 本轮保持不变

**PASS**

- `git diff -- dayu/host/tool_trace.py` 输出为空。
- 无 status/P3-E 改动混入本轮变更。
- README decision 符合 AGENTS.md：`dayu/host/README.md` 更新了 accepted evidence 投影边界描述（Host 实现事实变更触发），`tests/README.md` 不更新（仅扩展现有测试，无新测试层/命令族/维护规则）。

### 9. 验证充分性评估

**PASS，测试/pyright/coverage/source scan 足以支撑结论**

控制器独立验证结果（均由本 reviewer 重新执行并确认）：

| 验证项 | 命令 | 结果 |
|---|---|---|
| affected tests | `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q` | 287 passed, 1 skipped |
| compact related tests | `pytest tests/host/test_context_compact_events.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py -q` | 149 passed |
| import/typing | `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 25 passed |
| pyright | `pyright dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py` | 0 errors, 0 warnings |
| source scan: string constant | `grep -rn ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH dayu/host/` | 零匹配 |
| source scan: str(exc) | `grep -rn 'str(exc).*ACCEPTED_EVIDENCE' dayu/host/` | 零匹配 |
| source scan: envelope in consumers | `grep -rn accepted_evidence_envelope_from_payload dayu/host/{compact_material,durable/memory,run_input,memory}.py` | 零匹配 |
| source scan: dead helpers | `grep -rn 'def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text' dayu/host/` | 零匹配 |
| Tool Trace unchanged | `git diff -- dayu/host/tool_trace.py` | 空 |

覆盖率（控制器报告，需 `pytest-cov` 验证）：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/host/evidence.py` | 92% |
| `dayu/host/accepted_result_projection.py` | 94% |
| `dayu/host/memory.py` | 92% |
| `dayu/host/durable/memory.py` | 85% |
| `dayu/host/compact_material.py` | 86% |
| `dayu/host/compact_pipeline.py` | 94% |
| `dayu/host/run_input.py` | 88% |

全部 >= 80%，总覆盖率 89.38%。

**覆盖缺口**：`durable/memory.py` 的 85% 和 `compact_material.py` 的 86% 偏低，但都在 >=80% 阈值以上。未覆盖行经 inspection（`_MemorySnapshotIntegrityRowIdentity` 仅在 integrity scan 路径使用，当前测试覆盖率以 happy-path projection 为主），不属于 S3 引入的 gap。建议 P3-E 或 P3-J 补充 integrity scan 路径测试。

---

## Findings

### F-01 — 低 — accepted evidence material/renderer import 路径不一致

- **入口/函数**: `durable/memory.py:45-46` vs `compact_material.py:58-60`
- **文件(行号)**: `dayu/host/durable/memory.py:45-46`、`dayu/host/compact_material.py:58-60`、`dayu/host/accepted_result_projection.py:838-851`
- **输入场景**: 任何 import `AcceptedToolEvidenceLLMMaterial` 或 `render_accepted_tool_evidence_for_llm` 的 Host 模块
- **实际分支**: `durable/memory.py` 从 `accepted_result_projection`（re-export）import；`compact_material.py` 从 `evidence`（source）import
- **预期行为**: 所有消费者从同一公共模块 import，形成一致的 import convention
- **实际行为**: 两个消费者使用两条不同的 import 路径获取同一个符号
- **直接证据**:
  - `durable/memory.py:45-46`: `from dayu.host.accepted_result_projection import (AcceptedToolEvidenceLLMMaterial, project_accepted_tool_result)`
  - `compact_material.py:58-60`: `from dayu.host.evidence import AcceptedToolEvidenceLLMMaterial` / `from dayu.host.evidence import render_accepted_tool_evidence_for_llm`
  - 两者解析到同一个 `evidence.AcceptedToolEvidenceLLMMaterial` 和 `evidence.render_accepted_tool_evidence_for_llm`
- **影响**: 不产生运行时错误或 import cycle，但增加维护者认知负担——不清楚应该从哪个模块 import evidence material
- **建议改法和验证点**: 在 P3-E 统一消费者从 `accepted_result_projection`（作为 accepted-result 公共 API 入口）import；或反过来全部从 `evidence` import。更新 README 记录 canonical import path。验证：`rg "from dayu.host.evidence import.*(AcceptedToolEvidenceLLMMaterial|render_accepted_tool_evidence_for_llm)" dayu/host/durable/` 应为零匹配（或反方向统一）
- **修复风险**: 低（纯 import 重整，不涉及行为变更）
- **严重程度**: 低

### F-02 — 低 — `_pack_evidence_blocks` 中 `size_units` 统计口径变更未在 plan 中显式说明

- **入口/函数**: `_pack_evidence_blocks()`
- **文件(行号)**: `dayu/host/compact_material.py:2759`
- **输入场景**: 任意 accepted tool evidence block 被 pack 为 `CompactEvidenceBlock`
- **实际分支**: `size_units=len(material.result_text)`（仅结果文本长度）
- **预期行为**: 旧代码使用 `size_units=len(block.text)`（完整四行 renderer 长度）
- **实际行为**: `size_units` 现在只统计 `result_text` 长度，不包含工具名称/查询语义/业务来源标签行
- **直接证据**: diff 中 `size_units=len(block.text)` → `size_units=len(material.result_text)`（`compact_material.py:2759`）
- **影响**: `CompactEvidenceBlock.size_units` 值会比旧值小（约减少三行标签的固定字符数），下游 budget estimation 若依赖该值可能出现微小偏移。实际上 `size_units` 表示 evidence "内容"尺寸，result_text 是其主体内容，变更方向正确。但此变更未被 plan section 显式记录为 size_units 语义迁移。
- **建议改法和验证点**: 不需要回退。建议在 P3-E 中统一确认 compact material 中 `size_units` 的使用者是否已适配新口径（或无需适配）。验证：grep CompactEvidenceBlock 的所有消费者，确认它们对 size_units 的假设。
- **修复风险**: 低（无需回退，仅需确认下游消费者）
- **严重程度**: 低

---

## Open Questions

无。

---

## Residual Risk

1. **P3-E scope（非 S3 阻塞）**: accepted tool status fallback/raw outcome reconstruction 仍属于 P3-E。`_accepted_status()` 中 `LOST` 状态推断逻辑（`accepted_result_projection.py:397-410`）在 `resolution_kind`/`tool_fact_kind` 缺失且 `raw_outcome` 为 None 时返回 `LOST`，该逻辑未被本轮修改。
2. **P3-J scope（非 S3 阻塞）**: 全局 EventLog schema/taxonomy/DDL closed-set 仍属于 P3-J。evidence material/renderer 的无 durable 依赖 value contract 当前位于 `evidence.py` leaf，避免了 Host bootstrap cycle。P3-J 可能将此 contract 提升至公共契约层，但当前方案正确且不阻塞。
3. **F-01 import path 不一致**: 建议 P3-E 统一，当前无运行时风险。
4. **F-02 size_units 口径**: 建议 P3-E 确认下游消费者适配，当前无已知错误。

---

## 验证执行记录

以下验证由本 reviewer 在 review 期间独立运行：

| 验证 | 命令 | 结果 |
|---|---|---|
| affected tests | `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q` | 287 passed, 1 skipped |
| compact related tests | `pytest tests/host/test_context_compact_events.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py -q` | 149 passed |
| import/typing boundary | `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 25 passed |
| pyright (changed files) | `pyright dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py` | 0 errors, 0 warnings |
| source scan: string constant | `grep -rn ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH dayu/host/ --include='*.py'` | 零匹配 |
| source scan: str(exc) | `grep -rn 'str(exc).*ACCEPTED_EVIDENCE\|ACCEPTED_EVIDENCE.*str(exc)' dayu/host/ --include='*.py'` | 零匹配 |
| source scan: envelope in consumers | `grep -rn accepted_evidence_envelope_from_payload dayu/host/compact_material.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/memory.py` | 零匹配 |
| source scan: dead helpers | `grep -rn 'def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text' dayu/host/ --include='*.py'` | 零匹配 |
| source scan: tool_trace unchanged | `git diff -- dayu/host/tool_trace.py` | 空 |

以下验证未独立运行（信任控制器验证结果）：

- 覆盖率报告（需 `pytest-cov` 插件）
- 完整 `pyright dayu/ tests/ utils/` 全量扫描
