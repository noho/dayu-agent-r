# WU-RUNTIME-01 Slice 1 Code Review — AgentDS

**Review target**: 当前工作区相对 HEAD 的 diff（Slice 1 实现）
**Implementation artifact**: `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md`
**Accepted plan**: `docs/host/wu-runtime-01-filelock-contraction-plan.md`
**Design source**: `docs/host/design.md`
**Review date**: 2026-06-01

---

## Conclusion: pass

**Blocking findings**: 0

---

## Findings

### Finding 1 — Nested `__enter__` silently overwrites `_context_token`, leaking outer token release (Medium)

**Evidence**:

`dayu/runtime/filelock.py:189`:
```python
def __enter__(self) -> RuntimeFileLockToken:
    token = self.acquire()
    self._context_token = token  # overwrites any previous value
    return token
```

When the same `RuntimeFileLock` instance enters context manager twice without an intervening `__exit__`:

1. First `__enter__`: `acquire()` succeeds (third-party `FileLock` is thread-reentrant). `_context_token = token1`. Returns `token1`.
2. Second `__enter__`: `acquire()` succeeds again (same thread, reentrant). `_context_token = token2`. `token1` is orphaned.
3. Inner `__exit__`: releases `token2`, clears `_context_token = None`.
4. Outer `__exit__`: `_context_token is None`, does nothing. `token1.release()` is **never called**.

Result: third-party `FileLock` was acquired twice but released once. The outer token's release path is silently dropped.

**Risk**: Resource leak in the nested-context-on-same-instance misuse scenario. The third-party lock's internal reentrant counter becomes unbalanced, potentially leaving the lock file held after all expected releases.

**Why not blocking**:

The plan (Section 5, Implementation Decisions; Section 11, Risks) explicitly declares:
- "wrapper 不承诺 reentrant lock 语义是设计意图，不是待补能力"
- "调用方不得依赖同一 RuntimeFileLock 实例重复 acquire 的成功、失败、计数或 token 复用行为"
- "同一 RuntimeFileLock 实例的 reentrant / nested acquire 具体行为不承诺；这是设计真源非目标，不作为 bug"

The `RuntimeFileLock` class docstring (line 120-121) states: "同一个 RuntimeFileLock 实例不承诺 reentrant 语义；调用方应让第三方 FileLock 持有 acquire / release 生命周期真源。"

The old `_active_token` gate prevented this scenario via fail-fast; removing that gate was an explicit goal of Slice 1. Adding a guard back would partially undo the contraction.

**Design observation (not a required fix)**:

A minimal `if self._context_token is not None: raise RuntimeFileLockError(...)` guard in `__enter__` would fail-fast for nested context without reintroducing lifecycle truth tracking or affecting `acquire()` independence. It would not constitute "过度设计" — it's a single slot check akin to "you have an open context frame, close it first." The overhead is one conditional, no additional slots, no public state exposure. However, the plan deliberately chose not to include this, and the current behavior is within accepted residual risk.

**Required fix**: None. Accepted residual risk per plan.

---

### Finding 2 — `test_context_manager_release_failure_clears_context_token` directly accesses private `_context_token` (Low)

**Evidence**:

`tests/runtime/test_filelock.py:151-163`:
```python
lock = file_lock(lock_path)
lock._context_token = RuntimeFileLockToken(
    lock_path=lock_path,
    third_party_lock=cast(FileLock, third_party_lock),
)

with pytest.raises(RuntimeFileLockError, match="释放 runtime file lock 失败"):
    lock.__exit__(None, None, None)

assert lock._context_token is None
```

The test bypasses `__enter__` to inject a failing token into `_context_token`, then directly reads `_context_token` to verify cleanup. This is white-box testing of a private slot.

**Risk**: Low. The test verifies a critical invariant — that `__exit__` cleans up state even when `release()` fails. The alternative (mocking the full `__enter__` → `acquire` → third-party-acquire chain) would be more complex and fragile.

