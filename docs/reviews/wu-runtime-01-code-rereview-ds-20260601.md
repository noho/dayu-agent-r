# WU-RUNTIME-01 Slice 1 Code Re-Review — AgentDS

**Original review**: `docs/reviews/wu-runtime-01-code-review-ds-20260601.md`
**Fix artifact**: `docs/reviews/wu-runtime-01-fix-slice1-codex-20260601.md`
**Implementation artifact**: `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md`
**Re-review date**: 2026-06-01

---

## Conclusion: pass

**Findings status**: 2 closed, 1 open (accepted)，0 new

---

## Finding Status

### Finding 1 (原 Medium) — Nested `__enter__` silently overwrites `_context_token`

**Status: closed**

Evidence of fix — `dayu/runtime/filelock.py:189-190`:
```python
if self._context_token is not None:
    raise RuntimeFileLockError("runtime file lock context manager 不支持嵌套")
```

Validation:
- Guard is at the top of `__enter__()`, **before** `acquire()` — prevents both the `_context_token` overwrite AND an unnecessary third-party acquire.
- Guard reads only `_context_token` (private slot), one conditional, one raise. No new slots, no state machine, no lifecycle truth tracking. **Minimal**.
- `acquire()` (lines 148-180) does **not** read or write `_context_token`. The guard is confined to `__enter__()` — `acquire()` remains independent of the context manager lifecycle.
- New test `test_nested_context_manager_on_same_instance_fails_fast_without_leak` (test_filelock.py:146-163):
  - Nested `with lock:` raises `RuntimeFileLockError` with message "不支持嵌套".
  - After outer context exits, an independent `file_lock(lock_path).acquire(timeout_seconds=0)` succeeds — proves no silent leak.
  - Does NOT test manual-acquire-inside-context or context-after-manual-acquire — old gate tests remain deleted. Correct per fix artifact claim.
- `__enter__` docstring updated: `:raises RuntimeFileLockError: context manager 嵌套使用或获取锁失败时抛出。` — accurately reflects the new behavior.
- This is NOT a restoration of the old `_active_token` acquire gate:
  - Old gate: in `acquire()`, checked `_active_token is not None and not _active_token.released`, blocked manual acquire too.
  - New guard: in `__enter__()` only, checks `_context_token is not None`, blocks only nested context manager misuse.
  - Manual `acquire()` → manual `release()` → `acquire()` still works (confirmed by `test_manual_release_allows_same_instance_reacquire`).

**No overdesign**: single `if` check, no additional slots, no `acquire()` coupling, no lifecycle truth.

---

### Finding 2 (原 Low) — `test_context_manager_release_failure_clears_context_token` accesses private `_context_token`

**Status: open (accepted)**

The test at lines 166-183 still directly sets `lock._context_token` and asserts `lock._context_token is None`. This was classified as acceptable white-box testing in the original review, and the fix agent did not need to address it. The private access remains scoped to this single test; `test_public_api_shape_and_non_goals_are_explicit` still confirms `_context_token` is not in public exports or `RuntimeFileLockToken` fields. No new concern.

---

### Finding 3 (原 Low) — Implementation artifact inaccurately claims AGENTS.md/CLAUDE.md untouched

**Status: closed**

Evidence of fix — `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md` line 63:
> `AGENTS.md` and `CLAUDE.md` had pre-existing user changes before this fix pass; the implementation / fix agent did not modify, stage, or revert those files.

Consistent with fix artifact line 47:
> `AGENTS.md` and `CLAUDE.md` were not modified, staged, or reverted in this fix pass.

`git status` still shows AGENTS.md and CLAUDE.md as modified (pre-existing user changes, not from implementation/fix agent). Artifact now accurately reflects reality.

---

## New Findings

None.

---

## Verification Results (independently reproduced)

| Command | Result |
|---|---|
| `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed (was 22, +1 new test) |
| `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` | 12 passed, 90% coverage (+2 stmts from guard, coverage unchanged) |
| `pyright` | 0 errors, 0 warnings, 0 informations |

Uncovered lines unchanged from original review (145-146, 173-174, 275, 283-284, 296, 309-310, 322) — all edge cases or hard-to-trigger error paths. The new guard lines (189-190) are fully covered by the new test.

---

## Slice Boundary Re-Check

- [x] No Host production source modified
- [x] No Slice 2 work performed
- [x] `_active_token` acquire gate NOT restored — `acquire()` still has no gate
- [x] `acquire()` does not read/write `_context_token`
- [x] New test only covers nested context fail-fast; no old gate tests restored
- [x] `_context_token` remains private; not in `__all__`, not in `RuntimeFileLockToken` fields
- [x] No compat property, wrapper, or facade added
- [x] Design doc (`docs/host/design.md`) not further modified
