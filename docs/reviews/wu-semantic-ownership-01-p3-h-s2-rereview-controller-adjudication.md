# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 re-review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-fix-codex.md`
- Re-review inputs:
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-rereview-ds.md`

## Controller Result

P3-H S2 code-review fixes are accepted. No S2 fix gate remains.

## Finding Closure

| Finding | Re-review result | Controller decision |
|---|---|---|
| `P3-H-S2-CR-F01` `_failure_message` fallback to `snapshot.message`. | AgentMiMo: CLOSED. AgentDS: CLOSED. | Closed. `_failure_message(...)` now reads only `FinsResultSummary.error_message` and raises `ValueError` when it is missing. |
| `P3-H-S2-CR-F02` missing observation terminal `error_message` invariant tests. | AgentMiMo: CLOSED. AgentDS: CLOSED. | Closed. Tests now cover cancellation-before-activation, activation failure, producer-without-result, and malformed failed snapshot. |

## Observation Adjudication

- AgentMiMo's whitespace-only `fallback_message` observation remains rejected as non-defect. The helper docstring says empty fallback uses the error-kind default; whitespace-only input is empty after trimming.
- AgentDS `OBS-01` on `_wait_boundary_lost` is not current S2 uncommitted diff. `git diff -- dayu/fins/ingestion/wait_adapter.py` shows only helper imports, failed/cancelled text usage, and `_failure_message(...)` tightening. `_wait_boundary_lost` is already present in `HEAD`.
- AgentDS `OBS-02` on `FinsDirectStreamProtocolError` is not current S2 uncommitted diff. `git show HEAD:dayu/fins/ingestion_runtime.py` already contains `FinsDirectStreamProtocolError` and related tests; current S2 diff does not introduce that contract.

## Validation

- Fix focused tests: `4 passed, 3 warnings`
- S2 affected matrix: `215 passed, 3 warnings`
- Helper coverage: `dayu/fins/direct_event_text.py` `86%`
- Pyright: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed
- Source scan for `snapshot.message` fallback, generic Fins operation failure fallback, Observation-to-error-message, direct hint literals, and old Fins ingestion hint: no matches.

## Residual Risk

- Legacy job sidecar messages and adapter-provided progress messages remain outside S2 scope, as recorded in the plan.
- No current S2 code-review finding remains open.