**Mitigation**: `test_public_api_shape_and_non_goals_are_explicit` (line 252-274) already verifies `_context_token` is NOT in `RuntimeFileLockToken` dataclass fields, NOT in `__all__`, and NOT a public export. The private access is contained to this single white-box test.

**Required fix**: None. Acceptable white-box test for a narrow invariant. Does not constitute "为过测试而暴露私有状态" — the private state is not exposed in the public API; the test reaches into internals to verify an internal invariant.

---

### Finding 3 — Implementation artifact inaccurately claims AGENTS.md/CLAUDE.md were untouched (Low)

**Evidence**:

Implementation artifact line 63: "`AGENTS.md` and `CLAUDE.md` were left untouched."

`git diff HEAD -- AGENTS.md CLAUDE.md` shows both files modified — a new line `- 不做过度设计，以最小化满足需求为标准。` was added to both at line 26.

**Risk**: Documentation accuracy only. The actual change is adding a project principle consistent with the contraction's design philosophy; it does not affect runtime behavior.

**Required fix**: Update the implementation artifact's Stop Conditions section to accurately reflect the AGENTS.md/CLAUDE.md modification.

---

## Verification Results (independently reproduced)

| Command | Result |
|---|---|
| `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 22 passed |
| `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` | 11 passed, 90% coverage |
| `pyright` | 0 errors, 0 warnings, 0 informations |

Runtime dataclass fields confirmation:
```python
[field.name for field in fields(RuntimeFileLockToken)]
# → ['lock_path', '_release_completed', '_third_party_lock']
```
No `released` field. Public fields (no `_` prefix): `{'lock_path'}` only.

---

## Checklist

### Slice 1 boundary
- [x] No Host production source modified (audit.py, tool_trace.py untouched)
- [x] No Slice 2 work performed (no test_audit_sink.py or test_tool_trace_projection.py changes)
- [x] No stale lock / break lock / async wrapper / durable lease additions
- [x] No compat property, wrapper, re-export, or facade for removed `released`

### RuntimeFileLockToken.released removal
- [x] `released: bool` removed from dataclass fields
- [x] No compat `@property` or `__getattr__` bridge
- [x] Private `_release_completed: bool` added as internal idempotent guard
- [x] `_release_completed` set to `True` ONLY after third-party `release()` succeeds (line 105)
- [x] Release failure does NOT set `_release_completed`; retry calls third-party release again (line 103-104 → 101-104)
- [x] Test `test_release_failure_does_not_complete_and_allows_retry` verifies `release_calls == 2` on double failure

### RuntimeFileLock._active_token removal
- [x] `_active_token` removed from `__slots__` and annotations
- [x] `acquire()` no longer checks `_active_token` or any token state gate (line 148-180)
- [x] `acquire()` does not read or write `_context_token`
- [x] `_context_token` added as private slot, only for context manager cleanup
- [x] `__enter__()` stores acquired token in `_context_token` (line 190)
- [x] `__exit__()` reads `_context_token`, calls `release()`, clears in `finally` (lines 208-213)
- [x] `_context_token` not in `__all__`, not in `RuntimeFileLockToken` fields, not in public API

### Preserved behavior
- [x] Parent directory handling (`_prepare_parent_directory`) unchanged
- [x] Timeout wrapping (`_effective_timeout_seconds`) unchanged, `Timeout` → `RuntimeFileLockTimeoutError`
- [x] Marker restore (`_ensure_lock_file_marker_exists`) still best-effort after successful release
- [x] Import boundary — `from filelock import FileLock, Timeout` only in `dayu/runtime/filelock.py`
- [x] `test_import_boundary.py` unmodified, all 11 tests pass
- [x] `__all__` still exports `RuntimeFileLockToken`

### Tests
- [x] All `token.released` assertions removed
- [x] All `lock._active_token` reads/writes removed
- [x] `_FailingReleaseToken` helper class removed
- [x] `test_nested_context_manager_on_same_instance_fails_fast` removed
- [x] `test_manual_acquire_inside_context_fails_fast` removed
- [x] `test_context_enter_after_manual_acquire_fails_fast` removed
- [x] Context manager tests now verify via second independent lock acquire (not `released` field)
- [x] `test_release_is_idempotent` no longer asserts `token.released`
- [x] `test_release_success_before_marker_failure_remains_idempotent` renamed, no `released` assertion
- [x] `test_release_failure_does_not_complete_and_allows_retry` replaces old "prevent retry" test
- [x] `test_public_api_shape_and_non_goals_are_explicit` extended with structural field/slot checks
- [x] `test_manual_release_allows_same_instance_reacquire` no longer asserts `released`

### docs/host/design.md
- [x] `RuntimeFileLockToken.released: bool` removed from public API shape (line 257-259)
- [x] Added: "`RuntimeFileLockToken` 只暴露 `lock_path` 与 `release()`，不暴露 release 状态" (line 291)
- [x] Added: release 幂等和 release 失败 retry 语义 (line 292)
- [x] No over-documentation — does not describe `_release_completed`, `_context_token`, or internal state structure
- [x] All pre-existing design constraints preserved

### Architecture constraints
- [x] `dayu.runtime.filelock` does not import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`
- [x] Third-party `filelock` import confined to `dayu/runtime/filelock.py` (confirmed by `test_third_party_filelock_import_is_confined_to_runtime_filelock`)
- [x] No `Any`, `object`, untyped parameters, untyped return values introduced
- [x] No `hasattr` / `getattr` usage
- [x] No lazy imports
- [x] All functions have Chinese docstrings with params/returns/raises

