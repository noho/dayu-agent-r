# WU-OBS-SIGNALS-01 / OBS-SIG-04 Code Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-04` / P04 Provider Protocol Partial Tool-call Projection
- Implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-code-review-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-code-review-ds.md`

## Verdict

OBS-SIG-04 code review passed. No fix gate is required before accepting the slice.

## Review Results

### AgentMiMo

- Verdict: PASS.
- Findings: no required fix.
- Validation: 97 affected Host tests passed; pyright 0 errors.

### AgentDS

- Verdict: PASS.
- Findings:
  - LOW: malformed `partial_tool_call_signal` tests do not cover every fail-closed branch.
  - INFO: bare sha256 hex validation is intentionally different from Host `sha256:<hex>` digest validation.

## Controller Adjudication

- DS low coverage finding is not accepted as a current fix. Current tests cover valid producer paths, absent / none / present semantics, provider-request query retention, non-object failure, count mismatch, invalid digest, and present-with-empty-list fail-closed behavior. The remaining branches are simple schema/source/status/type guard paths using shared helper patterns already exercised by prior signal tests. Consider broader malformed matrix only if OBS-SIG-05 integration finds drift.
- DS info finding is accepted as design record only. Engine `PartialToolCallSummary.arguments_sha256` is a bare 64-character lowercase hex digest by contract; Host durable `sha256:<hex>` validation is intentionally not reused for this field.

No accepted findings remain.

## Controller Verification

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`
  - Result: 97 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## README Decision

No README update is required for OBS-SIG-04. The Host README already describes read-only structured Tool Trace signals after OBS-SIG-03, and this slice only adds one signal field within the same implemented boundary. The tests README already describes Tool Trace structured signal coverage without needing a new testing layer or command.

## Residual Risk

- Historical rows without `partial_tool_call_signal` remain analyzer limited signal.
- `arguments_present` intentionally follows Engine summary digest presence and does not prove malformed JSON by itself.
- WU-OBS-00 analyzer must combine this signal with provider protocol `error_code` instead of parsing raw provider payload.
