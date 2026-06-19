# WU-CM-12 S3 Code Review Adjudication

## Scope

- Work unit: WU-CM-12 Conversation Memory Drift Repair
- Slice: S3 Shared Rendering And Selected-Id Provenance Guards
- Branch: `wu-cm-12-conversation-memory-drift`
- Implementation artifact: `docs/reviews/wu-cm-12-s3-implementation-codex-20260618.md`
- Initial reviews:
  - `docs/reviews/code-review-wu-cm-12-s3-mimo-20260618-160003.md`
  - `docs/reviews/code-review-wu-cm-12-s3-ds-20260618-160229.md`
- Focused re-reviews:
  - `docs/reviews/code-review-wu-cm-12-s3-rereview-mimo-20260618-161132.md`
  - `docs/reviews/code-review-wu-cm-12-s3-rereview-ds-20260618-161031.md`

## Accepted Findings

### S3-F1 Required Fallback Provenance Fields

Accepted.

`RecentWindowFallbackSelection.to_window_payload()` writes `selected_recent_window_turn_floor`, `selected_raw_turn_count`, and `selected_material_view_digest` unconditionally. Reading those fields with optional readers allowed corrupted EventLog fallback payloads to produce `None` and skip downstream provenance guards.

Resolution:

- `EventLogContextFallbackProvider._load_context_fallback_tx(...)` now reads these fields with required readers.
- Missing fields, invalid integer types, `bool` values, negative integers, missing text, non-text values, or blank text fail closed with `HostDurableError`.

### S3-F2 Provider-Level Fail-Closed Coverage

Accepted.

Rendering-level tests did not prove the EventLog-backed provider path itself failed closed.

Resolution:

- Added provider-level EventLog payload tests covering missing fallback window, fallback digest mismatch, current input ref mismatch, missing / invalid selected material digest, missing / invalid selected raw turn count, and missing / invalid selected recent turn floor.
- The tests write a real `CONTEXT_COMPACTION_FAILED` event and call `EventLogContextFallbackProvider.load_context_fallback(...)`.

### S3-F3 Unreachable Marked Protected Group Guard

Accepted as cleanup.

The marked-group sub-check in `_validate_fallback_protected_groups(...)` depended on `protected_recent_raw_turn=True`, but production code did not set that marker. The main selected-id protected group guard was already sufficient.

Resolution:

- Removed the marked-group sub-check.
- Removed the synthetic test that manually set `protected_recent_raw_turn=True`.
- Kept the production protected group consistency guard based on newest turn-group floor ids and selected ids.

## Rejected / Deferred Findings

None for S3.

`WU-CM-12-S1-R1` remains outside S3 because this slice did not modify `dayu/host/memory.py`. It should be reconciled in a later WU-CM-12 residual / regression pass before final closeout.

## Final Review Result

PASS.

Both focused re-reviews confirmed all accepted findings are closed.

## Validation

Controller validation after fixes:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q
```

Result: `181 passed`.

```bash
source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: no whitespace errors.
