# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S6 Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `1b589ee6`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s6-code-review-mimo.md`
- Included scope: `dayu/host/waiting.py`, `dayu/host/_wait_observation.py`, `dayu/host/wait_adapter.py`, `dayu/host/command.py`, `dayu/host/open_host.py`, `dayu/host/api.py`, `dayu/host/durable/state.py`, tests
- Excluded scope: `dayu/fins/`, `dayu/engine/`, `dayu/service/`, `dayu/cli/`

## Findings

未发现实质性问题。

## Review Analysis

### 1. FAILED deadline-expiry vs LOST observation-timeout 分离

两条路径完全独立：

- **FAILED (deadline-expiry)**: `_expire_wait_in_transaction()` (waiting.py:1330) 构造 `ResolveWaitFailedOutcome(ToolResultFailure(error="wait_deadline_expired"))` 并调用 `fail_run_from_waiting_in_transaction()` → `RunStatus.FAILED` + `WaitRecordStatus.FAILED`。
- **LOST (observation-timeout)**: `WaitPoller` (wait_adapter.py:1098-1131) 在 `WaitObservationTimedOut` 时构造 `ResolveWaitLostOutcome(reason_code="wait_observation_timeout")` 并调用 `_resolve_claimed_wait()` → 通过既有 resolve pipeline 的 LOST path → `RunStatus.LOST` + `WaitRecordStatus.LOST`。

两者使用不同的 outcome 类型、不同的 reason code、不同的 terminal status，由不同的 owner 产生。Poller 在 boundary EXPIRED 时走 expiry helper，observation timeout 时走 LOST resolve，不混用。

### 2. Late result 在 expiry commit/projection/promotion 后拒绝

`DefaultHostResolveWaitService.resolve_wait()` (waiting.py:752-766) 的关键顺序：

1. `self._transaction_runner.run_write(...)` — transaction commit
2. `catch_up_projection_best_effort(self._projection_catchup_port)` — projection catch-up
3. `self._wake_queue_promotion_after_commit(result.queue_promotion_session_id)` — promotion wake
4. `if isinstance(result, _LateRejectResult): raise HostApiError(...)` — 拒绝

在 `_resolve_in_transaction()` 中，EXPIRED boundary 路径 (waiting.py:918-948) 先调用 `_expire_wait_in_transaction()` 提交 terminal fact，再调用 `_reject_late_result()` 写 `WAIT_LATE_RESULT_REJECTED` diagnostic，返回 `_LateRejectResult(queue_promotion_session_id=expiry.queue_promotion_session_id)`。因此 caller 收到 `INVALID_STATE` 时，durable Wait/Run 已 FAILED、projection 已 catch-up、promotion wake 已发出。

### 3. Expiry helper 只消费 caller-provided transaction

`_expire_wait_in_transaction(transaction, input)` (waiting.py:1330) 接收调用方已打开的 `HostTransaction`，所有 durable 操作都在该 transaction 内执行：`read_wait_record_by_id`、`classify_wait_time_boundary`、`fail_run_from_waiting_in_transaction`、`IdempotencyStore.read_idempotency_record`、`record_idempotent_result`。函数内创建的 `IdempotencyStore()` 和 `EventLogStore()` 是轻量级 helper，使用传入的 transaction 而非新建连接。不调用 public resolver，不打开嵌套 transaction。

### 4. Observation thread 不持 durable authority，late publish 被 token 拒绝

`_run_observation()` (_wait_observation.py:381-403) 只执行 adapter operation 和 `runner._publish(token, result)`，不访问 durable store。

`_publish()` (_wait_observation.py:336-361) 在 registry lock 下检查四个条件：
- `current is not token` — token 已被替换
- `token.state is not WaitObservationTokenState.ACTIVE` — 已 INVALIDATED
- `self._closed` — supervisor 已关闭
- `token.generation != self._generation` — 旧 generation

任一条件不满足 → `self._dropped_count += 1; return False`。Timeout 时 `_invalidate_token()` 将 state 设为 INVALIDATED，late provider result 只能被丢弃。

### 5. Outstanding cap / shared close deadline 有界

- **Cap**: `_start_observation()` (_wait_observation.py:288-317) 在 lock 下检查 `len(self._tokens) >= self._max_outstanding_adapter_calls` → `WaitObservationCapacityExceeded`。
- **Shared close deadline**: `WaitPollerSupervisor.close()` (wait_adapter.py:1642-1699) 计算 `deadline = time.monotonic() + self._policy.close_drain_timeout_seconds`，对 poller thread 和所有 observation thread 共享同一 deadline。`drain_until(deadline_monotonic)` (_wait_observation.py:235-261) 对每个 thread 使用 `remaining = max(0.0, deadline - time.monotonic())`，不按 thread 数倍增。
- **CLOSING → STOPPED**: 只在 poller thread 结束且 `live_count == 0` 时才转 STOPPED。超时后保持 CLOSING，最后一个 thread finally 后由 `_on_observations_drained()` 转 STOPPED。

### 6. Fins/Engine/Service/CLI 无 diff

`git diff 1b589ee6 --name-only | grep -E "^(dayu/fins|dayu/engine|dayu/service|dayu/cli)"` 输出为空。

### 7. Policy validation 收紧

`close_drain_timeout_seconds` 从 `float | None` 收窄为 required finite-positive float (api.py:358-363, wait_adapter.py:456-459)。新增 `adapter_call_timeout_seconds` 和 `max_outstanding_adapter_calls` 也有 finite/positive 校验。`_require_positive_float` 新增 `math.isfinite` 检查 (wait_adapter.py:1996-2006)。

## Open Questions

无。

## Residual Risk

1. **deferred-with-owner (R3-D)**: 不合作的同步 provider daemon thread 在 timeout 后仍可能运行到进程退出。Host 侧已用 outstanding cap、INVALIDATED token、dropped publish 与无 durable authority 有界化。Provider cooperative cancellation 由 R3-D owner 处理。
2. **`_expire_wait_in_transaction` 内部创建 `IdempotencyStore()` / `EventLogStore()`**: 与 `_resolve_in_transaction` 使用注入 store 的模式不一致，但不影响正确性（两者都使用 caller-provided transaction）。
