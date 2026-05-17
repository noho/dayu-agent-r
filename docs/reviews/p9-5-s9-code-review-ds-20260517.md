# P9.5 S9 Runtime Lane Hardening — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S9 Runtime Lane Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S9.
- Implementation artifact: `docs/reviews/p9-5-s9-runtime-lane-hardening-implementation-20260517.md`.
- Reviewed files: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `dayu/README.md`.
- No code, tests, or artifacts were modified.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- All changes within S9 allowed files: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `dayu/README.md`.
- No `Host`/`Engine`/`Fins` files modified or read for implementation.
- No new SQLite schema, DDL, or migration.

### Confirmed: no prohibited semantics introduced

| 语义 | 状态 |
|---|---|
| Host durable truth / state | 未引入 |
| EventLog / canonical fact | 未引入 |
| Attempt owner / lease / fencing / takeover | 未引入 |
| Recovery proof / recovery scan | 未引入 |
| RemoteProxy / wire protocol | 未引入 |
| Engine contract / Runner | 未引入 |
| Fins document / storage | 未引入 |
| 新状态机状态 | 未引入 |

---

## Findings

未发现实质性问题。

---

## 审查点逐项验证

### 1. Acquire cancellation precision

**Task.cancel() 透传 `asyncio.CancelledError`：**

- `acquire()` (lane.py:431-518) 调用 `_try_claim_once()` (lane.py:551-580)
- `_try_claim_once()` 在 `asyncio.shield(claim_task)` 上捕获 `CancelledError`（line 566），通过 `_await_task_after_outer_cancellation(claim_task)` 等待 DB claim task 完成，然后 best-effort 释放已插入 claim，最后重新抛出 `cancelled`。
- `acquire()` 接收到 `CancelledError` 后不做捕获，直接透传给调用方 — 正确。

**CancellationToken 返回 `LaneAcquireCancelled`：**

- 循环入口（line 470-471）：token 已取消 → 返回 `LaneAcquireCancelled`
- claim 成功后（line 480-482）：token 已取消 → 释放 untracked claim → 返回 `LaneAcquireCancelled`
- timeout 命中后（line 511-512）：token 已取消 → 返回 `LaneAcquireCancelled`

**协作式取消优先于 timeout：**

- claim 成功后检查顺序：CancellationToken（line 480）→ heartbeat error（line 483）→ close（line 486）→ timeout（line 489）。取消在 timeout 之前被检查。
- timeout 命中后分支内（line 511-512）：先检查 CancellationToken 再返回 `LaneAcquireTimedOut`。
- 对于 `effective_timeout == 0`（non-blocking），timeout 立刻命中，但此时 CancellationToken 已在循环顶部被检查（line 470）。race window 内 token 取消与 timeout 命中同时到达时，循环顶部检查提供了最佳防御。这是已有行为，S9 未改变。

**Repeated outer cancellation 不打断已插入 claim cleanup：**

- `_await_task_after_outer_cancellation()` (lane.py:973-994)：循环 `asyncio.shield(task)` 直到 task 完成。每次新的 `CancelledError` 命中时检查 `task.done()`；若 task 已完成，通过 `task.result()` 返回结果；若未完成，继续 shield 等待。
- `_try_claim_once` 取消路径（line 567-580）：先用 `_await_task_after_outer_cancellation` 等待 claim task 完成。若 claim 已插入，再用 `_release_untracked_claim`（同样使用 `_await_task_after_outer_cancellation`）做 cleanup release。两次 cleanup 均抵抗 repeated outer cancel。
- 调用方始终看到 `CancelledError`（line 569, 579, 580）。
- 测试 `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim` (test_lane.py:471-513)：double cancel + slow claim → `_claim_count(db_path) == 0` + `CancelledError` 透传。**通过。**

### 2. Heartbeat / token lost 与 release failure 的可观测错误

**Heartbeat error：**

- `_record_heartbeat_error()` (lane.py:882-893)：记录首次 heartbeat `RuntimeLaneError`，设置 `_closed=True`，`_close_reason=_CLOSE_REASON_HEARTBEAT_ERROR`，唤醒 pending waiter。
- `_raise_heartbeat_error_if_present()` (lane.py:895-903)：在 `acquire()` 循环入口与每次迭代中调用，heartbeat 已失败时抛出首记录的错误。
- 调用方通过 `acquire()` 看到 `RuntimeLaneError` — 显式暴露。**通过。**

**Token lost：**

- `_refresh_token_sync()` (lane.py:665-705)：DB row 不存在或已过期 → `RuntimeLaneClaimLostError`
- `_refresh_token()` (lane.py:644-663)：捕获 `RuntimeLaneClaimLostError` → `_mark_token_lost(token)` → 重新抛出
- `_mark_token_lost()` (lane.py:905-915)：`token._lost=True`，`token.released=True`，从 held set 移除，唤醒 waiter
- 调用方通过 `token.refresh()` 看到 `RuntimeLaneClaimLostError` — 显式暴露。**通过。**

