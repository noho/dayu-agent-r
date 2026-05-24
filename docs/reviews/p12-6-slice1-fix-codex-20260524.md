# P12.6 Slice 1 Targeted Fix

## Scope

- Gate: Slice 1 code review targeted fix only.
- Accepted findings fixed: D-F1, D-F2, D-F3, M-F3.
- Not changed: `docs/host/implementation-control.md`.
- Not done: commit, push, PR, Slice 2 work.

## Changed Files

- `dayu/host/run_input.py`
  - `CONTEXT_COMPACTED.preserved_fact_refs` now reads `canonical_evidence_refs`, matching the key emitted by `context_events.py`.
  - Compact artifact message text now renders `canonical_evidence_refs=...`.
- `dayu/host/context_events.py`
  - Renamed internal constants from accepted-evidence wording to canonical-evidence wording without changing payload key values.
- `dayu/host/llm_compaction.py`
  - Prompt-local label to canonical source ref mapping now raises explicit `ValueError` when a provenance entry has empty `canonical_source_refs`.
- `tests/host/test_run_input_builder.py`
  - Added focused coverage for reading `canonical_evidence_refs` from compacted payload preserved fact refs.
- `tests/host/test_llm_compaction.py`
  - Added focused coverage for explicit empty canonical source refs failure.
- `tests/host/test_compaction_operation.py`
  - Updated stale docstring that referenced removed `accepted_evidence_envelopes`.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py`
  - Result: 100 passed.
- `source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/context_events.py dayu/host/llm_compaction.py tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## README Sync

No README was updated. The fix changes internal Host key alignment, diagnostics, and focused tests only; it does not change stable user commands, package boundaries, public extension points, or test maintenance conventions.

## Residual Risks

- Validation was intentionally limited to affected Host tests and touched-file pyright per the targeted fix gate.
- Existing unrelated workspace changes remain present and were not reverted or modified outside the accepted finding scope.
