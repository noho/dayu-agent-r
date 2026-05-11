# P8.5 Slice 6 Implementation Report

## Work Gate

- work gate name: `implementation`
- work-unit name: P8.5 — P8 Stabilization / ToolRuntime Event Model
- assigned slice id: Slice 6 — Documentation / Migration Registry Closeout
- approved plan path: `docs/host/phase8.5-plan.md`
- accepted checkpoint before this slice: `8e5ca33`（Slice 5b accepted）
- artifact path: `docs/host/phase8.5-s6-implementation-report.md`

## Assigned Scope / Non-goals / Allowed Files

本 slice 只做文档与 residual registry closeout，不改生产代码和测试代码。

Allowed files:

- `docs/host/migration-plan.md`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- root `README.md` only if project-level usage / trace / render / CLI docs were triggered
- `docs/host/phase8.5-s6-implementation-report.md`

Explicit non-goals observed:

- No production code changes.
- No test code changes.
- No plan rewrite, plan review, commit, PR, or closeout.
- No future design described as already implemented.

## Changed Files

- `docs/host/migration-plan.md`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/phase8.5-s6-implementation-report.md`

Root `README.md` was not changed because this slice did not change project-level CLI usage, configuration, trace/render user entry points, or install/run workflows.

## Plan Items Implemented

- Updated `docs/host/migration-plan.md` current state from stale `plan fix` to current Slice 6 implementation handoff with accepted checkpoint `8e5ca33`.
- Updated P8.5 phase status and P8 / P8.5 current fact summary to match accepted Slice 1-5b implementation facts.
- Updated residual risk registry so completed items are marked fixed/validated and open items have destinations: P9, P15 / issue #28, P16, GitHub issue #36/#38/#41, or later provider adapter coverage.
- Recorded corrupt durable memory snapshot row root-cause / quarantine / operations / long-term overwrite policy as tracked by GitHub issue #41, not as solved by P8.5.
- Corrected `docs/host/design.md` P7-era text that still described inline raw payloads and trace sink/checkpoint behavior as current facts; current design now says `run_input_raw_payloads` side-store is committed with EventLog fact and non-required trace sink I/O happens outside checkpoint transaction.
- Adjusted `dayu/host/README.md` ToolRuntime smoke wording to describe current Host-private `RuntimeTruncateManager` / ordinary `fetch_more` tool path rather than old public handle wording.
- Updated `tests/README.md` type-check command to the current required `python -m pyright dayu/ tests/ utils/` form.

## Plan Items Not Implemented

- Root `README.md` was not updated; trigger did not apply.
- No production/test fix was attempted for the failing `tests/contracts tests/engine` validation because Slice 6 explicitly disallows production and test code changes unless a plan/code fact conflict requires stopping and reporting.

## Validation Commands And Results

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate && pytest tests/host -q
```

Result: passed, `376 passed in 2.77s`.

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

Result: failed, `3 failed, 323 passed in 1.13s`.

Failures:

- `tests/engine/test_metadata_boundary.py::test_provider_protocol_error_engine_data_has_explicit_fields`
- `tests/engine/test_metadata_boundary.py::test_provider_protocol_error_runner_data_has_explicit_fields`
- `tests/engine/test_package_exports.py::test_engine_all_matches_expected_set`

Observed failure shape: Engine / Runner protocol error data and `dayu.engine.__all__` now expose Slice 4 `partial_tool_calls` / `PartialToolCallSummary`, but these three tests still lock the previous explicit field/export sets. This is outside Slice 6 allowed edits and needs controller decision.

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" dayu tests dayu/host/README.md tests/README.md
```

Result: hits only in negative public-surface tests:

- `tests/host/test_host_public_api_surface.py`
- `tests/host/test_phase1_public_boundary.py`
- `tests/host/test_phase2_tool_runtime_boundary.py`

No hits in production `dayu/`, `dayu/host/README.md`, or `tests/README.md`. The test hits are forbidden-name guards asserting old public contracts / handles do not exist.

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" docs/host/migration-plan.md docs/host/phase8.5-plan.md
```

Result: hits are historical / residual / audit context:

- `docs/host/migration-plan.md` phase boundary and residual registry entries explain removal of old dedicated event names and mark them fixed by Slice 1.
- `docs/host/phase8.5-plan.md` retains historical evidence, non-goals, validation guard strings, and residual owner table from the approved plan.

## Documentation Decision And Result

- `docs/host/migration-plan.md`: updated because Slice 6 explicitly owns migration registry closeout.
- `docs/host/design.md`: updated only in small conflicting P7/P8 wording areas; §11 current ToolRuntime design was preserved.
- `dayu/host/README.md`: updated because Host README trigger applies and one ToolRuntime smoke paragraph still used old public-handle-flavored wording.
- `tests/README.md`: updated because tests README trigger applies and the type-check command needed to match current required validation.
- Root `README.md`: not triggered.

## Plan Gaps / Controller Questions

- Validation blocker: `pytest tests/contracts tests/engine -q` fails on existing Engine contract/export tests not recognizing Slice 4 `partial_tool_calls` / `PartialToolCallSummary`. Slice 6 plan does not assign ownership for this failure, and the allowed file list excludes the failing tests and production code. Controller needs to decide whether this is a missed Slice 4 fix/review gap, a new targeted fix handoff, or an accepted temporary validation exception.

## Residual Risks And Uncovered Areas

- current-slice fixed: stale migration gate/status, P8.5 residual owner registry, P7 inline raw payload design wording, P7 trace observer transaction wording, Host ToolRuntime smoke wording, tests README pyright command.
- existing issue: corrupt durable memory snapshot row root-cause / quarantine / operations / long-term overwrite policy remains tracked by GitHub issue #41.
- later phase / work unit: P9 Session / Run lifecycle admission and startup wiring; P15 hard-gate / required projection enforcement / watchdog / observer claim lease; P16 public/internal bundle freeze and cleanup items.
- controller decision required: failing `tests/contracts tests/engine` validation has no Slice 6 owner and blocks a clean PR gate unless fixed or explicitly accepted.

## Completion Signal

Slice 6 documentation and registry closeout edits are complete within the allowed file scope, and the implementation artifact is written.

## Stop Condition Status

- No document was updated to claim behavior unsupported by current code facts.
- A validation blocker was found outside Slice 6 allowed files: Engine contract/export tests fail against current code facts. Work stopped at reporting this blocker; no production or test code was changed.
- Did not commit, push, open PR, enter review/closeout, or start another slice.