**Tracked release failure (取消路径)：**

- `_release_token()` (lane.py:707-735)：取消路径使用 `_await_task_after_outer_cancellation(release_task)`。若 DB release 失败（`RuntimeLaneError`），通过 `_LOGGER.exception` 以 ERROR 级别记录 `_LOG_TRACKED_RELEASE_FAILED_AFTER_CANCEL`，然后重新抛出 `CancelledError`。
- 重复 release 幂等：`if token.released: return` (line 715-716)。**通过。**

**Untracked release failure：**

- `_release_untracked_claim()` (lane.py:749-791) — S9 新增两条错误路径：
  - 普通失败（非取消路径，line 775-781）：catch `RuntimeLaneError` → `_LOGGER.warning` 记录 `failure_message` → re-raise。调用方（`acquire()` 中的 CancellationToken/timeout/heartbeat-error/close 检查点）收到 `RuntimeLaneError`。
  - 取消路径（line 782-791）：catch `CancelledError` → `_await_task_after_outer_cancellation` 等待 DB release 完成 → 若 `RuntimeLaneError` → `_LOGGER.exception` 记录 `_LOG_UNTRACKED_RELEASE_FAILED_AFTER_CANCEL` → 重新抛出 `CancelledError`。
- 测试 `test_untracked_release_failure_without_outer_cancel_warns_and_raises` (test_lane.py:666-697)：验证 warning + `RuntimeLaneError` 透传。**通过。**
- 测试 `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` (test_lane.py:621-662)：验证取消路径 logged + `CancelledError` 优先。**通过。**

**模块级常量替换魔法字符串：**

- `_LOG_TRACKED_RELEASE_FAILED_AFTER_CANCEL` (line 34-36)
- `_LOG_UNTRACKED_RELEASE_FAILED` (line 37-39)
- `_LOG_UNTRACKED_RELEASE_FAILED_AFTER_CANCEL` (line 40-43)
- `_CLOSE_REASON_HEARTBEAT_ERROR` (line 44)
- 全部 `Final[str]`，在 `lane.py` 内与 `test_lane.py` 内使用。**通过。**

### 3. LaneController.close(reason=...)

**close() (lane.py:520-549) 完整路径：**

1. 幂等：`if self._close_completed: return` (line 528-529)
2. 设置 `_closed=True`，写入 `_close_reason` (line 530-532)
3. `_wake_waiters()` — 唤醒所有 pending acquire waiter (line 533)
4. 遍历 held tokens (line 534-542)：
   - 每个 token 调用 `release()`
   - 单个 release 失败（`RuntimeLaneError`）记录在 `first_release_error`，循环继续
   - 所有 token 释放尝试完成后进入下一步
5. 取消 heartbeat task（line 542-546）：检查 `is not asyncio.current_task()` 防止在 heartbeat 内调用 close 时死锁; suppress `CancelledError`
6. 设置 `_close_completed=True` (line 547)
7. 若有 release 失败，抛出 `first_release_error` (line 548-549)

- Pending acquire 被唤醒后：循环顶部检查 `if self._closed` (line 472) → `LaneAcquireCancelled(reason=self._close_reason)` — 正确。
- Best-effort release：单个 release 失败不阻止其余 token 释放 — 正确。
- 不发明 Host truth：close 只操作 release / heartbeat cancel / waiter wake，不写 EventLog、不推进状态机、不生成 recovery proof — 正确。

测试覆盖：
- `test_close_cancels_pending_and_releases_held_tokens` (test_lane.py:700-725)：验证 pending 取消、token 释放、新 acquire 拒绝。**通过。**
- `test_close_best_effort_release_continues_after_one_release_failure` (test_lane.py:728-764)：capacity=2，第一枚 release 失败，第二枚成功，`_claim_count == 1`，`first.token.released is False`，`second.token.released is True`。**通过。**
- `test_close_is_idempotent_when_called_twice` (test_lane.py:256-267)：验证幂等。**通过。**

### 4. Runtime import boundary

`dayu/runtime/lane.py` 的 import（lines 9-24）：

- **stdlib**: `asyncio`, `logging`, `os`, `secrets`, `sqlite3`, `time`, `collections.abc.Sequence`, `dataclasses`, `datetime`, `pathlib`, `types.TracebackType`, `typing` — 全部标准库。
- **dayu 契约**: `dayu.contracts.cancellation.CancellationToken` — 公开层中立契约，plan 明确允许。
- **禁止依赖验证**：
  - `grep 'from dayu\.\(engine\|host\|service\|ui\|fins\)' dayu/runtime/lane.py` → **无匹配**
  - 未引入 `EventLog`、`Attempt`、`lease`、`fencing`、`recovery`、`Host state`、`Engine contract`、`Fins document` 语义
  - `_TaskResult = TypeVar("_TaskResult")` — `TypeVar` 来自 stdlib `typing`，仅用于 local generic helper，不引入外部类型

