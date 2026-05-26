# Phase 12.5 Slice 6 Re-Review: RunInputBuilder Rendering And Compaction Request Wiring (Repair)

- Review Agent: MiMo
- Date: 2026-05-22
- Baseline: previous review `docs/reviews/phase12-5-slice6-code-review-mimo-20260522.md`
- Repair scope: shared helper extraction, stable derived fact refs, deduplication, adversarial tests
- Controller validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py` => 48 passed; `pyright dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_evidence.py` => 0 errors

## Verdict

**PASS. No blockers. All DS findings fixed or dispositioned per controller decision.**

## DS Finding Verification

### DS F1 [Blocker] Helper Duplication -- FIXED

**Before**: `dispatch.py` and `engine_ingest.py` each contained ~155 lines of identical helper code (`_compaction_request_evidence_inputs`, `_accepted_evidence_envelope_from_event`, `_evidence_backed_fact_refs_from_compacted_event`, `_required_text_list`, `_CompactionRequestEvidenceInputs` dataclass, five `_PAYLOAD_FIELD_*` constants).

**After**: New shared module `dayu/host/compaction_evidence.py` (242 lines) exports `CompactionRequestEvidenceInputs` and `collect_compaction_request_evidence_inputs`. Both `dispatch.py` and `engine_ingest.py` import from the shared module. Zero duplicate helper implementations remain.

Evidence: `dispatch.py` has exactly 2 references to the shared module (import at line 149, call at line 1245). `engine_ingest.py` has exactly 2 references (import at line 155, call at line 1165). Grep for old private helper names returns 0 matches in both files.

### DS F2 [Blocker] Malformed Envelope Not Rejected -- FIXED

**Before**: No test for malformed accepted evidence envelope.

**After**: New test `test_compaction_request_evidence_inputs_reject_malformed_envelope` (line ~317) constructs a `TOOL_RESULT_ACCEPTED` with payload `{"accepted_evidence_envelope": {"evidence_id": "evidence:bad"}}` (missing required fields). Asserts `HostDurableError` with match `"accepted evidence envelope"`.

### DS F3 [Blocker] Producer Event Ref Mismatch Not Rejected -- FIXED

**Before**: No test for producer_event_ref mismatch.

**After**: New test `test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch` (line ~338) constructs an envelope with `producer_event_ref="event-tool-result-other"` but appends it under event id `"event-tool-result-mismatch"`. Asserts `HostDurableError` with match `"producer_event_ref mismatch"`. The validation logic in `_accepted_evidence_envelope_from_event` (compaction_evidence.py line 120) checks `envelope.producer_event_ref != row.event_id`.

### DS F4 [Rejected] accepted_evidence_refs Derived Property -- CONTROLLER DECISION

Controller rejected this finding because `accepted_evidence_refs` is a derived property from `accepted_evidence_envelopes`. Not implemented. No action needed.

### DS F5 [Deferred] Additional Structural Validation -- DEFERRED

Deferred as residual. No action needed in this repair.

### DS F6 [Blocker] Malformed CONTEXT_COMPACTED Payload Not Rejected -- FIXED

**Before**: `_evidence_backed_fact_refs_from_compacted_event` in dispatch.py/engine_ingest.py used `isinstance(preserved, Mapping)` guard that silently returned empty refs for non-Mapping preserved_fact_refs.

**After**: New shared helper in `compaction_evidence.py` line 143-145 raises `HostDurableError("CONTEXT_COMPACTED preserved_fact_refs is invalid")` when `preserved_fact_refs` is present but not a Mapping. New parametrized test `test_compaction_request_evidence_inputs_reject_malformed_compacted_payload` covers 6 malformed scenarios:

1. `evidence_backed_fact_candidates` is not a list
2. candidate entry is not an object
3. `candidate_id` is empty string
4. `preserved_fact_refs` is not an object
5. `evidence_backed_fact_refs` is not a list
6. `evidence_backed_fact_refs` contains empty string

## MiMo Advisory Verification

### S6-A1 [Advisory] Helper Duplication -- FIXED

Same as DS F1. Shared module `compaction_evidence.py` eliminates all duplication.

## Additional Repair Quality Checks

### Stable Derived Fact Refs

**PASS.** `_evidence_backed_fact_refs_from_compacted_event` (compaction_evidence.py line 170) calls `_derived_evidence_backed_fact_ref(row, candidate_id)` which produces `memory-item:evidence_backed_fact:{candidate_id}:{compact_event_id}`. This ensures fact refs are stable across compaction cycles and unique per compact event, not raw candidate_id which was only item-local diagnostic metadata.

Test `test_compaction_request_evidence_inputs_use_stable_derived_fact_refs` verifies:
- Preserved fact refs from prior compaction pass through unchanged
- New candidate refs derive to `memory-item:evidence_backed_fact:{candidate_id}:{event_id}`
- Duplicate candidate_ids produce a single derived ref (deduplication)

### Accepted Evidence Deduplication

**PASS.** `_deduplicate_accepted_evidence` (compaction_evidence.py lines 185-201) deduplicates by `evidence_id` preserving first occurrence order. Test `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids` constructs two events with the same evidence_id and verifies only the first is retained.

### No New Blockers Introduced

- `dispatch.py` and `engine_ingest.py` contain zero old helper implementations
- Zero `tool_fact_refs` or `verified_fact_refs` references in either file
- `engine_ingest.py._ReactiveCompactPending` correctly uses `CompactionRequestEvidenceInputs` from shared module
- All new tests use real SQLite durable store with real EventLog writes, not mocks
- Shared module follows `dayu.host` layer boundary: imports only from `dayu.contracts`, `dayu.host.context_events`, `dayu.host.durable`, `dayu.host.evidence`, `dayu.host.payload_resolution`

## Remaining Residuals (from initial review, unchanged)

### S6-R1 Missing Post-Compaction Follow-Up Test

Still deferred to Slice 7 integration smoke. Repair did not address this.

### S6-R2 Missing No-Compaction Short-Link Follow-Up Test

Still deferred to Slice 7 integration smoke. Repair did not address this.

## Conclusion

All DS blocker findings (F1, F2, F3, F6) are fixed. DS F4 rejected by controller decision. DS F5 deferred as residual. MiMo advisory S6-A1 fixed. No new blockers introduced. Repair quality is clean: shared module extraction is correct, stable derived fact refs are properly tested, deduplication is verified, and adversarial payload rejection covers all identified malformed shapes.
