# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-mimo.md
- Included scope: dayu/host/wait_adapter.py、dayu/host/durable/state.py、tests/host/test_wait_adapter_polling.py、tests/host/test_wait_poller_runtime.py、docs/host/design.md、dayu/host/README.md、tests/README.md
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 详细审查

### 1. Root cause 证据支撑

**结论：成立，由日志/DB/代码直接证据支撑。**

背景 artifact `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-fix-codex.md` 提供了完整证据链：

- **真实日志**：`workspace/tmp/wu-cli-smoke-01-manual/interactive.log`
  - 目标 run：`run-806e7c850ae349ce9d103980202a59b5`
  - poller 观察链路：`18:21:36 not_ready` → `18:22:06 not_ready` → `18:23:06 not_ready` → `18:25:07 ready`
  - Fins 在 `18:23:11` 已完成，Host 直到 `18:25:07` 才 resolve_wait，延迟约 116 秒
  - final answer 后仍持续 `claimed=0` / `observed=0` 空轮询摘要

- **Host DB**：`workspace/.dayu/host/dayu_host.sqlite3`
  - wait record：`poll_last_outcome=not_ready`，`poll_backoff_attempt=0`（修复后）
  - terminal 后无 pending poll wait，确认后续日志是 supervisor 空轮询

- **代码同源证据**：
  - `FinsIngestionWaitPollAdapter.poll_wait()` 将 `PENDING/RUNNING` 映射为 `WaitPollNotReady`
  - 旧代码 `_release_with_backoff()` 导致正常 not_ready 进入 30/60/120 秒指数退避

### 2. 通用 poll path correctness

**结论：成立。无 callback/no wakeup 的纯 poll 也按 policy cadence observe ready。**

关键代码路径：

1. `_release_not_ready()` (wait_adapter.py:1208-1233)
   - 设置 `backoff_attempt=0`，不增加错误 backoff
   - 设置 `next_observe_at = now + not_ready_observe_interval_seconds`（默认 1 秒）
   - 不写入 `last_error_code` / `last_error_message`

2. `claim_wait_record_for_poll()` (state.py:2142-2228)
   - claim 条件：`(poll_next_observe_at IS NULL OR poll_next_observe_at <= ?)`
   - 确保 next_observe_at 到期后可被再次 claim

3. 测试覆盖：`test_pure_poll_observes_ready_after_not_ready_policy_cadence` (test_wait_poller_runtime.py:600-641)
   - 使用 `_ManualClock` 推进时间
   - 验证 not_ready 后按 policy cadence 复查并 resolve

### 3. idle/no-active-wait 是否真的减少 DB 空查

**结论：是的，不仅删日志，还真正减少了 DB 查询。**

关键实现：

1. `_next_loop_interval_seconds()` (wait_adapter.py:1541-1558)
   - 无活动时返回 `idle_poll_interval_seconds`（默认 5 秒）或 `next_poll_delay_seconds`
   - 有活动时返回 `poll_interval_seconds`（默认 1 秒）

2. `_sleep_until_next_poll()` (wait_adapter.py:1454-1464)
   - 使用 `self._wakeup_event.wait(interval_seconds)` 阻塞等待
   - 阻塞期间不调用 `poll_once()`，不查询 DB

3. `_next_poll_delay_seconds()` (wait_adapter.py:1036-1056)
   - 空轮询时读取 `read_next_wait_record_poll_due_at()` 返回下一次 due 时间
   - 返回 `max(delay_seconds, 0.0)`，确保非负

4. 测试覆盖：`test_background_loop_uses_idle_interval_after_empty_round` (test_wait_poller_runtime.py:529-555)
   - 设置 `idle_poll_interval_seconds=0.2`
   - 验证空轮询后 `poll_rounds` 不再快速增长

### 4. next due sleep 计算正确性

**结论：正确，claim expiry / poll_next_observe_at / timezone handling 安全。**

关键实现：

1. `read_next_wait_record_poll_due_at()` (state.py:2086-2139)
   - SQL 使用 `MIN(CASE ... END)` 取最早 due 时间
   - CASE 逻辑：
     - 有未过期 claim → 返回 `poll_claim_expires_at`
     - 有 next_observe_at → 返回 `poll_next_observe_at`
     - 否则 NULL
   - WHERE 条件：只查询 active wait（`status=WAITING` 或 `status=CANCELLED AND poll_abandoned_at IS NULL`）

2. 时间比较：
   - 所有 timestamp 使用 UTC 格式 `%Y-%m-%dT%H:%M:%S.%fZ`
   - `parse_utc_timestamp()` 返回 timezone-aware UTC datetime
   - 比较在同一 timezone 下进行，无 timezone 转换风险

