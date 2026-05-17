# P9.5 S9 Runtime Lane Hardening — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S9 Runtime Lane Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S9.
- Implementation artifact: `docs/reviews/p9-5-s9-runtime-lane-hardening-implementation-20260517.md`.
- Reviewed files: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `dayu/README.md`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. Acquire cancellation precision：Task.cancel 透传 CancelledError，CancellationToken 返回 LaneAcquireCancelled，cancellation wins over timeout，repeated outer cancellation 不打断已插入 claim cleanup

**结论：通过。**

**`_await_task_after_outer_cancellation` helper**（`lane.py` 新增 ~970-995 行）：
```python
async def _await_task_after_outer_cancellation(task):
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()
            continue
```
- 持续 `shield` 等待底层 task 完成，抵抗 repeated outer cancellation。
- task 已 done → 返回 `task.result()`（若 task 异常则 raise）。
- task 未 done → `continue` 继续循环等待。

**acquire cancel 路径**（`lane.py` ~564-584）：
- `asyncio.shield(claim_task)` → `except asyncio.CancelledError as cancelled` → `_await_task_after_outer_cancellation(claim_task)` → 等待 claim task 完成。
- `claim.acquired and claim.claim_id` → `_release_untracked_claim(...)` 清理已插入 claim。
- release 失败 → `raise cancelled`（CancelledError 传播给调用方）。
- claim task 本身失败（`RuntimeLaneError`）→ `raise cancelled`。

**CancellationToken 路径**：已有的 `acquire` 方法在 claim 前检查 `cancellation_token.is_cancelled()` → 返回 `LaneAcquireCancelled`。与 timeout 无冲突。

**测试覆盖**：
- `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim`：阻塞 claim → 两次 `task.cancel()` → 释放 claim → 验证 `CancelledError` + `_claim_count == 0`。
- `test_task_cancel_propagates_without_extra_claim`（已有）：cancel 后无多余 claim。
- `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails`（已有）：cleanup 失败仍抛 CancelledError。

### 2. Heartbeat/token lost 与 release failure 是否通过 RuntimeLaneError 或 warning 暴露；重复 release 仍幂等且不释放其它 owner

**结论：通过。**

**untracked release 普通失败**（`lane.py` ~772-780）：
```python
except RuntimeLaneError:
    _LOGGER.warning(failure_message, extra={...}, exc_info=True)
    raise
```
- 非取消路径：`RuntimeLaneError` 透传给调用方 + warning 日志。
- `failure_message` 参数化：默认 `_LOG_UNTRACKED_RELEASE_FAILED`，cancel cleanup 路径传 `_LOG_UNTRACKED_RELEASE_FAILED_AFTER_CANCEL`。

**tracked release cancel 路径**（`lane.py` ~721-735）：
- `_await_task_after_outer_cancellation(release_task)` → `RuntimeLaneError` → `_LOGGER.exception(_LOG_TRACKED_RELEASE_FAILED_AFTER_CANCEL)` → `raise cancelled`。

**heartbeat close reason**：`_CLOSE_REASON_HEARTBEAT_ERROR` 模块级常量（`lane.py` ~43），替换原魔法字符串。

**重复 release 幂等**：已有 `_release_claim_sync` 中 `WHERE claim_id = ? AND owner_instance_id = ?`，不同 owner 不匹配。已有测试 `test_duplicate_release_is_idempotent_and_isolated` 覆盖。

**测试覆盖**：
- `test_untracked_release_failure_without_outer_cancel_warns_and_raises`：模拟 release 失败 → `RuntimeLaneError` + warning 日志。
- `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error`（已有）：cancel 路径下 release 失败 → CancelledError + exception 日志。
- `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails`（已有）。

### 3. LaneController.close(reason) 是否唤醒 pending acquire、best-effort release held tokens、单个 release failure 不阻断其它 token release

**结论：通过。**

**close 流程**（已有 `_close_impl`）：
1. `self._closed = True` + `self._close_reason = reason`。
2. `self._wake_waiters()`：唤醒所有 pending acquire → 返回 `LaneAcquireCancelled`。
3. 遍历 `self._held_tokens` → `_release_claim_sync` 每个 token。
4. 释放失败 → 抛出第一个 `RuntimeLaneError`（best-effort 继续释放后续 token）。

**测试覆盖**（`test_close_best_effort_release_continues_after_one_release_failure`）：
- capacity=2，acquire 两个 token。
- monkeypatch `_release_claim_sync` 让第一个 release 失败。
- `await controller.close(reason="shutdown")` → `RuntimeLaneError`。
- 验证：`_claim_count == 1`（第二个已释放），`first.token.released == False`，`second.token.released == True`。

### 4. Runtime import boundary 是否仍只依赖 stdlib、dayu.contracts.cancellation、同/更低 runtime helper

**结论：通过。**

