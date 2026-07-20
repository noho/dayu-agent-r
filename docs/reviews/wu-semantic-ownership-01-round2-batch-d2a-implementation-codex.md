# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2a Implementation - AgentCodex

## Scope

本轮只处理 D2a：Host public / durable construction 与 run-start / terminal contract ownership。

未处理 D2b：tool outcome、compaction、memory、Engine fallback 或其它非本轮 findings。

## Changed Files

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/tooling.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/run_input.py`
- `dayu/host/open_host.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/host/README.md`
- Focused tests under `tests/host/` and `tests/service/`

## Semantic Owner Decisions

- Run terminal predicate owner moved to Host public contract: `TERMINAL_RUN_STATUSES` and `is_terminal_run_status(status)` are exported from `dayu.host.api` / package root. Service now consumes that helper instead of copying terminal status members.
- `RunSnapshot` now enforces terminal invariant at construction: terminal status requires a `TerminalResultSummary`; non-terminal status rejects one; summary status must match snapshot status. `TerminalResultSummary` itself rejects non-terminal statuses.
- Durable state reuses the Host public terminal helper/set for terminal projection. Durable summary projection remains the durable read projection point, but no longer owns a separate terminal predicate.
- `RUN_STARTED.start_reason` now has a required typed payload decoder in `dayu.host.durable.state` that reuses `deserialize_run_start_reason`. EventLog recovery counting and RunInput manifest/resume logic consume the typed decoder and fail closed for missing or unknown reasons.
- Host construction options now expose runtime-resolvable Protocol contracts for wait registries and wait poller policy. `HostToolingOptions` and `OpenHostOptions` fail fast on invalid registry/policy inputs; `open_host` no longer repeats downstream type补救 and only keeps cross-field enabled-poller configuration validation.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_public_open_host_options.py tests/host/test_tooling_options.py tests/host/test_state_schema.py tests/host/test_event_log_store.py tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_wait_callback_endpoint.py -q`
  - Result: `368 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass.

## Follow-up Audit Fix

- Controller audit found normal-path tests still hand-writing `RUN_STARTED.start_reason` as bare `"resume"` / `"recovery"` strings.
- Updated positive fixtures in `tests/host/test_event_log_store.py` and `tests/host/test_run_input_builder.py` to use `RunStartReason` plus `serialize_run_start_reason(...)`; bare `"unknown"` remains only in invalid / corrupt payload negative tests.
- Updated `count_recovery_dispatches_for_run` docstring to describe typed `RunStartReason.RECOVERY` comparison instead of raw string comparison.
- Follow-up validation:
  - `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_run_input_builder.py -q`
    - Result: `124 passed`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
    - Result: `0 errors, 0 warnings, 0 informations`
  - `git diff --check`
    - Result: pass.

## Second Follow-up Audit Fix

- Controller scan found one more positive `RUN_STARTED.start_reason` fixture in `tests/host/test_recovery_scan.py`.
- Updated that recovery-start fixture to use `RunStartReason.RECOVERY` plus `serialize_run_start_reason(...)`.
- Grep after the fix shows no positive `start_reason` literals remain in the checked D2a test files; remaining bare `"unknown"` values are corrupt-payload negative tests, and remaining bare `"resume"` / `"recovery"` mentions are documentation text.
- Second follow-up validation:
  - `source .venv/bin/activate && pytest tests/host/test_recovery_scan.py -q`
    - Result: `18 passed`

## Third Follow-up Audit Fix

- Controller scan found `tests/host/test_state_schema.py` still defined a local `_TERMINAL_RUN_STATUSES` tuple duplicating the Host public terminal owner.
- Replaced that local positive parameter source with an ordered tuple derived from `dayu.host.api.TERMINAL_RUN_STATUSES`.
- Did not touch `test_purge_session.py` raw SQLite string fixtures.
- Third follow-up validation:
  - `source .venv/bin/activate && pytest tests/host/test_state_schema.py -q`
    - Result: `57 passed`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
    - Result: `0 errors, 0 warnings, 0 informations`
  - `git diff --check`
    - Result: pass.

## Code Review Fix D2a-F1

- MiMo and DS accepted finding D2a-F1: CLI fake Host helpers built terminal `RunSnapshot` values with `terminal_result_summary=None`.
- Updated `_run_snapshot` in `tests/cli/test_prompt_command.py` and `tests/cli/test_interactive_command.py` to derive terminal summaries through Host public `is_terminal_run_status(status)` and construct `TerminalResultSummary(status=status, summary_ref=None, summary_digest=None)`.
- Grep over `tests/cli` found no other `RunSnapshot` helper with `terminal_result_summary=None`.
- Fix validation:
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
    - Result: `90 passed, 3 warnings`
    - Warnings: existing `edgar` deprecation warnings.
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
    - Result: `0 errors, 0 warnings, 0 informations`
  - `git diff --check`
    - Result: pass.

## README Decision

- Updated `dayu/host/README.md` because Host public `RunSnapshot` terminal contract changed and belongs to Host developer-facing public contract documentation.
- `tests/README.md` required no update because test hierarchy, execution rules, and maintenance policy did not change.

## Residual Risks

None identified inside D2a scope.

## Stop Status

COMPLETE. No commit, push, PR, D2b work, or unrelated file changes performed.
