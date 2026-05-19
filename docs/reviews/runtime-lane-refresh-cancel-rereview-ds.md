# Code Review — runtime lane refresh cancellation 修复

## Scope

- Mode: current changes (窄范围)
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main
- Output file: docs/reviews/runtime-lane-refresh-cancel-rereview-ds.md
- Included scope:
  - `dayu/runtime/lane.py`：`_refresh_token()` 中 `CancelledError` 分支（行 663-679）
  - `dayu/runtime/lane.py`：新增日志常量 `_LOG_REFRESH_FAILED_AFTER_CANCEL`（行 44-46）
  - `tests/runtime/test_lane.py`：新增 3 个测试（行 357-501）
- Excluded scope: 非 refresh cancel 相关的其它 diff 改动、未变更代码

## 逐条回答

### 1) 外层 CancelledError 发生后，_refresh_token 是否一定 await 了 refresh_task，不留下 orphan task？

**是，一定 await 了。**

执行链路证据（`dayu/runtime/lane.py`）：

1. `refresh_task = asyncio.create_task(asyncio.to_thread(self._refresh_token_sync, token))`（行 658）创建任务。
2. `await asyncio.shield(refresh_task)`（行 662）在收到外层 `CancelledError` 后进入 `except asyncio.CancelledError as cancelled:` 分支（行 663）。
3. 分支内第一行即调用 `_await_task_after_outer_cancellation(refresh_task)`（行 665）。
4. `_await_task_after_outer_cancellation`（行 993-1014）通过 `while True: await asyncio.shield(task)` 持续等待 task 完成，重复取消仅 catch CancelledError 后 `continue`，直到 `task.done()` 为 True 后通过 `task.result()` 获取结果。

`asyncio.shield` 语义保证内部 `refresh_task` 不会被外层取消传播污染。while 循环保证即使多次重复取消也不会放弃等待。`refresh_task` 是 `asyncio.to_thread`，底层线程必定会完成（或成功返回 `datetime`，或 raise `RuntimeLaneClaimLostError`/`RuntimeLaneError`）。

**唯一理论风险**：解释器崩溃或 event loop 被强制关闭（`loop.close()` 后 running tasks 被丢弃），此时 `to_thread` 线程可能仍运行但无人等待结果。这是 asyncio 共有风险，非本次改动引入，且 `_refresh_token_sync` 内部使用短超时 SQLite 连接（默认 5s busy timeout，`_DEFAULT_BUSY_TIMEOUT_SECONDS`），不会无限阻塞。

**结论：refresh_task 一定被 await 到完成，无 orphan task 风险。**

### 2) 底层 success / RuntimeLaneClaimLostError / RuntimeLaneError 三种结果下，token.expires_at、token lost/released 状态、日志和调用方可见 CancelledError 是否正确？

逐路径走读（全部基于 `dayu/runtime/lane.py` 行 663-679）：

#### Path A：底层 refresh 成功（返回 datetime）

```
_await_task_after_outer_cancellation(refresh_task) 返回 datetime expires_at
→ 未进入任何 except 子句
→ token.expires_at = expires_at（行 678）
→ raise（行 679，bare raise 重抛当前 CancelledError）
```

| 项目 | 结果 | 判定 |
|------|------|------|
| `token.expires_at` | 更新为新值 | ✅ 正确 |
| `token.released` | 保持 False | ✅ 正确 |
| `token._lost` | 保持 False | ✅ 正确 |
| 调用方可见异常 | `CancelledError` | ✅ 正确 |
| 日志 | 无额外日志 | ✅ 正确（正常收尾无需告警） |
| DB 状态 | heartbeat 已刷新（同步函数已 commit） | ✅ 正确 |

#### Path B：底层 raise RuntimeLaneClaimLostError

```
_await_task_after_outer_cancellation(refresh_task) raise RuntimeLaneClaimLostError
→ except RuntimeLaneClaimLostError（行 666）:
    self._mark_token_lost(token)（行 667）
    raise cancelled（行 668）
```

`_mark_token_lost`（行 925-935）执行：
- `token._lost = True`
- `token.released = True`
- `self._held_tokens.pop((token.name, token.claim_id), None)`
- `self._wake_waiters()`

| 项目 | 结果 | 判定 |
|------|------|------|
| `token.expires_at` | 不更新（无意义，token 已 lost） | ✅ 正确 |
| `token.released` | True | ✅ 正确 |
| `token._lost` | True | ✅ 正确 |
| held tokens | 已移除 | ✅ 正确 |
| waiters | 已唤醒 | ✅ 正确 |
| 调用方可见异常 | `CancelledError` | ✅ 正确 |
| 日志 | 无额外日志（token 丢失是正常可恢复路径） | ✅ 正确 |
| DB 状态 | claim row 已不存在（refresh sync 检测到 rowcount=0） | ✅ 正确 |

#### Path C：底层 raise RuntimeLaneError

```
_await_task_after_outer_cancellation(refresh_task) raise RuntimeLaneError
→ except RuntimeLaneError（行 669）:
    _LOGGER.exception(_LOG_REFRESH_FAILED_AFTER_CANCEL, ...)（行 670-676）
    raise cancelled（行 677）
```

