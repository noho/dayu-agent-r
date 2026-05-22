# Phase 12.5 Slice 2 Code Review — Accepted Evidence Envelope In Tool Accept Path

- **Reviewer**: AgentDS (independent code review)
- **Date**: 2026-05-22
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Scope**: Uncommitted diff only
- **Plan**: docs/reviews/phase12-5-implementation-ready-plan-20260522.md
- **Accepted Slice 1**: 04b758d

## Files Reviewed

| File | Change |
|------|--------|
| `dayu/host/evidence.py` | +516 (new) |
| `dayu/host/tool_runtime.py` | +61 |
| `dayu/host/memory.py` | −9 / +4 |
| `tests/host/test_toolruntime_accept_barrier.py` | +64 |
| `tests/host/test_memory_projection.py` | −105 / +44 |

## Verification

Controller validation result: 47 passed, 0 pyright errors.

## Findings

### F1 — MEDIUM: `test_context_compacted_summary_fact_refs_do_not_create_evidence_backed_facts` 移除了 `confirmed_fact_refs` 但未充分说明动机

**File**: `tests/host/test_memory_projection.py:1491-1495`

旧测试传入 `confirmed_fact_refs=("event-tool-for-summary",)` 验证 CONTEXT_COMPACTED 引用已有 tool fact 时不新建 fact（只做引用确认）。新测试移除了该参数，变为验证 CONTEXT_COMPACTED 不引用任何 fact 时不产生 fact。这是一个更弱的断言。

变更动机是成立的：TOOL_RESULT_ACCEPTED 不再生成 fact，`_validate_compact_summary_fact_refs` 会因找不到引用目标而 reject，测试必须调整。但测试名称 `summary_fact_refs_do_not_create_evidence_backed_facts` 暗示还应该覆盖 `confirmed_fact_refs` 的路径，当前版本已不覆盖该路径。

**Severity**: MEDIUM — 不是阻塞性问题，但丢失了 compact 引用场景的覆盖。建议在 Slice 5（Memory Projection Materialization）恢复该路径的测试，确保 CONTEXT_COMPACTED 引用已有 evidence_backed_fact 时不重复创建。

### F2 — INFO: `_validate_compact_summary_fact_refs` 在 CONTEXT_COMPACTED 路径仍激活，但已知 ref 集合为空

**File**: `dayu/host/memory.py:1164`

当前 Slice 2 后 `evidence_backed_facts` 在 TOOL_RESULT_ACCEPTED 后恒为空 tuple（因为 `pass` 分支不追加 fact）。CONTEXT_COMPACTED 处理路径中 `_validate_compact_summary_fact_refs(event, base.evidence_backed_facts)` 仍被调用，但 `allowed_refs` 恒为空集，导致任何带 `confirmed_fact_refs` 的 CONTEXT_COMPACTED 都会 raise `ValueError`。

这不影响 Slice 2 正确性（CONTEXT_COMPACTED 尚未被 Slice 3-5 实现），但构成了过渡期断裂点。Slice 5 通过 `_evidence_backed_fact_from_projection_event()` 从 CONTEXT_COMPACTED 创建 fact 后会自然修复。

**Severity**: INFO — 过渡期设计，Slice 5 修复，无需在 Slice 2 处理。

### F3 — INFO: `_accepted_evidence_envelope` 中 `tool_call_requested_event_ref` 使用 `requested.event_id` 但 plan 声明类型为 `str | None`

**File**: `dayu/host/tool_runtime.py:3557`

Plan §4.2 中 `AcceptedEvidenceToolQuery.tool_call_requested_event_ref` 定义为 `str | None`，但实现中传入了 `requested.event_id`（必填 `str`，因为 `requested` 是已写入的 TOOL_CALL_REQUESTED row）。这是预期行为：在 tool accept 流程中 `requested` row 必然存在，所以传实际 event_id；类型允许 None 是为了 codec 的通用性（反序列化时可能为 null）。

**Severity**: INFO — 类型契约与运行时行为一致，None 为 codec 弹性保留。

### F4 — INFO: `source_refs` 和 `locator_refs` 当前硬编码为 `()`

**File**: `dayu/host/tool_runtime.py:3585-3586`

Plan §7 Slice 2 明确要求 "absence is represented as empty tuples, not fallback business parsing"。实现正确。后续 Fins tool provider 可以填充这些字段时，需要修改 `_accepted_evidence_envelope` 的调用方传入实际的 source/locator refs。当前空 tuple 是合规的最小实现。

**Severity**: INFO — 符合 plan 要求，后续 Fins 工作单元扩展。

## Positive Confirmations

### C1: `evidence.py` 的 typed contract 设计正确

