# WU-RUNTIME-01 Plan Review (AgentDS)

**Review target**: `docs/host/wu-runtime-01-filelock-contraction-plan.md`
**设计真源**: `docs/host/design.md`
**总控文档**: `docs/host/host-core-followup-implementation-control.md`
**Review date**: 2026-06-01
**Reviewer**: AgentDS

---

## Conclusion

**pass-with-fixes** — 1 blocking finding, 3 non-blocking findings, 0 overdesign items.

---

## Findings

### Finding 1 (blocking): Slice 1 Explicit Test Deletion List Missing Nested Context Tests

**Evidence**:

当前 `tests/runtime/test_filelock.py` 中存在 3 个测试，其唯一测试目标就是 `_active_token` reentrant gate 行为：

- `test_nested_context_manager_on_same_instance_fails_fast` (line 174)
- `test_manual_acquire_inside_context_fails_fast` (line 187)
- `test_context_enter_after_manual_acquire_fails_fast` (line 199)

这三个测试不直接读取 `lock._active_token`（因此不会被 "删除所有直接写入 / 读取 `lock._active_token` 的测试" 覆盖），也不直接断言 `token.released`（test 8 没有该断言）。它们唯一在测的是：同实例 acquire 被拒绝并抛出 `"already active"`。

Plan Section 5 明确裁决：`RuntimeFileLock.acquire()` 不再检查 `_active_token`，不再保存 active token。Plan Section 2 正确指出 "把同一 wrapper 实例嵌套 context / manual acquire 的具体失败方式当成 public contract" 属于应删除的实现细节。但 Slice 1 Exact Changes 的测试删除列表只列出了：
- "删除所有 `token.released` 断言"
- "删除所有直接写入 / 读取 `lock._active_token` 的测试"
- "删除或改写旧测试 `test_release_failure_marks_token_released_to_prevent_retry`"

没有把上述 3 个嵌套 context gate 测试列入显式删除清单。

此外，`test_manual_release_allows_same_instance_reacquire` (line 212) 也间接依赖 `_active_token` gate（验证手动 release 后同实例可再次 acquire），也需要在 Slice 1 中明确其命运（删除或改写为只验证两次独立 acquire 各返回不同 token）。

**Risk**: 实现 Agent 可能不清楚这 4 个测试应该被删除（gate 已移除），尝试改写使它们通过，导致保留 `_active_token` 兼容逻辑或引入新的 gate 机制。

**Required fix**: 在 Slice 1 Exact Changes 的 tests 小节显式列出：
- `test_nested_context_manager_on_same_instance_fails_fast` → 删除
- `test_manual_acquire_inside_context_fails_fast` → 删除
- `test_context_enter_after_manual_acquire_fails_fast` → 删除
- `test_manual_release_allows_same_instance_reacquire` → 删除或改写（若保留，不得断言 `token.released`，且不得依赖同实例 gate）

同时在 Slice 1 Exact Changes 的 source 小节，显式声明 `acquire()` 删除的 gate 代码是 `if self._active_token is not None and not self._active_token.released: raise RuntimeFileLockError(...)`。

**Blocking**: 是。Plan 的意图在 Section 2/Section 5 中已清晰，但 Slice 1（implementation agent 的直接执行依据）存在测试覆盖缺口，可能导致实现 Agent 不确定应删除还是改写这些测试。

---

### Finding 2 (non-blocking): `__exit__` Token Tracking Mechanism 未指定具体属性名

**Evidence**:

Plan Section 5 说 "如果实现需要私有 context-frame 引用，命名必须避免 `_active_token`"，但没有给出推荐属性名（如 `_context_token`），也没有说明这个引用与 `acquire()` 的交互契约。

**Risk**: 实现 Agent 可能选用 `_active_token` 以外但仍暗示 lifecycle truth 的名字（如 `_held_token`、`_current_token`），或者不小心在 `acquire()` 中引用它做 gate。

