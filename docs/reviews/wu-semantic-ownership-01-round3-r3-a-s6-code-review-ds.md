# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S5 accepted commit `1b589ee6`（S5 acceptance record）之后的 S6 implementation workspace changes
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s6-code-review-ds.md`
- Included scope:
  - Production: `dayu/host/_wait_observation.py`（新增 bounded observation runner、token gate、cap、shared deadline）、`dayu/host/waiting.py`（`ExpireWaitInput`/`ExpireWaitResult`、`_expire_wait_in_transaction` helper、late result 拒绝、promotion wake 统一）、`dayu/host/wait_adapter.py`（poller expiry 路径、bounded observation 集成、stuck abandon timeout marker、supervisor shared close deadline）、`dayu/host/api.py`（policy 新增 bounded budget/runtime protocol）、`dayu/host/command.py`（internal `expire_wait` handoff）、`dayu/host/durable/state.py`（`mark_wait_record_poll_abandon_timeout`）、`dayu/host/open_host.py`（poller factory 注入 observation runner）
  - Tests: `tests/host/test_wait_observation_runner.py`、`tests/host/test_wait_expiry_closeout.py`、更新 `test_wait_adapter_polling.py`/`test_wait_poller_runtime.py`/`test_resolve_wait_command.py`/`test_wait_callback.py`/`test_wait_cancel_late_result.py`/`test_public_open_host_options.py`
  - Docs: `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
- Excluded scope: `dayu/fins/` diff 为空；S3 health、S4 recovery、S5 cancel、Service/CLI/Engine 均无变更。`dayu/host/__init__.py` 未修改（新增类型为 Host-internal owner，不扩大 package public surface）。
- Parallel review coverage: 无。

## Review Method Summary

沿 S6 review focus 逐项走读完整生产调用链：

1. **expiry helper**：`_expire_wait_in_transaction()` 在 `waiting.py` 中接收 caller-provided `HostTransaction`；直接调用 `classify_wait_time_boundary()` 判定 EXPIRED；构造固定 `ResolveWaitFailedOutcome(ToolResultFailure(error="wait_deadline_expired"))` → `fail_run_from_waiting_in_transaction(RUN_FAILED, WAIT_FAILED)`；expiry identity 由 `(wait_id, boundary_field, boundary_value, reason)` 的 sha256 digest 派生，不依赖 source/actor。

2. **poller expiry vs observation timeout**：poller `_handle_time_boundary()` 在 EXPIRED 时调用 `resolver.expire_wait(ExpireWaitInput(...))` → FAILED；observation timeout 时构造 `WaitPollLost(ResolveWaitLostOutcome(reason_code="wait_observation_timeout"))` → `_resolve_claimed_wait(record, timeout_result)` → LOST。两条路径分别产出 `RUN_FAILED/WAIT_FAILED` 与 `RUN_LOST/WAIT_LOST`，互不混淆。

3. **late result after expiry**：`DefaultHostResolveWaitService._resolve_in_transaction()` 检查 `wait_record.status == FAILED AND resolve_idempotency_key.startswith("wait-expiry-")` → `_reject_late_result(WAIT_EXPIRED)`（`waiting.py:871-883`）。expiry 路径的 resolve 保证 projection catch-up 与 promotion wake 在向 caller 抛 `INVALID_STATE` 之前完成。

4. **observation thread 无 durable authority**：`_run_observation` 只持有 `operation` callable（adapter + immutable wait snapshot）和 `result_queue`；publish 通过 `_ObservationToken` 的 gated `_publish()` 在线性化 lock 下验证 token 仍 ACTIVE、generation 未变、runner 未 close 后才写 `result_queue`。late publish（token 已 INVALIDATED 或 runner 已 close）→ `_dropped_count += 1`、返回 `False`。

5. **outstanding cap / shared close deadline**：`WaitObservationRunner._start_observation()` 在 `len(self._tokens) >= max_outstanding_adapter_calls` 时返回 `WaitObservationCapacityExceeded`，不创建线程。`drain_until(deadline_monotonic)` 对所有 tracked threads 使用同一个 monotonic budget，不按线程数倍增。`WaitPollerSupervisor.close()` 用 `begin_close()` INVALIDATE 全部 token，再用 `time.monotonic() + close_drain_timeout_seconds` 作为一次 shared deadline join。

