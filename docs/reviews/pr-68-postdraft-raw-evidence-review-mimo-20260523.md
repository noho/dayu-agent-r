# PR 68 Post-Draft Raw Evidence Compaction Fix Review

**Reviewer**: MiMo  
**Date**: 2026-05-23  
**Scope**: Current workspace diff (uncommitted changes on `feat/phase-12-5-conversation-memory-optimize`)  
**Gate**: Phase 12.5 PR 68 post-draft raw evidence compaction fix

---

## Review Checklist

### 1. `result_preview` Removal

**Required**: `result_preview` must be fully removed from production code, tests, and design docs.

| Location | Status |
|----------|--------|
| `dayu/host/evidence.py` | `result_preview` field removed from `AcceptedEvidenceResultRef`, `_FIELD_RESULT_PREVIEW`, `MAX_ACCEPTED_EVIDENCE_RESULT_PREVIEW_CHARS`, `_require_optional_bounded_non_empty_text` all deleted. |
| `dayu/host/tool_runtime.py` | `_accepted_tool_outcome_preview`, `_TRUNCATED_PREVIEW_SUFFIX`, `_require_optional_bounded_non_empty_text` deleted. `ToolFactAcceptCandidate.result_preview` replaced with `raw_tool_outcome`. |
| `dayu/host/llm_compaction.py` | `result_preview` line removed from envelope prompt rendering. |
| `dayu/host/compaction_evidence.py` | No `result_preview` remnants. |
| `dayu/host/compaction.py` | No `result_preview` remnants. |
| `dayu/host/compact_artifact.py` | No `result_preview` remnants. |
| `dayu/host/dispatch.py` | No `result_preview` remnants. |
| `dayu/host/engine_ingest.py` | No `result_preview` remnants. |
| `tests/host/*` | All `result_preview` references removed from test fixtures and assertions. |
| `docs/host/design.md` | `result_preview` language replaced with raw evidence / Host-minted evidence id design. |
| `dayu/host/README.md` | `result_preview` language replaced. |
| `tests/README.md` | `result_preview` language replaced. |
| `docs/host/implementation-control.md` | Only appears in tracking/status context describing the fix task itself. Acceptable. |

**PASS** — `result_preview` is fully eliminated from production code, tests, and design docs. Only residual is in `implementation-control.md` status tracking.

---

### 2. Host-Minted Evidence ID at Accept Barrier

**Required**: `evidence_id` must be Host-minted at `TOOL_RESULT_ACCEPTED` accept barrier; LLM/tool provider must not generate canonical evidence id.

- `tool_runtime.py:3559`: `evidence_id=derive_accepted_evidence_id(result_event_id)` — Host derives evidence id from the result event id.
- `llm_compaction.py`: LLM compactor prompt renders `accepted_evidence_refs` alongside raw content, but does not generate evidence ids.
- `compaction_evidence.py:174`: `accepted_evidence_refs=tuple(envelope.evidence_id for envelope in envelopes)` — evidence refs come from Host-minted envelopes.

**PASS** — Evidence id is exclusively Host-minted.

---

### 3. Raw Evidence Persistence & Fail-Closed

**Required**: `raw_tool_outcome` must be persisted in `TOOL_RESULT_ACCEPTED` payload; missing must fail-closed.

**Write path** (`tool_runtime.py:3531`):
```python
_PAYLOAD_FIELD_RAW_TOOL_OUTCOME: candidate.raw_tool_outcome,
```
Written to EventLog alongside accepted evidence envelope.

**Validation** (`tool_runtime.py:4095-4104`):
```python
def _require_raw_tool_outcome(candidate: ToolFactAcceptCandidate) -> None:
    if candidate.raw_tool_outcome is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires raw_tool_outcome")
```
Called for COMPLETED, FAILED, CANCELLED, and GOVERNED_ERROR fact kinds.

**Reuse guard** (`tool_runtime.py:4091-4092`):
```python
if candidate.raw_tool_outcome is not None:
    raise ValueError("reuse must not carry raw_tool_outcome")
```

