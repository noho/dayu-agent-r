# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Fix Re-Review — AgentDS

## 结论

PASS

P3-C-S3-CR-F01 已正确关闭。accepted evidence material / renderer / fallback texts 的 canonical owner 为 `dayu.host.evidence`；`accepted_result_projection` 不再作为 evidence material 的 public surface；各消费者与测试均从 `dayu.host.evidence` import。无 import cycle、lazy import、facade、兼容 re-export、类型倒挂或反向依赖。README 准确表达 projection 产出 typed material、`dayu.host.evidence` 拥有唯一 renderer/fallback。F-02 维持 rejected-as-non-defect，无直接反证。S3 原始九项 review 重点无 regression。

---

## 验证重点逐项审计

### 1. P3-C-S3-CR-F01 关闭确认：canonical owner 迁移

**PASS**

| 检查项 | 结果 | 证据 |
|---|---|---|
| `accepted_result_projection.__all__` 不含 evidence material/renderer/fallback | PASS | `accepted_result_projection.py:844-852`：仅含 `AcceptedToolResultProjection`、projection 子类型、`project_accepted_tool_result`。无 `AcceptedToolEvidenceLLMMaterial`、`render_accepted_tool_evidence_for_llm`、`ACCEPTED_EVIDENCE_*_UNAVAILABLE_TEXT`。 |
| Host/test consumer 不从 `accepted_result_projection` import evidence leaf symbols | PASS | `grep -rn "from dayu.host.accepted_result_projection import.*AcceptedToolEvidenceLLMMaterial" dayu/host/ tests/` 零匹配；renderer 与 fallback text 同样零匹配。 |
| 消费者从 `dayu.host.evidence` import | PASS | `durable/memory.py:46`、`memory.py:26`、`compact_material.py:58-60`、`compact_pipeline.py:36`、`run_input.py:129` 均从 `dayu.host.evidence` import；测试文件 `test_accepted_result_projection.py:33,57`、`test_compact_material.py:14,92-93`、`test_memory_projection.py:75,81`、`test_run_input_builder.py:163`、`test_compact_pipeline.py:51` 同样从 `evidence` import。 |
| `accepted_result_projection` 内部使用 private alias | PASS | `accepted_result_projection.py:27-38`：`AcceptedToolEvidenceLLMMaterial as _AcceptedToolEvidenceLLMMaterial`、`render_accepted_tool_evidence_for_llm` 的 import 已移除，其余 evidence 符号使用 `_` 前缀 private alias。这些是 projection producer 的内部依赖，不对外暴露。 |
| `accepted_result_projection` 只生产 `llm_material`，不再作为 renderer/material public surface | PASS | `project_accepted_tool_result()` 在 `accepted_result_projection.py:209-214` 构造 `AcceptedToolResultProjection.llm_material`，调用 `_llm_material()`（内部 helper）。Consumer 取 `projection.llm_material` 后交由 `evidence.render_accepted_tool_evidence_for_llm()` 渲染。 |

**F-01 关闭确认**: accepted evidence material / renderer / fallback texts 的 canonical owner 为 `dayu.host.evidence`；Host/test consumer 不再从 `accepted_result_projection` import 这些 leaf symbols；`accepted_result_projection` 只生产 `llm_material`，不再作为 renderer/material public surface。

### 2. Import cycle / lazy import / facade / 兼容 re-export / 类型倒挂 / 反向依赖

**PASS**

| 检查项 | 结果 | 证据 |
|---|---|---|
| import cycle | PASS | `evidence.py` 仅 import `dayu.contracts.json_value` 和 `dayu.host.durable.codec`（`evidence.py:13-14`），不 import 任何 projection/durable/memory/compact 模块。`accepted_result_projection.py` import `evidence`（单向）。Import boundary tests 25 passed。 |
| lazy import | PASS | `grep -rn "lazy_import\|LazyImport\|import_module\|importlib"` 在全量 S3 变更文件中零匹配。 |
| facade / 兼容 re-export | PASS | `accepted_result_projection.__all__` 不含任何 evidence leaf symbol；内部使用的 evidence 符号均以 `_` 前缀 private alias 导入，不构成 facade。无兼容性 wrapper 或胶水 seam。 |
| 类型倒挂 | PASS | `AcceptedToolEvidenceLLMMaterial` 是 frozen dataclass with `__post_init__` 强校验（`evidence.py:131-165`），所有字段为 `str`。下游消费者使用该类型时均为 typed field access，无 `hasattr`/`getattr` 或 loose dict 访问。 |
| 反向依赖 | PASS | 依赖方向：`evidence` ← `accepted_result_projection` ← `memory` / `compact_material` / `compact_pipeline` / `run_input` / `durable/memory`。`evidence` 不依赖任何上层模块。符合 `UI -> Service -> Host -> Engine` 分层约束。 |

