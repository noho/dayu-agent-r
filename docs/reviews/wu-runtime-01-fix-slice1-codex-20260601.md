# WU-RUNTIME-01 Slice 1 Fix Completion

## Accepted Findings Fixed

- Fixed same-instance nested context manager leak risk by adding a fail-fast guard at the start of `RuntimeFileLock.__enter__()` when `_context_token` is already set.
- Preserved the Slice 1 contraction boundary: `acquire()` still does not read or write `_context_token`, and the old `_active_token` acquire gate was not restored.
- Updated `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md` to clarify that `AGENTS.md` and `CLAUDE.md` had pre-existing user changes before this fix pass and were not modified, staged, or reverted by the implementation / fix agent.

## Changed Files

- `dayu/runtime/filelock.py`
- `tests/runtime/test_filelock.py`
- `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md`
- `docs/reviews/wu-runtime-01-fix-slice1-codex-20260601.md`

## Tests Added

- Added `test_nested_context_manager_on_same_instance_fails_fast_without_leak`.
- The test verifies same-instance nested context manager usage raises `RuntimeFileLockError` before the inner acquire path can overwrite `_context_token`.
- After the outer context exits, the test acquires the same lock path with an independent `RuntimeFileLock` instance using `timeout_seconds=0`, proving the outer token was released and no silent leak occurred.

## Validation

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
```

Result: pass, `23 passed in 0.41s`.

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
```

Result: pass, `12 passed in 0.07s`; `dayu.runtime.filelock` coverage `90%`.

```bash
source .venv/bin/activate && pyright
```

Result: pass, `0 errors, 0 warnings, 0 informations`.

## Stop Conditions

- No stop condition was hit.
- Slice 2 was not entered.
- No code review, commit, push, or PR action was performed.
- `AGENTS.md` and `CLAUDE.md` were not modified, staged, or reverted in this fix pass.
