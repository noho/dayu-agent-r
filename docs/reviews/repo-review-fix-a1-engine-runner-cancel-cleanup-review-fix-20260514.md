# A1 Review Fix Artifact: Engine Runner CancelledError Branch Coverage

- **Date**: 2026-05-14
- **Gate**: full repository review fix work unit A1 follow-up
- **Source fix artifact**: `docs/reviews/repo-review-fix-a1-engine-runner-cancel-cleanup-20260514.md`
- **Accepted review artifact**: `docs/reviews/repo-review-code-review-a1-engine-runner-cancel-cleanup-mimo-20260514.md`
- **Accepted finding**: MiMo low finding 1 — `_enter_response_context_or_cancel()` outer `asyncio.CancelledError` branch lacked direct test coverage
- **Scope**: `tests/engine/runners/openai/test_response_cleanup_race.py` only, plus this artifact
- **Non-goals**: no production change, no Host/runtime/contracts/config change, no A4 or unrelated finding work

## Motivation Check

The finding is valid and low severity. The original A1 tests covered the `_runtime_wait_for_or_cancel` `WaitCancelled` outcome branches, including response-acquired and response-not-acquired cases. They did not directly exercise the separate `except asyncio.CancelledError` branch used when the outer runner task is cancelled while `_enter_response_context_or_cancel()` is awaiting the real runtime race helper.

This is worth covering because that branch must both preserve `Task.cancel()` semantics and release an already acquired response exactly once.

## Implementation

Updated `tests/engine/runners/openai/test_response_cleanup_race.py`:

- Added `_CancelOuterAfterAcquireContext`, a focused fake response context whose `__aenter__()` creates the tracked response, schedules cancellation of the outer runner task with `loop.call_soon(...)`, then returns the response.
- Added `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once`.
- The new test calls `AsyncOpenAIRunner._enter_response_context_or_cancel()` directly and does not monkeypatch `_runtime_wait_for_or_cancel`, so it exercises the real runtime helper path.
- The assertion proves `asyncio.CancelledError` propagates and the already acquired fake response is released exactly once, without body reads.

No production testability change was needed.

## Validation

Commands run from activated virtualenv:

```text
source .venv/bin/activate && pytest tests/engine/runners/openai/test_response_cleanup_race.py -q
```

Result: `3 passed`.

```text
source .venv/bin/activate && pytest tests/engine/runners/openai
```

Result: `184 passed`.

```text
source .venv/bin/activate && pyright tests/engine/runners/openai/test_response_cleanup_race.py
```

Result: `0 errors, 0 warnings, 0 informations`.

```text
source .venv/bin/activate && pyright dayu/engine/runners/openai tests/engine/runners/openai
```

Result: `0 errors, 0 warnings, 0 informations`.

## Residual Risk

No known residual risk remains for the accepted MiMo low finding. This follow-up intentionally does not address A4 or any unrelated review item.

## Stop Status

Review-fix implementation, validation, and artifact are complete. Changes are left unstaged; no commit, push, PR, or other gate action was performed.
