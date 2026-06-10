# WU-TOOLS-01-F01-02-R3 Slice 0 Implementation

## Work Unit / Slice / Gate

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: `Slice 0: Current ToolCallable Support`
- Gate: implementation
- Implementer: Codex

## Changed Files

- `dayu/runtime/tool_call_projection.py`
- `tests/runtime/test_tool_call_projection.py`
- `docs/reviews/wu-tools-01-f01-02-r3-slice0-implementation-codex.md`

No edits were made to Doc / Web / Fins providers, legacy adapter modules, ToolRuntime, Host, Engine, Service, or public contracts.

## What Was Implemented

- Added a runtime-neutral `dayu.runtime.tool_call_projection` helper for native current `ToolCallable` migration.
- Added typed result classes:
  - `ValidatedToolArguments`
  - `ToolArgumentValidationFailure`
  - `ToolBusinessFailure`
  - `ToolBusinessCancelled`
  - `ToolArgumentValidationResult`
- Added `validate_and_project_arguments(call, tool_name, schema)` with fixed `invalid_argument` validation failure code.
- Implemented minimal demand-driven schema validation:
  - tool name match
  - top-level object schema projection through `ToolParametersSchema`
  - required fields
  - unknown field rejection unless `additional_properties=True`
  - defaults
  - supported field types: `string`, `integer`, `number`, `boolean`, `array`, `object`
  - enum
  - string bounds
  - numeric bounds
  - array bounds
  - scalar array item schema
  - integer rejects bool
  - number rejects non-finite float
  - unsupported advanced schema keywords fail closed as `invalid_argument`
- Added outcome construction helpers:
  - `completed_outcome(...)`
  - `failed_outcome(...)`
  - `host_cancelled_outcome(...)`
- `host_cancelled_outcome(...)` returns `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` and supplies non-empty default message / hint when absent or blank.
- Outcome helpers consistently construct `ToolResultMeta(tool_name, started_at, finished_at)`.
- Helper depends only on standard library and `dayu.contracts`; it does not observe `CancellationToken` and does not expose run/session/correlation/cancellation governance fields.

## Validation Commands and Results

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py`
  - Result: passed, `14 passed`.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed, no output.
- Additional coverage check:
  - `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py --cov=dayu.runtime.tool_call_projection --cov-report=term-missing`
  - Result: passed, `14 passed`, `dayu/runtime/tool_call_projection.py` coverage `85%`.

## Docs Decision

- `tests/README.md` was read before deciding whether to update docs.
- This slice adds a focused test file under the existing `tests/runtime/` layer and does not add a new test layer, test command, or maintenance rule.
- No README update was required.

## Residual Risks / Uncovered Areas

- This slice intentionally does not migrate Doc / Web / Fins providers; they still use the legacy adapter until later slices.
- The helper deliberately implements only the accepted narrow JSON Schema subset. Advanced JSON Schema features such as `oneOf`, `anyOf`, nested object property validation, pattern constraints, and non-scalar array items fail closed instead of being interpreted.
- `ToolBusinessFailure` and `ToolBusinessCancelled` are support dataclasses for later native callable slices; this slice does not wire them into business providers.

## Stop Condition Status

- No public contract changes were required.
- `dayu.runtime` did not need to import business packages, Host, Engine, Service, UI, or Fins.
- Current Doc / Web / Fins read tool schemas inspected for this slice fit the supported validation subset; no unsupported required validation behavior was found.
- Slice 0 stops here and does not enter Slice 1/2/3/4.
