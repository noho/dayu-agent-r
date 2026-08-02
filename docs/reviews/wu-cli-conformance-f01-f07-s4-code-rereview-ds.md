# Code Re-review — WU-CLI-CONFORMANCE-F01-F07 S4/F04

## Scope

- Mode: current changes (uncommitted working tree, post-fix)
- Branch: `codex/interactive-oracle`
- Base: `25400fba` (HEAD, `fix(cli): preserve graceful input cancellation`)
- PR: 190 (未提交 S4/F04 slice)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-rereview-ds.md`
- Review basis:
  - 首轮 review: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-s4-fix-codex.md`
- Included scope (working tree diff):
  - `dayu/cli/session_execution.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/host/test_session_attachment_registry.py`（本 fix 未修改）
- Excluded scope: 无。
- Parallel review coverage: 无。

### 验证基线

| 检查项 | 结果 |
|---|---|
| Fix-specific tests (`-k attachment_controller or ...raw_string... or interactive_read_only`) | `7 passed, 71 deselected, 3 warnings` |
| Full focused suite (209 targeted) | `209 passed, 3 warnings in 10.15s` |
| Focused pyright (3 allowlist files) | `0 errors, 0 warnings, 0 informations` |
| Frozen oracle/scenario hash | 未变 |

## 首轮 Finding 逐项最终状态

### DS-1（原 中）：`attachment_for_mutation()` close 失败后状态不一致

- **裁决**: accepted（与 MiMo-2 合并）
- **最终状态**: **已修复**
- **修复摘要**:
  - `attachment_for_mutation()` refresh 路径在 await close 前执行 `self.current = None`（行 437），旧对象不再被 controller 持有
  - close 失败时 `open_fresh()` 不被调用（行 439 异常传播，行 440 不执行），`refresh_required` 保持 `True`
  - 下一次显式 mutation 进入 refresh 路径时，`self.current is None` → 跳过 close → 直接 `open_fresh()`
- **直接证据**:
  - 生产代码 `dayu/cli/session_execution.py:435-442`
  - 测试 `test_attachment_controller_refresh_close_failure_retries_with_fresh_open` (line 2733):
    - 首次 mutation: `close_attempts == [initial]`, `open_attempt_count == 0`, `refresh_required is True`
    - 二次 mutation: `close_attempts == [initial]` (无新增), `open_attempt_count == 1`, `refresh_required is False`
  - 测试 `test_attachment_controller_refresh_never_opens_before_close_completes` (line 2771):
    - close 未完成时 `open_attempt_count == 0`，controller state 已提交
- **反例覆盖**: close 失败路径 ✓, open 失败路径 ✓, close-before-open 偏序 ✓

### DS-2（原 低）：`_is_read_only_mutation_rejection()` 使用 `is` 进行 enum 身份比较

- **裁决**: rejected-with-reason — `is` 是 typed enum contract 的正确用法；`==` 会接受裸字符串形成 loose parsing
- **最终状态**: **已修复（按裁决方向）** — 保持 `is` 身份匹配，新增裸字符串在 typed schema boundary 被拒的对抗测试
- **直接证据**:
  - 生产代码 `dayu/cli/session_execution.py:1644-1645` — 仍使用 `is` 身份比较 ✓
  - 测试 `test_session_mutation_detail_rejects_raw_string_enum_values` (line 2840):
    - `cast(HostSessionMutationRejectionReason, "read_only")` → `TypeError("reason must be HostSessionMutationRejectionReason")` ✓
    - `cast(HostSessionAccessMode, "read_only")` → `TypeError("actual_mode must be HostSessionAccessMode")` ✓
  - 裸字符串无法通过 Host typed detail 的构造边界，CLI 下游不会收到非 enum 成员的值 ✓
- **语义 owner**: Host API schema boundary (`HostSessionMutationErrorDetail.__post_init__` 或等价 validator) 是 enum 身份的唯一保证者；CLI 不补偿也不放宽 ✓

### DS-3（原 低）：`close()` docstring 与实际行为在失败路径上不一致

