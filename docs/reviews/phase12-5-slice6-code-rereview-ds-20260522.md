# Phase 12.5 Slice 6 Code Re-Review: Repair Verification

- **Review type**: targeted re-review of repair changes
- **Original review**: `docs/reviews/phase12-5-slice6-code-review-ds-20260522.md`
- **Review date**: 2026-05-22
- **Reviewer**: DS (DeepReview Agent)

---

## Repair Summary

The following repairs were applied in response to the original review's findings F1, F2, F3, F6. F4 was rejected by controller (accepted_evidence_refs is a derived property from envelopes), and F5 was deferred as residual risk.

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| F1: Code duplication dispatch/engine_ingest | CRITICAL | FIXED | Shared `compaction_evidence.py` extracted |
| F2: candidate_id as stable fact refs | HIGH | FIXED | Stable derived ref `memory-item:evidence_backed_fact:{candidate_id}:{compact_event_id}` |
| F3: Missing adversarial test coverage | HIGH | FIXED | 5 new adversarial tests added |
| F6: No dedup for accepted_evidence_envelopes | MEDIUM | FIXED | `_deduplicate_accepted_evidence()` by evidence_id |
| F4: Missing accepted_evidence_refs field | HIGH | REJECTED by controller | Derived property from envelopes |
| F5: Hardcoded start_event_sequence=1 | MEDIUM | DEFERRED | Residual risk |

---

## F1 Verification — Code Duplication Eliminated

**Check**: grep for duplicate symbols in `dispatch.py` and `engine_ingest.py`.

```
dispatch.py: 0 matches for _compaction_request_evidence_inputs,
  _accepted_evidence_envelope_from_event, _evidence_backed_fact_refs_from_compacted_event,
  _required_text_list, _CompactionRequestEvidenceInputs, _PAYLOAD_FIELD_* constants.

engine_ingest.py: 0 matches for same symbols.

compaction_evidence.py: sole owner of CompactionRequestEvidenceInputs,
  collect_compaction_request_evidence_inputs, and all private helpers.
```

**Shared module**: `dayu/host/compaction_evidence.py` (243 lines). Public API:
- `CompactionRequestEvidenceInputs` — dataclass (exported in `__all__`)
- `collect_compaction_request_evidence_inputs()` — single entry point for both paths

**dispatch.py** imports only `collect_compaction_request_evidence_inputs` (line 29 in diff).
**engine_ingest.py** imports `CompactionRequestEvidenceInputs` (for type annotation on `_ReactiveCompactPending`) and `collect_compaction_request_evidence_inputs` (line 154-157 in diff).

**Verdict**: F1 resolved. No residual duplication. ✓

---

## F2 Verification — candidate_id Replaced by Stable Derived Fact Refs

**Before (original Slice 6)**:
```python
# Raw candidate_id used as fact ref
refs.append(candidate_id)
```

**After (repair)**:
```python
# compaction_evidence.py:174-182
def _derived_evidence_backed_fact_ref(row: EventLogRow, candidate_id: str) -> str:
    return f"{_MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX}:{candidate_id}:{row.event_id}"

# _MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX = "memory-item:evidence_backed_fact"
```

This produces refs like `memory-item:evidence_backed_fact:fact-new:event-context-compacted-derived`. The inclusion of `{row.event_id}` (the CONTEXT_COMPACTED event id) guarantees cross-compaction uniqueness — two different compact events with `candidate_id="fact-1"` will produce different stable refs.

**Preserved fact refs** (from `preserved_fact_refs.evidence_backed_fact_refs`) are passed through as-is, since they were already derived in stable format by a prior compaction cycle.

**Deduplication** via `_deduplicate_texts()` using `dict.fromkeys()` preserves the first occurrence of each ref while maintaining insertion order.

**Test coverage**: `test_compaction_request_evidence_inputs_use_stable_derived_fact_refs` verifies:
1. A preserved ref `memory-item:evidence_backed_fact:existing:event-old` is passed through unchanged.
2. Two candidates with `candidate_id="fact-new"` are deduplicated to one.
3. The derived ref is `memory-item:evidence_backed_fact:fact-new:{compacted_event_id}`.

**Verdict**: F2 resolved. Stable derived refs guarantee cross-compaction uniqueness. ✓

---

## F3 Verification — Adversarial Tests Added

Five new tests added to `tests/host/test_compaction_operation.py`:

### test_compaction_request_evidence_inputs_reject_malformed_envelope (line 385)
- Inserts TOOL_RESULT_ACCEPTED with `accepted_evidence_envelope: {"evidence_id": "evidence:bad"}` (missing required keys).
- Asserts `pytest.raises(HostDurableError, match="accepted evidence envelope")`.
- Covers the `accepted_evidence_envelope_from_json_value()` → `ValueError` → `HostDurableError` re-raise path. ✓

### test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch (line 411)
- Inserts TOOL_RESULT_ACCEPTED where `accepted_evidence_envelope.producer_event_ref` points to a different event_id.
- Asserts `pytest.raises(HostDurableError, match="producer_event_ref mismatch")`.
- Covers the `envelope.producer_event_ref != row.event_id` validation. ✓

### test_compaction_request_evidence_inputs_reject_malformed_compacted_payload (line 441)
- Parametrized with 6 cases covering every validation path in `_evidence_backed_fact_refs_from_compacted_event`:

