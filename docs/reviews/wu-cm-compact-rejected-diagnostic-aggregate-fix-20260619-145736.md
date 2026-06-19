# Aggregate Deepreview Fix: Public Compact Smoke Assertion Drift

- **Gate**: aggregate deepreview fix
- **Work unit**: Conversation Memory compact rejected attempt diagnostics
- **Timestamp**: 20260619-145736
- **Blocking review artifact**: `docs/reviews/code-review-20260619-144741.md`
- **Prior adjudication**: `docs/reviews/wu-cm-compact-rejected-diagnostic-aggregate-deepreview-adjudication-20260619-144950.md`

## Finding Fixed

### `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`

- **Decision**: `accepted`
- **Status**: `已修复`
- **Root cause**: test assertion drift. The old test expected long current input to bypass compactor and dispatch fallback. Current design allows long current input to enter LLM-facing compact material as full `current_input_anchor` instead of restoring a Host-side field-length/schema guard.
- **Fix**: renamed and rewrote the test to assert current behavior:
  - compactor is called once;
  - `current_input_anchor.anchor_label == "C1"`;
  - `current_input_anchor.text` equals the full long prompt;
  - no `truncated`, `preview`, or `summary` marker is present in material JSON;
  - `previous_compacted_view is None`;
  - `trace_material`, `evidence_material`, and `answer_material` are empty;
  - compact artifact files are produced.

## Files Changed

- `tests/host/test_public_compact_smoke.py`

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_proactive_compact_long_current_input_reaches_compactor_without_lossy_anchor
```

Result: `1 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py
```

Result: `11 passed, 1 skipped`.

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py
```

Result: `87 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

## Scope Boundary

No production compact, fallback, recovery tier, parser, validator, accept barrier, or memory projection behavior was changed. This fix only updates a smoke assertion to match the current accepted design.

## Residual Risks

- Production compact root cause for invalid previous reference continuity remains assigned to the separate production memory compact failure work unit.
- Recovery-tier audit diagnostics remain deferred to a later recovery-tier compact audit diagnostics work unit.
- Diagnostic artifact file-only orphan after SQL rollback remains assigned to existing artifact maintenance ownership.

## Completion Status

Ready for aggregate deepreview re-review.