**通过。**

### 5. AGENTS 合规

**类型签名：**

- `_await_task_after_outer_cancellation(task: asyncio.Task[_TaskResult]) -> _TaskResult` — 完整泛型，无 `Any`/`object`/无类型
- `_release_untracked_claim(self, lane_name: str, claim_id: str, *, failure_message: str = ...) -> None` — 完整类型
- 四个模块级常量：`Final[str]` — 完整类型
- 无新增 `Any`、`object`、无类型参数、无类型返回值

**中文 docstring：**

- `_await_task_after_outer_cancellation` (lane.py:973-986)：完整，含 `:param` `:returns` `:raises`
- `_release_untracked_claim` (lane.py:749-768)：已更新，包含新增 `failure_message` 参数说明
- 模块级常量命名自文档化，无需额外 docstring

**README 同步：**

- `dayu/README.md` runtime section (line 145-147 in diff)：同步当前行为——"协作式取消优先于 timeout。heartbeat / token lost 与 release failure 会通过 runtime lane error 或 warning 暴露"
- 未修改 `dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`、根 `README.md` — 它们不在 S9 触发范围内
- 文档只描述当前行为，不写"未来设计" — 合规

**通过。**

### 6. 测试覆盖

S9 plan 要求的覆盖与实现对照：

| Plan 要求 | 测试 | 覆盖确认 |
|---|---|---|
| 重复外层取消不打断已插入 claim cleanup | `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim` | ✓ double cancel，`_claim_count==0`，`CancelledError` 透传 |
| untracked release 普通失败 | `test_untracked_release_failure_without_outer_cancel_warns_and_raises` | ✓ warning + `RuntimeLaneError` 透传 |
| close best-effort，单个 release 失败不阻断其它 | `test_close_best_effort_release_continues_after_one_release_failure` | ✓ 第一枚失败，第二枚成功，`_claim_count==1` |
| Task.cancel 透传，不泄漏额外 claim | `test_task_cancel_propagates_without_extra_claim` (已有) | ✓ `CancelledError` + `_claim_count==1` |
| CancellationToken 取消 | `test_cancellation_token_cancels_waiting_acquire` (已有) | ✓ `LaneAcquireCancelled` |
| claim 已写入但 cleanup release 失败 | `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails` (已更新) | ✓ `CancelledError` 优先 + log fragment + `_claim_count==1` |
| release 被外层取消后等 DB release 完成 | `test_release_token_waits_for_shielded_release_after_outer_cancel` (已有) | ✓ `token.released is True` + `_claim_count==0` |
| untracked release 取消路径 | `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` (已更新) | ✓ log + `CancelledError` |
| heartbeat 错误停止新 acquire | `test_heartbeat_runtime_error_stops_new_acquire` (已有) | ✓ `RuntimeLaneError` 暴露 |
| token lost 不影响其它 token | `test_heartbeat_lost_claim_does_not_close_controller` (已有) | ✓ 只标记丢失 token |
| close 幂等 | `test_close_is_idempotent_when_called_twice` (已有) | ✓ 连续两次 close |
| idle scheduler sleeping task interaction | plan 明确“可交由 S10 覆盖” | N/A — S9 不在 runtime lane 内模拟 Host scheduler |

全部测试通过真实 `LaneController.open()`/`acquire()`/`close()` 入口执行，未走内部 shortcut。并发竞态使用 `asyncio.Event`（`_wait_for_thread_event` helper），避免任意 sleep。

**通过。**

---

## Open Questions

无。

---

## Residual Risk

- `close(reason=...)` 仍是 best-effort release：若底层 SQLite release 失败，失败 claim 只能依赖 TTL stale cleanup。这是 runtime capacity 语义，不提升为 Host recovery proof — 与 plan S9 stop condition 一致。
- lane 仍不承诺 FIFO、公平性、lease/fencing、Attempt owner、takeover 或跨机器分布式容量 — 与 plan 一致。
- `_await_task_after_outer_cancellation` 在极端情况下（DB hung、task 永不完成）会无限循环。这与修改前的 `asyncio.shield(task)` 行为等价（同样无限等待），由 SQLite busy_timeout 提供边界。不构成新风险。
- idle scheduler sleeping task 的 Host dispatch 覆盖留给 S10 — 与 plan 一致。

---

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **六项审查点**: 全部通过
- **测试**: 31 passed, 0 failed (`pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py`)
- **类型检查**: `python -m pyright dayu/runtime tests/runtime` → 0 errors, 0 warnings, 0 informations
- **import boundary**: 只依赖 stdlib + `dayu.contracts.cancellation`，无 Host/Engine/Fins/EventLog/lease/fencing/recovery 语义
