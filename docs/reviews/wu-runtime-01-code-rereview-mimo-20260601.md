# WU-RUNTIME-01 Slice 1 Code Re-Review

Reviewer: AgentMiMo
Date: 2026-06-01
Original review: `docs/reviews/wu-runtime-01-code-review-mimo-20260601.md`
Fix artifact: `docs/reviews/wu-runtime-01-fix-slice1-codex-20260601.md`
Implementation artifact: `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md`

## Conclusion

**pass**

Blocking findings: 0
New findings: 0

## Finding Status

| ID | Description | Status |
|----|-------------|--------|
| F-1 | 嵌套 context `_context_token` 覆盖导致静默 lock leak | **closed** |
| F-2 | `AGENTS.md` / `CLAUDE.md` 变更超出 Slice 1 scope | **closed** |

### F-1 closed — 嵌套 context fail-fast guard

`filelock.py:189-190`:

```python
if self._context_token is not None:
    raise RuntimeFileLockError("runtime file lock context manager 不支持嵌套")
```

确认：

- Guard 是单行 if-check，在 `acquire()` 之前执行，不引入新 state 结构。
- 未恢复旧 `_active_token` acquire gate；`acquire()`（L148-180）不读写 `_context_token`。
- `__exit__` 的 `finally` 块（L214-215）仍清空 `_context_token`，release 失败路径不受影响。
- `__enter__` docstring 已更新为包含"嵌套使用"异常说明。

新测试 `test_nested_context_manager_on_same_instance_fails_fast_without_leak`（L146-163）确认：

- 嵌套 `with lock` 抛 `RuntimeFileLockError` 且 match `"不支持嵌套"`。
- 外层 context 正常退出。
- 退出后独立 `file_lock(lock_path).acquire(timeout_seconds=0)` 成功，证明外层 token 已 release、无 silent leak。
- 未恢复 `test_manual_acquire_inside_context_fails_fast`、`test_context_enter_after_manual_acquire_fails_fast` 或 `_FailingReleaseToken` 等旧 gate 测试。

### F-2 closed — `AGENTS.md` / `CLAUDE.md` scope 偏离

Fix artifact 明确说明 `AGENTS.md` 和 `CLAUDE.md` 的变更是 pre-existing user changes，fix agent 未修改、stage 或 revert。Implementation artifact 已补充说明。确认 closed。

## Verification

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
# Result: 23 passed in 0.41s

source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
# Result: 12 passed in 0.07s; coverage 90%

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

## Overdesign Check

| 检查项 | 结果 |
|--------|------|
| Guard 未引入新 state 或 lifecycle truth | pass |
| 未恢复旧 `_active_token` gate | pass |
| 未新增 stale lock / async / recovery 逻辑 | pass |
| 新测试只覆盖 nested context fail-fast + 无 leak 验证 | pass |
| 未恢复旧 gate 测试 | pass |
