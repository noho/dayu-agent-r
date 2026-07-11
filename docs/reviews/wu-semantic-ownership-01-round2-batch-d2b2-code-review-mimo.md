# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Code Review — MiMo

## Review Context

- Reviewer: AgentMiMo
- Baseline: D2b1 accepted commit `1d46c137`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-implementation-codex.md`
- Scope: current workspace changes for D2b2 findings `144330-20`, `144330-23`, `144330-24`, `144330-25`

## Findings

### F1: `EvidenceBackedFactCandidateVNext.__post_init__` 残留 stale docstring（Minor）

**Location**: `dayu/host/compaction.py:1188`

**Issue**: docstring 仍声明 `:raises TypeError: enum 类型非法时抛出。`，但 `evidence_kind` 字段与 `isinstance` 校验已在 D2b2 中移除。当前 `__post_init__` 只执行 `_require_non_empty` / `_require_non_empty_unique_string_tuple` / `_require_unique_string_tuple`，不可能抛出 `TypeError`。

**Severity**: Minor — 不影响运行时行为，但 docstring 与实现不一致违反编码硬约束（docstring 必须准确描述异常）。

**Owner fix**: 移除 `:raises TypeError:` 行或改为 `:raises ValueError:`（如果仍需声明 ValueError）。

### F2: `_parse_fact` docstring 残留 `evidence kind` 引用（Minor）

**Location**: `dayu/host/compact_payload.py:294`

**Issue**: docstring 声明 `:raises ValueError: fact shape、文本、labels 或 evidence kind 非法时抛出。`，但 `evidence_kind` 已不再是 fact 字段。`_require_exact_fields` 现在拒绝未知字段（如残留的 `evidence_kind`），错误信息为 `evidence_kind is not supported`，而非 `evidence kind 非法`。

**Severity**: Minor — docstring 措辞不精确，不影响运行时。

**Owner fix**: 改为 `:raises ValueError: fact shape、文本、labels 或未知字段非法时抛出。`

## Verification Summary

### 144330-20: evidence_kind 移除

- `FactEvidenceKindVNext` enum 已从 `compaction.py` 完整移除，`__all__` 已更新。
- `EvidenceBackedFactCandidateVNext` 不再有 `evidence_kind` 字段，`to_json()` 不输出该字段。
- `_FACT_FIELDS` 不含 `evidence_kind`；`_require_exact_fields` 在 persisted payload 解析时拒绝含 `evidence_kind` 的 JSON（`test_compacted_semantic_parser_rejects_unsupported_evidence_kind_field` 验证）。
- LLM proposal 解析（`llm_compaction.py`）不再读取或派生 `evidence_kind`；LLM 提供的 `evidence_kind` 被静默忽略（`test_parse_conversation_compact_output_vnext_does_not_accept_fact_evidence_kind` 验证 `to_json()` 输出不含该字段）。
- `compact_payload.py` import 已清理，`_FIELD_EVIDENCE_KIND` 常量已移除。
- 全局 grep 确认 `FactEvidenceKindVNext` 零残留；`evidence_kind` 仅存在于 memory 层的 `MemoryEvidenceBackedFactKind`（不同 owner、不同语义）和拒绝测试中。

**结论**: owner fix 正确。Compact candidate 不再承载无 owner 的 `evidence_kind`；persisted schema 严格拒绝该字段；LLM parser 不保留该字段。

### 144330-23: session summary 保留

- `_session_summary_from_accepted_event` 新增 `previous_summary` 参数。
- `candidate.session_summary is None` 时返回 `previous_summary`（保留既有 summary），不再返回 `_empty_session_summary_memory()`。
- 调用处在 `project_conversation_memory_event` 中传入当前 `session_summary` 状态。
- `test_accepted_compact_without_summary_preserves_prior_session_summary` 验证：第一个 compact 设置 summary → 第二个 compact（`summary_text=None`）保留第一个的 summary，且 `event_id` 仍指向前一个 compact event。
- `_accepted_compact_payload` helper 已支持 `summary_text=None` 构造 `session_summary=None` 的 candidate。

**结论**: `session_summary=None` 语义正确区分了"compact owner 未提供 replacement"（保留）与"提供 replacement"（替换）。未发现误清空风险。

### 144330-24: reactive compact hard threshold

- `_requires_budget_acceptance` 现在无条件返回 `True`（`del request; return True`），移除了 `ContextCompactionTriggerSource` import 和条件分支。
- proactive 和 reactive path 均受 compact 后 hard threshold 闸门约束。
- `test_run_compaction_operation_retries_reactive_hard_threshold_after_compact`: reactive path 在 `max_attempts=2` 时重试并接受第二次 candidate（`compactor.calls == 2`，`rejected_attempts == 1`，`failure_category is HARD_THRESHOLD_AFTER_COMPACT`）。
- `test_run_compaction_operation_fails_closed_for_reactive_over_budget_output`: reactive path 在 `max_attempts=1` 时 fail closed（`accepted_candidate is None`，`repairable is False`，`failure_reason == "hard_threshold_after_compact"`）。
- `repairable` 逻辑不变：`attempt_number < max_attempts` 时可重试，否则 fail closed。
- README Context governance 段已更新，反映 proactive 与 reactive 均需 hard threshold 验收。

**结论**: reactive path 不再绕过 hard threshold，operation owner 统一执行验收。重试与 fail-closed 语义正确。

### 144330-25: memory raw payload fallback 移除

- `_selected_assistant_item` 不再 import 或调用 `assistant_final_answer_text_from_run_payload`。
- 只消费 `event.assistant_final_answer_text`（typed field），`None` 时返回 `None`。
- `MemoryProjectionEvent.assistant_final_answer_text` 由 durable memory projection 层（`dayu/host/durable/memory.py:360`）在 `_memory_projection_payload_view` 中通过 `assistant_final_answer_continuity_text`（`_terminal_answer.py`）解析。该函数先尝试 inline `final_answer`，再尝试 descriptor-backed terminal payload，是 typed field 的真源 owner。
- `test_run_succeeded_raw_final_answer_payload_does_not_materialize_assistant_window`: 构造含 `final_answer` payload 但无 typed `assistant_final_answer_text` 的 event，验证 selected_recent_window 为空。
- 现有测试已更新：`RUN_SUCCEEDED` event helper 现在显式传入 `assistant_final_answer_text` 参数。
- `test_memory_direct_consumer_does_not_follow_terminal_descriptor` docstring 已更新，反映纯 consumer 不解析 raw terminal payload。

**结论**: memory 不再越级解析 raw payload，typed field 由 durable projection 边界保证。fallback 移除正确。

### 测试质量

- 测试断言 owner 级 contract 行为（如 `_require_exact_fields` 拒绝未知字段、`_session_summary_from_accepted_event` 保留语义、`_requires_budget_acceptance` 统一验收），而非围绕实现细节重写期望。
- 新增测试覆盖了正向（保留 summary、重试成功）和反向（fail closed、raw payload 不 materialize）场景。
- test helper `_accepted_compact_payload` 正确支持 `summary_text=None` 构造。

### README 变更

- Context governance 段更新：准确反映 proactive 与 reactive 均需 hard threshold 验收。
- CONTEXT_COMPACTED 投影段更新：准确反映 session summary 保留语义。
- 变更限于 `dayu/host/README.md` 职责范围，未越界。

### utils 变更

- `smoke_host_public_conversation_memory_scenarios.py` 仅移除 `FactEvidenceKindVNext` import 和 LLM proposal JSON 中的 `evidence_kind` 字段，跟踪 removed enum，无生产行为 drift。

## 结论

两个 Minor docstring 残留（F1、F2）不影响运行时正确性。四个 accepted findings 均已在 owner boundary 正确关闭，未引入新 regression 或 contract 缺口。

## Artifact

- MiMo: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-mimo.md`
