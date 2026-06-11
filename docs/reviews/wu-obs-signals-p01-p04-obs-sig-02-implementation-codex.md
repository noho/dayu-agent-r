# WU-OBS-SIGNALS-01 / OBS-SIG-02 Implementation

## Gate

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `implementation`
- Slice: `OBS-SIG-02 / P02 Tool Duration Signal`
- Artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-implementation-codex.md`
- Scope statement: only `OBS-SIG-02` was implemented. `P03` / `P04` and analyzer aggregation were not implemented.

## First-Principles Motivation Check

- Motivation is valid. Analyzer-visible tool duration must come from the same durable path as accepted tool outcomes, otherwise later diagnosis would reconstruct latency from weak process-local logs or projection time.
- Stable source is `ToolResultMeta.started_at` / `finished_at` on completed / failed / cancelled outcomes. That is closer to the real tool execution boundary than Tool Trace projection time, Engine wall-clock timing, or accept retry duration.
- Severity is correctly scoped. Missing `ToolResultMeta` is not a runtime correctness failure; it is an analyzer limited signal. Malformed timing already inside EventLog projection input is a durable integrity problem and should fail closed.

## Changed Files

- `dayu/host/tool_runtime.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-implementation-codex.md`

## Exact Slice Changes

- Added private ToolRuntime helpers:
  - `_tool_result_meta(...)` extracts `ToolResultMeta` from completed / failed / cancelled outcomes.
  - `_tool_timing_from_meta(...)` builds the additive `tool_timing` object.
- Extended `ToolAcceptResult` with explicit `tool_timing`, so the accepted payload is sourced from the typed outcome path rather than inferred from raw JSON or projection time.
- Added `tool_timing` to `TOOL_RESULT_ACCEPTED` payload:
  - `status="available"` includes `started_at`, `finished_at`, non-negative integer `duration_ms`, and `duration_source="tool_result_meta"`.
  - `status="missing_tool_result_meta"` keeps all timing/source fields `null`.
- Tool Trace now validates `tool_timing` before copying it into `trace_summary.tool_timing`.
  - Missing or `null` `tool_timing` remains omitted.
  - Non-object, unsupported status/schema, type errors, missing required fields, non-null missing-meta timing fields, and negative duration fail closed with `HostDurableError`.
- No timeout, cancellation, accept retry, duplicate governance, ToolExecutor scheduling, Engine public contract, SQLite schema, or analyzer aggregation behavior was changed.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py`
  - Result: `80 passed in 0.68s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

- Read `dayu/host/README.md` Agent update constraints.
- Read `tests/README.md` maintenance constraints.
- No README update was made. The slice adds an internal additive diagnostic/projection signal within already documented ToolRuntime accept barrier and Tool Trace projection boundaries; it does not change public Host interfaces, architecture boundaries, test layering, or documented commands.

## Risks / Not Covered

- Tools that do not populate `ToolResultMeta` produce `status="missing_tool_result_meta"`; this is intentional limited signal for the analyzer.
- Analyzer aggregation, median latency, distribution, slow-tool candidate reporting, P03 failure metadata, and P04 partial tool-call diagnostics remain out of scope for this slice.
- Projection validates timing structure and negative duration but does not parse ISO timestamps or recompute duration from strings; the producer computes duration from typed `datetime` values before serialization.

## Completion Status

- Implementation gate for `OBS-SIG-02` is complete.
- No code review, commit, push, PR, merge, or next gate action was performed.
- Waiting for controller.