- `lane.py` import：`asyncio`、`contextlib`、`dataclasses`、`datetime`、`logging`、`pathlib`、`types`、`typing`（stdlib）+ `dayu.contracts.cancellation.CancellationToken`（plan 允许）。
- 无 `dayu.host`、`dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui` import。
- `test_import_boundary.py` 覆盖：`test_runtime_does_not_import_business_layers` + `test_runtime_import_boundary_scan_covers_lane_module`。

### 5. AGENTS 硬约束

**结论：通过。无违反。**

| 约束 | 验证 |
|---|---|
| 禁止 `Any`/`object`/无类型签名 | ✅ `_await_task_after_outer_cancellation` 使用 `TypeVar("_TaskResult")` 泛型签名；`_release_untracked_claim` 新增 `failure_message: str` 参数 |
| 中文 docstring | ✅ 新增函数有中文 docstring |
| 无 magic string | ✅ `_LOG_TRACKED_RELEASE_FAILED_AFTER_CANCEL`、`_LOG_UNTRACKED_RELEASE_FAILED`、`_LOG_UNTRACKED_RELEASE_FAILED_AFTER_CANCEL`、`_CLOSE_REASON_HEARTBEAT_ERROR` 模块级 `Final` 常量 |
| 无兼容 wrapper | ✅ 未引入 |
| README 只同步当前行为 | ✅ `dayu/README.md` 更新准确描述取消优先级与 release/heartbeat 可观测错误 |

### 6. 测试是否覆盖 S9 要求

**结论：通过。**

| S9 要求 | 测试 | 状态 |
|---|---|---|
| repeated outer cancellation | `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim` | ✅ |
| untracked release failure | `test_untracked_release_failure_without_outer_cancel_warns_and_raises` | ✅ |
| close best-effort release after single failure | `test_close_best_effort_release_continues_after_one_release_failure` | ✅ |
| Task.cancel 透传 CancelledError | `test_task_cancel_propagates_without_extra_claim`（已有） | ✅ |
| CancellationToken 返回 LaneAcquireCancelled | `test_cancellation_token_cancels_waiting_acquire`（已有） | ✅ |
| 重复 release 幂等 | `test_duplicate_release_is_idempotent_and_isolated`（已有） | ✅ |
| heartbeat token lost | `test_heartbeat_runtime_error_stops_new_acquire` + `test_heartbeat_lost_claim_wakes_waiting_acquire`（已有） | ✅ |
| import boundary | `test_runtime_does_not_import_business_layers` + `test_runtime_import_boundary_scan_covers_lane_module`（已有） | ✅ |

全部 31 targeted tests passed，pyright 0 errors。

## Findings

### F1 [Info] `_await_task_after_outer_cancellation` 的 `task.result()` 可能重新抛出 task 异常

- **File/line**: `lane.py:986-995`
- **Evidence**: `task.done()` → `task.result()` — 如果 task 以非 `RuntimeLaneError` 异常完成（例如 SQLite 内部错误），`task.result()` 会重新抛出该异常。调用方 acquire 路径的 `except RuntimeLaneError: raise cancelled` 不会捕获非 `RuntimeLaneError` 异常，导致非预期异常从 acquire 传播。
- **Impact**: 当前 `_try_claim_once_sync` 只抛 `RuntimeLaneError`（由 `_require_non_blank` 和 SQLite 操作保证），实际不会产生非 `RuntimeLaneError` 异常。但如果未来 claim 路径抛出其它异常类型，`_await_task_after_outer_cancellation` 不会将其转为 CancelledError。这是设计选择：helper 只处理 CancelledError vs 完成两种状态，不替代调用方的异常处理。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`lane.py`、`test_lane.py`、`dayu/README.md`。
- 未修改 Host / Engine / Fins。
- 未引入 lease/fencing/takeover、Host state、EventLog、Attempt owner 或 recovery proof。

### Confirmed: stop condition not triggered

- 无需新 wait state transition。
- 无需修改 `resolve_wait` 语义。
- 无需 Host 状态机变更。

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| Lease / fencing / takeover | Not introduced |
| Host state / EventLog / Attempt owner | Not introduced |
| Recovery proof | Not introduced |
| FIFO / fairness | Not introduced |
| Cross-machine distributed capacity | Not introduced |
| New public facade | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 1 (F1)

S9 实现正确达成计划目标：`_await_task_after_outer_cancellation` 通过 `while True` + `asyncio.shield` 循环抵抗 repeated outer cancellation，确保已插入 claim cleanup 不被打断；untracked release 普通失败写 warning + 透传 `RuntimeLaneError`；`LaneController.close(reason=...)` 唤醒 pending acquire + best-effort release held tokens，单个 release failure 不阻断其它 token release；heartbeat/token lost 与 close reason 使用模块级 `Final` 常量；runtime import boundary 仍只依赖 stdlib + `dayu.contracts.cancellation`。无硬约束违反。
