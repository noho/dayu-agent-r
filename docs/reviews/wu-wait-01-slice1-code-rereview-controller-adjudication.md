# WU-WAIT-01 Slice 1 Code Re-review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: Slice 1 code re-review
- Fix artifact: `docs/reviews/wu-wait-01-slice1-fix-codex.md`
- Prior adjudication: `docs/reviews/wu-wait-01-slice1-code-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/code-review-20260621-225901.md` (AgentMiMo)
  - `docs/reviews/code-review-20260621-225831.md` (AgentDS)
- Base: accepted plan commit `bf359ebb`

## Controller Judgment

Both re-review lanes passed. No material correctness, architecture, stability, or maintainability finding remains for Slice 1.

## Accepted Finding Closure

### S1-CR-F01

- Status: closed.
- Evidence:
  - `callback_payload_digest(...)` and direct resolve `_wait_resolution_digest(...)` now call the same Host wait resolution digest helper.
  - The shared helper centralizes outcome JSON projection and outcome kind constants.
  - `waiting.py` no longer carries the duplicated outcome/result JSON projection implementation.
  - Tests cover completed and lost outcome digest alignment between callback and direct resolve paths.

### S1-CR-F02

- Status: closed.
- Evidence:
  - callback stale boundary parsing now uses Host durable `parse_utc_timestamp(...)`.
  - invalid stored deadline format maps to `INVALID_WAIT_STATE` before resolver invocation.
  - A focused test covers the invalid persisted boundary path.

### S1-CR-F03

- Status: closed-covered-by S1-CR-F02.
- Evidence:
  - the local callback timestamp parser and its `Z -> +00:00` normalization path were removed.

## Residual Risk

- failed / cancelled outcome digest alignment has no separate callback-vs-direct digest unit test. Controller accepts this as low residual risk because both paths now invoke the same pure helper and existing resolve wait tests continue to cover failed/cancelled behavior.
- stale check vs resolve concurrency remains governed by the accepted Slice 1 design: races collapse into the common resolve pipeline or typed invalid-state result. No new current work item is required.
- strict `parse_utc_timestamp(...)` rejects `+00:00` persisted boundaries. Controller accepts this because Host durable timestamps are written through the fixed UTC `Z` helper, and malformed stored boundaries should fail closed as `INVALID_WAIT_STATE`.

## Required Next Gate

Slice 1 may enter accepted slice commit gate.

Required validation before commit:

- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
- `pyright`
- `git diff --check`