---

## Overdesign Check

| Check | Result |
|---|---|
| `_release_completed` vs simpler guard (e.g., a bare `bool` flag without dataclass field) | `_release_completed` is a single `bool` slot — minimal and appropriate for the idempotent guard role. No overdesign. |
| `_context_token` as a full `RuntimeFileLockToken | None` vs a lighter reference | The token object must be held to call `.release()` in `__exit__`. A lighter reference would still need the token object. No overdesign. |
| `__exit__` try/finally structure | Minimal — one `try` for release, one `finally` for cleanup. No overdesign. |
| Public shape test using `dataclasses.fields` and `__slots__` | Uses structured introspection (not string matching or `hasattr`), per plan instruction. Appropriate. |
| Design doc update scope | Two paragraphs added, one line removed. Synchronizes public API shape and release semantics without describing internals. Appropriate. |

No overdesign detected.

---

## Residual Risks

1. **Nested `__enter__` on same instance** (Accepted): `_context_token` overwrite silently drops outer token release. Declared non-goal per plan; documented in class docstring.
2. **Lock marker restore best-effort** (Accepted): Failed marker restore after successful release is debug-logged only. Not Host truth.
3. **Slice 2 regression coverage** (Deferred): Host audit/tool trace lock-path regression tests not yet executed. No evidence of breakage — Host callers use `with file_lock(...)` pattern that remains API-compatible.
4. **AGENTS.md/CLAUDE.md modification** (Observation): Both files modified to add "不做过度设计，以最小化满足需求为标准。" — not reported in implementation artifact. Change is aligned with contraction philosophy; no code impact.

---

## Review Summary

Slice 1 implementation faithfully executes the plan:
- `RuntimeFileLockToken.released` is fully removed with no compatibility shim.
- `RuntimeFileLock._active_token` and its acquire gate are fully removed.
- `_release_completed` correctly guards only after successful third-party release; failed release allows retry.
- `_context_token` correctly scoped to context manager cleanup only.
- Parent directory, timeout wrapping, marker restore, import boundary all preserved.
- Tests correctly migrated from old implementation-detail assertions to behavioral contract assertions.
- `docs/host/design.md` correctly synchronized without over-documentation.
- No blocking findings. One medium finding (silent nested-context overwrite) is explicitly accepted residual risk per plan.
