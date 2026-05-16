# PR 58 Fix Re-Review — AgentDS — 2026-05-16

## Scope

- **Mode**: Fix re-review (not full PR review)
- **PR**: [#58](https://github.com/noho/dayu-agent-r/pull/58)
- **Branch**: `feat/host-phase8-projection-core-event-stream`
- **Accepted finding**: PR58-F1 — `RuntimeFileLock.__exit__` release failure clears active token too early
- **Controller adjudication**: `docs/reviews/pr-58-review-controller-adjudication-20260516.md`
- **Fix artifact**: `docs/reviews/pr-58-fix-codex-20260516.md`
- **Original review**: `docs/reviews/pr-58-review-ds-20260516.md`
- **Reviewed files**:
  - `dayu/runtime/filelock.py`
  - `tests/runtime/test_filelock.py`

## Controller Fix Requirements (recap)

1. `__exit__` 必须先调用 `token.release()`。
2. 只有 release 成功后才能清空 `_active_token`。
3. 新增测试模拟 release 失败，断言 `_active_token` 保留且同实例再次 `acquire(timeout_seconds=0)` fail fast。

## Fix Verification

### `__exit__` 执行顺序（filelock.py:198-201）

```python
token = self._active_token
if token is not None:
    token.release()
    self._active_token = None
```

- `token.release()` (line 200) 在 `self._active_token = None` (line 201) 之前执行：**满足要求 1**。
- 若 `release()` 抛出异常，异常直接从 `__exit__` 传播，`self._active_token = None` 不执行：**满足要求 2**。
- `if token is not None:` 守卫保证 `_active_token` 为 `None` 时不调用 `release()`：该分支正确。

### 测试覆盖（test_filelock.py:130-149）

`test_context_manager_release_failure_keeps_active_token_and_reacquire_fails_fast`:

1. 用 `_FailingReleaseToken`（`release()` 始终抛 `RuntimeFileLockError`）注入为 `lock._active_token`。
2. 调用 `lock.__exit__(None, None, None)`，断言抛出 `RuntimeFileLockError("release failed")` — release 失败正确传播。
3. 断言 `lock._active_token is failing_token` — active token 在 release 失败后保留：**满足要求 3 前半**。
4. 调用 `lock.acquire(timeout_seconds=0)`，断言抛出 `RuntimeFileLockError("already active")` — active-token guard 生效，阻止重复 acquire：**满足要求 3 后半**。

### `_FailingReleaseToken` 替身正确性

`_FailingReleaseToken` 继承 `RuntimeFileLockToken`，直接重写 `release()` 抛异常，不调用 `super().release()`，不设置 `self.released = True`。这与真实 `RuntimeFileLockToken.release()` 中 `_third_party_lock.release()` 抛异常时的行为一致——`released` 保持 `False`，token 处于未释放状态。替身准确建模了失败语义。

### 回归检查

正常路径测试不受影响：

- `test_context_manager_releases_on_normal_path` — 正常退出，token.released=True ✓
- `test_context_manager_releases_on_exception_path` — with 块内抛异常，token 仍正确 release ✓
- `test_nested_context_manager_on_same_instance_fails_fast` — 嵌套 context 拒绝 ✓
- `test_manual_acquire_inside_context_fails_fast` — context 内手动 acquire 拒绝 ✓
- `test_context_enter_after_manual_acquire_fails_fast` — 手动 acquire 后 context enter 拒绝 ✓
- `test_manual_release_allows_same_instance_reacquire` — 手动 release 后可再 acquire ✓
- `test_release_is_idempotent` — 幂等 release ✓
- `test_release_marks_released_after_underlying_release_before_marker_failure` — marker 恢复失败不影响 released 标记 ✓
- `test_non_blocking_timeout_is_wrapped` — timeout 包装 ✓
- `test_public_api_shape_and_non_goals_are_explicit` — API shape ✓

所有已有测试路径与 fix 无冲突。

### 裁决边界检查

- 只修改了 `dayu/runtime/filelock.py` 和 `tests/runtime/test_filelock.py`：**符合允许修改范围**。
- 未触及时 Host projection/read model/event stream、Engine/Fins/Service/UI、schema/DDL：**符合禁止修改范围**。
- 未 stage/commit/push：**符合要求**。

## Findings

未发现实质性问题。Fix 精确满足 controller 裁决的三项要求，无回归。

## Open Questions

无。

## Residual Risk

- `__exit__` 中若 context-manager 内已有异常在传播（`exc_type is not None`），同时 `release()` 也失败，release 异常会替换原始异常。Controller 裁决未要求此场景做 exception chaining，且 token 保留行为正确——后续 acquire 会 fail fast 而非静默死锁。此场景为已有行为，非 fix 引入。
- `_FailingReleaseToken` 直接重写 `release()` 而非 mock 底层 `_third_party_lock.release()`，测试的是 token 层 release 失败而非底层 FileLock.release() 失败。但 token.release() 是 `__exit__` 调用的真实入口，覆盖层次正确。

## Conclusion

**PASS** — PR58-F1 fix 完整、符合裁决边界、无回归。`__exit__` 执行顺序正确，release 失败时 active token 保留，release 成功后清空，测试覆盖有效。
