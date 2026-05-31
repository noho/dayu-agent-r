# WU-RUNTIME-01 Plan Review — AgentMiMo 2026-06-01

## Conclusion

**pass-with-fixes**

Plan 动机成立、scope 克制、contract 裁决正确。有一个 blocking finding（context manager 私有状态存储方式未明确指定）和两个 non-blocking findings。修复 blocking finding 后可进入 implementation。

## Findings

### F1 [Blocking] Context manager 私有状态存储方式未明确

**Severity**: blocking

**Evidence**: Plan §5 "Context manager" 写道：

> `RuntimeFileLock.__exit__()` 必须调用同一 `__enter__()` 获得的 token 的 `release()`，保证 marker restore 语义一致。如果实现需要私有 context-frame 引用，命名必须避免 `_active_token`，并在注释 / docstring 说明它只用于 context manager cleanup，不是 lock lifecycle truth；不得在 `acquire()` 中使用它阻止或允许 acquire。

Plan 删除了 `_active_token`，但没有明确指定 `__exit__` 如何找到 `__enter__` 返回的 token。当前代码 `__exit__` 通过 `self._active_token` 获取 token。Plan 说"如果实现需要私有 context-frame 引用"，但这是 **必须** 而非 **如果** —— `__exit__` 必须有一个途径拿到 token。Plan 应该明确指定：使用一个私有 `__slots__` 字段（例如 `_context_token`）存储 `__enter__` 返回的 token，`__exit__` 通过它释放，`__exit__` 完成后清空。该字段不得在 `acquire()` 中用于 gate 逻辑。

**Risk**: Implementation agent 可能自行设计不一致的存储方式，或误以为不需要存储。如果不存储 token，`__exit__` 无法调用 `token.release()`，marker restore 语义丢失。

**Required fix**: 在 §5 "Context manager" 段落补充明确指令：

> `__enter__()` 调用 `acquire()` 后，将返回的 token 存储到一个私有 `__slots__` 字段（例如 `_context_token: RuntimeFileLockToken | None`）；`__exit__()` 通过该字段找到 token 并调用 `release()`，完成后将该字段清为 `None`。该字段只服务于 context manager cleanup，不得在 `acquire()` 中用于阻止或允许 acquire。在 `acquire()` 开始时应将该字段清为 `None`，避免残留旧 context frame 干扰新的 context manager 生命周期。

### F2 [Non-blocking] Context manager exit 时 release 抛错的行为应明确

**Severity**: non-blocking

**Evidence**: Plan §5 写道 "context manager 退出时 release 失败必须继续向外抛 `RuntimeFileLockError`"。当前代码 `__exit__` 使用 `try/finally` 确保 `_active_token` 被清空，即使 release 失败。Plan 没有明确说新的 `__exit__` 是否保留这个 `try/finally` 结构。

**Risk**: 低。Python context manager protocol 本身处理 `__exit__` 抛异常的情况（会与 business exception chaining），但实现应确保即使 release 失败，`_context_token` 也被清空，避免后续 acquire 或 context manager 残留脏状态。

**Required fix**: 在 §5 "Context manager" 补充一句：`__exit__()` 必须在 `finally` 块中清空私有 context frame 引用，即使 `release()` 抛错。

### F3 [Non-blocking] release 失败后 retry 语义是正确设计，但应显式记录为 deliberate contract

**Severity**: non-blocking

**Evidence**: Plan §4 "RuntimeFileLockToken" 裁决：

> release 失败时私有 guard 不得切到成功态；后续 retry 仍会调用同一 token 持有的第三方 lock，或继续抛出底层失败包装后的 `RuntimeFileLockError`。

这与当前代码行为相反（当前代码在 release 失败时设置 `released = True` 阻止 retry）。Plan 的设计是正确的 —— 不掩盖失败 —— 但这是一个 **behavioral change**：旧行为是 "release 失败后 retry 是 no-op"，新行为是 "release 失败后 retry 会再次尝试底层 release"。

**Risk**: 低。当前生产调用方全部通过 context manager 使用，不会手动 retry。但作为 contract 变更应显式记录。

**Required fix**: 在 §4 "RuntimeFileLockToken" 或 §5 "Token release" 段落显式说明这是 deliberate behavioral change：

> 旧实现 release 失败后设置 `released = True` 阻止 retry；新实现不掩盖失败，允许后续 `release()` 调用再次尝试底层 release。这是 deliberate contract 收缩，不是回归。

## Overdesign Check

Plan 整体克制，以下设计项 **应保留**：

| 设计项 | 判定 | 理由 |
|---|---|---|
| 删除 `RuntimeFileLockToken.released` | 保留 | 生产调用方不依赖；当前已在 release 失败时表达错误事实 |
| 移除 `RuntimeFileLock._active_token` | 保留 | 与 `released` 组合形成第二套 lifecycle truth |
| 保留 `RuntimeFileLockToken` 类型 | 保留 | acquire/context manager 返回值仍需要一个可 release 的 token |
| 私有 `_release_completed` 幂等 guard | 保留 | 防止同一 token 重复调用底层 release；不对外暴露状态 |
| Slice 2 Host audit/tool trace 回归测试 | 保留 | 验证 runtime contract 收缩不破坏生产调用面 |
| `docs/host/design.md` 同步 | 保留 | 设计真源仍列出 `released: bool`，必须同步 |

**无应删减项**。Plan 没有引入过度设计。

## Open Questions / Residual Risk

1. **无 blocking open question**。
2. **Accepted residual risk**: 同一 `RuntimeFileLock` 实例的 reentrant/nested acquire 行为不承诺，这是设计真源明确的非目标。
3. **Accepted residual risk**: file lock marker 文件不是 Host truth，marker restore best-effort 失败只记录 debug log。
4. **Trigger signal**: 若代码核对发现生产代码读取 `token.released`（audit.py 和 tool_trace.py 已确认不依赖），必须停止并重新裁决。