### 3. README 准确性

**PASS**

| 声明 | README 位置 | 与实际代码一致性 |
|---|---|---|
| "typed evidence material，再由唯一 renderer 输出四行业务可读文本" | `dayu/host/README.md:34` | 一致：`AcceptedToolEvidenceLLMMaterial`（`evidence.py:131-165`）为 typed material；`render_accepted_tool_evidence_for_llm()`（`evidence.py:168-186`）为唯一 renderer。 |
| "调用 `dayu.host.evidence` 的唯一 renderer" | `dayu/host/README.md:364` | 一致：RunInputBuilder 路径通过 `run_input.py:129` import `render_accepted_tool_evidence_for_llm`，并在 `run_input.py:2937` 调用。 |
| "Conversation Memory 总是调用 `dayu.host.evidence` 的唯一 renderer" | `dayu/host/README.md:662` | 一致：`memory.py:26-28` import `render_accepted_tool_evidence_for_llm`，`memory.py:1710` 调用。 |
| "material 缺失时使用同一 renderer 的整体 fallback" | `dayu/host/README.md:662` | 一致：`render_accepted_tool_evidence_for_llm(None)` 返回 `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT`（`evidence.py:177-178`）。 |

README 准确表达了 projection 产出 typed material、`dayu.host.evidence` 拥有唯一 renderer/fallback。

### 4. F-02 rejected-as-non-defect 确认

**同意 rejected-as-non-defect，无直接反证。**

Controller 裁决理由经复核成立：

- `_pack_evidence_blocks()` 中 `size_units=len(material.result_text)`（`compact_material.py:2759`）的语义是 evidence "内容"尺寸，`result_text` 是其主体内容分量。
- 初始 evidence packing 路径（`compact_material.py:1496`）已使用 `size_units=len(material.raw_result_text)` 的相同分量语义。
- S3 plan 明确要求 `CompactEvidenceBlock.raw_result_text` 和 `EvidenceReadableItemVNext.response_text` 携带纯 result component，而 `block.text` 保持完整四行 renderer 输出。`size_units` 使用 `result_text` 长度与这一 design 一致。
- `content_digest` 同样使用 `_text_digest(material.result_text)`（`compact_material.py:2761`），与 `size_units` 语义对齐。

未发现任何直接证据表明该口径变更会导致下游 budget estimation 错误或行为异常。controller 的 rejected-as-non-defect 裁决维持。

### 5. S3 原始九项 review 重点 — regression 检查

全部九项经独立重验，无 regression：

