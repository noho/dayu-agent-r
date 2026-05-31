# WU-RUNTIME-01 PR Review — AgentMiMo 2026-06-01

PR: https://github.com/noho/dayu-agent-r/pull/100
Branch: refactor/wu-runtime-01-filelock-contraction
Base: main
Reviewer: AgentMiMo
Review scope: PR diff only (excluding local uncommitted AGENTS.md / CLAUDE.md changes)

## Conclusion

**pass-with-fixes**

PR 完整实现了 WU-RUNTIME-01 的目标，没有过度设计。RuntimeFileLock contract 收缩、design doc、tests、Host regression 一致。Control doc 状态合理。无 blocking finding。

## Findings

### F-1: Control doc 修改与 plan Explicitly Forbidden 声明不一致

**Severity**: advisory
**Evidence**: `docs/host/wu-runtime-01-filelock-contraction-plan.md` Section 3 明确声明 `docs/host/host-core-followup-implementation-control.md` 为 "Explicitly forbidden"，理由是 "本 WU 当前 plan 不修改总控文档；后续由 controller 在 gate 状态推进时单独维护"。但 PR 实际修改了该文件。
**Risk**: 低。修改内容是 gateflow controller 状态推进（gate/status/active work unit/review artifacts/RR-HCF-01 状态），不是 implementation slice 内容。这是 gateflow 流程的正常行为——controller 在 gate 状态推进时维护总控文档。
**Required fix**: 无。但建议在 plan 或 gateflow 约定中明确：plan 的 "Explicitly forbidden" 约束只针对 implementation agent，不约束 controller 状态推进。
**Blocking**: 否

### F-2: PR 包含 20 个 review artifact 文件

**Severity**: advisory
**Evidence**: PR diff 包含 20 个 `docs/reviews/wu-runtime-01-*.md` 文件，总计约 2000+ 行。
**Risk**: 低。这些是 gateflow 流程的 review 过程产物，对 PR review 者增加阅读负担，但属于项目 review 流程的正常产出。
**Required fix**: 无。可考虑未来将 review artifacts 与 implementation PR 分离。
**Blocking**: 否

### F-3: `RuntimeFileLock.__exit__` 在 token 为 None 时的行为

**Severity**: advisory
**Evidence**: `filelock.py:210-215` 中 `__exit__` 的实现：
```python
token = self._context_token
try:
    if token is not None:
        token.release()
finally:
    self._context_token = None
```
当 `_context_token` 为 None 时（理论上不应发生，因为 `__enter__` 会设置），`__exit__` 会静默返回。这比旧实现更安全（旧实现依赖 `_active_token`），但 `__exit__` 在 token 为 None 时的行为未被测试覆盖。
**Risk**: 极低。`__enter__` 总是设置 `_context_token`，且嵌套 context 被显式拒绝。唯一可能导致 `_context_token` 为 None 的场景是 `__enter__` 中 `acquire()` 抛异常，此时 Python 不会调用 `__exit__`。
**Required fix**: 无。当前实现是正确的防御性编程。
**Blocking**: 否

### F-4: Host regression 测试只覆盖 happy path

**Severity**: advisory
**Evidence**: `tests/host/test_audit_sink.py` 和 `tests/host/test_tool_trace_projection.py` 的修改只添加了显式 `lock_path` 参数到现有测试，没有新增专门的 lock-path-specific 断言（如验证 lock marker 文件存在）。
**Risk**: 低。测试已证明 Host 调用面在 runtime contract 收缩后仍正常工作。Plan 的 Non-goals 明确 "不新增多进程 contention 测试"。
**Required fix**: 无。当前覆盖已满足 plan 要求。
**Blocking**: 否

### F-5: Coverage 90%，未覆盖行主要是错误路径

**Severity**: advisory
**Evidence**: `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` 显示 90% coverage，未覆盖行 145-146, 173-174, 275, 283-284, 296, 309-310, 322。
**Risk**: 低。未覆盖行主要是：
- 145-146: `FileLock` 构造失败的 except 分支
- 173-174: `acquire()` 中非 Timeout 的其他异常分支
- 275: parent 不是目录的检查
- 283-284: mkdir 失败的 except 分支
- 296, 309-310, 322: 路径校验和 marker restore 的 except 分支
这些都是错误处理路径，覆盖率 >= 80% 目标已达成。
**Required fix**: 无。
**Blocking**: 否

## Contract / Design Doc 一致性

### `docs/host/design.md`

- `RuntimeFileLockToken` public API shape 已删除 `released: bool` ✓
- Release 语义已更新：token 不暴露 release 状态；幂等 release 只防止同一 token 重复释放 ✓
- 第三方 release 失败时不得标记为成功 release ✓

### `docs/host/host-core-followup-implementation-control.md`

- WU-RUNTIME-01 状态更新为 "已完成" ✓
- RR-HCF-01 状态更新为 "closed" ✓
- Gate 状态更新为 "ready-to-open-draft-PR" ✓
- Review artifacts 列表完整 ✓

### `dayu/runtime/filelock.py` vs Design Doc

- `RuntimeFileLockToken` 只暴露 `lock_path` 和 `release()` ✓
- `_release_completed` 是私有幂等 guard，不在 public API 中 ✓
- `_context_token` 只服务 context manager cleanup，不是 lifecycle truth ✓
- 第三方 `FileLock` 持有 acquire/release 生命周期真源 ✓

## Tests 一致性

### Runtime contract tests (`tests/runtime/test_filelock.py`)

- 删除了 `_FailingReleaseToken` 测试 helper ✓
- 删除了所有 `token.released` 断言 ✓
- 删除了 `_active_token` 相关测试 ✓
- 新增 `test_release_failure_does_not_complete_and_allows_retry` ✓
- 新增 public API shape 测试（`released` 不在 token fields 中，`_active_token` 不在 slots 中）✓
- Context manager 测试改为验证独立 lock 可再次获取 ✓

### Host regression tests

- `test_audit_sink.py`: 显式 `lock_path` 参数已添加 ✓
- `test_tool_trace_projection.py`: 显式 `lock_path` 参数已添加 ✓

### Import boundary tests (`tests/runtime/test_import_boundary.py`)

- 未修改，符合 plan 预期 ✓

## PR Readiness

| 检查项 | 状态 |
|---|---|
| Tests pass | ✓ 23 passed (runtime), 13 passed (host) |
| Coverage >= 80% | ✓ 90% |
| pyright | ✓ 0 errors |
| Design doc 同步 | ✓ |
| Control doc 状态 | ✓ |
| Scope 泄漏 | 无 |
| 反向依赖 | 无 |
| 遗漏文件 | 无 |
| 错误 commit | 无 |

## Residual Risk

1. **同一 RuntimeFileLock 实例的 reentrant 行为不承诺**：这是设计真源非目标，不作为 bug。Plan 已明确声明。
2. **file lock marker 文件不是 Host truth**：marker restore best-effort 失败只记录 debug，不升级为 durable failure。这是设计意图。
3. **Control doc 修改与 plan "Explicitly forbidden" 声明不一致**：这是 gateflow 流程的正常行为，不是 implementation 问题。

## Summary

PR 完整实现了 WU-RUNTIME-01 的所有目标：
- 收缩 `RuntimeFileLock` 为普通文件互斥 wrapper
- 删除 public `RuntimeFileLockToken.released`
- 移除 `_active_token` acquire gate
- 第三方 `FileLock` 继续持有 acquire/release 生命周期真源
- Host audit/tool trace regression 已覆盖
- Design doc 已同步更新

无 blocking finding。PR ready to merge。