| 项目 | 结果 | 判定 |
|------|------|------|
| `token.expires_at` | 不更新（保留旧值） | ✅ 正确（refresh 失败，旧过期时间仍有效） |
| `token.released` | 保持 False | ✅ 正确（claim 仍有效，未被释放） |
| `token._lost` | 保持 False | ✅ 正确 |
| held tokens | 不变 | ✅ 正确 |
| 调用方可见异常 | `CancelledError` | ✅ 正确 |
| 日志 | ERROR 级别含 traceback，包含 lane_name/claim_id | ✅ 正确 |
| DB 状态 | 原始值（refresh sync 已 rollback，无脏数据） | ✅ 正确 |

**三种路径 token 状态、日志、调用方异常传播全部正确。**

### 3) 三个测试是否 deterministic，是否可能死锁或误判？

#### test_refresh_waits_for_shielded_success_after_outer_cancel（行 357-403）

- 同步机制：使用 `Event`（`refresh_started`、`finish_refresh`、`refresh_finished`）代替 sleep 做时序控制。
- 流程：create task → `_wait_for_thread_event(refresh_started)` 确保线程已进入 slow function → `cancel()` × 2 → `finish_refresh.set()` 放行线程 → `await refresh_task` → 断言。
- `_wait_for_thread_event` 内部使用 `asyncio.to_thread(event.wait, timeout=1.0s)`，保证确定性等待。
- 死锁风险：无。`finish_refresh.set()` 在 `await refresh_task` **之前**调用，线程在 `finish_refresh.wait()` 上最多等待 1s 即可返回并设置 `refresh_finished`。
- 双重 cancel 意图：验证 `_await_task_after_outer_cancellation` 的 while 循环能正确处理重复取消。
- 误判风险：低。assert 覆盖 token.expires_at 更新、token.released 状态、refresh_finished 确认底层完成。

#### test_refresh_cancel_cleanup_marks_lost_after_claim_lost（行 406-449）

- 同步机制：同上 Event 三元组。
- `_delete_claim` 在 slow function 内部调用，精准模拟"refresh 过程中 claim row 被他人删除"的场景。
- 死锁风险：无。
- 误判风险：低。assert 覆盖 token.released=True、`_claim_count(db_path) == 0`（确认 DB 中 claim 已清除）。

#### test_refresh_cancel_cleanup_logs_runtime_error_and_preserves_cancel（行 452-501）

- 同步机制：同上 Event 三元组。
- `caplog.set_level(logging.ERROR, logger="dayu.runtime.lane")` 精确设置捕获级别。
- 日志断言：使用 `_REFRESH_FAILED_LOG_FRAGMENT in caplog.text` 子串匹配，可靠。
- 死锁风险：无。
- 误判风险：低。assert 覆盖 token.released 保持 False、DB claim 数不变（line 498）、日志片段存在。

**三个测试均为 deterministic，无死锁风险，无误判可能。同步原语使用 Event + timeout，无 sleep-based 竞态。**

### 4) 是否有 blocker？

**无 blocker。**

以下为逐项排查结果：

| 检查项 | 结果 |
|--------|------|
| _refresh_token 一定 await refresh_task | ✅ 通过 `_await_task_after_outer_cancellation` 的 shield+while 循环保证 |
| token 状态一致性（三种路径） | ✅ 每种路径下 token 状态与 DB 状态一致 |
| CancelledError 始终传播给调用方 | ✅ 三种路径均 raise cancelled 或 bare raise |
| 日志在错误路径可观测 | ✅ RuntimeLaneError 路径有 ERROR 级别日志含 lane_name/claim_id |
| `_mark_token_lost` 已正确调用 | ✅ ClaimLost 路径调用了，RuntimeLaneError 路径正确不调用 |
| 不存在资源泄漏 | ✅ 底层 SQLite connection 在 `finally: connection.close()` 释放 |
| 测试覆盖三条路径 | ✅ success / ClaimLost / RuntimeLaneError 各一条测试 |
| 测试 deterministic | ✅ Event 同步，无 sleep 竞态 |
| 与已有 claim cancel 模式一致 | ✅ 与 `_acquire_claim`（行 571）、`_release_token`（行 744、804）使用相同 `_await_task_after_outer_cancellation` 模式 |

额外确认的 **非 blocker 但值得记录的边界**：

- `_await_task_after_outer_cancellation` 的 `task.done()` 分支（行 1013）中 `task.result()` 在 task 已完成且结果为例外时不会吞掉异常——该异常会正确传播到 `_refresh_token` 的内层 try/except。已验证 `refresh_task`（`asyncio.to_thread` 包装）不会被取消（外层 cancel 被 shield 隔离），故 `task.result()` 只会返回 datetime / RuntimeLaneClaimLostError / RuntimeLaneError，不会意外抛出 CancelledError。
- `raise cancelled` 和 `bare raise` 在 `except asyncio.CancelledError as cancelled:` 块内语义正确，均重抛原始 CancelledError 实例。Python 3.11 对 except 块内 bare raise 有完善支持。

## Conclusion

**PASS** — 无 blocker。refresh cancellation 修复在三种底层结果路径下 token 状态、日志与异常传播均正确，三个测试确定性覆盖三条路径，不存在 orphan task 风险。
