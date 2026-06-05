# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-dur-obs-cm-closeout
- Base: main
- Output file: docs/reviews/wu-dur-obs-cm-closeout-slice5-code-review-mimo.md
- Included scope:
  - Production: `dayu/host/compaction_evidence.py`
  - Tests: `tests/host/test_compaction_operation.py`
  - Docs: `dayu/host/README.md`, `tests/README.md`, `docs/host/issues-implementation-control.md`
  - Plan source: `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 5
  - Implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice5-implementation-codex.md`
- Excluded scope: compact candidate output schema (out of Slice 5), Slice 6 prompt rewrite, Slice 7 public smoke closeout
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项验证结果：

1. **query_text 从 durable TOOL_CALL_REQUESTED atoms 派生**：`_readable_query_text()` (`compaction_evidence.py:281-329`) 通过 `envelope.tool_query.tool_call_requested_event_ref` 回读 request event，调用 `tool_call_request_atoms()` 解析 durable arguments，不再从 tool result content 推断，不再输出裸 `tool_call_id=...`。`compaction_evidence.py:296-329` 完整覆盖了 ref 缺失、event 缺失、session 不匹配、atom 解析失败、同源校验失败五种异常路径。PASS。

2. **semantic_query_text 优先于 arguments fallback**：`compaction_evidence.py:325-326` 先检查 `atoms.semantic_query_text is not None`，命中则直接返回 `_bounded_query_text(atoms.semantic_query_text)`，不走 arguments fallback。PASS。

3. **arguments fallback 有界、canonical、业务可读、不暴露内部 refs**：`compaction_evidence.py:327-329` 输出 `工具参数: {"arguments":...}`，使用 `canonical_json_dumps(atoms.arguments_json)` 渲染。`atoms.arguments_json` 是 durable request atom 的 canonical preimage，不包含 `tool_call_id`、event id、payload ref、digest、cursor 或 Host provenance key。PASS。

4. **limited-signal 策略**：四种异常路径（ref 缺失、event 缺失、atom 不可验证、evidence/request 不同源）均调用 `_limited_signal_query_text()` (`compaction_evidence.py:367-383`)，输出 `状态=limited_signal；原因=...；说明=...` 格式。常量值（`_LIMITED_SIGNAL_REASON_*`、`_LIMITED_SIGNAL_DETAIL_*`）均为业务中性中文描述，不含 Host 内部 refs/digests。PASS。

5. **evidence/request 同源校验**：`_request_atoms_match_envelope()` (`compaction_evidence.py:332-347`) 校验 `tool_call_id`、`tool_name`、`normalized_arguments_digest` 三项一致性。session 边界在 `compaction_evidence.py:308` 单独校验。PASS。

6. **chunked evidence 复用 base query_text**：`_readable_query_text()` 是 per-envelope 调用，同一 `tool_call_requested_event_ref` 的多个 chunk 共享同一 durable atom，输出相同的 `query_text`。chunk ordinal 由 `compact_material.py` 的 label 系统管理，不进入 `query_text`。测试 `test_evidence_chunks_share_same_durable_query_text` 验证三个 chunk (`E1.1`/`E1.2`/`E1.3`) 的 `query_text` 完全一致。PASS。

7. **compact candidate output schema 未变更**：diff 中 `compaction.py`、`compact_payload.py`、`compact_artifact.py` 均未修改。`InitialEvidenceMaterial.readable_query_text` 字段类型和位置不变。PASS。

8. **result content 不混入 query_text**：`_readable_query_text()` 只读取 request atom 的 arguments/semantic_query，不读取 `raw_tool_outcome` 或 result payload。PASS。

9. **测试覆盖**：
   - `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview`：验证 descriptor payload 路径下 query_text 从 durable arguments 渲染。已从旧 `_accepted_evidence_envelope_for_event_with_payload_ref` 更新为 `_accepted_evidence_envelope_for_tool_request`，并追加 `_append_tool_call_requested_event`。PASS。
   - `test_evidence_input_prefers_semantic_query_from_tool_request_atom`：验证 semantic query 优先。PASS。
   - `test_evidence_input_missing_tool_request_atom_emits_limited_signal`：验证 `tool_call_requested_event_ref=None` 时输出 limited-signal，且不包含 `tool-call` 或 event id。PASS。
   - `test_evidence_chunks_share_same_durable_query_text`：验证 9000 字符 raw content 被拆为三个 chunk 后 query_text 稳定一致。PASS。
   - 测试不使用 test-only production bridge；所有 helper (`_accepted_evidence_envelope_for_tool_request`、`_append_tool_call_requested_event`、`_accepted_arguments_digest`) 通过真实 EventLog / payload 路径写入数据。PASS。

10. **README 同步**：
    - `dayu/host/README.md`：在 Context Compaction 段落补充了 `query_text` 消费 `TOOL_CALL_REQUESTED` durable request atom 的说明，语义准确，不超出该 README 职责范围。PASS。
    - `tests/README.md`：在 P12.6 memory semantic smoke 段落补充了 "accepted evidence query_text 消费 durable tool-call request atoms"。PASS。
    - `docs/host/issues-implementation-control.md`：状态更新为 review gate，记录 implementation artifact 路径。PASS。

## Open Questions

无。

## Residual Risk

- **同源校验失败路径缺少 focused test**：`_request_atoms_match_envelope()` 校验三项（`tool_call_id`、`tool_name`、`normalized_arguments_digest`），但当前没有专门测试覆盖 request event 找到但同源校验失败时输出 `状态=limited_signal；原因=工具请求与当前证据来源不一致` 的路径。虽然 `_request_atoms_match_envelope` 逻辑简单且 `tool_call_request_atoms()` 内部已有 digest 校验，但该边界未被直接断言。
- **request event 找不到路径缺少 focused test**：`requested_ref` 非空但 `event_log_store.read_event_by_id()` 返回 `None` 的路径（`compaction_evidence.py:303-307`）没有专门测试。该路径逻辑与 `requested_ref is None` 路径相同（输出 limited-signal），但缺少独立覆盖。
- **`_bounded_query_text` 截断路径未测试**：`_READABLE_QUERY_TEXT_MAX_CHARS=1200` 的截断逻辑没有专门测试，包括截断后 JSON 可能不完整的可读性问题（不影响正确性，因为 `query_text` 是 LLM 提示而非结构化解析输入）。
- **`_limited_signal_query_text` 输出格式稳定性未测试**：`状态=limited_signal；原因=...；说明=...` 的拼接格式依赖 `_LIMITED_SIGNAL_FIELD_SEPARATOR` 常量，缺少对格式稳定性的回归断言。
