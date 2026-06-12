# WU-OBS-SIGNALS-01 OBS-SIG-05 Integration Validation

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `OBS-SIG-05 Integration, Docs Decision, Validation`
- Design sources checked: `docs/host/design.md`, `docs/engine/design.md`
- Plan source checked: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Control doc checked: `docs/host/issues-implementation-control.md`
- Accepted slice commits checked from control doc: `OBS-SIG-01 82c21f1b`, `OBS-SIG-02 d2fcd091`, `OBS-SIG-03 77049041`, `OBS-SIG-04 8e578532`
- Non-goals honored: no analyzer module/body, no SQLite schema change, no Engine public contract change, no ToolRuntime semantics change, no commit, no push, no PR, no review/deepreview.

Code changes in this gate are limited to `tests/host/test_tool_trace_queries.py`: added compact query fixture/assertion helpers and extended the existing query-ordering test to assert that Tool Trace query helpers preserve all four OBS signal objects in returned hot `trace_summary`.

## First-Principles Integration Check

The OBS-SIG signal contract is valid only if the same production payload fields flow through the existing durable projection boundary without becoming governance truth:

```text
Engine / ToolRuntime / context canonical or diagnostic payload
-> EventLog canonical_fact / diagnostic / projection_signal
-> Tool Trace projection
-> hot trace_summary_json and cold JSONL trace_summary
-> durable query helpers
```

The motivation is real: before this gate, projection tests covered hot/cold rows and producer tests covered payload fields, but query helper tests did not jointly prove that all four signal objects remain visible to analyzer-facing read helpers. The fix is appropriately scoped to tests because the query helpers already return hot `trace_summary`; no production implementation change is needed.

The design truth remains aligned:

- Host design states projection, audit, usage and tool trace cannot become EventLog truth or drive state transitions.
- Host design states `diagnostic` and `projection_signal` are for trace/projection input, not governance state.
- Engine design states usage, tool trace and memory are caller-owned durable concerns outside the Engine event stream.
- ToolRuntime accept barrier remains the producer of accepted tool facts; Tool Trace does not time tools or infer failure semantics.

## Coverage Matrix

| Signal | Production payload coverage | Projection hot/cold coverage | Query helper coverage |
|---|---|---|---|
| `context_pressure` | `test_usage_reported_is_projection_signal_without_state_change`; unavailable/invalid usage variants in `tests/host/test_engine_ingest_mapping.py`; context compaction payload builders in `tests/host/test_context_compact_events.py` | `test_tool_trace_copies_optional_summary_signal_objects`; compaction failed/rejected projection tests in `tests/host/test_tool_trace_projection.py` assert cold JSONL matches hot summary | `test_query_helpers_return_rows_ordered_by_event_sequence` now asserts `read_tool_trace_by_run`, `find_tool_trace_by_tool_call_id`, and `find_tool_trace_by_diagnostic_ref` preserve the signal |
| `tool_timing` | `tests/host/test_toolruntime_accept_barrier.py` asserts `TOOL_RESULT_ACCEPTED` payloads include missing timing for accepted facts; `tests/host/test_toolruntime_executor.py` covers executor-produced timing payload shape | `test_tool_trace_projects_tool_timing_available_and_missing_signals` and `test_tool_trace_copies_optional_summary_signal_objects` | `test_query_helpers_return_rows_ordered_by_event_sequence` now asserts run/tool-call/diagnostic query helpers preserve the signal |
| `failure_metadata` | `tests/host/test_toolruntime_executor.py` covers tool failed/cancelled/policy blocked metadata; `test_provider_protocol_error_is_diagnostic_without_state_change` covers provider protocol metadata; accept barrier tests cover accepted fact payloads | tool failure/cancel/policy, provider protocol, context compaction failed/rejected projection tests in `tests/host/test_tool_trace_projection.py` assert hot/cold equality where relevant | `test_query_helpers_return_rows_ordered_by_event_sequence` now asserts run/tool-call/diagnostic query helpers preserve tool failure metadata; provider-request query separately covers protocol diagnostic rows |
| `partial_tool_call_signal` | `test_provider_protocol_error_is_diagnostic_without_state_change`; `test_provider_protocol_error_serializes_partial_tool_call_signal` | `test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states` covers absent/none/present and cold JSONL | `test_query_helpers_return_rows_ordered_by_event_sequence` now asserts `read_tool_trace_by_run` and `find_tool_trace_by_provider_request_id` preserve the signal; `test_provider_request_id_terminal_diagnostic_query` also covers provider request diagnostic query |

## State Side-Effect Checks

- Usage diagnostic path: `test_usage_reported_is_projection_signal_without_state_change` asserts `USAGE_REPORTED` is `EventClass.PROJECTION_SIGNAL` and Run / Attempt remain `RUNNING`.
- Usage unavailable/invalid paths: existing usage tests assert accepted non-failing projection and Run / Attempt remain `RUNNING`.
- Provider protocol path: `test_provider_protocol_error_is_diagnostic_without_state_change` asserts `PROVIDER_PROTOCOL_ERROR` is `EventClass.DIAGNOSTIC` and Run / Attempt remain `RUNNING`.
- Tool result paths stay within accepted tool fact semantics; no test change introduced status transitions.

## Hot/Cold Equality

Relevant projection tests assert cold JSONL `trace_summary` matches hot `trace_summary`:

- shared optional signal object copy
- tool timing
- failure metadata variants
- provider protocol failure metadata
- provider protocol partial tool-call signal states
- context compaction failed / attempt rejected context pressure

## README Decision

Read:

- `dayu/host/README.md` Agent update constraints
- `tests/README.md` README update boundary

Decision: no README content update.

Reason:

- `dayu/host/README.md` already describes Tool Trace as a read-only derived diagnostic view that projects structured signals including context pressure, tool timing and failure metadata; OBS-SIG-05 only validates the loop and does not change stable Host developer interfaces, architecture boundaries, state machines, schema, or operation model.
- `tests/README.md` already describes Host Tool Trace structured signal coverage. This gate only extends an existing test file's assertions; it does not add a test layer, test running mode, or maintenance rule.

## Validation Results

Commands run from repository root:

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_queries.py
```

Result: `3 passed in 0.27s`.

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_context_compact_events.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py
```

Result: `193 passed in 1.32s`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

## Risks / Not Covered

- Analyzer classification, aggregation and report generation remain intentionally out of scope for `WU-OBS-SIGNALS-01`; owner remains `WU-OBS-00` / GitHub Issue #70.
- Historical traces without newly added signal objects remain limited signal for future analyzer logic; this gate does not add backfill or compatibility readers.
- No new malformed query-helper cases were added because query helpers read already-projected hot rows; malformed signal validation belongs to Tool Trace projection tests and is already covered there.

## Review / Deepreview Recommendation

Do not enter review/deepreview from this gate automatically. The gate has passed local validation and should wait for controller adjudication. A later review/deepreview may be useful only if controller decides the whole work unit is moving to a closeout or draft PR gate.
