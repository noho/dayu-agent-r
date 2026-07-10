# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Fix Re-Review — AgentMiMo

## Scope

- Mode: current changes (re-review of S3 fix only)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-rereview-mimo.md`
- Included scope: S3 code review findings after fix gate
- Excluded scope: P3-E / P3-J residual, non-S3 changes

## 输入证据

- 原 code review: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-ds.md`
- controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-controller-adjudication.md`
- fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-fix-codex.md`
- fix validation: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-fix-controller-validation.md`

---

## 结论

**PASS**

S3 fix 正确关闭了 controller-accepted finding P3-C-S3-CR-F01，未引入 regression。F02 被 controller 正确裁决为非缺陷，无直接反证。以下逐项 evidence-based 验证。

---

## 1. P3-C-S3-CR-F01 关闭验证

### 1.1 `accepted_result_projection.__all__` 不再导出 evidence 符号

**Evidence**: `accepted_result_projection.py:844-852` 的 `__all__` 只包含 projection 类型：

```python
__all__ = [
    "AcceptedToolResultProjection",
    "AcceptedToolResultQueryProjection",
    "AcceptedToolResultQueryState",
    "AcceptedToolResultSourceProjection",
    "AcceptedToolResultSourceState",
    "AcceptedToolResultStatus",
    "project_accepted_tool_result",
]
```

无 `AcceptedToolEvidenceLLMMaterial`、`render_accepted_tool_evidence_for_llm`、`ACCEPTED_EVIDENCE_*_UNAVAILABLE_TEXT` 或 `AcceptedEvidenceProducerEventRefMismatchError`。

`accepted_result_projection.py` 仍 import 这些符号供内部使用（lines 20-38），但全部使用 `_` 前缀别名（`_AcceptedToolEvidenceLLMMaterial`、`_ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 等），不暴露到 public API。

**裁决**: PASS。evidence 符号不再是 `accepted_result_projection` 的 public surface。

### 1.2 Host/test consumer 直接从 `evidence` import

**Evidence** — 生产代码 import 路径：

| 文件 | import 来源 | 符号 |
|---|---|---|
| `durable/memory.py:46` | `dayu.host.evidence` | `AcceptedToolEvidenceLLMMaterial` |
| `compact_material.py:59` | `dayu.host.evidence` | `AcceptedToolEvidenceLLMMaterial` |
| `compact_material.py:60` | `dayu.host.evidence` | `render_accepted_tool_evidence_for_llm` |
| `compact_pipeline.py:36` | `dayu.host.evidence` | `render_accepted_tool_evidence_for_llm` |
| `memory.py:26-29` | `dayu.host.evidence` | `AcceptedToolEvidenceLLMMaterial`, `render_accepted_tool_evidence_for_llm` |
| `run_input.py:129` | `dayu.host.evidence` | `render_accepted_tool_evidence_for_llm` |

**Evidence** — 测试代码 import 路径：

| 文件 | import 来源 |
|---|---|
| `test_accepted_result_projection.py:33,57` | `dayu.host.evidence` |
| `test_memory_projection.py:75,81` | `dayu.host.evidence` |
| `test_compact_material.py:14,93` | `dayu.host.evidence` |
| `test_compact_pipeline.py:51` | `dayu.host.evidence` |
| `test_run_input_builder.py:163` | `dayu.host.evidence` |

**Source scan**: `grep -rn "from dayu.host.accepted_result_projection import.*AcceptedToolEvidenceLLMMaterial\|from dayu.host.accepted_result_projection import.*render_accepted_tool_evidence\|from dayu.host.accepted_result_projection import.*UNAVAILABLE" dayu/host/ tests/host/` — 零匹配。

**裁决**: PASS。所有 consumer 直接从 `dayu.host.evidence` import evidence 符号，无一从 `accepted_result_projection` import。

### 1.3 `accepted_result_projection` 只生产 `llm_material`，不再作为 renderer/material public surface

**Evidence**: `accepted_result_projection.py` 的职责明确为 projection producer——将 `TOOL_RESULT_ACCEPTED` durable truth 投影为 `AcceptedToolResultProjection`，包括 `llm_material` 字段。`_llm_material()` helper（lines 697-720）从已校验 projection 字段构造 material，但不对外暴露 material 类型本身。

README `dayu/host/README.md:34` 明确记录："需要进入 LLM 上下文的工具名称、查询语义、业务来源和工具结果会先形成 typed evidence material，再由唯一 renderer 输出四行业务可读文本。"

README `dayu/host/README.md:364` 明确记录："accepted tool evidence 的 ordinary raw tail 和 fallback 渲染只消费 accepted-result projection 产出的 typed material，并调用 `dayu.host.evidence` 的唯一 renderer。"

README `dayu/host/README.md:662` 明确记录："durable memory consumer 先通过 Host accepted result projection 取得 typed LLM evidence material，Conversation Memory 总是调用 `dayu.host.evidence` 的唯一 renderer。"

**裁决**: PASS。projection 产出 typed material，`evidence.py` 拥有唯一 renderer/fallback，README 准确表达。

---

## 2. 架构违规检查

### 2.1 Import cycle

**Evidence**: `evidence.py` 是 leaf——只 import `dayu.contracts.json_value` 和 `dayu.host.durable.codec`，不 import 任何 projection / durable / memory / compact 模块。`accepted_result_projection.py` import `evidence.py`（正确方向：producer → leaf contract）。各 consumer import `evidence.py`（正确方向：consumer → leaf contract）。

