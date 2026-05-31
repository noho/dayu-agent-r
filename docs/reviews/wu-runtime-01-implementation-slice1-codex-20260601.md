# WU-RUNTIME-01 Implementation Slice 1 Completion

## Changed Files

- `dayu/runtime/filelock.py`
- `tests/runtime/test_filelock.py`
- `docs/host/design.md`

Checked but not modified:

- `tests/README.md`
- `dayu/README.md`

## Implemented Plan Items

- Removed public `RuntimeFileLockToken.released`.
- Kept `RuntimeFileLockToken` with public contract limited to `lock_path` and `release()`.
- Added private `_release_completed` guard on `RuntimeFileLockToken`; it is set only after third-party `release()` succeeds.
- Preserved retry behavior after third-party release failure: failed release does not mark completion, and a later `token.release()` calls the third-party release again.
- Removed `RuntimeFileLock._active_token` and the same-instance acquire gate based on token state.
- Added private `_context_token` only for context manager cleanup.
- Updated `__enter__()` to store the acquired token in `_context_token`.
- Updated `__exit__()` to release `_context_token` and clear it in `finally`, including release failure paths.
- Preserved parent directory handling, timeout wrapping, runtime error wrapping, and best-effort lock marker restore behavior.
- Updated runtime tests to remove old `released` / `_active_token` assertions and cover the contracted public shape plus release-failure retry behavior.
- Updated `docs/host/design.md` to remove `RuntimeFileLockToken.released` from the public API shape and document that token release state is not exposed.

## Validation Command / Result

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
```

Result: pass, `22 passed in 0.40s`.

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
```

Result: pass, `11 passed in 0.07s`; `dayu.runtime.filelock` coverage `90%`.

```bash
source .venv/bin/activate && pyright
```

Result: pass, `0 errors, 0 warnings, 0 informations`.

## README Decision

- `tests/README.md`: not updated. Existing filelock bullet describes parent directory behavior, structured errors, context manager release, release idempotency, non-blocking timeout wrapping, and import boundary. It does not mention `released` or equivalent old public token-state semantics.
- `dayu/README.md`: not updated. Existing runtime summary says filelock is a third-party `FileLock` synchronous wrapper for ordinary file mutual exclusion and does not replace SQLite transactions, EventLog ordering, or Host state machines. That remains consistent with Slice 1.

## Residual Risks

- Same-instance manual acquire behavior remains intentionally unspecified and delegated to the third-party `FileLock` lifecycle truth. Same-instance nested context manager now fails fast to avoid `_context_token` overwrite.
- Lock marker restore remains best-effort after successful third-party release and is not Host truth.
- Slice 2 Host audit / tool trace regression coverage was not executed or modified in this slice by instruction.

## Stop Conditions

- No stop condition was hit.
- No Host production source, lane code, audit/tool trace behavior, stale lock handling, async wrapper, durable lease, or recovery behavior was modified.
- `AGENTS.md` and `CLAUDE.md` had pre-existing user changes before this fix pass; the implementation / fix agent did not modify, stage, or revert those files.
