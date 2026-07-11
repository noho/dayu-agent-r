# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B1 Code Review Controller Adjudication

## Scope

- Batch: B1 - Fins path/document identity, HKEX completeness, rebuild_processed effectiveness, atomic JSON.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-controller-validation.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-code-review-ds.md`

## Decisions

### B1-MIMO-01 - HKEX total_count greater than row_count lacks test coverage

Decision: accepted.

Reason: low-cost owner-level coverage for the new completeness contract. Add a direct regression test for explicit total proving truncation even when row count is below local maximum assumptions.

### B1-MIMO-02 - `_normalize_document_id` and `_normalize_entry_name` duplicate logic

Decision: rejected-with-reason.

Reason: low-value cleanup. The two helpers serve different storage facts: document id contract and existing directory entry validation. No current failure path requires merging them.

### B1-01 - `_resolve_handle_dir` normalization style inconsistency

Decision: rejected-with-reason.

Reason: style consistency only; review explicitly says no current correctness or ownership failure.

### B1-02 - `_coerce_non_negative_int` does not handle float total fields

Decision: accepted.

Reason: HKEX JSON may encode counts as numeric values; accepting integral non-negative floats in the completeness owner improves the direct fail-closed proof without widening to loose parsing. Non-integral and negative floats must still be rejected.

### B1-03 - repeated meta read in reprocess marker path

Decision: rejected-with-reason.

Reason: performance/cleanup only, no current semantic ownership failure. Defer unless later B2 changes this path.

## Required Fix

- Add HKEX explicit `total_count > row_count` truncation test.
- Update count coercion to accept only non-negative integral floats, with tests for valid integral float and invalid non-integral/negative values.
- Re-run B1 focused HKEX/Fins tests, pyright, and `git diff --check`.