**Required fix**: 非阻塞。在 Slice 1 Exact Changes 中补充一条：`__enter__()` 将 `acquire()` 返回的 token 存入私有属性（建议 `_context_token`），`__exit__()` 通过该属性释放；`acquire()` 不得读写该属性；该属性不得出现在 public API、`__all__` 注释或 dataclass fields 中。

**Blocking**: 否。

---

### Finding 3 (non-blocking): `tests/README.md` 更新触发条件不精确

**Evidence**:

Plan Section 8 说 `tests/README.md` "需要检查，预计需要小幅更新"，理由是 "如果 implementation 后新增 release 失败不标成功 / public token 不暴露状态的测试，应同步一句稳定说明"。当前 `tests/README.md` 的 filelock bullet (line 80) 为：

> filelock：覆盖同步 file lock wrapper 的 parent directory 创建策略、禁用创建时的结构化错误、context manager 正常与异常路径 release、release 幂等、non-blocking timeout 包装，以及第三方 `filelock` import 只能出现在 `dayu.runtime.filelock` 的边界。

这段描述没有提到 `released` 字段，语义上也不依赖 `released`。但 "context manager 正常与异常路径 release" 的验证方式会从 "断言 `token.released`" 变为 "通过第二个独立 lock non-blocking acquire 成功来证明释放"。这是测试策略变化，不是公共契约变化。

**Risk**: 实现 Agent 可能机械更新 README 描述新测试覆盖口径，也可能完全不更新。两种极端都不理想。

**Required fix**: 非阻塞。在 Slice 1 Exact Changes 中给出明确判定：除非 `tests/README.md` filelock bullet 中出现 `released` 字样或等价语义（当前未出现），否则不改；若实现后新增的 public shape 测试属于 runtime test 内部策略变化，`tests/README.md` 不需同步。将此判定从 "预计需要小幅更新" 收敛为明确 yes/no。

**Blocking**: 否。

---

### Finding 4 (non-blocking): Release 失败后无 public state 的测试覆盖策略可更具体

**Evidence**:

Plan Section 4 裁决删除 public `released`，Section 6 Slice 1 要求增加 "public shape 测试：`RuntimeFileLockToken` dataclass fields 不包含 `released`"。但 shape 测试只验证字段不存在，不验证 release 失败后调用方无法通过任何 public API 获知 "release 成功" 的假事实。

Plan 的改写测试说 "新期望为：底层 release 失败抛 `RuntimeFileLockError`，不出现 public `released` 字段，且再次调用 `release()` 会再次尝试同一底层 release 或继续抛同一 wrapper 错误，证明没有标记成功"——这实际上已经覆盖了行为验证。但措辞中 "不出现 public `released` 字段" 是 shape 验证，而 "再次调用 release() 会再次尝试同一底层 release" 是行为验证。两者分开描述更好。

**Risk**: 如果实现 Agent 只做 shape 测试不做行为测试，可能漏掉 "release 失败后 `_release_completed` 未设置的幂等重试" 这个关键语义。

**Required fix**: 非阻塞。在 Slice 1 Exact Changes 中把 shape 测试和行为测试分成两条显式条目：
1. public shape 测试：`RuntimeFileLockToken` dataclass fields 不包含 `released`
2. release 失败行为测试：底层 release 抛错后，再次调用 `token.release()` 会再次调用底层 release（`_FailingThirdPartyLock.release_calls == 2`），证明无成功状态被标记

**Blocking**: 否。

---

## Overdesign Check

Plan 无过度设计。逐项检查：

