# Phase 12.5 Slice 5 Code Re-Review (Repair Verification)

- **Review agent**: Deep Review (no code modification)
- **Prior review**: `docs/reviews/phase12-5-slice5-code-review-ds-20260522.md`
- **Reviewed repair**: Finding 1/2 fixes + new tests + schema update
- **Controller validation**: 47 tests passed, 0 pyright errors
- **Date**: 2026-05-22

---

## DS Finding 1: Error Masking in Two-Pass Validation — FIXED

**Prior finding**: `_validate_compacted_payload_for_memory_projection` raised original `exc` when both fact and non-fact fields were invalid, masking the real non-fact error.

**Fix** (`dayu/host/memory.py:1397-1398`):

```python
# Before (broken):
except ValueError:
    raise exc

# After (fixed):
except ValueError as non_fact_exc:
    raise non_fact_exc from exc
```

The patched validation now surfaces `non_fact_exc` (with `from exc` chaining), ensuring the non-fact-candidate error is not masked.

**Test** (`test_fact_candidate_error_does_not_mask_non_fact_candidate_error`, line 1690): Constructs a payload with both invalid fact candidate (bad evidence_refs) and overlong minimum preserve text. Asserts `ValueError` with `match="minimum preserve text exceeds maximum length"` — the non-fact error is correctly surfaced, not the fact-candidate error.

**Verdict**: FIXED. No residual masking.

---

## DS Finding 2: Missing Bounded Text Enforcement — FIXED

**Prior finding**: `_evidence_backed_facts_from_compacted_event` and `_minimum_preserve_items_from_compacted_event` read raw JSON fields directly into `EvidenceBackedFactView` / `ConversationContinuityItem`, bypassing `EvidenceBackedFactCandidate.__post_init__` bounded validation.

**Fix** — both functions now construct typed intermediate objects:

1. `_evidence_backed_facts_from_compacted_event` (`memory.py:1458-1475`):
   ```python
   fact_candidate = EvidenceBackedFactCandidate(
       candidate_id=...,
       claim_text=...,
       evidence_kind=...,
       evidence_refs=...,
       attributes=...,
   )
   ```
   `EvidenceBackedFactCandidate.__post_init__` (`compaction.py:745-781`) enforces:
   - `claim_text` non-empty after strip AND `<= MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS`
   - `evidence_refs` non-empty, `<= MAX_EVIDENCE_REFS_PER_FACT`
   - `attributes` canonical JSON `<= MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS`

2. `_minimum_preserve_items_from_compacted_event` (`memory.py:1514-1525`):
   ```python
   preserve_candidate = MinimumPreserveItemCandidate(
       item_id=..., label=..., text=..., source_refs=..., preserve_reason=...,
   )
   ```
   `MinimumPreserveItemCandidate.__post_init__` (`compaction.py:815-828`) enforces:
   - `text` non-empty after strip AND `<= MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS`
   - `label` non-empty after strip AND `<= MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS`
   - `source_refs` `<= MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM`

**Tests**:
- `test_overlong_fact_candidate_records_diagnostic_without_fact` (line 1727): `claim_text` of `MAX + 1` chars → diagnostic only, zero facts materialized
- `test_fact_candidate_error_does_not_mask_non_fact_candidate_error` (line 1690): overlong minimum preserve text → `ValueError` (non-fact error surfaces)

**Verdict**: FIXED. Memory materialization now validates raw JSON through shared typed constructors with bounded checks.

---

## DS Finding 3: Extra SQL Query on Read Path — DEFERRED

The `_validate_snapshot_item_kinds` check in `durable/memory.py:941-972` still performs a `SELECT item_kind FROM host_memory_items WHERE snapshot_id = ?` on every snapshot read. This was assessed MEDIUM in the prior review and explicitly accepted as deferred. No change was requested or made.

**Verdict**: Deferred. Acceptable with bounded item counts per snapshot (< 100 rows). The CHECK constraint on write + JSON-level rejection on parse provide two prior layers of defense.

---

## Regression Check: Schema / Durable / Materialization

### Schema (`dayu/host/durable/schema.py`)

