# WU-CLI-ACTIVITY-01 Slice B review fix artifact

## Gate / scope

- Gate: fix after Slice B code review.
- Agent: AgentCodex.
- Adjudication: `docs/reviews/code-review-wu-cli-activity-01-slice-b-adjudication-20260617-135835.md`.
- Scope: accepted findings DS F-1 and DS F-3 only.
- Non-goals kept: no `cancel_entrypoint_run_and_wait(...)` activity callback, no CLI renderer/composer, no prompt/interactive key handling, no Slice C-F work.

## Findings fixed

- DS F-1: `_terminal_result_from_live_event(...)` no longer writes terminal event id or terminal dedupe key state for non-terminal Host events. Non-terminal progress/activity can no longer suppress a later terminal event with the same public `dedupe_key`.
- DS F-3: Added a focused test proving `on_activity` callback exceptions propagate to the caller.

## Changed files

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`
- `docs/reviews/wu-cli-activity-01-slice-b-fix-codex.md`

Pre-existing unrelated local change observed and left untouched:

- `docs/host/issues-implementation-control.md`

## Tests / validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q`
  - Result: 32 passed, 3 existing third-party edgar deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/service tests/service`
  - Result: 0 errors, 0 warnings, 0 informations. Pyright reported a newer version is available.
- `git diff --check`
  - Result: clean.

## Residual risks

- `cancel_entrypoint_run_and_wait(...)` still has no activity callback by adjudication; this remains deferred to Slice E.
- CLI still does not render activity; renderer/composer/key handling remain later slices.
