# WU-RUNTIME-01 Slice 1 Code Review

Reviewer: AgentMiMo
Date: 2026-06-01
Target: workspace diff relative to HEAD (`refactor/wu-runtime-01-filelock-contraction`)
Implementation artifact: `docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md`
Accepted plan: `docs/host/wu-runtime-01-filelock-contraction-plan.md`
Design source: `docs/host/design.md`

## Conclusion

**pass-with-fixes**

Blocking findings: 0
Non-blocking findings: 1 (nested context `_context_token` overwrite)

## Verification Results

```bash
# tests
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
# Result: 22 passed in 0.39s

# coverage
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
# Result: 11 passed in 0.07s; coverage 90%

# pyright
source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

## Findings

### F-1 [non-blocking] 嵌套 context manager `_context_token` 覆盖导致静默 lock leak

**Evidence**

`RuntimeFileLock.__enter__()` 无条件将 `acquire()` 返回的 token 赋给 `self._context_token`。若同一实例已在外层 `with lock` 中，内层 `__enter__` 会覆盖外层 token 引用。内层 `__exit__` 释放内层 token 并清空 `_context_token`；外层 `__exit__` 发现 `_context_token is None`，不再释放外层 token。

具体时序：

```python
lock = file_lock(path)
with lock as outer:          # __enter__: _context_token = outer_token
    with lock as inner:      # __enter__: _context_token = inner_token (覆盖)
        pass                 # __exit__: inner_token.release(), _context_token = None
                             # __exit__: _context_token is None, outer_token 未 release
```

第三方 `FileLock` 对同线程 reentrant acquire 默认 succeed（内部计数 +1），所以 `__enter__` 不会抛错。外层 token 持有的底层 lock 未被 release，lock file 保持 locked 状态。

**Risk**

低。设计真源明确"不承诺 reentrant 语义"，生产调用方（`audit.py`、`tool_trace.py`）每次都创建独立 `RuntimeFileLock` 实例，不嵌套使用同一实例。但 silent leak 比 explicit error 更难诊断。

**Required fix**

在 `__enter__()` 中增加最小 fail-fast guard：

```python
def __enter__(self) -> RuntimeFileLockToken:
    if self._context_token is not None:
        raise RuntimeFileLockError("runtime file lock context manager 已持有 token，不支持嵌套")
    token = self.acquire()
    self._context_token = token
    return token
```

这不恢复旧 `_active_token` acquire gate，只保护 context manager 的 `_context_token` 不被静默覆盖。手动 `acquire()` 路径不受影响。

**Blocking?** 否。生产调用方不嵌套同一实例；风险被调用模式天然隔离。

### F-2 [info] `AGENTS.md` / `CLAUDE.md` 变更超出 Slice 1 scope

**Evidence**

Slice 1 allowed files 列表不含 `AGENTS.md` 或 `CLAUDE.md`。diff 显示两者增加了"不做过度设计，以最小化满足需求为标准。"。

**Risk**

无。这是项目约束文档新增，不影响 production source、tests 或 design contract。但 implementation artifact 未提及此变更。

**Blocking?** 否。文档级 meta 变更，不影响 Slice 1 contract 目标。

## Checklist: Slice 1 Adherence

| 检查项 | 结果 |
|--------|------|
| 只修改 Slice 1 allowed files | pass（含 F-2 info 级偏离） |
| 未修改 Host production source | pass |
| 未进入 Slice 2 | pass |
| 删除 public `RuntimeFileLockToken.released` | pass |
| 无 compat property / wrapper / re-export | pass |
| `_release_completed` 仅在第三方 release 成功后置 True | pass |
| release 失败允许 retry | pass（`test_release_failure_does_not_complete_and_allows_retry` 覆盖） |
| 移除 `RuntimeFileLock._active_token` acquire gate | pass |
| `_context_token` 只服务 context manager cleanup | pass |
| `acquire()` 不读写 `_context_token` | pass |
| parent directory / timeout / marker restore 保持 | pass |
| import boundary 保持 | pass（`test_import_boundary.py` 22 passed） |
| 测试删旧实现细节、覆盖关键行为 | pass |
| 无私有状态暴露坏味道 | pass（测试对 runtime module 自身 `_context_token` 的操作合理） |
| `docs/host/design.md` 同步且不过度 | pass |
| pyright 通过 | pass（0 errors） |

## Checklist: Overdesign Check

| 检查项 | 结果 |
|--------|------|
| 未引入 stale lock / break lock / async wrapper | pass |
| 未引入 durable lease / fencing / recovery | pass |
| 未引入 Host state machine 变更 | pass |
| `_context_token` 未升级为 lifecycle truth | pass |
| release 幂等 guard 未暴露为 public API | pass |
| F-1 建议的 fix 不引入新 state 结构 | pass（单行 if-check） |

## Residual Risk

- 同一 `RuntimeFileLock` 实例 reentrant / nested acquire 行为仍不承诺；F-1 建议的 fail-fast 可进一步收窄风险，但即使不修，生产调用模式也天然隔离。
- Lock marker 文件不是 Host truth；marker restore best-effort 失败只 debug log。
- Slice 2 Host audit / tool trace regression 覆盖不在本 slice 范围。
