# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Code Review — AgentDS

## Review Context

- Reviewer: AgentDS
- Baseline: D2b1 accepted commit `1d46c137`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-implementation-codex.md`
- Scope: current workspace changes for D2b2 findings `144330-20`, `144330-23`, `144330-24`, `144330-25`

## Review Method

逐 findings 做 adversarial verification：从第一性原理判断动机是否成立、owner 是否正确、实现是否在正确边界、是否有遗漏消费者或回归风险。对每个 finding 做上游 chain 追踪、跨模块引用扫描、以及 fail-closed 边界验证。

---

## Findings

### F1: `EvidenceBackedFactCandidateVNext.__post_init__` 残留 stale docstring（Minor）

**Location**: `dayu/host/compaction.py:1188`

**Issue**: docstring 声明 `:raises TypeError: enum 类型非法时抛出。`，但 `evidence_kind` 字段与 `isinstance` 校验已移除。当前 `__post_init__` 只执行 `_require_non_empty` 和 `_require_non_empty_unique_string_tuple`，不可能抛出 `TypeError`。

**Severity**: Minor——不影响运行时行为，但 docstring 与实现不一致违反编码规范。

**Owner fix**: 移除 `:raises TypeError:` 行。

---

### F2: `_parse_fact` docstring 残留 `evidence kind` 引用（Minor）

**Location**: `dayu/host/compact_payload.py:294`

**Issue**: docstring 声明 `:raises ValueError: fact shape、文本、labels 或 evidence kind 非法时抛出。`，但 `evidence_kind` 已不再是 fact 字段，`_FACT_FIELDS` 不再包含它。当前 `_require_exact_fields` 拒绝的是 unknown fields（包括 `evidence_kind`），不是专门校验 `evidence_kind`。

**Severity**: Minor——不影响运行时行为，但 docstring 引用已删除的概念。

**Owner fix**: 将 `或 evidence kind 非法时抛出` 改为 `或 unknown fields 非法时抛出`。

---

## Verification Summary

### 144330-20: compact fact `evidence_kind` 移除 ✅

**动机验证**：`FactEvidenceKindVNext` 有三个枚举值但生产代码只赋值 `ACCEPTED_EVIDENCE_MATERIAL`。枚举暗示了一个不存在的分类能力，是虚假的。正确修复是删除而非补偿。

**Owner 变更**：
- Compact candidate schema（`EvidenceBackedFactCandidateVNext`）不再声明 `evidence_kind`——从 schema 层面消除了不拥有的语义。
- Persisted payload parser（`_parse_fact` → `_require_exact_fields`）拒绝含 `evidence_kind` 的旧 schema payload，错误信息 `"evidence_kind is not supported"`——在边界 fail-closed。
- LLM proposal parser（`_fact_candidates_vnext`）不读取、不保留 LLM 可能输出的 `evidence_kind`——LLM 垃圾输入被静默丢弃。

**完整残留扫描**：
- `FactEvidenceKindVNext`：全代码库零引用（`grep -rn` 确认）。
- `_HOST_DERIVED_FACT_EVIDENCE_KIND`：全代码库零引用。
- `dayu/host/memory.py` 中的 `evidence_kind` 引用是 `MemoryEvidenceBackedFactKind`——Memory 内部枚举（值 `DERIVED_FROM_EVIDENCE`），与已删除的 compact fact enum 是不同 owner、不同语义。不冲突。

**下游消费者验证**：
- `compact_payload.py._parse_fact`：已更新，`_FACT_FIELDS` 不含 `evidence_kind`。
- `llm_compaction.py._fact_candidates_vnext`：已更新，不再赋值 `evidence_kind`。
- `compaction.py` 中 `EvidenceBackedFactCandidateVNext.to_json()`：不再输出 `evidence_kind`。
- `ReadableFactItemVNext`（previous view fact 渲染）：不受影响，它只有 `claim_text`/`source_label`/`source_note`，从不包含 `evidence_kind`。
- `CompactReadableViewVNext` → `CompactMaterialBlock` 转换（line 2228）：block text 为 `item.claim_text`，不涉及 `evidence_kind`。
- `run_input.py` 中 RunInput builder：不受影响，它通过 `CompactReadableViewVNext` 间接消费 previous view facts。
- `utils/smoke_host_public_conversation_memory_scenarios.py`：仅移除 `FactEvidenceKindVNext` import 和 usage——机械变更。

**测试验证**：
- `test_parse_conversation_compact_output_vnext_does_not_accept_fact_evidence_kind`：LLM proposal 含 `evidence_kind: "tool_result"` → `to_json()` 不含该字段。
- `test_compacted_semantic_parser_rejects_unsupported_evidence_kind_field`：persisted payload 含 `evidence_kind` → `ValueError("evidence_kind is not supported")`。
- 所有 fixture（`_candidate()`, `_accepted_candidate()`, `_fact()`, etc.）不再传 `evidence_kind`。

---

### 144330-23: compact 后 session summary 保留 ✅

**动机验证**：`ConversationCompactOutputVNext.session_summary` 类型为 `SessionSummaryCandidateVNext | None`。`None` 语义是 "compact owner 未提供 replacement"，不是 "显式删除 summary"。旧代码将二者等同，是错误的。

**Owner 变更**：
- Memory projection `_session_summary_from_accepted_event` 是 session summary 物化的唯一 owner。现在接收 `previous_summary` 参数，`candidate.session_summary is None` 时返回 `previous_summary`。

**调用链验证**：
- `project_conversation_memory_event`（line 1245）：`session_summary = base.session_summary_memory`——从 previous snapshot 读取。
- Line 1267-1272：`_session_summary_from_accepted_event(..., previous_summary=session_summary)`——传入 loop accumulator。
- 首次 compact：`base` 为 `build_empty_conversation_memory_snapshot` 返回的空 snapshot，其 `session_summary_memory.summary_text is None`——首次 compact 的 `session_summary=None` 保留空 summary，语义正确。
- 多次 compact：facts-only compact 保留前一个 summary text compact 设置的 summary；summary text compact 正常替换。

**测试验证**：
- `test_accepted_compact_without_summary_preserves_prior_session_summary`：两个 CONTEXT_COMPACTED event，第二个 `summary_text=None` → `snapshot.session_summary_memory.summary_text == "上一轮已接受 summary。"` 且 `event_id == "compact-prior-summary"`。

---

### 144330-24: reactive compact post-compact hard threshold ✅

**动机验证**：旧 `_requires_budget_acceptance` 对 `REACTIVE` 返回 `False`，将验收责任推给下游 dispatch/Engine loops。但 dispatch/Engine 不拥有 compact candidate 的完整语义，只能做间接判断。Compact operation 是 post-compact 预算验收的唯一 natural owner。

**Owner 变更**：
- `_requires_budget_acceptance` 无条件返回 `True`——proactive 和 reactive path 统一走 hard threshold 检查。
- Compaction operation（`run_compaction_operation`）是 post-compact hard threshold 验收的唯一 owner。

**Fail-closed 路径验证**：
- Line 773: `if _requires_budget_acceptance(pass_request) and (last_budget >= hard_threshold_tokens)`——统一闸门。
- Line 617: `repairable = attempt_number < max_attempts`——repair budget 控制。
- Line 792-801: `not repairable` → fail-closed 返回 `CompactionFailureCategory.HARD_THRESHOLD_AFTER_COMPACT`。

**误杀风险评估**：
- 估算使用相同的 `estimate_post_compact_budget`，对两种 path 一致——无路径特定偏差。
- `repairable` 机制允许在 budget 允许时重试，给 LLM compactor 修正过大输出的机会。
- `max_attempts=1` 时直接 fail-closed——调用方显式选择。

**测试验证**：
- `test_run_compaction_operation_retries_reactive_hard_threshold_after_compact`：reactive over-threshold → `compactor.calls == 2`, `rejected_attempts[0].failure_category == HARD_THRESHOLD_AFTER_COMPACT`。
- `test_run_compaction_operation_fails_closed_for_reactive_over_budget_output`：`max_attempts=1` → `accepted_candidate is None`, `failure_reason == "hard_threshold_after_compact"`。

---

### 144330-25: memory raw payload fallback 移除 ✅

**动机验证**：旧 `_selected_assistant_item` 在 typed field 为 `None` 时 fallback 到 raw payload 解析。这是下游消费者（Memory）在补偿上游（terminal answer continuity）可能遗漏的工作——典型的 semantic ownership 反模式。

**Owner 变更**：
- Memory 只消费 typed `event.assistant_final_answer_text`。
- Raw payload 解析留在正确的 owner boundary（`terminal_payload.py` → `_terminal_answer.py`）。

**上游 chain 追踪**：

```
terminal_payload.py::assistant_final_answer_text_from_run_payload  ← raw 解析 owner
    ↑ (调用)
