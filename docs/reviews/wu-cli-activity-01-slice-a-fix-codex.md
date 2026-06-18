# WU-CLI-ACTIVITY-01 Slice A code review fix artifact

## Gate / scope

- Gate: fix after code review.
- Agent: AgentCodex.
- Scope: only accepted Slice A findings from `docs/reviews/code-review-wu-cli-activity-01-slice-a-adjudication-20260617-132855.md`.
- Non-goals kept: no Slice B-F work, no Engine / Service / CLI changes, no durable schema migration, no public API beyond accepted Slice A contract.

## Changed files

- `dayu/host/read_api.py`
- `tests/host/test_host_activity_event_projection.py`
- `docs/reviews/wu-cli-activity-01-slice-a-fix-codex.md`

## Findings fixed

- DS F-1: added focused projection tests for:
  - `TOOL_RESULT_ACCEPTED` completed and cancelled outcomes.
  - `TOOL_AWAITING` and `RUN_WAITING` activity projection.
  - `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, and `CONTEXT_COMPACTION_ATTEMPT_REJECTED`.
  - non-terminal lifecycle events `RUN_ACCEPTED` and `RUN_STARTED`.
  - display fallback paths for missing run, missing input event, corrupt tool set mapping, corrupt display-name mapping, and empty display name.
  - descriptor-read degradation for activity payload and bounded summary edge cases.
- DS F-2: replaced `_tool_display_name` local `EventLogStore()` construction with a module-private `_EVENT_LOG_STORE` instance. `EventLogStore` is used here as a stateless durable primitive method container, so this keeps dependency ownership explicit without changing public API or adding stateful runtime.
- DS F-3: removed redundant `_public_event_class_from_durable(row.event_class)` call from `_activity_from_row`; `_host_event_from_row` remains the single validation point for public event identity.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py -q`
  - Result: 82 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings.
- `git diff --check`
  - Result: clean.

## Docs decision

- No README update needed for this fix. The public contract/docs were already updated in the Slice A implementation; this pass only tightened tests and read_api private dependency shape.

## Residual risks

- Covered by later approved slice: Service / CLI activity consumption, dedupe, and rendering behavior remain Slice B-F work.
- Current slice accepted risk: `_EVENT_LOG_STORE` assumes `EventLogStore` remains a stateless primitive method container. If that durable primitive later gains constructor state, read_api should switch to explicit operation-level injection.

## Completion status

Accepted Slice A code review findings are fixed. No commit, push, PR, or re-review gate was performed.

## Validation Fix: Full pyright HostEvent fixture migration

### Scope

- Gate: validation fix after Slice A re-review.
- Trigger: full `python -m pyright dayu/ tests/ utils/` found five remaining `HostEvent(...)` constructor migrations outside the narrowed host test set.
- Non-goals kept: no production change, no Slice B-F work, no public API change, no commit/push/PR.

### Changed files

- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `docs/reviews/wu-cli-activity-01-slice-a-fix-codex.md`

### Fix applied

- Added `HostEventClass` imports to the five affected test modules.
- Updated terminal `HostEvent` fixtures to pass:
  - `event_class=HostEventClass.CANONICAL_FACT`
  - terminal `event_type` matching the fixture status: `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, or `RUN_LOST`
  - `activity=None`
- Added local status-to-`event_type` helpers where fixtures accept multiple terminal statuses.

### Validation

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.
- `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q`
  - Result: 67 passed, 3 third-party deprecation warnings from `edgar`.
- `git diff --check`
  - Result: clean.

### Residual risks

- No new residual risk identified for this validation fix. The remaining activity consumption/rendering work stays in later slices.
