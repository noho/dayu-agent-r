# A1 Fix Artifact: Engine OpenAI Runner Cancel Cleanup Race

- **Date**: 2026-05-14
- **Gate**: full repository review fix work unit A1
- **Source artifact**: `docs/reviews/repo-review-controller-adjudication-20260514.md`
- **Accepted finding**: A1 — Engine runner response cleanup on cancellation
- **Scope**: only `dayu/engine/runners/openai/runner.py` and focused tests under `tests/engine/runners/openai/`
- **Non-goals**: Host, runtime, contracts, config, docs beyond this artifact, A4 parser/provider robustness, broad runner refactors

## Motivation Check

A1 is a real resource ownership defect. `AsyncOpenAIRunner._do_attempt()` previously delegated `response_ctx.__aenter__()` to the generic `await_or_cancel` helper. That helper intentionally gives cancellation priority when the target awaitable and cancellation watcher complete together. In the response acquisition path, that means a response can already have been produced by `__aenter__()` while the runner receives `_RunnerInterrupted` before the local `response` variable reaches the later `finally: response.release()` block.

The correct fix is not to weaken cancellation priority. The response acquisition path needs explicit ownership of the enter task so it can release a response only if acquisition actually produced one.

## Implementation

Changed `dayu/engine/runners/openai/runner.py`:

- Added `_enter_response_context_or_cancel()` for the `response_ctx.__aenter__()` boundary.
- The helper creates and owns the response-enter task, races it with the cancellation token through `dayu.runtime.cancellation.wait_for_or_cancel`, and preserves runner cancellation semantics by raising `_RunnerInterrupted` when cancellation wins.
- Added `_release_response_task_if_acquired()` to cancel the enter task and release the returned response only when the task has actually produced one.
- Left the existing body-processing `try/finally: response.release()` intact for normal response ownership after acquisition succeeds.

Added `tests/engine/runners/openai/test_response_cleanup_race.py`:

- `test_cancel_after_response_acquired_releases_once` simulates cancellation winning after the fake response has been acquired, before body processing. It asserts no events are emitted, `release()` is called exactly once, and `read()` is not called.
- `test_cancel_before_response_acquired_does_not_release` simulates cancellation winning before fake response acquisition completes. It asserts no events are emitted and no response exists to release.

## Validation

Commands run from activated virtualenv:

```text
source .venv/bin/activate && pytest tests/engine/runners/openai/test_response_cleanup_race.py tests/engine/runners/openai/test_cancellation_boundaries.py
```

Result: `5 passed`.

```text
source .venv/bin/activate && pytest tests/engine/runners/openai
```

Result: `183 passed`.

```text
source .venv/bin/activate && pyright dayu/engine/runners/openai/runner.py tests/engine/runners/openai/test_response_cleanup_race.py
```

Result: `0 errors, 0 warnings, 0 informations`.

```text
source .venv/bin/activate && pyright dayu/engine/runners/openai tests/engine/runners/openai
```

Result: `0 errors, 0 warnings, 0 informations`.

## README Decision

Checked `dayu/engine/README.md` and `tests/README.md`. No README change was needed:

- The production change is internal response cleanup at an existing runner cancellation boundary.
- The test change adds coverage within the existing `tests/engine/runners/openai/` cancellation/resource category and does not introduce a new test layer or new public workflow.

## Residual Risk

No A1 residual risk remains known after the targeted regression coverage. The implementation intentionally does not address A4 or any other accepted finding from the controller adjudication.

## Stop Status

Implementation, tests, pyright validation, README decision, and this required artifact are complete. Changes are left unstaged; no commit, push, PR, or other gate action was performed.
