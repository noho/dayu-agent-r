# WU-RUNTIME-01 Plan Re-Review — AgentMiMo 2026-06-01

## Conclusion

**pass**

所有 accepted findings 已关闭，无新增 finding，无新增 overdesign。Plan 可进入 accepted plan commit。

## Finding 状态

### F1 [Blocking → Closed] Context manager 私有状态存储方式未明确

**状态**: closed

**关闭证据**:

Plan §4 "RuntimeFileLock._active_token" 裁决段（L153）已写明：

> `RuntimeFileLock` context manager 必须用私有 `_context_token: RuntimeFileLockToken | None` 保存 `__enter__()` 返回的 token 供 `__exit__()` 释放；不得在 `acquire()` 中基于该引用推导全局 lock lifecycle。

Plan §5 "Context manager"（L205-211）完整指定了：

- `_context_token: RuntimeFileLockToken | None` 作为 `__slots__` 字段（L205）
- `__enter__()` 存入 `_context_token` 并返回（L206）
- `__exit__()` 通过 `_context_token` 找到 token 并调用 `release()`（L207）
- `__exit__()` 在 `finally` 块中清为 `None`（L208）
- `acquire()` 不得读写 `_context_token`（L209）
- `_context_token` 不得出现在 public API（L210）

Plan §6 Slice 1 "Exact changes"（L249-251）也同步更新：

- L249: 删除 acquire gate `if self._active_token is not None and not self._active_token.released`
- L250: 增加 `_context_token` slot / annotation
- L251: `__enter__` 存入、`__exit__` 通过它释放并在 `finally` 清空

**判定**: 原始 review 要求的所有要点（字段名、类型、存储/释放/清空语义、acquire 不读写、不暴露 public）均已覆盖。Implementation agent 不需要自行设计。

---

### F2 [Non-blocking → Closed] Context manager exit 时 release 抛错的行为应明确

**状态**: closed

**关闭证据**:

Plan §5 "Context manager" L208：

> `RuntimeFileLock.__exit__()` 必须在 `finally` 块中把 `_context_token` 清为 `None`，即使 `release()` 抛出 `RuntimeFileLockError`。

L211 补充：

> context manager 退出时 release 失败必须继续向外抛 `RuntimeFileLockError`，且不得产生成功 release 状态。

**判定**: `try/finally` 结构和异常传播行为均已明确指定。

---

### F3 [Non-blocking → Closed] release 失败后 retry 语义应显式记录为 deliberate contract

**状态**: closed

**关闭证据**:

Plan §4 "RuntimeFileLockToken" L143：

> 旧实现 release 失败后设置 `released = True` 阻止 retry；新实现不掩盖失败，允许后续 `release()` 调用再次尝试底层 release。这是 deliberate contract contraction，不是回归。

**判定**: behavioral change 已显式记录为 deliberate 设计，不是遗漏。

---

### 总控追加要求逐条核对

| 总控要求 | Plan 覆盖位置 | 状态 |
|---|---|---|
| 明确 `_context_token: RuntimeFileLockToken \| None` | §4 L153, §5 L205-210, §6 L250-251 | closed |
| 明确删除旧 `_active_token` acquire gate | §4 L147-152, §5 L174, §6 L249 | closed |
| 点名处置四个旧同实例 gate 测试 | §6 L256-259（三个显式删除，一个删除或改写） | closed |
| release 失败测试拆成 public shape 与 retry 行为，要求 `release_calls == 2` | §6 L260, L262 | closed |
| tests/README.md 决策收敛为当前证据倾向不改 | §8 L362-364 | closed |
| 明确 release 失败允许 retry 是 deliberate contract contraction | §4 L143 | closed |

---

## Overdesign Check

**无新增 overdesign**。Re-review 只涉及对已接受 findings 的补充说明，没有引入新设计项。

原有 overdesign check 结论不变：Plan 整体克制，无应删减项。

## Residual Risk

与原 review 一致，无新增 residual risk。