- `host_memory_diagnostics.reason` CHECK constraint: `missing_fact_summary_fallback` **removed**; `evidence_backed_fact_candidate_invalid` **present** ✅
- `host_memory_items.item_kind` CHECK constraint: `minimum_preserve_item` **added** ✅
- `MemoryDiagnosticReason.MISSING_FACT_SUMMARY_FALLBACK` removed from enum (`memory.py:265` — old line) ✅
- `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` present in enum (`memory.py:265-268`) ✅
- No orphaned CHECK values: all 8 reason values match `MemoryDiagnosticReason` enum ✅

### Durable (`dayu/host/durable/memory.py`)

- `_validate_snapshot_item_kinds` rejects `verified_fact` and unknown kinds on read ✅
- `_insert_evidence_backed_fact_item` hardcodes `claim_status=MemoryClaimStatus.EVIDENCE_BACKED` ✅
- No old `MISSING_FACT_SUMMARY_FALLBACK` references in diagnostic write path ✅
- Durable roundtrip test confirms `evidence_backed_facts` (not `verified_facts`) in snapshot JSON and `evidence_backed_fact` item kind ✅

### Materialization (`dayu/host/memory.py`)

- `TOOL_RESULT_ACCEPTED` → `pass` (no fact generation) ✅
- `CONTEXT_COMPACTED` → `_validate_compacted_payload_for_memory_projection` → `_evidence_backed_facts_from_compacted_event` with typed `EvidenceBackedFactCandidate` constructor ✅
- `_minimum_preserve_items_from_compacted_event` with typed `MinimumPreserveItemCandidate` constructor ✅
- `EvidenceBackedFactView.provenance` anchored to `CONTEXT_COMPACTED` event with `HOST_PROJECTION` producer ✅
- `conversation_memory_snapshot_from_json_value` rejects `verified_facts` key ✅
- `_evidence_backed_fact_from_json_value` rejects `fact_summary` / `evidence_anchor` keys ✅

### New Tests Coverage

| Test | Line | What it proves |
|------|------|---------------|
| `test_evidence_backed_fact_budget_keeps_latest_facts_and_records_diagnostic` | 1542 | Budget enforcement: oldest dropped, latest-N kept, budget diagnostic emitted |
| `test_invalid_fact_candidate_diagnostic_survives_durable_snapshot_write` | 1647 | Invalid fact candidate diagnostic persists through durable write/read cycle |
| `test_fact_candidate_error_does_not_mask_non_fact_candidate_error` | 1690 | Non-fact error surfaces when both fact and non-fact fields are invalid |
| `test_overlong_fact_candidate_records_diagnostic_without_fact` | 1727 | Overlong claim_text → diagnostic only, typed constructor enforces bound |

All 47 tests pass. Controller residual searches confirm no `missing_fact_summary_fallback` in touched files.

---

## Residual Risk: Unhandled Typed Constructor Error in Materialization

**Risk level**: LOW

In the current design, `_evidence_backed_facts_from_compacted_event` is only called when `_validate_compacted_payload_for_memory_projection` returns `fact_candidates_valid=True`. The validation function uses `validate_context_compacted_payload(event.payload)` for the first pass, which may be less strict than `EvidenceBackedFactCandidate.__post_init__` (e.g., different whitespace stripping behavior).

If `validate_context_compacted_payload` passes but `EvidenceBackedFactCandidate.__post_init__` raises inside `_evidence_backed_facts_from_compacted_event`, the `ValueError` propagates unhandled and crashes the projection (hard failure instead of diagnostic degradation). This asymmetrical defense is not a regression — it's the same behavior as before the repair — but it's worth documenting:

- If the compaction layer's JSON schema validation is always at least as strict as the typed constructor, this never triggers.
- If a future change makes the JSON schema validation looser, this becomes a crash path.
- Mitigation: ensure `validate_context_compacted_payload` and `EvidenceBackedFactCandidate.__post_init__` stay in sync.

**Owner**: Compaction layer maintainer. Not a blocker for Slice 5.

---

## Verdict

**PASS**. All three prior findings are resolved:
- Finding 1 (error masking): **FIXED** with test
- Finding 2 (bounded text enforcement): **FIXED** with test
- Finding 3 (extra SQL query): **DEFERRED** (accepted)

No schema regression. No durable materialization regression. No diagnostic reason mismatch. 47 tests pass, 0 pyright errors. One LOW residual risk (asymmetrical defense depths) documented, not blocking.