_terminal_answer.py::_resolve_assistant_final_answer_continuity_text  ← 统一选择 inline/descriptor
    ↑ (调用)
_terminal_answer.py::assistant_final_answer_continuity_text  ← 公开 API
    ↑ (调用, STRICT_NON_EMPTY policy)
durable/memory.py::_memory_projection_payload_view (line 395-404)  ← 投影边界
    ↑ (填入 MemoryProjectionEvent)
memory.py::_selected_assistant_item  ← 只读 typed 字段
```

Chain 完整，每层职责单一。`assistant_final_answer_text_from_run_payload` 仍在 `terminal_payload.py` 中定义、在 `_terminal_answer.py` 和 `test_terminal_payload.py` 中使用——留在正确边界。

**`assistant_final_answer_text=None` 时的行为**：
- `_selected_assistant_item` 返回 `None`——不生成 assistant selected recent item。
- 比旧 fallback（`LENIENT_NON_EMPTY` 可能读取非 canonical answer）更严格，也更正确。

**测试验证**：
- `test_run_succeeded_raw_final_answer_payload_does_not_materialize_assistant_window`（新增）：raw `final_answer` 存在但 `assistant_final_answer_text=None` → `selected_recent_window == ()`。
- 预存在测试中多个 `RUN_SUCCEEDED` event 现在显式传入 `assistant_final_answer_text`——证明 typed field 是进入 memory 的唯一路径。
- `test_memory_direct_consumer_does_not_follow_terminal_descriptor` docstring 更新：从 "只读取 inline `final_answer`" 改为 "不解析 raw terminal payload"。

---

### 跨 Finding 一致性检查

**D2a/D2b1 回归检查**：未发现。
- D2b2 改动不触及 D2a（terminal answer continuity resolution）和 D2b1（run input builder、context governance、evidence renderer）的 owner boundary。
- 唯一交叉：`test_dispatch_scheduler.py:5128-5131` previous view block text 格式变化。旧格式 `"fact=claim_text=...; evidence_refs=..."` → 新格式 `"previous evidence fact must stay exact"`（纯 `claim_text`）。这是因为 `ReadableFactItemVNext` 的 block text 一直是 `claim_text`（line 2228），旧格式中的 `evidence_refs=E1` 可能来自其他渲染路径。当前变更使之与 `_require_previous_item_blocks` 中的 pair invariant 一致。

**144330-21/22**：D1 scope，未触及。

**144330-26**（English LLM-facing text）：D2b2 未触及 LLM-facing prompt。`test_llm_compaction.py:250` 的 `"evidence_kind" not in prompt` 是预存在断言，行为未变。

**`__all__` 更新**：`compaction.py.__all__` 中已移除 `FactEvidenceKindVNext`。

**Memory import 清理**：`memory.py` 不再 import `assistant_final_answer_text_from_run_payload` 和 `PayloadTextReadPolicy`。

---

### 测试质量评估

所有新增/修改测试都是 owner-level contract 测试，不绑定实现细节：

| 测试 | Owner boundary | Contract |
|---|---|---|
| `test_compacted_semantic_parser_rejects_unsupported_evidence_kind_field` | Persisted payload parser | unknown field → reject |
| `test_parse_..._does_not_accept_fact_evidence_kind` | LLM proposal parser | LLM field → drop |
| `test_accepted_compact_without_summary_preserves_prior_session_summary` | Memory projection | None summary → preserve |
| `test_run_succeeded_raw_final_answer_payload_does_not_materialize...` | Memory projection | raw payload → skip |
| `test_run_compaction_operation_retries_reactive_hard_threshold...` | Compaction operation | over-threshold → retry |
| `test_run_compaction_operation_fails_closed_for_reactive_over_budget...` | Compaction operation | no budget → fail-closed |

### README 与 Utils

- `dayu/host/README.md`：两处更新在 Host 行为文档职责范围内——统一 hard threshold 和 session summary 保留行为。
- `utils/smoke_host_public_conversation_memory_scenarios.py`：仅移除 `FactEvidenceKindVNext` import 和 usage——机械变更。

---

## 结论

四个 accepted findings（144330-20, 144330-23, 144330-24, 144330-25）均在正确的 owner boundary 实现，无遗漏消费者、无回归风险、无边界泄露。

两个 Minor docstring 残留（F1、F2）建议修复但不影响运行时正确性。

**D2b2 可以 accepted。**

## Artifact

- DS: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-ds.md`