- **裁决**: accepted（与 MiMo-1 合并）
- **最终状态**: **已修复**
- **修复摘要**:
  - `close()` 在任何 await 前原子地设置 `_closed=True` 并 take-and-clear `current`（行 458-460）
  - 底层 close 异常原样传播；第二次调用因 `_closed=True` 直接 no-op（行 456-457）
  - docstring 更新为"terminal 状态与 current 引用在等待底层关闭前提交；即使底层关闭失败，后续调用也不会再次关闭同一 attachment"（行 447-449）
- **直接证据**:
  - 生产代码 `dayu/cli/session_execution.py:445-462`
  - 测试 `test_attachment_controller_close_failure_is_terminal_and_attempted_once` (line 2707):
    - `exc_info.value is close_error` — 异常 identity 原样传播 ✓
    - `probe.close_states == [(None, False, True)]` — await 前 current=None, refresh=False, _closed=True ✓
    - 第二次 `close()` 后 `probe.close_attempts == [initial]` — 恰好一次 attempt ✓

## Adversarial 逐项验证

### 1. close 在 await 前 terminal/take-clear，失败后第二次 no-op

**验证路径**: `_InteractiveSessionAttachmentController.close()` lines 445-462

```text
入参: 无
  → _closed 检查 (line 456): True → 立即返回 (no-op)
  → _closed = True (line 458): 在任何 await 之前提交 terminal 状态
  → take current, self.current = None (lines 459-460): 在任何 await 之前移除本地引用
  → if current is not None: await shielded close_current(current) (lines 461-462)
     → 异常: 原样传播，_closed 已为 True, current 已为 None
     → 成功: 正常返回
返回值: None
副作用: _closed=True, current=None, 底层 close 恰好一次 attempt
```

- **terminal-before-await**: `_closed=True` (line 458) 和 `self.current=None` (line 460) 都在首个 `await` (line 462) 之前执行 ✓
- **失败后第二次 no-op**: `_closed=True` 已提交 → 第二次调用 line 456 命中 `return` ✓
- **异常 identity**: 无 `try/except`，异常直接穿透 `asyncio.shield` → 原对象传播 ✓
- **测试锁定**: `probe.close_states == [(None, False, True)]` 证明 close callback 观察到 await 前的已提交状态 ✓

### 2. refresh close 失败不 open/不 double-close，下一次 mutation fresh open

**验证路径**: `_InteractiveSessionAttachmentController.attachment_for_mutation()` lines 416-443

```text
入参: 无
  → _closed 检查 (line 428)
  → refresh_required 检查 (line 430): False → 返回 current
  → [refresh 路径] previous = self.current (line 436)
  → self.current = None (line 437): take-and-clear BEFORE 任何 await
  → if previous is not None: await shielded close_current(previous) (lines 438-439)
     → close 失败: 异常传播，line 440+ 均不执行
       状态: current=None, refresh_required=True
       下一次 mutation: refresh_required=True → previous=None → 跳过 close → 直接 open_fresh()
     → close 成功: 继续
  → fresh = await open_fresh() (line 440)
     → open 失败: 异常传播，line 441-442 不执行
       状态: current=None, refresh_required=True
       下一次 mutation: 同上，跳过 close → 直接 open_fresh()
     → open 成功: 继续
  → self.current = fresh, self.refresh_required = False (lines 441-442)
返回值: fresh attachment
副作用: current 更新, refresh_required 清除（仅成功路径）
```

- **不 open on close failure**: line 439 异常传播，line 440 `open_fresh()` 不执行 ✓
- **不 double-close**: `self.current = None` (line 437) 在 close await 前执行；下一次 mutation 时 `previous = self.current = None` → `previous is not None` 为 False → 跳过 close ✓
- **下一次 mutation fresh open**: `refresh_required` 保持 True → 进入 refresh 路径 → 跳过 close → `open_fresh()` ✓
- **测试锁定**:
  - close 失败后 `open_attempt_count == 0` ✓
  - retry 后 `close_attempts` 不增加 ✓
  - retry 后 `open_attempt_count == 1` ✓

### 3. open 失败 state 与显式 retry

