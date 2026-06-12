# WU-OBS-SIGNALS-01 / OBS-SIG-05 Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `OBS-SIG-05` / Integration, Docs Decision, Validation
- Integration artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-05-integration-codex.md`

## Verdict

OBS-SIG-05 integration validation passed. The integration gate is accepted for commit.

## Controller Verification

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_context_compact_events.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py`
  - Result: 193 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## Integration Findings

- Query helper coverage now proves all four OBS signal objects survive durable query helpers:
  - `context_pressure`
  - `tool_timing`
  - `failure_metadata`
  - `partial_tool_call_signal`
- Existing projection tests continue to assert hot `trace_summary` and cold JSONL `trace_summary` consistency for the relevant signal rows.
- Existing ingest tests continue to assert no state transition side effects for usage projection signals and provider protocol diagnostics.

## README Decision

No README update is required in OBS-SIG-05:

- `dayu/host/README.md` already records Tool Trace as a read-only derived diagnostic view that projects structured signals.
- `tests/README.md` already records Tool Trace structured signal coverage.
- This gate strengthens existing query helper assertions and does not add a new test layer, command, public Host interface, state machine, durable schema, or architecture boundary.

## Residual Risk

- Analyzer classification, aggregation, and reporting remain intentionally out of scope and owned by WU-OBS-00 / GitHub Issue #70.
- Historical traces without new signal fields remain limited signal for analyzer logic.
- No stop condition was triggered: validation did not require design truth, SQLite schema, Engine public contract, ToolRuntime semantics, or analyzer body changes.