| Payload | Expected error |
|---|---|
| `evidence_backed_fact_candidates: "not-list"` | "must be list" |
| `evidence_backed_fact_candidates: ["not-object"]` | "must be object" |
| `evidence_backed_fact_candidates: [{"candidate_id": ""}]` | "candidate_id is invalid" |
| `preserved_fact_refs: "not-object"` | "preserved_fact_refs is invalid" |
| `preserved_fact_refs: {evidence_backed_fact_refs: "not-list"}` | "must be list" |
| `preserved_fact_refs: {evidence_backed_fact_refs: [""]}` | "item is invalid" |

All cases use `pytest.raises(HostDurableError, match=...)`. ✓

### test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids (line 501)
- Inserts two TOOL_RESULT_ACCEPTED events with same `evidence_id` but different `producer_event_ref` (both valid for their respective rows).
- Asserts only the first envelope is retained. ✓

### test_compaction_request_evidence_inputs_use_stable_derived_fact_refs (line 581)
- Tests combined preserved ref pass-through + candidate_id derivation + dedup of duplicate candidate_ids. ✓

**Test helper refactor**: `_append_event_and_return_sequence()`, `_collect_evidence_ids()`, and `_collect_fact_refs()` extracted as reusable helpers to reduce boilerplate in adversarial tests. ✓

**Verdict**: F3 resolved. All adversarial paths are now tested. ✓

---

## F6 Verification — Envelope Deduplication

**Before (original Slice 6)**:
```python
accepted_evidence_envelopes=tuple(accepted_evidence),
evidence_backed_fact_refs=tuple(dict.fromkeys(evidence_backed_fact_refs)),
```

**After (repair)**: `compaction_evidence.py:185-201`
```python
def _deduplicate_accepted_evidence(
    envelopes: list[AcceptedEvidenceEnvelope],
) -> tuple[AcceptedEvidenceEnvelope, ...]:
    seen: set[str] = set()
    unique: list[AcceptedEvidenceEnvelope] = []
    for envelope in envelopes:
        if envelope.evidence_id in seen:
            continue
        seen.add(envelope.evidence_id)
        unique.append(envelope)
    return tuple(unique)

def _deduplicate_texts(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
```

Both envelopes and fact refs are now deduplicated, with dedicated functions for each type. `_deduplicate_accepted_evidence` uses `evidence_id` as the dedup key, preserving insertion order (first envelope wins). `_deduplicate_texts` uses `dict.fromkeys()` for string dedup.

**Call site** (compaction_evidence.py:91-94):
```python
return CompactionRequestEvidenceInputs(
    accepted_evidence_envelopes=_deduplicate_accepted_evidence(accepted_evidence),
    evidence_backed_fact_refs=_deduplicate_texts(evidence_backed_fact_refs),
)
```

**Test coverage**: `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids`. ✓

**Verdict**: F6 resolved. Both data types are now deduplicated with consistent order-preserving behavior. ✓

---

## Additional Repair Quality Observations

### Positive

1. **Module hygiene**: `compaction_evidence.py` has clear module-level docstring stating its scope ("只负责从 bounded EventLog range 读取 Host-neutral accepted evidence envelopes 与已存在 evidence-backed fact refs"). No business-layer imports.

2. **`CompactionRequestEvidenceInputs` is properly public**: Removed leading underscore since `engine_ingest.py` types `_ReactiveCompactPending.evidence_inputs` with it. Added to `__all__`.

3. **Validation hardening**: `_evidence_backed_fact_refs_from_compacted_event` now explicitly checks `if preserved is not None` before `isinstance(preserved, Mapping)`. Previously used `if isinstance(preserved, Mapping)` which silently skipped non-Mapping, non-None values; now raises clear `HostDurableError`.

4. **Test helper extraction**: `_append_event_and_return_sequence()`, `_collect_evidence_ids()`, and `_collect_fact_refs()` properly factored, reducing test boilerplate and making adversarial test intent clearer.

5. **Controller validation passed**:
   - `pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py` → 48 passed
   - `pyright dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_evidence.py` → 0 errors

### No New Blockers

The repair introduces no new issues. Specifically:
- No new imports that violate layer boundaries.
- No new public API surface beyond what's needed.
- No test pollution — adversarial tests are self-contained with tmp_path isolation.
- No semantic change to the bounded read logic — only the derivation and dedup layers were added.

---

## Remaining Deferred Items

| Finding | Disposition | Owner |
|---|---|---|
| F4: Missing `accepted_evidence_refs` | Controller rejected — derived property | Controller |
| F5: Hardcoded `start_event_sequence=1` | Deferred residual | Later phase |

---

## Unchanged Items (Verified Intact)

The following original Slice 6 components were not modified by the repair and remain correct:

- `_memory_evidence_backed_fact_message()` rendering (run_input.py:1726-1751)
- `_memory_minimum_preserve_message()` injection (run_input.py:1819-1850)
- `_memory_raw_turn_messages()` inclusion filter (run_input.py:1791-1798)
- `_preserved_fact_refs_text()` renamed rendering (run_input.py:2147-2177)
- `_memory_messages()` ordering (run_input.py:1564-1602)
- Proactive dispatch call site (dispatch.py:1242-1290)
- Reactive engine ingest wiring (engine_ingest.py:1162-1205, 2991-2968)
- `_rich_memory_snapshot` test fixture update (test_run_input_builder.py)
- README update (dayu/host/README.md)

---

## Verdict: PASS

All four targeted findings (F1, F2, F3, F6) are confirmed fixed with direct evidence. No new blockers introduced. Controller validation (48 tests passed, 0 pyright errors) confirms correctness. Two deferred items (F4 controller-rejected, F5 residual) remain but do not block Slice 6 completion.

The repair is clean and complete.
