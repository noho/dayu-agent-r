# WU-OBS-SIGNALS-01 OBS-SIG-04 Implementation

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-04 / P04 Provider Protocol Partial Tool-call Projection`
- Agent: AgentCodex
- Gate: implementation only; no commit, no push, no PR, no code review.

Implemented additive projection of Engine bounded partial tool-call summaries from `ProviderProtocolErrorData.partial_tool_calls` into:

- Host `PROVIDER_PROTOCOL_ERROR` diagnostic payload field `partial_tool_call_signal`.
- Tool Trace hot `trace_summary_json` and cold JSONL `trace_summary`.

## First-principles Motivation

The motivation is valid. Engine already has same-source, bounded and redacted partial tool-call summaries for provider protocol failures. Host previously preserved only `partial_tool_call_count`, which is insufficient for a downstream analyzer to distinguish a new positive no-partial signal, historical limited signal, and present bounded partial summaries without guessing from raw provider payloads or logs.

The accepted plan is the right boundary because it uses existing Engine contract fields, keeps Host projection read-only, and avoids Engine parser changes, raw stream replay, SQLite schema changes, raw argument persistence, or analyzer taxonomy implementation.

## Direct Evidence

- `dayu/engine/contracts/partial_tool_call.py` defines `PartialToolCallSummary` with `tool_call_index`, bounded `tool_call_id`, bounded `name_fragment`, `arguments_byte_size`, and `arguments_sha256`; it contains no raw arguments.
- `dayu/engine/contracts/engine_events.py` defines `ProviderProtocolErrorData.partial_tool_calls: tuple[PartialToolCallSummary, ...]`.
- `docs/engine/design.md` classifies `provider_protocol_error` as provider protocol parsing failure.
- `docs/host/design.md` maps Engine `provider_protocol_error` to Host `PROVIDER_PROTOCOL_ERROR`.
- Before this slice, `dayu/host/engine_ingest.py` wrote `partial_tool_call_count` but no bounded summary details.
- `dayu/host/tool_trace.py` already had a grouped signal copy path for `partial_tool_call_signal`, but no P04 closed-shape validation.

## Changes

- Added `partial_tool_call_signal` construction in `_append_provider_protocol_error`.
- Kept top-level `partial_tool_call_count` in the same diagnostic payload for coarse compatibility.
- Added signal fields: `schema_version=1`, `signal_source="PROVIDER_PROTOCOL_ERROR"`, `partial_tool_call_count`, `summary_status`, `raw_payload_present`, and `partial_tool_calls`.
- Set `summary_status="none"` for empty Engine tuple and `summary_status="present"` for non-empty tuple.
- Set `raw_payload_present` only from Host raw payload descriptor presence after `_write_raw_payload`; raw payload contents are not read for this signal.
- Serialized only Engine bounded summary fields plus derived `arguments_present = arguments_sha256 is not None`.
- Added Tool Trace validation for partial signal schema/source/status/count/list shape, bounded summary field types, non-negative index/byte size, bare Engine sha256 hex digest shape, and digest/presence consistency.
- Did not modify Engine parser, Engine public contract, SQLite schema, provider stream replay, raw payload export, P03 failure metadata, or analyzer report.

## Tests

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

Result: 97 passed.

Passed:

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors.

Coverage added:

- Engine ingest mapping covers empty partial tuple, raw payload descriptor present, `summary_status="none"`, and count `0`.
- Engine ingest mapping covers non-empty bounded partial summaries, digest present, digest absent, `arguments_present`, raw payload absent, and count `2`.
- Consumer impact coverage simulates a legacy provider protocol diagnostic consumer reading only existing fields while tolerating additive `partial_tool_call_signal`.
- Tool Trace projection fixture distinguishes absent historical limited signal, new positive no-partial signal, and present bounded summary signal.
- Tool Trace malformed signal tests fail closed for status/count/digest inconsistencies.
- Provider-request query test confirms query results retain `trace_summary.partial_tool_call_signal`.

## README Decision

- `dayu/host/README.md`: read Agent update constraints. No update made because the current Tool Trace paragraph already describes read-only structured signals at a high level using "等", and P04 does not change public Host interface, architecture boundary, state machine, schema, or developer-facing operation.
- `tests/README.md`: read README update boundary. No update made because this slice only extends existing Host test files and does not add a test layer, test running mode, or maintenance rule.

## Risks / Not Covered

- No analyzer classification was implemented. Analyzer must still combine `error_code` with bytes/digest; this slice does not infer malformed JSON from `arguments_sha256`.
- `arguments_present` is derived from Engine summary digest presence, not from raw arguments or provider stream replay.
- Old traces without `partial_tool_call_signal` remain limited signal for analyzer; this slice only ensures new empty tuples are positive no-partial signals.
- No indexed query was added for partial summaries; existing provider request and trace scan paths remain the planned analyzer input.