**验证路径**: 同上 `attachment_for_mutation()` lines 440-442

- **open 失败 state**: `current=None`, `refresh_required=True` — 与 close 失败后完全相同的收敛状态 ✓
- **显式 retry**: 仅由下一次用户 mutation 触发，无后台 poll/retry/循环 ✓
- **retry 不重复 close**: `self.current is None` → 跳过旧 attachment close ✓
- **测试锁定**:
  - open 失败后 `probe.close_attempts == [initial]` (close 一次), `probe.open_attempt_count == 1` (open 一次) ✓
  - retry 后 `probe.close_attempts == [initial]` (不增加), `probe.open_attempt_count == 2` ✓
  - retry 成功: `controller.current is fresh`, `refresh_required is False` ✓

### 4. 异常 identity

在 `close()` 和 `attachment_for_mutation()` 两条路径中：
- `close_current()` 和 `open_fresh()` 的异常均不经 `try/except` 包装，原样穿透 `asyncio.shield` 传播 ✓
- 测试使用 `assert exc_info.value is close_error`（identity check, not equality）证明异常对象完全一致 ✓

### 5. typed enum 仍 identity 严格，裸字符串在 typed schema boundary 被拒

- `_is_read_only_mutation_rejection()` 保持 `is` 身份比较（lines 1644-1645） ✓
- `HostSessionMutationErrorDetail` 构造时对裸字符串执行 typed validation → `TypeError` ✓
- 测试证明两种 enum 字段（`reason`, `actual_mode`）的裸字符串输入均在构造时被拒 ✓
- CLI 下游不会收到非 enum 成员的值，`is` 身份比较的安全前提由 Host API schema boundary 保证 ✓

### 6. Close-before-open 偏序（无 premature open）

- `attachment_for_mutation()` refresh 路径: `self.current = None` → `await close_current(previous)` → `await open_fresh()` → 严格顺序 ✓
- 测试 `test_attachment_controller_refresh_never_opens_before_close_completes`:
  - close 阻塞期间 `open_attempt_count == 0` ✓
  - `refresh_task.done() is False` ✓
  - close 放行后 `open_attempt_count == 1` ✓
  - 返回的 attachment 是 fresh B2 ✓

## Open Questions

无。首轮 DS-1（close 失败状态）、DS-2（enum `is` vs `==`）、DS-3（docstring 一致性）均已裁决并验证修复。

## Residual Risk

- **S8 真实双进程 PTY evidence**: 与首轮相同，由已批准 S8 覆盖。本 slice 的 controller owner tests 与 Host public attachment registry test 在单进程 owner boundary 层面全覆盖。
- **Host `aclose()` 幂等性**: controller 现在保证 exactly-once close attempt，不依赖下游实现的幂等性。即使 Host `aclose()` 非幂等，也只会被调用一次（异常路径下不会重试）。此项风险从首轮"中"降级为已消除。
- **Close/open callback 注入**: 测试使用的 `_AttachmentControllerLifecycleProbe` 以可控异常注入验证了 close/open 失败路径。生产路径的 close/open callback 是 `partial(host.attach_session, session_id)` 和 `_close_interactive_session_attachment`，均为简单透传，无额外状态。风险低。

## Verdict

首轮 review 的三个 findings 全部已修复，无新增 finding。修复严格遵循 controller adjudication 的 required fix contract：

1. `close()`: terminal/take-clear 在任何 await 之前，失败后第二次 no-op — **已修复**
2. `attachment_for_mutation()` refresh: take-and-clear 在 close await 之前，close 失败不 open/不 double-close，下一次 mutation fresh open — **已修复**
3. open 失败 state 收敛（`current=None, refresh_required=True`），仅由显式下次 mutation 重试 — **已修复**
4. 异常 identity 原样传播 — **已修复**
5. typed enum 保持 `is` 身份匹配，裸字符串在 Host typed schema boundary 被拒 — **已修复（按裁决方向）**

209 tests 全部通过，pyright 零错误。无 blocking residual risk。

**建议**: 通过。可进入下一 gate。
