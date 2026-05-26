# Phase 12.5 Slice 3 Code Re-Review Controller Adjudication

## Scope

- Phase: 12.5 Conversation Memory Optimization
- Slice: 3, Compaction Structured Candidate Contract And Accept Barrier
- Base accepted slice: `e154c46` (`gateflow: accept phase 12.5 slice 2`)
- Reviewed artifacts:
  - `docs/reviews/phase12-5-slice3-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice3-code-review-ds-20260522.md`
  - `docs/reviews/phase12-5-slice3-code-rereview-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice3-code-rereview-ds-20260522.md`

## Controller Decision

PASS. Slice 3 is accepted for local commit.

The initial code reviews found no HIGH or MEDIUM blockers. The controller accepted two small repair items before acceptance:

- DS LOW-1 was treated as a semantic precision bug: `summary.confirmed_fact_refs` must only reference existing `evidence_backed_fact_refs`, not accepted evidence envelope ids.
- MiMo F2 was treated as a test gap: old `proposed_verified_fact_refs` in a compacted summary needed explicit fail-closed coverage.

Both repairs were implemented and targeted re-review by MiMo and DS returned PASS with no new blocking findings.

## Accepted Repair Outcome

- `dayu/host/context_governance.py` now scopes `_summary_pretends_evidence_backed_fact` to `request.evidence_backed_fact_refs` only.
- `tests/host/test_compaction_contract.py` now rejects `summary.confirmed_fact_refs=("evidence:accepted-1",)` with `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT`.
- `tests/host/test_context_compact_events.py` now explicitly rejects the old `proposed_verified_fact_refs` summary key.

## Deferred Non-Blocking Findings

- Candidate JSON helper duplication across `compaction.py`, `context_events.py`, and `compact_artifact.py` is deferred to Slice 7 / aggregate polish. It is not behaviorally risky for Slice 3.
- Compact artifact v1 read-path fail-closed handling remains assigned to Slice 5 Memory Projection Materialization, where artifact reads are introduced.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py
=> 52 passed

source .venv/bin/activate && pyright dayu/host/compaction.py dayu/host/context_events.py dayu/host/context_governance.py dayu/host/compaction_operation.py dayu/host/compact_artifact.py
=> 0 errors
```

## Next Gate

Proceed to Phase 12.5 Slice 4: LLM Compactor Structured JSON Rewrite.