6. **Fins/Engine/Service/CLI 无 diff**：`git diff --name-only -- dayu/fins/` 空输出；`git diff --stat HEAD` 的变更仅在 `dayu/host/` 下。

## 逐项验证详情

### FAILED deadline-expiry 与 LOST observation-timeout 分离

**expiry 路径**（`waiting.py` 新增 `_expire_wait_in_transaction`）：
- 入参：`transaction: HostTransaction, input: ExpireWaitInput`
- 读取 wait record → 校验 WAITING 状态 → `classify_wait_time_boundary` → EXPIRED 分支
- 构造 `ResolveWaitFailedOutcome(ToolResultFailure(ok=False, error="wait_deadline_expired", message=<中文期限说明>, hint=None, meta=None), payload_ref=None)`
- expiry identity：`sha256({"wait_id", "boundary_field", "boundary_value", "reason": "wait_deadline_expired"})` → key = `"wait-expiry-" + digest_suffix`
- 调用 `fail_run_from_waiting_in_transaction(RUN_FAILED, WAIT_FAILED)` → 记录幂等 result
- 返回 `ExpireWaitResult(transition, queue_promotion_session_id=session_id)`

**observation timeout 路径**（`wait_adapter.py` `WaitPoller.poll_once()`）：
- `observation is WaitObservationTimedOut` → 检查 lifecycle gate
- 构造 `WaitPollLost(ResolveWaitLostOutcome(reason_code="wait_observation_timeout"))`
- 调用 `self._resolve_claimed_wait(record, timeout_result)` → 进入 `resolve_wait` LOST pipeline
- 终态：`RUN_LOST, WAIT_LOST`

**poller deadline-first**：`_handle_time_boundary()` 在 `EXPIRED` 时调用 `resolver.expire_wait(ExpireWaitInput(wait_id, observed_at, actor, source=POLL))`，不调用 adapter，`provider_call=0`。该行为由更新后的 `test_expired_poll_wait_is_released_before_provider_observation` 覆盖。

### late result 在 expiry commit/projection/promotion 后拒绝

**direct/callback resolve 路径**（`waiting.py:867-883`）：
```python
if wait_record.status in (RESOLVED, FAILED):
    if (wait_record.status == FAILED
        and wait_record.resolve_idempotency_key is not None
        and wait_record.resolve_idempotency_key.startswith(_WAIT_EXPIRY_KEY_PREFIX)):
        return self._reject_late_result(
            transaction=transaction,
            wait_record=wait_record,
            request=request,
            rejection_reason=WaitLateRejectionReason.WAIT_EXPIRED,
        )
```

**commit→projection→promotion 顺序**（`waiting.py:754-763`）：
- `run_write` 返回 → `catch_up_projection_best_effort()` → `_wake_queue_promotion_after_commit(session_id)` → 然后才 raise `INVALID_STATE`（对 late result）

`test_resolve_wait_rejects_expired_wait_from_common_owner` 与 `test_expired_callback_is_rejected_by_resolve_owner` 覆盖 caller 收 `INVALID_STATE` 但 durable Wait/Run 已 FAILED 且 late diagnostic 已提交。

### expiry helper 只消费 caller-provided transaction

`_expire_wait_in_transaction(transaction, input)` 的签名明确要求 caller 传入已打开的 `HostTransaction`：
- 不创建嵌套 transaction
- 不调用 public `resolve_wait()`
- 在 transaction 内完成边界检查 + `fail_run_from_waiting_in_transaction()` + 幂等记录
- `test_expiry_helper_owns_failed_terminal_and_stable_replay` 直接把 `host._transaction_runner().run_write(lambda transaction: _expire_wait_in_transaction(transaction, input))` 传入，验证 helper 是纯函数。

### observation thread 不持 durable authority

`_run_observation()`（`_wait_observation.py:381-403`）：
- 只接收 `runner: WaitObservationRunner, token: _ObservationToken, operation: Callable`
- `operation` 是 adapter 的 `partial(adapter.poll_wait, record)` —— 只持 immutable `WaitRecordRow` snapshot
- 成功/异常后调用 `runner._publish(token, result)`，不直接调用 resolver 或操作 SQLite
- `_publish()` 在线性化 lock 下验证 token 仍 ACTIVE、generation 匹配、runner 未 close → 通过才写入 `result_queue`