| # | Review Point | 状态 | 验证方法 |
|---|---|---|---|
| 1 | typed mismatch exception 替代 string constant / str(exc) 协议 | PASS | `evidence.py:105-128` `AcceptedEvidenceProducerEventRefMismatchError`；`evidence.py:422-426` raise typed exception；source scan 零旧常量/str(exc) 匹配。 |
| 2 | evidence.py 作为 leaf contract owner boundary | PASS | `evidence.py` 定义全部 evidence 类型/renderer/fallback；`accepted_result_projection.__all__` 不含 evidence leaf symbols；consumers 从 `evidence` import。 |
| 3 | accepted_result_projection 仍是 producer | PASS | `AcceptedToolResultProjection` 含 `llm_material`、`tool_call_requested_event_ref`、`source_locator_refs` 三字段；`_optional_payload_text` strict fail-closed；同源构造。 |
| 4 | 消费者不再自行 parse envelope | PASS | `accepted_evidence_envelope_from_payload` 在 `compact_material.py`/`durable/memory.py`/`run_input.py`/`memory.py` 零匹配。 |
| 5 | MemoryProjectionEvent / RunInputMaterialBlock evidence contract | PASS | `memory.py:973` `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial \| None`；`compact_material.py:220` 同字段 + invariant 校验；non-evidence block 禁止携带 evidence fields。 |
| 6 | LLM-facing renderer 只输出业务可读四行 | PASS | `evidence.py:179-186` 四行中文格式；三个 fallback 常量均不含内部治理术语；`material is None` 时返回整体 fallback。 |
| 7 | CompactEvidenceBlock / EvidenceReadableItemVNext no-rename mapping | PASS | `_pack_evidence_blocks()` 字段直接取自 typed material（`compact_material.py:2754-2761`）；`result_text` 只在 `raw_result_text`/`response_text` 语义中。 |
| 8 | Tool Trace 不变 | PASS | `git diff -- dayu/host/tool_trace.py` 空。 |
| 9 | 验证充分性 | PASS | 本 reviewer 独立运行：227 targeted passed、449 full matrix passed (1 skipped)、25 import boundary passed、pyright 0 errors、全部 source scan 零匹配。 |

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

---

## Residual Risk

- P3-E 仍为 accepted tool status fallback / raw outcome reconstruction owner。`_accepted_status()` 中 `LOST` 推断逻辑未被 S3 改动。
- P3-J 仍为全局 EventLog schema / taxonomy / DDL closed-set owner。evidence material/renderer 的 value contract 当前位于 `evidence.py` leaf，避免了 Host bootstrap cycle。
- `accepted_result_projection.py` 内部使用的 evidence 符号以 `_` 前缀 private alias 导入（`_AcceptedToolEvidenceLLMMaterial`、`_AcceptedEvidenceProducerEventRefMismatchError`、`_ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`、`_ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`）。这是 projection producer 的内部实现细节，不属于 public API surface，但若未来有模块通过 `from dayu.host.accepted_result_projection import _AcceptedToolEvidenceLLMMaterial` 绕过 public contract，将构成语义漂移。当前 source scan 确认无此类绕过，建议 P3-E 或 P3-J 中将此约束写入 import convention 文档。

---

## 验证执行记录

以下验证由本 reviewer 在 re-review 期间独立运行：

| 验证 | 命令 | 结果 |
|---|---|---|
| targeted S3 tests | `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py -q` | 227 passed |
| full S3 affected matrix | `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py -q` | 449 passed, 1 skipped |
| import/typing boundary | `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 25 passed |
| pyright (changed files) | `pyright dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py` | 0 errors, 0 warnings, 0 informations |
| canonical import scan: evidence material from projection | `grep -rn "from dayu.host.accepted_result_projection import.*AcceptedToolEvidenceLLMMaterial" dayu/host/ tests/` | 零匹配 |
| canonical import scan: renderer from projection | `grep -rn "from dayu.host.accepted_result_projection import.*render_accepted_tool_evidence_for_llm" dayu/host/ tests/` | 零匹配 |
| canonical import scan: fallback from projection | `grep -rn "from dayu.host.accepted_result_projection import.*ACCEPTED_EVIDENCE" dayu/host/ tests/` | 零匹配 |
| source scan: old string constant | `grep -rn ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH dayu/host/ --include='*.py'` | 零匹配 |
| source scan: str(exc) | `grep -rn 'str(exc).*ACCEPTED_EVIDENCE\|ACCEPTED_EVIDENCE.*str(exc)' dayu/host/ --include='*.py'` | 零匹配 |
| source scan: envelope in consumers | `grep -rn accepted_evidence_envelope_from_payload dayu/host/compact_material.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/memory.py` | 零匹配 |
| source scan: dead helpers | `grep -rn 'def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text' dayu/host/ --include='*.py'` | 零匹配 |
| source scan: lazy import | `grep -rn 'lazy_import\|LazyImport\|import_module\|importlib' dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py` | 零匹配 |
| Tool Trace unchanged | `git diff -- dayu/host/tool_trace.py` | 空 |

以下验证未独立运行（信任 controller validation 结果）：

- 全量 `pyright dayu/ tests/ utils/` 扫描
- 覆盖率报告（需 `pytest-cov` 插件）
- `git diff --check`
