# WU-OBS-SIGNALS-01 / OBS-SIG-01 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-01` / P01 context pressure signal
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-rereview-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-rereview-ds.md`

## Verdict

OBS-SIG-01 fix re-review passed. The slice is accepted for commit.

## Re-Review Results

### AgentMiMo

- Verdict: PASS.
- Accepted findings recheck:
  - `_duplicate_terminal_result` documents `transaction`.
  - `_ingest_validated` documents `transaction`.
  - `_usage_observation_diagnostic` no longer documents stale `transaction`.
- New findings: none.
- Validation: 116 affected Host tests passed; pyright 0 errors.

### AgentDS

- Verdict: PASS.
- Accepted findings recheck:
  - `_duplicate_terminal_result` documents `transaction`.
  - `_ingest_validated` documents `transaction`.
  - `_usage_observation_diagnostic` no longer documents stale `transaction`.
- New findings: none.
- Validation: 116 affected Host tests passed; pyright 0 errors.

## Controller Verification

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`
  - Result: 116 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.

## README Decision

`dayu/host/README.md` and `tests/README.md` update constraints were checked. OBS-SIG-01 changes extend internal Host projection signal behavior and focused tests without changing public Host entrypoints, architecture boundaries, state machines, stable developer workflows, or the documented tests directory structure. No README update is required.

## Residual Risk

- P02 / P03 / P04 signal producers remain intentionally unimplemented and are owned by later slices in the accepted plan.
- DS non-blocking coverage notes for missing compaction request facts and malformed bool payloads remain non-blocking residual observations for later integration or analyzer-facing coverage.
