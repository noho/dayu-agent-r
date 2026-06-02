# WU-ENGINE-01 Slice 1 Implementation Report

## Gate / Scope

- Gate: `implementation`
- Work unit: `WU-ENGINE-01 Runner diagnostic payload audit`
- Slice: `Slice 1 Protocol Diagnostic Payload Helper + Parser 收口`
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Accepted plan commits: `10b0eaa`, `e55f05e`
- Role: implementation agent only; no commit, push, PR, controller gate transition.

## Changed Files

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `tests/engine/runners/openai/test_diagnostic_payload.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`

## Implemented Items

- Added OpenAI runner internal diagnostic payload helper with bounded, redacted, summarized payload generation.
- Implemented provider error, protocol object, and invalid UTF-8 diagnostic payload helpers.
- Canonical byte size and SHA-256 digest use local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` plus UTF-8 bytes.
- Provider error diagnostics inspect only `payload["error"]` and extract bounded `code` / `type` / `param`; full provider error object is not retained.
- Sensitive key redaction uses case-insensitive substring matching for configured key fragments.
- Oversized diagnostic fallback first truncates preview fields, then removes preview/top-level keys and returns minimal version/source/kind/size/digest structure.
- Replaced protocol parser `raw_payload=dict(parsed)` paths in non-stream provider error, SSE provider error, SSE missing choices, and SSE invalid choice object.
- Replaced SSE invalid UTF-8 full chunk base64 payload with bounded chunk size, digest, and prefix diagnostic payload.
- Promoted invalid UTF-8 codes and missing choices reasons to module-level private constants.
- Updated `RunnerProtocolErrorData` and `ProviderProtocolErrorData` docstrings to clarify `raw_payload` is bounded diagnostic payload, not guaranteed raw provider payload.
- Updated tests to remove exact raw provider payload assertions and assert bounded diagnostic semantics instead.
- Added stream/non-stream provider error object consistency coverage.

## Validation

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py
```

Result: passed, `33 passed in 0.14s`.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

## Docs Decision

- No README was changed in this slice.
- Reason: the handoff allowed files for Slice 1 did not include README files. The stable contract wording touched by this slice was updated in the two contract dataclass docstrings.
- Follow-up: the approved plan assigns `dayu/engine/README.md` consideration to Slice 2 if the final work unit needs developer-facing contract wording after HTTP diagnostic payload changes.

## Residual Risks / Uncovered Areas

- HTTP JSON error body raw payload is still out of scope for Slice 1 and remains assigned to Slice 2 in the approved plan.
- Host ingest artifact behavior and EventLog schema were intentionally not touched; this slice relies on existing opaque `JsonValue` diagnostic handling.
- Helper tests validate current diagnostic schema fields but do not define a public version-aware reader. The approved plan explicitly defers version-aware consumption to future design only if Host/projection/tools need to parse this payload.

## Stop Condition Status

- No public dataclass field shape change.
- No Engine/Host event type change.
- No Host production, Host state machine, EventLog schema, or provider state union change.
- No `Any`, `object`, `getattr`, `hasattr`, extra payload bag, compatibility facade, or re-export was introduced in the implementation.
- No blocking questions.