**裁决**: PASS。无 import cycle。

### 2.2 Lazy import / facade / 兼容 re-export

**Evidence**: 全量 source scan `grep -rn "lazy\|importlib\|__getattr__" dayu/host/evidence.py dayu/host/accepted_result_projection.py` 零匹配。`accepted_result_projection.py` 的 `_` 前缀 import 是内部使用，不构成 facade 或兼容 re-export（不暴露到 `__all__`）。

**裁决**: PASS。无 lazy import、facade 或兼容 re-export。

### 2.3 类型倒挂 / 反向依赖

**Evidence**: 依赖方向为 `consumer → accepted_result_projection → evidence → durable/codec → contracts`，无反向。`evidence.py` 不 import 任何上层模块。

**裁决**: PASS。无类型倒挂或反向依赖。

---

## 3. README 准确性

**Evidence**: `dayu/host/README.md` 三处关键描述：

- Line 34: "typed evidence material...唯一 renderer 输出四行业务可读文本"——准确。
- Line 364: "accepted-result projection 产出的 typed material...`dayu.host.evidence` 的唯一 renderer"——准确。
- Line 662: "Host accepted result projection 取得 typed LLM evidence material...`dayu.host.evidence` 的唯一 renderer"——准确。

**裁决**: PASS。README 准确表达 projection 产出 typed material、`evidence.py` 拥有唯一 renderer/fallback。

---

## 4. F02 裁决确认

**Controller 裁决**: P3-C-S3-CR-F02 rejected as non-defect。

**Controller 理由**: existing initial evidence packing already used `size_units=len(material.raw_result_text)`，and the accepted P3-C S3 plan requires `CompactEvidenceBlock.raw_result_text` and `EvidenceReadableItemVNext.response_text` to carry the pure result component while `block.text` remains the full four-line renderer. The delta evidence path now matches that existing compact evidence component-size semantics.

**反证检查**: 无直接反证。`size_units` 表示 evidence "内容"尺寸，`result_text` 是其主体内容。现有 initial evidence path 已使用相同口径。delta evidence path 现在与 initial evidence path 一致。

**裁决**: 同意 rejected-as-non-defect。无需代码变更。

---

## 5. S3 原始九项 review 重点 regression 检查

| # | Review 重点 | Regression? | Evidence |
|---|---|---|---|
| 1 | typed mismatch exception 替代 string constant | 无 | `AcceptedEvidenceProducerEventRefMismatchError` 在 `evidence.py:105-128`，source scan 零匹配旧常量 |
| 2 | evidence.py 作为 leaf contract owner boundary | 无 | `evidence.py` 仍是 leaf，不 import 上层模块 |
| 3 | accepted_result_projection 作为 producer 同源性 | 无 | `llm_material` / `tool_call_requested_event_ref` / `source_locator_refs` 仍从同一 projection 上下文构造 |
| 4 | 消费者不再自行 parse envelope | 无 | source scan `accepted_evidence_envelope_from_payload` 在 consumer 文件零匹配 |
| 5 | MemoryProjectionEvent / RunInputMaterialBlock evidence contract | 无 | 449 tests pass，含 evidence invariant 测试 |
| 6 | LLM-facing renderer 只输出四行业务可读文本 | 无 | `render_accepted_tool_evidence_for_llm` 在 `evidence.py:168-186`，无内部治理信息泄漏 |
| 7 | CompactEvidenceBlock / EvidenceReadableItemVNext no-rename mapping | 无 | `material.result_text` → `raw_result_text` → `response_text` 映射不变 |
| 8 | Tool Trace 本轮保持不变 | 无 | `git diff -- dayu/host/tool_trace.py` 为空 |
| 9 | 验证充分性 | 无 | 449 passed / 25 passed / pyright 0 errors / source scans 全部 clean |

**裁决**: PASS。S3 原始九项 review 重点无 regression。

---

## Open Questions

无。

## Residual Risk

- P3-E 仍为 accepted tool status fallback / raw outcome reconstruction 的 owner。S3 不触及 status 投影逻辑。
- P3-J 仍为全局 EventLog schema / taxonomy / DDL closed-set 的 owner。S3 不改 schema。
- `_optional_payload_text` 的 strict fail-closed 行为比旧 `_optional_text` 更严格，但这是 plan 中 AgentMiMo DS-7 的 accepted finding，有测试覆盖。

---

## 验证记录

### 已独立运行

| 验证项 | 命令 | 结果 |
|---|---|---|
| targeted Host tests | `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py -q` | 227 passed |
| S3 affected matrix | `pytest tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_memory_projection.py tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q` | 449 passed, 1 skipped |
| import / weak typing guards | `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 25 passed |
| targeted pyright | `pyright dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py` | 0 errors, 0 warnings, 0 informations |
| canonical import scan | `grep "from dayu.host.accepted_result_projection import.*AcceptedToolEvidenceLLMMaterial\|from dayu.host.accepted_result_projection import.*render_accepted_tool_evidence\|from dayu.host.accepted_result_projection import.*UNAVAILABLE" dayu/host/ tests/host/` | 零匹配 |
| Tool Trace unchanged | `git diff -- dayu/host/tool_trace.py` | 空 |
| `git diff --check` | `git diff --check` | pass |

### 已阅读但未独立重跑

- full pyright（controller validation artifact 已报告 0 errors）
- coverage（controller validation artifact 已报告 total 89.39%，all files >= 80%）