**Read path** (`compaction_evidence.py:166-168`):
```python
raw_outcome = payload.get(_PAYLOAD_FIELD_RAW_TOOL_OUTCOME)
if raw_outcome is None:
    raise HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")
```
Only invoked when envelopes exist (fail-open for envelope-less events, which is correct since those don't carry evidence).

**PASS** — Raw tool outcome write and read are fail-closed for non-reuse tool results.

---

### 4. Compact Raw Context Collection

**Required**: Compaction evidence collection must gather raw transcript content from compact input range.

**New data model** (`compaction.py`):
- `CompactRawContextKind` enum: `USER_INPUT`, `ASSISTANT_CONCLUSION`, `ACCEPTED_TOOL_RESULT`
- `CompactRawContextItem` dataclass with `event_ref`, `content_kind`, `content_text`, `accepted_evidence_refs`

**Collection** (`compaction_evidence.py:86-113`):
- `TOOL_RESULT_ACCEPTED` → `_tool_result_raw_context_items` → reads `raw_tool_outcome` from payload, serializes to canonical JSON
- `USER_INPUT_ACCEPTED` → `_user_input_raw_context_items` → reads `display_text` from payload
- `RUN_SUCCEEDED` → `_assistant_raw_context_items` → reads assistant summary via `assistant_summary_from_payload`

All three event types are `EventClass.CANONICAL_FACT`, passing the event class guard at line 94.

**PASS** — Raw context collection covers tool results, user input, and assistant conclusions from the compact input range.

---

### 5. Evidence ID Anchor Placement in LLM Prompt

**Required**: `evidence_id` must be adjacent to raw evidence content for LLM reference.

**Prompt rendering** (`llm_compaction.py:403-426`):
```python
def _compact_raw_context_lines(items):
    for item in items:
        lines.extend([
            f"- event_ref: {item.event_ref}",
            f"  content_kind: {item.content_kind.value}",
            f"  accepted_evidence_refs: {_refs_text(item.accepted_evidence_refs)}",
            "  content:",
            *_indented_content_lines(item.content_text),
        ])
```

Evidence refs appear immediately before content text.

**Test proof** (`test_llm_compaction.py:test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id`):
```python
assert raw_context_index < evidence_ref_index < raw_content_index
```

**PASS** — Evidence id anchors are placed adjacent to raw content, verified by test.

---

### 6. Long Raw Evidence Survives

**Required**: Long raw evidence (e.g., "管理层讨论与分析" chapters) must not be truncated.

**Test proof** (`test_llm_compaction.py:test_llm_context_compactor_prompt_keeps_long_raw_evidence_content`):
```python
long_prefix = "A" * 1300
tail_marker = "MD&A section says backlog conversion improved in Q4."
raw_content = f"{long_prefix}{tail_marker}"
# ...
assert tail_marker in prompt
```

1300+ chars raw content with tail marker verified present in prompt. No truncation applied to raw context items.

**PASS** — Long raw evidence content passes through without truncation.

---

### 7. Host Layer Correctness

**Required**: Host must not understand Fins locator/metric/chunk semantics.

- `CompactRawContextItem.content_text` is stored as opaque text (canonical JSON for tool results, plain text for user input/assistant).
- `AcceptedEvidenceEnvelope` retains opaque `source_refs` and `locator_refs` without Host interpretation.
- `_tool_result_raw_context_items` uses `canonical_json_dumps(raw_outcome)` — Host serializes but does not parse the outcome structure.

**PASS** — Host remains layer-correct.

---

### 8. Cancellation Hardening Not Regressed

**Required**: Compaction LLM call must receive Host lifecycle cancellation token.

- `llm_compaction.py`: `ContextCompactor.compact` signature includes `CancellationToken`.
- `compaction.py`: `run_compaction_operation` propagates token.
- `dispatch.py` and `engine_ingest.py`: Both pass cancellation token to compaction.

**PASS** — Cancellation token propagation is intact.

---

### 9. No Compatibility Wrappers

**Required**: No compatibility re-exports, wrappers, or old schema compatibility.

- `_require_optional_bounded_non_empty_text` deleted from both `evidence.py` and `tool_runtime.py`.
- `MAX_ACCEPTED_EVIDENCE_RESULT_PREVIEW_CHARS` deleted from `evidence.py` and removed from `__all__`.
- `_accepted_tool_outcome_preview` and `_TRUNCATED_PREVIEW_SUFFIX` deleted from `tool_runtime.py`.
- No re-exports of deleted symbols.

**PASS** — Clean deletion, no compatibility remnants.

---

### 10. CompactionRequest Contract Update

**Required**: `CompactionRequest` must carry `compact_raw_context_items`.

- `compaction.py:290`: New field `compact_raw_context_items: tuple[CompactRawContextItem, ...]` added to `CompactionRequest`.
- `compaction.py:347-349`: Validation via `_require_compact_raw_context_item_tuple`.
- `compaction.py:403-405`: JSON serialization in `to_json`.
- `compact_artifact.py:303-305`: Snapshot serialization includes raw context items.
- `dispatch.py:1376` and `engine_ingest.py:2998`: Both proactive and reactive paths pass `compact_raw_context_items`.

**PASS** — Contract updated consistently across all construction paths.

---

### 11. FakeCompactor Correctness

**Required**: `FakeContextCompactor` must consume raw context items, not envelope previews.

**Updated** (`fake_compaction.py:210-229`):
```python
def _fact_candidates(request):
    candidates = []
    for item in request.compact_raw_context_items:
        for evidence_ref in item.accepted_evidence_refs:
            candidates.append(EvidenceBackedFactCandidate(
                claim_text=f"Accepted evidence raw content: {item.content_text}",
                evidence_refs=(evidence_ref,),
                ...
            ))
    return tuple(candidates)
```

Fact claims now derive from `item.content_text` (raw content), not envelope preview.

**PASS** — FakeCompactor correctly consumes raw context items.

---

### 12. Test Coverage

| Test | What it proves |
|------|---------------|
| `test_llm_context_compactor_prompt_contains_raw_evidence_content` | Prompt contains raw context section, content_kind, evidence_refs, and raw content text. |
| `test_llm_context_compactor_prompt_keeps_long_raw_evidence_content` | 1300+ char raw content survives to prompt without truncation. |
| `test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id` | Evidence ref appears between raw context header and content text (ordering proof). |
| `test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive` | Raw context items collected from TOOL_RESULT_ACCEPTED and USER_INPUT_ACCEPTED within range; outside-range and other-session events excluded. |
| `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids` | Deduplication still works with raw context. |
| `test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch` | Producer mismatch still raises HostDurableError. |
| `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | `raw_tool_outcome` persisted in TOOL_RESULT_ACCEPTED payload. |
| `test_oversized_tool_result_returns_completed_outcome_without_default_governance` | `raw_tool_outcome` contains full oversized value (no truncation). |
| `test_fact_candidates_can_reference_accepted_evidence_envelopes` (contract) | FakeCompactor fact claims derive from raw content. |
| `test_compact_artifact_store` | Compaction request snapshot includes raw context items. |

**PASS** — Tests cover long raw evidence survival, evidence id anchoring, range bounding, and payload persistence.

---

## Findings

### No Findings

No correctness, stability, or maintainability findings identified.

---

## Adversarial Failure Pass

| Attack vector | Result |
|---------------|--------|
| Can LLM generate its own evidence id? | No. Evidence refs are rendered by Host; LLM only references them. |
| Can raw_tool_outcome be missing silently? | No. `_require_raw_tool_outcome` raises for non-reuse; `compaction_evidence` raises HostDurableError. |
| Can old TOOL_RESULT_ACCEPTED events (without raw_tool_outcome) cause crash? | Yes, HostDurableError. This is correct fail-closed behavior for events written before this schema change. Production impact depends on whether any such events exist in the current durable store. |
| Can reuse candidates leak raw_tool_outcome? | No. Explicit guard rejects non-null raw_tool_outcome for reuse. |
| Can compaction run without cancellation token? | No. Token is required by contract. |
| Can USER_INPUT_ACCEPTED/RUN_SUCCEEDED events be silently skipped? | No. Both are CANONICAL_FACT and handled in the elif chain. |

**One residual**: Existing `TOOL_RESULT_ACCEPTED` events in durable stores written before this change will lack `raw_tool_outcome`. On compaction, `_tool_result_raw_context_items` will raise `HostDurableError`. This is intentional fail-closed — such events predate the raw evidence design and should not produce stale/incomplete evidence. However, this means the first compaction after upgrade on sessions with pre-existing tool results will fail until those events age out of the compact input range. **This is an acceptable migration boundary** given the "全新 schema 起库处理" constraint.

---

## Verdict

**PASS**

All required checks satisfied. `result_preview` is fully eliminated. Raw evidence flow is fail-closed. Evidence id is Host-minted. LLM compactor receives full raw content with adjacent evidence id anchors. Long raw evidence survives. Cancellation hardening intact. No compatibility wrappers. No layer violations.

Residual: first compaction on sessions with pre-existing `TOOL_RESULT_ACCEPTED` events (lacking `raw_tool_outcome`) will fail-closed. This is expected per schema migration policy.
