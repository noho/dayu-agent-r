# WU-ENGINE-01 Slice 1 Fix Report

## Gate / Scope

- Gate: `Slice 1 fix`
- Work unit: `WU-ENGINE-01 Runner diagnostic payload audit`
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Implementation artifact: `docs/reviews/wu-engine-01-slice1-implementation-codex-20260602.md`
- Code review artifacts:
  - `docs/reviews/wu-engine-01-slice1-code-review-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-slice1-code-review-ds-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-slice1-code-review-controller-adjudication-20260602.md`
- Role: fix agent only; no commit, push, PR, or gate transition.

## Changed Files

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `tests/engine/runners/openai/test_diagnostic_payload.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `docs/reviews/wu-engine-01-slice1-fix-codex-20260602.md`

## Per-Finding Fix Status

### DS-1-已修复-[中]-non-stream parser 剩余协议错误码内联

- Added module-level private constants for `non_stream_invalid_json`, `non_stream_payload_not_object`, `non_stream_missing_choices`, `non_stream_choice_not_object`, and `tool_call_arguments_not_object`.
- Replaced production references while preserving exact string values.

### DS-2-已修复-[中]-protocol object diagnostic payload 脱敏测试缺口

- Added direct `protocol_object_diagnostic_payload` redaction test with top-level sensitive field and nested sensitive value.
- Test asserts sensitive values do not appear in diagnostic leaf strings.

### MIMO-1-已修复-[低]-invalid UTF-8 final_decode=True 单测缺口

- Added unit test for `invalid_utf8_diagnostic_payload(b"", final_decode=True)`.
- Test asserts `final_decode=True`, zero byte size, empty prefix, and empty chunk SHA-256.

### DS-3-已修复-[低]-SSE parser 剩余协议错误码内联

- Added module-level private constants for `sse_invalid_json` and `sse_payload_not_object`.
- Replaced production references while preserving exact string values.

### DS-4-已修复-[低]-invalid UTF-8 common digest/size 语义不清

- Changed invalid UTF-8 diagnostic common `canonical_byte_size` and `sha256_digest` to use raw chunk bytes length and SHA-256.
- Kept `chunk_byte_size` and `chunk_sha256_digest` dedicated fields with the same raw chunk facts.
- Updated tests to assert common and dedicated fields match raw chunk bytes.

### DS-5-已修复-[低]-large provider error integration fallback 未断言 minimal structure

- Updated large non-stream provider error integration test to assert `preview` and `top_level_keys` are absent after fallback.

## Validation

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py
```

Result: passed, `35 passed in 0.17s`.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

## Docs Decision

- No README or product documentation changed.
- Reason: fix scope was limited to controller-accepted Slice 1 findings and allowed files; no public contract shape, CLI, schema, or user workflow changed.

## New Risks / Open Questions

- No new blocking question.
- No new residual risk introduced by this fix pass.
- Existing out-of-scope residual risk remains unchanged: HTTP JSON error body raw payload handling belongs to Slice 2.

## Stop Condition Status

- No public dataclass field shape change.
- No Engine/Host event type change.
- No Host production, README, schema, or `runner.py` change.
- No commit, push, PR, or gate transition performed.

