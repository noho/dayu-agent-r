# WU-CM-13 Slice 1 Code Review Adjudication

## Scope

- Work unit: `WU-CM-13`
- Gate: code review after Slice 1 implementation
- Reviewed implementation scope: thin `compact_pipeline.py` helper owner and `compaction_evidence.py` cleanup
- Review artifacts:
  - `docs/reviews/deepreview-20260619-211229.md`
  - `docs/reviews/deepreview-wu-cm-13-slice-1-20260619-211311.md`
- Validation:
  - `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` passed with 91 tests.
  - `python -m pyright dayu/ tests/ utils/` passed with 0 errors.
  - `git diff --check` passed.
  - `rg -n "compaction_evidence|collect_selected_compaction_request_evidence_inputs|SelectedEvidenceBlockRef" dayu tests` returned no matches.

## Judgment

Both reviews are accepted as PASS. Slice 1 satisfies the accepted plan boundary:

- `dayu/host/compact_pipeline.py` is Host-internal and does not own lifecycle, EventLog writes, artifact writes, Attempt creation, or dispatch / ingest state transitions.
- `dayu/host/compaction_evidence.py` is deleted, and old test-only evidence helper references are removed from production and tests.
- WU-CM-14 protected recent raw-tail selection has a pipeline-owned shared helper surface for Slice 2c wiring.
- No public API, durable schema, EventLog canonical semantic, Engine contract, or tier 5 fallback implementation was introduced.

## Finding Decisions

| Finding | Decision | Reason |
|---|---|---|
| `compact_pipeline.py` is 1092 lines while the plan targeted less than 500 lines. | rejected-with-reason | The line count is mostly full Chinese docstrings, frozen dataclasses, Protocols, and explicit typed helper contracts required by repository rules and the accepted plan. Review confirmed no lifecycle coordinator behavior, no God function, and no added ownership beyond Slice 1. No code change is warranted. |
| Old evidence test names do not map one-to-one to the migration table. | rejected-with-reason | The migration is semantically equivalent. New tests cover the useful old behavior through `compact_material.py` and `compact_pipeline.py` production paths instead of preserving stale test-only helper names. |
| Malformed compacted payload / evidence-label edge coverage is not explicit at the new helper boundary. | deferred-with-owner | Slice 1 helper accepts typed `ConversationCompactOutputVNext`; old malformed JSON payload input is no longer the same entry path. The remaining edge is evidence-label / provenance validation under accepted compact quality and should be rechecked during Slice 2 wiring or final compact quality gate audit. Owner: WU-CM-13 Slice 2. |
| `_dedupe_texts` duplicates tiny local dedupe helpers that still exist in dispatch / ingest code. | deferred-with-owner | Slice 1 intentionally does not wire dispatch / ingest. This duplication should disappear or be explicitly justified when Slice 2a / 2b replace proactive and reactive compact glue with `compact_pipeline.py`. Owner: WU-CM-13 Slice 2. |
| Slice 2 wiring is not implemented. | deferred-with-owner | This is not a Slice 1 defect. Slice 2a / 2b / 2c are explicit plan slices for proactive dispatch, reactive ingest, and RunInput protected raw-tail wiring. |

## Conclusion

Slice 1 may proceed to accepted slice commit. No fix gate is required before committing this slice. The deferred items are tracked in `docs/host/issues-implementation-control.md` under WU-CM-13 residuals and must be reconciled before WU-CM-13 ready-to-open-draft-PR.