| 检查项 | 裁决 |
|---|---|
| 删除 public `released` | 正确：生产调用方不依赖，且当前实现在 release 失败时表达错误事实 |
| 移除 `_active_token` | 正确：第二套 lifecycle truth，设计真源明确 reentrant lock 不承诺 |
| 保留 `RuntimeFileLockToken` | 正确：acquire/context manager 仍需返回可显式 release 的对象；不保留则需让 RuntimeFileLock 自身持 release()，会混淆实例与单次 acquire 的生命周期 |
| 私有 `_release_completed` guard | 正确：最小化幂等保护，不在 public contract 中暴露；仅防止同 token 重复调用底层 release |
| Slice 2 Host regression tests | 正确：不修改 Host production code，只补调用面回归；符合 "证明 contract 收缩不破坏生产调用" 的最小目标 |
| 不引入 stale lock / async wrapper / durable lease | 正确：严格遵循 scope boundary |
| 不提供 compat property/wrapper | 正确：符合项目编码硬约束 |
| 两个 slice 拆分 | 合理：Slice 1 做 contract 收缩 + runtime 测试，Slice 2 做 Host 调用面回归；可独立验证 |

无不必要的新增类型、错误类、抽象层或辅助函数。

---

## Residual Risk / Open Questions

### Accepted residual risk（plan 已识别，确认合理）

1. 同一 `RuntimeFileLock` 实例 reentrant acquire 行为不承诺 → 设计真源非目标，生产调用方不依赖
2. Marker restore best-effort 失败只 debug log → marker 不是 Host truth
3. `test_manual_release_allows_same_instance_reacquire` 删除后，不再有测试验证 "同一实例可重复使用" → 非 public contract

### Additional residual risk（本 review 识别）

4. **`RuntimeFileLockToken` 保留后可能被误解为 lifecycle handle**：虽然 plan 明确 token 不暴露 release 状态，但 `RuntimeFileLockToken` 类型名本身可能暗示 "token 代表了被持有的锁"。在 README/设计真源同步时，建议明确 token 只是 release 路由 handle，不是 lifecycle 证明。

5. **`test_public_api_shape_and_non_goals_are_explicit` 需小幅更新**：当前该测试已在检查 `force_release`、`break_lock`、`__aenter__`、`__aexit__` 不在 `RuntimeFileLock` 的 vars 中。Slace 1 增加 "`_active_token` 不在 `RuntimeFileLock.__slots__`" 的断言后，应确保该测试也被更新。Plan 已有 public shape 测试条目，但未明确是否在现有 `test_public_api_shape_and_non_goals_are_explicit` 中追加还是新建测试函数。

### Open questions

无阻塞性问题。所有设计裁决已由 plan 明确。

---

## Verification Commands Adequacy

Plan Section 7 验证命令：

```bash
# 主验证
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
source .venv/bin/activate && pyright

# 可选
source .venv/bin/activate && pytest tests/runtime -q
source .venv/bin/activate && pytest tests/host/test_import_boundary.py -q
```

判定：**足够但不过度**。

- `test_filelock.py` + `test_import_boundary.py`: 覆盖 runtime contract 变更 + import 边界
- `test_audit_sink.py` + `test_tool_trace_projection.py`: 覆盖 Host 调用面回归
- `--cov=dayu.runtime.filelock`: 覆盖单文件 80% 目标
- `pyright`: 项目强制类型检查
- 可选 `tests/runtime -q` 和 `tests/host/test_import_boundary.py` 提供 broader confidence，标记为 optional 正确

建议：Slace 1 验证命令增加 `tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py` 的覆盖率检查，Slace 2 验证命令包含 `tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py` 的全量运行。当前命令已覆盖。

---

## Plan Review Gate Checklist

| Gate | 结果 |
|---|---|
| Scope 只解决 runtime filelock wrapper contraction | pass |
| 未扩大到 stale lock / async lock / durable lease / Host recovery | pass |
| Contract 裁决明确：删除 released、保留 token、移除 _active_token、无 compat wrapper | pass |
| Implementation instructions 足够具体 | pass-with-fixes (Finding 1, 2) |
| Tests 覆盖 runtime contract / import boundary / audit-tool-trace 调用面 / pyright | pass-with-fixes (Finding 1, 3, 4) |
| README / design doc sync 符合触发规则 | pass |
| 无反向依赖 / Any-object-无类型签名 / lazy import / magic compatibility path | pass |
| 设计真源同步已纳入计划 | pass |
| Slice 拆分合理可独立验证 | pass |
| Stop conditions 明确 | pass |
