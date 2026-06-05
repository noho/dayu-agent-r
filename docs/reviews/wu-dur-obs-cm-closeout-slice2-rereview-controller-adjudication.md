# WU-DUR-P01 Slice 2 Fix Re-Review Controller Adjudication

## Verdict

pass. Slice 2 runner-call manifest contract and Engine signals are accepted for this phase after controller validation.

## Reviewed Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice2-implementation-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-code-review-controller-adjudication.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-fix-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-rereview-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-rereview-ds.md`
- Current Slice 2 workspace diff.

## Accepted Fix Verification

| Accepted finding | Controller decision |
|---|---|
| S2-F1: continuation runner calls lacked canonical manifest signal | Fixed. Host ingest writes canonical `RUNNER_CALL_INPUT_ASSEMBLED` limited-signal manifests for Engine-internal continuation `iteration_started` events when no matching manifest exists. This is no longer preview-only and does not claim complete reconstruction. |
| S2-F2: Tool Trace non-complete diagnostic hardcoded details to `None` | Fixed. Tool Trace reads typed diagnostic fields from canonical payload and fail-closes when a non-complete signal lacks a diagnostic object. |
| S2-F3: continuation validation was not visible through canonical / Tool Trace path | Fixed. Continuation limited-signal validation is visible through canonical manifest events and Tool Trace projection. |

## Re-Review Findings

No blocking findings remain.

DS Finding-1, missing direct test for Tool Trace fail-closed diagnostic path, is accepted as a non-blocking residual test hardening item. The implementation is fail-closed and covered by valid non-complete diagnostic projection tests; the missing malformed diagnostic case does not block Slice 2 acceptance.

DS Finding-2, iteration matching fallback when Engine resets `iteration_index` to zero, is accepted as a non-blocking boundary hardening item. Current Engine iteration indexes are monotonic within an execution, and continuation normal path is covered. The boundary should be tracked for later runner-call signal hardening.

Previously non-accepted maintenance issues remain non-blocking:

- Duplicate manifest lookup helper between `run_input.py` and `engine_ingest.py`.
- Recovery trigger taxonomy precision.

## Validation Status

Sub-agent validation:

- `pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`: 155 passed.
- `pyright`: 0 errors.
- `git diff --check`: clean.

Controller validation:

- `pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`: 155 passed.
- `pyright`: 0 errors.
- `git diff --check`: clean.

## Residual Risks To Track

- Slice 2 runner-call diagnostic malformed-payload fail-closed path needs direct test coverage.
- Iteration matching fallback should be hardened or explicitly tested if Engine iteration indexing semantics change.

## Decision

Slice 2 is ready for accepted commit after controller validation and residual-risk control-doc tracking.