3. 边界处理：
   - `next_due_at is None` → 返回 `None`，supervisor 使用 `idle_poll_interval_seconds`
   - `delay_seconds < 0` → `max(delay_seconds, 0.0)` 确保非负

### 5. wakeup 是否 race-safe

**结论：race-safe，不会丢新 wait 信号或造成 busy loop。**

关键实现：

1. `wakeup()` (wait_adapter.py:1318-1324)
   - 使用 `self._wakeup_event.set()` 唤醒等待线程
   - `threading.Event.set()` 是线程安全的

2. `_sleep_until_next_poll()` (wait_adapter.py:1454-1464)
   - `self._wakeup_event.wait(interval_seconds)` 阻塞等待
   - 被唤醒后 `self._wakeup_event.clear()` 重置事件
   - 如果 `wakeup()` 在 `wait()` 之前调用，`wait()` 立即返回 `True`

3. 竞态场景分析：
   - **场景 A**：`wakeup()` 在 `wait()` 之前调用
     - `Event` 状态为 `set`
     - `wait()` 立即返回 `True`
     - `clear()` 重置事件
     - 无 busy loop
   - **场景 B**：`wakeup()` 在 `wait()` 期间调用
     - `wait()` 被唤醒返回 `True`
     - `clear()` 重置事件
     - 无信号丢失
   - **场景 C**：`wakeup()` 在 `clear()` 之后、下一次 `wait()` 之前调用
     - `Event` 状态为 `set`
     - 下一次 `wait()` 立即返回 `True`
     - 无信号丢失

4. close() 中的 wakeup (wait_adapter.py:1326-1381)
   - `close()` 先设置 `self._close_event.set()`
   - 再设置 `self._wakeup_event.set()`
   - 确保 sleep 被打断后 loop 能检查 close_event 退出

### 6. backoff 边界是否保留

**结论：保留，adapter error/missing adapter/resolve error/shutdown skipped 的重试语义完整。**

关键实现：

1. `_release_with_backoff()` (wait_adapter.py:1166-1206)
   - 仍然被以下场景调用：
     - `adapter is None` (missing adapter) → line 903
     - `adapter.poll_wait()` 抛异常 (adapter error) → line 922
     - `resolve_status` 非 UPDATED (resolve error) → line 969
     - `shutdown_skipped` → line 1245 (`_release_shutdown_skipped` 调用)
   - 写入 `backoff_attempt = record.poll_backoff_attempt + 1`
   - 写入 `next_observe_at = now + _backoff_delay_seconds(next_attempt, policy)`

2. `_release_not_ready()` (wait_adapter.py:1208-1233)
   - 只用于正常 not_ready 场景
   - 设置 `backoff_attempt=0`，不增加错误 backoff
   - 设置 `next_observe_at = now + not_ready_observe_interval_seconds`

3. 边界清晰：
   - 正常 not_ready → 短间隔复查，不增加 backoff
   - 错误场景 → 指数退避，增加 backoff

### 7. tests/pyright/README 是否充分

**结论：充分。**

1. **测试覆盖**：
   - `test_poll_adapter_not_ready_leaves_wait_active`：验证 not_ready 不增加 backoff
   - `test_poll_adapter_empty_round_does_not_log_poll_summary`：验证空轮询不输出日志
   - `test_background_loop_uses_idle_interval_after_empty_round`：验证 idle interval
   - `test_wakeup_interrupts_idle_after_new_wait_is_created`：验证 wakeup 打断
   - `test_pure_poll_observes_ready_after_not_ready_policy_cadence`：验证纯 poll 按 cadence 复查

2. **pyright**：
   - 背景 artifact 记录：`0 errors, 0 warnings, 0 informations`
   - 新增代码类型完整：`_ReadNextPollDueAtOperation` 返回 `str | None`，`_release_not_ready` 返回 `int`

3. **README 更新**：
   - `dayu/host/README.md`：更新了 poller 描述，包含 next-observe、idle、wakeup 语义
   - `docs/host/design.md`：更新了 poll adapter 设计描述
   - `tests/README.md`：更新了测试覆盖描述

## Open Questions

无。

## Residual Risk

1. **真实网络 smoke**：本次修复基于真实日志和 DB 证据，但未重复真实 SEC 下载验证。建议按背景 artifact 中的"真实验证建议"进行端到端测试。

2. **idle_poll_interval_seconds 默认值**：默认 5 秒。没有 wakeup 的"全新 wait 初次出现"最多可能等待 5 秒才被首次 observe。已有 active wait 的 not-ready 复查不受影响（使用 1 秒 interval）。

3. **并发 wakeup**：多个线程同时调用 `wakeup()` 是安全的（`Event.set()` 幂等），但可能导致 supervisor 在一次 sleep 中被唤醒多次。这不会造成问题，因为 `clear()` 在 `wait()` 返回后立即执行。
