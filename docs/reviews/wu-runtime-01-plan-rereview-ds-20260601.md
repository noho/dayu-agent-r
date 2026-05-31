# WU-RUNTIME-01 Plan Re-Review (AgentDS)

**Re-review target**: `docs/host/wu-runtime-01-filelock-contraction-plan.md`
**Original review**: `docs/reviews/wu-runtime-01-plan-review-ds-20260601.md`
**Re-review date**: 2026-06-01
**Reviewer**: AgentDS

---

## Conclusion

**pass** — 4/4 findings closed, 0 new findings, 0 overdesign regressions. Plan 可进入 accepted plan commit。

---

## Finding Status

### Finding 1 (was blocking) → CLOSED

**原问题**: Slice 1 Exact Changes 未显式列出 4 个依赖旧 `_active_token` gate 的测试的处置。

**修复验证**:

- Slice 1 Exact Changes source 小节新增 line 249：`删除现有 acquire gate，即删除 if self._active_token is not None and not self._active_token.released: raise RuntimeFileLockError(...)` — gate 代码已显式声明。
- Slice 1 Exact Changes tests 小节新增 lines 256-259：
  - `test_nested_context_manager_on_same_instance_fails_fast` → 删除
  - `test_manual_acquire_inside_context_fails_fast` → 删除
  - `test_context_enter_after_manual_acquire_fails_fast` → 删除
  - `test_manual_release_allows_same_instance_reacquire` → 删除或改写（附明确约束条件）
- Plan Section 4 同步新增 line 143：release 失败允许 retry 是 deliberate contract contraction，不是回归。

结论：4 个旧 gate 测试已点名处置，gate 代码删除已显式声明，行为变更语义已明确。**关闭**。

---

### Finding 2 (was non-blocking) → CLOSED

**原问题**: `__exit__` token tracking 未指定具体属性名和交互契约。

**修复验证**:

- Section 4 line 153：`RuntimeFileLock` context manager 必须用私有 `_context_token: RuntimeFileLockToken | None`。
- Section 5 lines 205-210：完整指定了属性名、类型、`__enter__` 存储、`__exit__` 释放、`finally` 清空、`acquire()` 禁止读写，以及不出现在 public API / `__all__` / dataclass fields。
- Slice 1 Exact Changes source 小节 line 250-251：重复确认 `_context_token` 的 slot/annotation 和 context manager 行为。

结论：属性名 `_context_token` 已指定，完整交互契约已明确，无 ambiguity。**关闭**。

---

### Finding 3 (was non-blocking) → CLOSED

**原问题**: `tests/README.md` 更新触发条件为模糊的"预计需要小幅更新"。

**修复验证**:

- Section 8 line 362-363：收敛为"需要检查，当前证据倾向不修改"，附明确理由（filelock bullet 无 `released` 或等价旧语义）。
- Slice 1 Allowed files line 239：`tests/README.md`（只检查；除非现有 filelock bullet 出现 `released` 或等价旧语义，否则不改）。
- Slice 2 Allowed files line 302：同样收敛为明确条件。

结论：`tests/README.md` 决策已从模糊收敛为明确的 evidence-gated 判定。**关闭**。

---

### Finding 4 (was non-blocking) → CLOSED

**原问题**: shape 测试和行为测试混在一起，实现 Agent 可能遗漏行为验证。

**修复验证**:

- Slice 1 Exact Changes tests 小节 line 261："增加 public shape 测试" — 单独列出，覆盖字段/slots/public exports 三重检查。
- Slice 1 Exact Changes tests 小节 line 262："增加 release 失败行为测试" — 单独列出，明确要求 `release_calls == 2` 断言。

结论：shape 测试和行为测试已拆成两条独立条目，各自有明确断言目标。**关闭**。

---

## Overdesign Regressions Check

对比原 plan 与修订后 plan，逐项检查新增内容：

| 新增内容 | 位置 | 裁决 |
|---|---|---|
| `_context_token: RuntimeFileLockToken \| None` 属性 | Section 4 line 153, Section 5 lines 205-210, Section 6 line 250-251 | 不增加：是移除 `_active_token` 后的最小替代，只服务 context manager cleanup |
| release 失败允许 retry 语义声明 | Section 4 line 143 | 不增加：是 contract 语义澄清，不引入新机制 |
| 四个旧 gate 测试显式删除条目 | Section 6 lines 256-259 | 不增加：是 plan 文档 precision 提升 |
| shape/behavior 测试拆分 | Section 6 lines 261-262 | 不增加：是 plan 文档 precision 提升 |
| `tests/README.md` 决策收敛 | Section 8 lines 362-363 | 不增加：是 plan 文档 precision 提升 |

无过度设计新增。Plan 核心设计决策（删除 `released`、移除 `_active_token`、`_context_token` 替代、`_release_completed` 幂等 guard）与原 review 时一致，仅 precision 提升。

---

## Internal Consistency Verification

| 检查项 | Section 4 (Contract) | Section 5 (Impl) | Section 6 (Slice 1) | 一致？ |
|---|---|---|---|---|
| `_release_completed` 只在成功 release 后设置 | line 142 | line 188 | line 246 | ✓ |
| release 失败不标成功，允许 retry | line 142-143 | line 196-200 | line 262 (`release_calls == 2`) | ✓ |
| `_context_token` 不出现在 public API | line 153 | line 210 | line 261 (shape 测试) | ✓ |
| `acquire()` 不得读写 `_context_token` | line 153 | line 209 | line 251 | ✓ |
| 旧 acquire gate 删除 | line 174 | — | line 249 | ✓ |
| 四个旧 gate 测试删除 | — | — | lines 256-259 | ✓ |

无内部矛盾。

---

## Plan Readiness

Plan 满足以下条件，可进入 accepted plan commit：

- [x] 动机判断成立且严重性未扩大
- [x] 所有 contract 裁决明确（删除 `released`、保留 token、移除 `_active_token`、无 compat wrapper）
- [x] Implementation instructions code-generation-ready：`release()` 伪代码、context manager 行为契约、`_context_token` 交互约束、测试条目逐项点名
- [x] Tests 覆盖 runtime contract、import boundary、Host 调用面回归、pyright
- [x] README / design doc sync 触发条件明确
- [x] Stop conditions 明确
- [x] Scope boundary 清晰，无扩大到 stale lock / async lock / durable lease / Host recovery
- [x] 无反向依赖、无 `Any`/`object`/无类型签名、无 lazy import、无 magic compatibility path
- [x] 原始 review 4 条 finding 全部关闭
- [x] 无新增 overdesign
