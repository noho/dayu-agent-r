# WU-OBS-SIGNALS-01 / OBS-SIG-01 Fix Gate Codex

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-01` / P01 context pressure signal
- Gate: controller adjudication fix
- Controller adjudication artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-controller-adjudication.md`

## Direct Evidence

- `EngineEventIngestor._duplicate_terminal_result` still accepts `transaction: HostTransaction`, but its docstring was missing `:param transaction: 当前 Host transaction。`.
- `EngineEventIngestor._ingest_validated` still accepts `transaction: HostTransaction`, but its docstring was missing `:param transaction: 当前 Host transaction。`.
- `EngineEventIngestor._usage_observation_diagnostic` no longer accepts `transaction`, but its docstring still documented `:param transaction: 当前 Host transaction。`.

## Changes

- Restored `:param transaction: 当前 Host transaction。` in `EngineEventIngestor._duplicate_terminal_result`.
- Restored `:param transaction: 当前 Host transaction。` in `EngineEventIngestor._ingest_validated`.
- Removed the stale `:param transaction: 当前 Host transaction。` line from `EngineEventIngestor._usage_observation_diagnostic`.

## Validation

- Passed: `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`
  - Result: 116 passed.
- Passed: `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.

## Docs Decision

- `dayu/host/README.md` was checked for its Agent update constraints. This fix only corrects private method docstring consistency and does not change Host architecture, public contract, state machine, event semantics, or developer-facing stable behavior, so no README update is required.

## Residual Risk

- No uncovered risk from this fix gate. The change is documentation-only and does not modify runtime behavior or test semantics.

## Completion Status

- Fix applied and validated. Waiting for controller.
