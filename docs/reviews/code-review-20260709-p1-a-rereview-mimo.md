# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Re-Review — AgentMiMo

## Metadata

- Reviewer: AgentMiMo
- Review date: 2026-07-09
- Scope: narrow re-review of controller accepted findings P1A-CR-F01 through P1A-CR-F05
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-codex.md`
- Fix validation: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-controller-validation.md`
- Current workspace diff against HEAD

## Conclusion

**`pass`**

All five controller accepted findings are closed. No new blockers introduced by the fix.

---

## Finding Closure Verification

### P1A-CR-F01: Conversation Memory legacy fallback removed

**Required fix**: Remove or tighten envelope/raw outcome fallback in Conversation Memory; if projection fields absent, emit limited-signal text.

**Evidence from diff**:

1. `dayu/host/memory.py` removed imports of `accepted_evidence_envelope_from_payload` and `accepted_tool_raw_outcome_text_from_payload`.
2. `_selected_evidence_text()` rewritten: when `evidence_tool_name` and `evidence_result_text` are present, uses `_accepted_evidence_readable_text()` with projection fields; otherwise returns `"工具结果已接受；可读投影字段缺失，未展开原始工具响应。"`.
3. No envelope or raw outcome payload reconstruction path remains.

**Test coverage**:
- `test_accepted_tool_evidence_uses_projection_fields_without_payload_rebuild`: verifies projection fields are used and payload fields do not leak.
- `test_accepted_tool_evidence_missing_projection_fields_fail_closed`: verifies missing projection fields produce limited-signal text without payload reconstruction.

**Status**: `closed`

---

### P1A-CR-F02: Compact pipeline uses projection owner unavailable query text

**Required fix**: Replace `_UNAVAILABLE_TOOL_QUERY` with projection owner constant.

**Evidence from diff**:

1. `dayu/host/compact_pipeline.py` removed `_UNAVAILABLE_TOOL_QUERY = "The original tool query is not available in readable form."`.
2. Added import `from dayu.host.accepted_result_projection import ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`.
3. `_accepted_tool_evidence_content()` now uses `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` instead of local constant.

**Status**: `closed`

---

### P1A-CR-F03: `_arguments_fallback_query` misleading signature fixed

**Required fix**: Rename or simplify helper so it no longer accepts unused payload.

**Evidence from fix artifact**: `_arguments_fallback_query(payload, reason)` replaced with `_request_unavailable_query(reason)`. The function no longer accepts a `payload` parameter, eliminating the misleading suggestion that payload can be a query source.

**Status**: `closed`

---

### P1A-CR-F04: Projection helper tests cover completion signals

**Required fix**: Add focused tests for identity mismatch, wait-resolution priority, source filtering, descriptor behavior, unsafe arguments, raw `result.ok == false`, and details extraction.

**Evidence from test file** (`tests/host/test_accepted_result_projection.py`):

| Test | Completion Signal |
|---|---|
| `test_projection_identity_mismatch_returns_limited_signal` | request atom identity mismatch |
| `test_projection_wait_resolution_status_takes_priority` | wait-resolution `resolution_kind` priority |
| `test_projection_filters_internal_source_refs` | internal source refs filtered |
| `test_projection_reads_descriptor_payload_and_reports_missing_descriptor` | descriptor payload + missing descriptor diagnostic |
| `test_projection_unsafe_argument_keys_return_limited_signal` | unsafe argument keys → limited signal |
| `test_projection_maps_raw_result_ok_false_and_extracts_details` | raw `result.ok == false` → failed + details extraction |

**Total**: 11 tests passing, all using real durable store write/read pattern.

**Status**: `closed`

---

### P1A-CR-F05: Cross-consumer equivalence test added

**Required fix**: Add test verifying one accepted result projects consistently across consumers.

**Evidence**: `test_same_accepted_result_has_equivalent_consumer_projection` constructs one accepted result and verifies:
- Tool Trace `query_text`, `query_state`, `result_status`, `result_text` match projection
- Memory text contains projection query, result, and source
- RunInputBuilder content contains projection query, source, and result
- CompactMaterial evidence block fields match projection

All assertions compare consumer outputs to projection owner result; fixture does not reimplement projection rules.

**Status**: `closed`

---

## New Blockers Introduced by Fix

None identified. The fix:
- Removes downstream reconstruction logic (net negative lines)
- Replaces local constants with projection owner imports
- Adds test coverage without test fixture workarounds
- Preserves fail-closed behavior for missing projection fields

---

## Validation

- `pytest tests/host/test_accepted_result_projection.py`: 11 passed
- `pytest tests/host/test_memory_projection.py`: 58 passed
- `pytest tests/host/test_compact_pipeline.py`: 11 passed
- `pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`: 181 passed
- `pyright`: 0 errors, 0 warnings

---

## Conclusion

All five controller accepted findings (P1A-CR-F01 through P1A-CR-F05) are verified closed. The fix correctly removes downstream accepted evidence reconstruction, unifies unavailable query text, fixes misleading helper signature, adds completion signal test coverage, and adds cross-consumer equivalence test. No new blockers introduced.