late publish 拒绝：`_publish()` 检测到 `token.state != ACTIVE` 或 `self._closed` 或 `token.generation != self._generation` → `_dropped_count += 1` → `return False`。测试 `test_stuck_poll_times_out_to_lost_and_late_result_is_dropped` 验证 provider 释放后 `dropped_count=1`，Wait 保持 LOST。

### outstanding cap / shared close deadline 有界

**cap**（`_wait_observation.py:297-302`）：
```python
if len(self._tokens) >= self._max_outstanding_adapter_calls:
    self._capacity_rejections += 1
    return WaitObservationCapacityExceeded()
```

`test_outstanding_cap_does_not_spawn_second_thread` 验证 cap=1 时第二次 observe 返回 `WaitObservationCapacityExceeded`，不创建线程，不调用 operation。

**shared close deadline**（`WaitPollerSupervisor.close()`，`wait_adapter.py:1642-1700`）：
```python
self._observation_runner.begin_close()
deadline = time.monotonic() + self._policy.close_drain_timeout_seconds
if thread is not None:
    thread.join(max(0.0, deadline - time.monotonic()))
observations_drained = self._observation_runner.drain_until(deadline)
```

- `drain_until(deadline)` 对所有 token.thread 使用同一个 budget，不按线程数倍增
- 预算耗尽后仍 `CLOSING`，`_on_observations_drained` 回调在最后一个线程 finally 后才转 `STOPPED`

`test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 验证：poller + 两个 provider 均阻塞时 close 在 0.03s 预算内返回（`elapsed < 0.15`），状态为 `CLOSING`且 `live_count=2`；依次释放后收敛到 `STOPPED`。

**policy 校验**：`WaitPollerRuntimePolicy.__post_init__` 拒绝 `None`、NaN、infinity、零、负数 close timeout；新增 `adapter_call_timeout_seconds` 和 `max_outstanding_adapter_calls` 同样 finite-positive 校验。`_require_positive_float` 收窄为同时检查 `math.isfinite()`。

### Scope creep 扫描

- `dayu/fins/` diff 空（controller 独立确认 `git diff --name-only -- dayu/fins/` 零输出）
- `dayu/host/_execution_health.py`（S3）、`dayu/host/recovery.py`（S4）、`dayu/host/dispatch.py`（S5）、`dayu/host/command.py`（cancel 部分）未修改
- `dayu/service/`、`dayu/cli/`、`dayu/engine/` 无变更
- `dayu/host/__init__.py` 未修改：新增 expiry/observation 类型为 Host-internal owner
- `_release_expired_or_invalid_boundary` 已彻底删除；`WAIT_EXPIRED` 仅用于 `WaitLateRejectionReason` 枚举

## Findings

未发现实质性问题。

所有 review focus 的代码实际行为与 plan Slice S6 冻结契约一致：

- FAILED deadline-expiry 与 LOST observation-timeout 完全分离：前者走 `_expire_wait_in_transaction(FAILED)`，后者走 `WaitPollLost → resolve_wait(LOST)`。poller deadline-first 路径在 expiry 时不调用 provider adapter
- late result 在 expiry commit → projection catchup → promotion wake 全部完成后才向 caller 抛 `INVALID_STATE`，durable Wait/Run 已 FAILED
- `_expire_wait_in_transaction(transaction, input)` 只消费 caller-provided transaction，不打开嵌套 transaction、不调用 public resolver
- observation thread（`_run_observation`）不持 durable authority；`_publish()` 在线性化 lock 下通过 token state/generation/runner-closed 三重 gate 拒绝 late publish
- outstanding cap（`max_outstanding_adapter_calls`）与 shared close deadline（`drain_until` 一次 monotonic budget）均有界；close 不按线程数倍增预算
- `dayu/fins/` diff 为空；Engine/Service/CLI 无变更

## Open Questions

无。

## Residual Risk

- 不合作的同步 provider daemon thread 在 timeout 后仍可能运行到进程退出。本 slice 已用 outstanding cap、INVALIDATED token、dropped publish 与无 durable authority 把 Host 风险有界化。provider cooperative cancellation 与 Fins adapter reverse-dependency 搬迁由 controller 已指定的 R3-D owner 处理。
- Legacy `_release_expired_or_invalid_boundary` 已删除；旧 poller backoff helper 不再存在，无未清理 dead code。
