# WU-ENGINE-01 Code Inspection Controller Notes

## Scope

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: discussion / code inspection before planning.
- Design source: `docs/host/design.md`.
- Control source: `docs/host/host-core-followup-implementation-control.md`.

## Motivation Judgment

The work unit motivation is valid but narrower than the historical title suggests. Current code already uses typed provider state and typed runner / engine events, so the correct target is not provider state redesign. The directly evidenced risk is diagnostic raw payload breadth and stream / non-stream protocol error consistency.

## Direct Evidence

- `dayu/engine/contracts/runner_events.py` defines `RunnerProtocolErrorData.raw_payload` and `RunnerHTTPErrorData.raw_payload` as diagnostic `JsonValue | None`.
- `dayu/engine/contracts/engine_events.py` defines `ProviderProtocolErrorData.raw_payload`, preserving the runner protocol diagnostic payload into Engine events.
- `dayu/engine/runners/openai/runner.py` reads HTTP error bodies through `_HTTP_ERROR_BODY_MAX_BYTES`, so HTTP error diagnostics already have a byte-size boundary before JSON object preservation.
- `dayu/engine/runners/openai/non_stream_parser.py` emits `RunnerProtocolErrorData(raw_payload=dict(parsed))` for non-stream provider error objects.
- `dayu/engine/runners/openai/sse_parser.py` emits `RunnerProtocolErrorData(raw_payload=dict(parsed))` for SSE provider error, missing choices, and invalid choice object cases; invalid UTF-8 stores a bounded base64 chunk diagnostic.
- `tests/engine/runners/openai/test_protocol_error.py` asserts exact raw payload preservation for stream and non-stream provider error objects.
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py` covers successful terminal parity but does not cover protocol error object parity.

## Controller Boundary

Planning should keep the implementation within Engine runner diagnostic payload boundaries and related tests. It must not:

- rewrite typed provider state;
- move Host lifecycle or state-machine responsibility into Engine;
- introduce compatibility facades;
- use raw metadata bags or extra payload to avoid typed contracts;
- expand into generic provider abstraction redesign.

## Planning Input

The planning agent should produce a code-generation-ready plan that decides whether to summarize, bound, or otherwise normalize diagnostic raw payloads in the OpenAI-compatible runner path, and should specify exact stream / non-stream consistency tests. The plan must include documentation impact for `dayu/engine/README.md` only if the stable Engine developer contract changes.

