# P9.5 S2 Engine / OpenAI Runner / Parser Hardening Implementation

## Scope

- Gate: P9.5 S2 Engine / OpenAI Runner / Parser Hardening implementation.
- Branch: `p9.5-pre-p10-hardening`.
- Role: implementation worker only; no commit, push, PR, review, or review fix loop.
- Allowed boundary observed: changes are limited to `dayu/engine/runners/openai/*`,
  `tests/engine/runners/openai/*`, `tests/engine/test_metadata_boundary.py`, and
  this implementation artifact.

## Motivation And Direct Evidence

- Existing targeted tests were already green, so the slice did not justify broad
  speculative parser rewrites.
- Direct inspected defect: both SSE and non-stream usage parsing used
  `isinstance(value, int)`, which accepts `bool` as a valid token count in Python.
  Token-count contract expects integer counts, while `JsonValue` explicitly leaves
  bool/int runtime distinction to consumers.
- Direct observability gap: non-stream malformed `usage` was silently ignored,
  while the SSE path already emitted a WARN diagnostic and continued safely.
- Plan-required boundary gap: metadata/log leakage needed a focused Engine event
  stream test proving log records remain outside `EngineEvent.metadata`.

## Changed Files

- `dayu/engine/runners/openai/usage.py`
  - Added `UsageTokenCounts` and `coerce_usage()` as a shared parser helper.
  - Rejects `bool` token fields while accepting real `int` token counts.
- `dayu/engine/runners/openai/sse_parser.py`
  - Reused `coerce_usage()` for usage normalization.
  - Preserved existing WARN-and-continue behavior for malformed usage.
- `dayu/engine/runners/openai/non_stream_parser.py`
  - Reused `coerce_usage()` for usage normalization.
  - Added WARN diagnostic for malformed non-stream usage and continued without
    emitting `RUNNER_USAGE_RECORDED`.
- `tests/engine/runners/openai/test_non_stream_response.py`
  - Added non-stream bool usage malformed test.
- `tests/engine/runners/openai/test_protocol_error.py`
  - Added SSE bool usage malformed test.
- `tests/engine/runners/openai/test_sse_tool_call_stream.py`
  - Added parallel tool-call aggregation test for id fallback without explicit
    indexes.
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`
  - Added stream/non-stream content finish reason parity matrix for `stop`,
    `length`, and `content_filter`.
- `tests/engine/test_metadata_boundary.py`
  - Added behavioral Agent event stream test proving debug logs do not enter
    `EngineEvent.metadata`.

## Public Contract And Docs Decision

- No Engine public state contract changed.
- No provider-specific public state, retry model redesign, Host governance,
  memory state, tool governance, wait truth, or durable cursor was added.
- README update not required: the changes are internal parser validation,
  diagnostics, and targeted test coverage; current user/developer interface docs
  remain accurate.

## Validation

- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_engine_event_contract.py`
  - Result: passed, 228 tests.
- `source .venv/bin/activate && python -m pyright dayu/engine tests/engine`
  - Result: passed, 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## Residual Risks And Uncovered Areas

- Usage validation now rejects bool and missing/wrong-type token fields, but does
  not add non-negative range checks because current contracts do not explicitly
  define token-count range validation in this slice.
- No usage-only retry granularity or partial tool-call-delta retry behavior was
  reopened.
- Provider 200 response shapes beyond the existing OpenAI-compatible parser
  contract were not expanded without direct evidence.

## Stop Status

- S2 implementation complete.
- Required validation complete.
- No blocking stop condition encountered.
- No commit, push, PR, or review action performed.
