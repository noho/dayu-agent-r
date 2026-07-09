# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Review

## Metadata

- Reviewer: AgentMiMo
- Review date: 2026-07-09
- Scope: P1-A implementation diff against HEAD
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Implementation report: `docs/reviews/wu-semantic-ownership-01-p1-a-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-a-controller-validation.md`

## Executive Summary

Implementation correctly establishes `dayu/host/accepted_result_projection.py` as the single owner boundary for accepted tool result query/status/source/result projection. All seven downstream consumers are migrated to consume the shared projection helper. No residual back-query, status fallback, or source blacklist logic found in consumers.

**Conclusion: `pass`**

## Findings

### F1. Duplicate `_result_details_text` / `_structured_details_text` logic

**Severity**: low

**Location**:
- `dayu/host/accepted_result_projection.py:672-724`
- `dayu/host/tool_trace.py:1419-1479` (deleted in diff, now uses projection)

**Evidence**: Implementation report states "复用 Tool Trace 现有 details 抽取规则或迁移为共享私有 helper". The diff shows tool_trace.py deleted its own `_result_details_text` / `_structured_details_text` / `_detail_scalar_text` implementations and now consumes `projection.result_details_text`.

**Impact**: None. The migration is complete; projection helper owns this logic, consumers only read the projected text.

**Owner-boundary判断**: Correct. `accepted_result_projection.py` is the owner; tool_trace.py is consumer.

**Required fix**: None. Finding closed.

---

### F2. Conversation Memory legacy fallback for missing projection fields

**Severity**: low

**Location**: `dayu/host/memory.py:1694-1706`

**Evidence**:
```python
if event.evidence_tool_name is not None and event.evidence_result_text is not None:
    return _accepted_evidence_readable_text(...)
envelope = accepted_evidence_envelope_from_payload(...)
if envelope is not None:
    raw_text = event.evidence_result_text
    if raw_text is None:
        raw_text = accepted_tool_raw_outcome_text_from_payload(event.payload)
    ...
```

**Impact**: Historical inputs without projection fields (e.g., memory snapshots written before P1-A) will fall back to envelope + raw outcome. This is a degradation path, not the new owner path. New durable projections always populate `evidence_tool_name` / `evidence_result_text`.

**Owner-boundary判断**: Correct. The fallback reads from durable payload (pre-P1-A truth), not from a consumer-private reconstruction. The primary path consumes projection fields.

**Required fix**: None. Controller classified this as historical-input degradation. Verified it cannot mask current projection drift because new projections always populate the typed fields.

---

### F3. `_accepted_evidence_query_unavailable_text()` local import

**Severity**: info

**Location**: `dayu/host/memory.py:608-622`

**Evidence**:
```python
def _accepted_evidence_query_unavailable_text() -> str:
    """读取 accepted-result projection owner 定义的 unavailable query 文案。"""
    from dayu.host.accepted_result_projection import (  # noqa: PLC0415
        ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT,
    )
    return ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT
```

**Impact**: None. The local import is documented as breaking a circular import during bootstrap. The text truth remains in `accepted_result_projection.py`.

**Owner-boundary判断**: Correct. `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` owner is `accepted_result_projection.py`; `memory.py` only consumes it.

**Required fix**: None.

---

### F4. `_result_details_text` recursion depth

**Severity**: info

**Location**: `dayu/host/accepted_result_projection.py:672-697`

**Evidence**: The function recurses into nested JSON (`value`, `result`, `data` keys and list items). No depth guard.

**Impact**: Extremely low. Raw tool outcomes are bounded by tool output size. Maliciously deep nesting would require a compromised tool producer, which is outside Host threat model.

**Owner-boundary判断**: N/A (implementation detail within owner).

**Required fix**: None.

---

### F5. `_contains_unsafe_argument_key` heuristic

**Severity**: low

**Location**: `dayu/host/accepted_result_projection.py:509-532`

**Evidence**: The function checks for `api_key`, `token`, `secret`, `password`, `*path`, `path_*` in argument keys. This is a heuristic, not an exhaustive list.

**Impact**: If a tool uses an unexpected sensitive key name (e.g., `credentials`, `auth_header`), it would pass through to LLM-facing query text. However, this is an improvement over the previous state where no such check existed.

**Owner-boundary判断**: Correct. This is projection-owner responsibility; consumers should not implement their own sensitivity filters.

**Required fix**: None for this WU. Consider expanding the heuristic in a future WU if tool schemas expose additional sensitive patterns.

---

### F6. `source_note` schema field name

**Severity**: info

**Location**: `dayu/host/compaction.py:679-706`, `dayu/host/compact_material.py:3229`

**Evidence**: `source_note` remains as a compaction schema field name. The value is now produced from `projection.source.text` (cleaned by owner).

**Impact**: None. The field name is schema vocabulary; the value semantics are now owner-controlled.

**Owner-boundary判断**: Correct.

