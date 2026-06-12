# WU-OBS-SIGNALS-01 / OBS-SIG-01 Implementation

## Gate

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `implementation`
- Slice: `OBS-SIG-01 / P01 Context Pressure Signal`
- Artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md`
- Scope statement: only `OBS-SIG-01` was implemented. `P02` / `P03` / `P04` were not implemented.

## Changed Files

- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md`

## Exact Slice Changes

- `EngineEventIngestor._append_projection_signal` now includes `payload.context_pressure` on `USAGE_REPORTED` projection signals.
- The usage `context_pressure` object is serialized from the existing Host context budget policy, the single `BudgetEstimate` built for usage observation, and `decide_context_budget`; no threshold or decision math was duplicated.
- Missing budget policy, missing input event, and unreadable input remain accepted non-failing usage projection signals with `status="estimate_unavailable"` and `budget_decision="unknown"`.
- Invalid usage tokens remain accepted non-failing usage projection signals with `status="usage_invalid"`.
- Tool Trace projection continues to copy `payload.context_pressure` from usage projection signals into `trace_summary.context_pressure`; it does not recompute usage budget thresholds or decisions.
- Tool Trace projection now derives `trace_summary.context_pressure` for `CONTEXT_COMPACTION_FAILED` from existing failed payload fields plus the existing request fact referenced by `operation_id`.
- Tool Trace projection now derives minimal `trace_summary.context_pressure` for `CONTEXT_COMPACTION_ATTEMPT_REJECTED` from existing attempt-rejected payload fields.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`
  - Result: `116 passed in 1.00s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

- Read `dayu/host/README.md` Agent update constraints.
- Read `tests/README.md` maintenance constraints.
- No README update was made. The slice adds an internal diagnostic/projection signal and focused tests, but does not change stable Host developer interfaces, architecture boundaries, test layering, or documented run commands.

## Residual Risks

- Covered by later approved slice: `tool_timing`, `failure_metadata`, and `partial_tool_call_signal` remain unchanged placeholders/copy paths until `P02` / `P03` / `P04`.
- Assigned to later analyzer work unit: aggregation such as compact counts and pressure trend summaries remains analyzer-owned and was not added per scope.
- No unclassified residual risk for `OBS-SIG-01`.

## Completion Status

- Implementation gate for `OBS-SIG-01` is complete.
- No review, commit, push, PR, merge, or next gate action was performed.
