# WU-OBS-SIGNALS-01 / OBS-SIG-01 Code Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-01` / P01 context pressure signal
- Reviewed implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-ds.md`

## Verdict

Code review completed with accepted docstring-only findings. A fix gate is required before accepting the slice.

## Accepted Findings

### MIMO-F1: Missing `transaction` parameter documentation

- Source: AgentMiMo code review.
- Finding: `EngineEventIngestor._duplicate_terminal_result` and `EngineEventIngestor._ingest_validated` still accept `transaction: HostTransaction`, but their docstrings no longer document the parameter.
- Direct evidence: `dayu/host/engine_ingest.py` function signatures keep `transaction`, while each docstring only documents `context` and return value.
- Adjudication: accepted.
- Required fix: restore `:param transaction: 当前 Host transaction。` in both docstrings.

### DS-F1: Stale `transaction` parameter documentation

- Source: AgentDS code review.
- Finding: `EngineEventIngestor._usage_observation_diagnostic` no longer accepts `transaction`, but its docstring still documents `:param transaction: 当前 Host transaction。`.
- Direct evidence: `dayu/host/engine_ingest.py` function signature contains only keyword-only `context`, `data`, and `estimate`; the docstring still contains the stale parameter line.
- Adjudication: accepted.
- Required fix: remove the stale `:param transaction: 当前 Host transaction。` line.

## Rejected Findings

None.

## Fix Gate Instructions

AgentCodex should apply only the accepted docstring consistency fixes in `dayu/host/engine_ingest.py`, then run the affected Host tests and pyright:

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`
- `source .venv/bin/activate && pyright`

The fix artifact should be written to `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-fix-codex.md`.

## Residual Risk

- P02 / P03 / P04 signal fields remain intentionally unimplemented in this slice.
- DS residual notes about fallback coverage for missing compaction request facts and malformed bool payloads are not accepted as OBS-SIG-01 blocking findings; they may be reconsidered during OBS-SIG-05 integration or analyzer-facing coverage.