**Required fix**: None.

---

### F7. Read API PREVIEW vs CANONICAL_FACT dispatch

**Severity**: info

**Location**: `dayu/host/read_api.py:1222-1270`

**Evidence**:
```python
if row.event_class is EventClass.CANONICAL_FACT:
    return _canonical_tool_result_accepted_activity(transaction, row)
if row.event_class is not EventClass.PREVIEW:
    return None
return _preview_tool_result_accepted_activity(transaction, row)
```

**Impact**: None. The dispatch boundary is explicit. PREVIEW path reads from preview payload (existing behavior). CANONICAL_FACT path uses projection helper.

**Owner-boundary判断**: Correct. Canonical accepted result status/query/summary come from projection; PREVIEW does not fallback to canonical.

**Required fix**: None.

---

### F8. `_accepted_result_activity_state` status mapping

**Severity**: info

**Location**: `dayu/host/read_api.py:1287-1302`

**Evidence**:
```python
if status is AcceptedToolResultStatus.COMPLETED:
    return HostActivityStatus.COMPLETED, HostActivitySeverity.INFO
if status is AcceptedToolResultStatus.CANCELLED:
    return HostActivityStatus.CANCELLED, HostActivitySeverity.WARNING
return HostActivityStatus.FAILED, HostActivitySeverity.ERROR
```

**Impact**: None. Mapping matches plan specification: `completed -> COMPLETED`, `cancelled -> CANCELLED`, all others (`failed`, `governed_error`, `lost`, `unknown`) -> FAILED.

**Owner-boundary判断**: Correct. Status mapping is in Read API (consumer), consuming projection status.

**Required fix**: None.

---

### F9. Tool Trace request summary display-only boundary

**Severity**: info

**Location**: `dayu/host/tool_trace.py:1269-1345`

**Evidence**: `_tool_request_summary_from_tool_result` now takes `projection` as input, constructs display-only summary with bounded text, redacted arguments. Does not re-read request atom or re-own query/status/source.

**Impact**: None. Tool Trace only formats projection fields for display.

**Owner-boundary判断**: Correct. Projection provides truth; Tool Trace renders it.

**Required fix**: None.

---

### F10. Tests coverage

**Severity**: info

**Location**: `tests/host/test_accepted_result_projection.py`

**Evidence**: 4 tests cover:
1. Semantic query + completed status + business source filtering
2. Arguments fallback when semantic query absent + failed status
3. Limited signal when request atom missing + cancelled status
4. governed_error and unknown status mapping

**Impact**: Core projection scenarios are covered. Cross-consumer equivalence tests are in existing test suites (test_tool_trace_projection.py, test_memory_projection.py, etc.).

**Owner-boundary判断**: N/A.

**Required fix**: None. Additional wait-resolution status tests could be added in future WUs.

---

### F11. README / Design updates

**Severity**: info

**Location**: `dayu/host/README.md`, `tests/README.md`

**Evidence**: Both READMEs updated per trigger rules. `docs/host/design.md` not modified (no durable schema or public contract change).

**Impact**: None.

**Required fix**: None.

---

## Propagation Audit

| Step | Status | Evidence |
|---|---|---|
| Produce | ✓ | ToolRuntime / waiting produce accepted result facts (unchanged). |
| Validate | ✓ | `project_accepted_tool_result()` centralizes envelope, request atom identity, payload digest, status, query, source validation. |
| Persist | ✓ | EventLog / payload store / request atom tables unchanged. Projection does not write back. |
| Trace / Read API | ✓ | Both consume projection status/query/result/source. PREVIEW path separate. |
| Memory | ✓ | Durable memory and Conversation Memory consume projection fields. Legacy fallback only for pre-P1-A inputs. |
| Run input / compact | ✓ | RunInputBuilder, CompactMaterial, compact pipeline consume projection. No residual blacklist. |
| LLM-facing output | ✓ | Limited-signal query text and cleaned source text from projection owner. |

## Residual Risks

1. `_contains_unsafe_argument_key` heuristic may not cover all sensitive key patterns. Low risk; tools should not expose secrets in arguments.
2. Conversation Memory legacy fallback exists for pre-P1-A memory snapshots. Verified it cannot mask current drift.
3. `source_note` remains as compaction schema field name. Value semantics are owner-controlled.

## Validation Results

- `pytest tests/host/test_accepted_result_projection.py tests/host/test_tool_trace_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py`: 242 passed
- `pyright`: 0 errors
- `git diff --check`: passed
- `rg` residual classification: only allowed schema fields, projection owner calls, and primitive definitions

## Conclusion

**`pass`**

P1-A implementation correctly establishes `accepted_result_projection.py` as the single owner boundary for accepted tool result query/status/source/result projection. All consumers migrated. No residual back-query, status fallback, or source blacklist in consumers. Tests pass. Pyright clean. README updated per trigger rules.