- 所有 dataclass 为 `frozen=True, slots=True`，不可变且内存高效。
- 类型层次清晰：`AcceptedEvidenceEnvelope` → `AcceptedEvidenceToolQuery` + `AcceptedEvidenceResultRef` → `OpaqueEvidenceRef`。
- `__post_init__` 校验覆盖所有必填字段：非空文本、sha256 digest 格式、类型检查、`evidence_id` 前缀。
- `__all__` 严格导出 7 个公开符号，无内部 helper 泄露。

### C2: JSON codec 三层严格校验

- `_require_exact_keys` 对 envelope / tool_query / result_ref 三层均做精确字段匹配。
- `accepted_evidence_envelope_from_json_value` 对 partial object 正确 raise `ValueError`（test confirmed）。
- 所有必填字段通过 `_required_str` 正则化空字符串检查。
- Digest 字段统一通过 `_require_sha256_digest` / `_require_optional_sha256_digest` 校验。

### C3: REUSE 路径的正确保护

`_append_tool_result_if_needed` 行 3467 的 REUSE 提前返回：
```python
if candidate.tool_fact_kind is ToolFactKind.REUSE:
    return None
```
此 guard 在 envelope 构造（行 3473）和 event append（行 3478）之前，确保 REUSE 不产生新 event 和新 envelope。正确。

### C4: Envelope 构造的事务安全

Envelope 在 `append_event` 之前构造，使用预计算的 `result_event_id`。若 `append_event` 失败，transaction 回滚，envelope 被丢弃。`evidence_id` 通过 `derive_accepted_evidence_id(result_event_id)` 派生，与最终存储的 event row 的 `event_id` 一致。无事务分裂风险。

### C5: memory.py 的 `pass` 实现正确

```python
if event.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
    pass
```
移除了 `_evidence_backed_fact_from_projection_event()` 调用、`_replace_item_by_id` 和 `diagnostics` 追加。注释清楚说明推迟到 compacted context output。连 fallback fact 一并移除（因为 fallback 源自同一个被删除的函数调用）。符合 controller-approved scope。

### C6: 测试覆盖充分

- `test_tool_result_accepted_payload_carries_accepted_evidence_envelope`: 验证 envelope 在 TOOL_RESULT_ACCEPTED payload 中存在，所有字段值正确（evidence_id、producer_event_ref、tool_name、tool_call_id、tool_query、result_ref、source_refs、locator_refs）。
- `test_accepted_evidence_envelope_codec_rejects_partial_object`: 验证 codec 拒绝不完整 JSON。
- 5 个 memory projection 测试从 `test_tool_result_accepted_produces_verified_fact_*` 改为 `test_tool_result_accepted_does_not_project_*` / `test_*_do_not_create_tool_result_fact`，正确验证 TOOL_RESULT_ACCEPTED 不再生成 fact 或 fallback。
- `test_tool_fact_accept_concrete_memory_catchup_does_not_project_fact` 从 `assert len(snapshot.snapshot.verified_facts) == 1` 改为 `assert snapshot.snapshot.evidence_backed_facts == ()`。

## Scope Compliance Checklist

| Requirement (Plan §7 Slice 2) | Status | Evidence |
|---|---|---|
| `accepted_evidence_envelope` JSON contract in `TOOL_RESULT_ACCEPTED` payload | PASS | `tool_runtime.py:3525-3529` |
| `evidence_id` = `"evidence:" + TOOL_RESULT_ACCEPTED.event_id` | PASS | `evidence.py:196-205`, `tool_runtime.py:3552` |
| Envelope only for non-REUSE candidates | PASS | `tool_runtime.py:3467` |
| No business source/locator parsing | PASS | `source_refs=(), locator_refs=()` hardcoded |
| No direct fact materialization in memory.py | PASS | `memory.py:1146-1150` `pass` branch |
| No fallback fact | PASS | All fallback logic removed with `_evidence_backed_fact_from_projection_event` call |
| No public API / Engine / Fins / Service scope creep | PASS | All changes contained in `evidence.py`, `tool_runtime.py`, `memory.py`, test files |
| Tests adequate | PASS (see F1 caveat) | 47 passed |
| Pyright clean | PASS | 0 errors |

## Conclusion

**PASS** — No blocking findings.

`evidence.py` 的 typed contract 设计严格、codec 三层精确校验、envelope 嵌入 TOOL_RESULT_ACCEPTED payload 的位置正确、REUSE 保护到位、memory.py 的 `pass` 分支干净移除了旧逻辑。测试覆盖了 golden path 和 codec rejection。F1（测试弱化）是 MEDIUM 级别但非阻塞，属于后续 slice 预期恢复的覆盖。建议 Slice 5 实现时恢复 CONTEXT_COMPACTED `confirmed_fact_refs` 路径的测试。
