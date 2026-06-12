# WU-OBS-SIGNALS-01 / OBS-SIG-02 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-02` / P02 Tool Duration Signal
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-rereview-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-rereview-ds.md`

## Verdict

OBS-SIG-02 fix re-review passed. The slice is accepted for commit.

## Re-Review Results

### AgentMiMo

- Verdict: PASS.
- Accepted finding recheck: failed, cancelled, and governed-error payloads now assert `tool_timing == _missing_tool_timing()`.
- New findings: none.
- Validation: 80 affected Host tests passed; pyright 0 errors.

### AgentDS

- Verdict: PASS.
- Accepted finding recheck: failed, cancelled, and governed-error payloads now assert the expected missing-meta limited signal shape.
- New findings: none.
- Validation: 80 affected Host tests passed; pyright 0 errors.

## Controller Verification

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py`
  - Result: 80 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## README Decision

`dayu/host/README.md` and `tests/README.md` update constraints were checked during implementation and fix gates. OBS-SIG-02 adds an internal additive diagnostic / projection signal and strengthens existing Host tests; it does not change public Host entrypoints, architecture boundaries, documented state machines, test layering, or documented test commands. No README update is required.

## Residual Risk

- Tools without `ToolResultMeta` intentionally emit `status="missing_tool_result_meta"` as analyzer limited signal.
- Analyzer aggregation for latency distribution remains owned by WU-OBS-00.
- P03 failure metadata and P04 partial tool-call diagnostics remain unimplemented and owned by later slices.
