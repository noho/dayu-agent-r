# Code Review

## Scope

- Mode: current changes
- Branch: `fix/wu-runtime-02-lane-clock-cancellation`
- Base: `main`
- Output file: `docs/reviews/wu-runtime-02-aggregate-deepreview-mimo-20260601.md`
- Included scope:
  - `dayu/runtime/lane.py`（committed diff：385 行变更）
  - `tests/runtime/test_lane.py`（committed diff：380 行新增测试）
  - `docs/host/design.md`（6 行 lane clock 表述更新）
  - `docs/host/host-core-followup-implementation-control.md`（14 行状态更新 + 1 行 uncommitted bookkeeping）
  - `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`（plan artifact 全量新增）
  - `tests/README.md`（1 行 lane 测试覆盖描述更新）
  - `docs/reviews/wu-runtime-02-*`（review artifacts 全量新增）
- Excluded scope: `dayu/engine/**`、`dayu/host/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/config/**`、runtime lane 以外的 `dayu/runtime/**`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为详细走读结论，按 plan 决策点逐项验证：

### 1. 真实 UTC per SQLite transaction（Slice 1）

**入口**: `_LaneClock.utc_now()` → `_try_claim_once_sync()` / `_refresh_token_sync()`

**验证**:
- `_LaneClock` 已删除 `monotonic_anchor` / `utc_anchor` 字段，`utc_now()` 直接返回 `datetime.now(UTC)`（lane.py:362-368）。
- `_try_claim_once_sync()` 在 transaction 前读取一次 `now = self._clock.utc_now()`，stale cleanup（`expires_at <= now`）、active count（`expires_at > now`）和 insert 均使用同一个 bound value（lane.py:648-695）。
- `_refresh_token_sync()` 同理，`now` 读取一次后在同一事务内更新 `heartbeat_at`、`expires_at` 并判断旧 `expires_at > now`（lane.py:768-791）。
- `monotonic()` 仅用于 acquire timeout / deadline（lane.py:370-376），不参与跨进程 TTL。
- design.md 已同步：删除 "monotonic-to-wall strategy" 表述，替换为 "每个 SQLite transaction 前读取真实 UTC"（design.md:200, 204, 222）。
- 测试 `test_lane_ttl_uses_real_utc_not_monotonic_elapsed` 和 `test_refresh_uses_real_utc_not_monotonic_elapsed` 通过 monkeypatch monotonic 大幅前跳证明 TTL 不受影响。

### 2. 有界外层取消 cleanup（Slice 2）

**入口**: `_await_task_after_outer_cancellation()` → 4 个调用点（claim / refresh / tracked release / untracked release）

**验证**:
- `_await_task_after_outer_cancellation` 接收显式 `timeout_seconds`（lane.py:1120-1173），使用 monotonic deadline。
- 每次循环先检查 `remaining_seconds <= 0`，再用 `asyncio.wait_for(asyncio.shield(task), timeout=remaining_seconds)` 有界等待。
- `TimeoutError` 被转换为 `_OuterCancellationCleanupTimeoutError`。
- `CancelledError` 分支中：先检查 `task.done()` 读取结果；未完成时计算剩余时间、capped sleep，并在 sleep 后再次检查 `task.done()`。
- cleanup timeout 计算：`busy_timeout_seconds + 0.25s grace`（lane.py:1176-1192）。

**4 个调用点均正确处理 timeout**:
- `_try_claim_once`（lane.py:613-626）：注册 claim observer → warning log → `raise cancelled from exc`。
- `_refresh_token`（lane.py:730-741）：注册 refresh observer → warning log → `raise cancelled from exc`；不标记 token released/lost。
- `_release_token`（lane.py:824-840）：注册 release observer → warning log → `raise cancelled from exc`；不标记 token released。
- `_release_untracked_claim`（lane.py:907-923）：注册 release observer → warning log → `raise cancelled from exc`。

### 3. Observer late result handling

**验证**:
- `_observe_abandoned_claim_task` / `_observe_abandoned_release_task` / `_observe_abandoned_refresh_task` 均通过 `add_done_callback` 注册（lane.py:1195-1349）。
- 消费函数检查 `task.cancelled()` 后读取 `task.result()`，异常通过 `LOGGER.exception` 或 `LOGGER.warning` 记录。
- claim observer 特别处理 late acquired claim，记录 claim_id 并说明将依赖 TTL cleanup。
- 测试 `test_abandoned_release_observer_logs_non_runtime_exception` 验证普通异常被消费并记录。
- 测试 `test_cancel_during_claim_cleanup_timeout_preserves_cancelled_error_and_observes_late_claim` 验证 late claim 的完整 observer 链路。

### 4. 异常链修复

**直接证据**: `_release_token` 中 `RuntimeLaneError` 分支从 `raise cancelled` 改为 `raise cancelled from exc`（lane.py:849）；`_release_untracked_claim` 同理（lane.py:929）。这修复了原有异常链丢失问题。

### 5. Public API / Schema 一致性

**验证**:
- `__all__` 未变化（lane.py:1525-1539），无新增 public symbol。
- `_OuterCancellationCleanupTimeoutError` 是私有类，未加入 `__all__`。
- DB schema 未变化，`runtime_lane_claims` 表字段、主键与索引保持现状。
- `LaneConfig`、`LaneOwner`、`SQLiteLaneCoordinatorConfig`、`LaneClaimToken`、`LaneAcquireOutcome` 等 public type 签名未变。

### 6. Runtime import boundary

**验证**:
- `dayu/runtime/lane.py` 仅 import `dayu.contracts.cancellation.CancellationToken`，不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `tests/runtime/test_import_boundary.py` 通过（11 passed）。

### 7. 测试覆盖

**新增测试**:
- `test_lane_ttl_uses_real_utc_not_monotonic_elapsed`：证明 monotonic 前跳不影响 TTL 判断。
- `test_refresh_uses_real_utc_not_monotonic_elapsed`：证明 refresh 不因 monotonic 前跳误判 lost。
- `test_outer_cancellation_cleanup_timeout_seconds_adds_grace`：验证 cleanup timeout 计算。
- `test_await_task_after_outer_cancellation_times_out_without_cancelling_task`：验证 timeout 后底层 task 未被取消。
- `test_await_task_after_outer_cancellation_yields_before_retry`：更新为传入显式 timeout。
- `test_abandoned_release_observer_logs_non_runtime_exception`：验证 observer 消费普通异常。
- `test_cancel_during_claim_cleanup_timeout_preserves_cancelled_error_and_observes_late_claim`：完整 claim cleanup timeout E2E。
- `test_release_token_cleanup_timeout_preserves_held_token_for_retry`：验证 tracked release timeout 后 token 状态。
- `test_release_token_failure_after_outer_cancel_preserves_cause`：验证异常链保留。
- `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error`：更新断言检查异常链。

**验证结果**:
- `pytest tests/runtime/test_lane.py -q`：38 passed。
- `pytest tests/runtime/test_lane_multiprocess.py -q`：3 passed。
- `python -m pyright dayu/runtime/lane.py`：0 errors, 0 warnings, 0 informations。

### 8. 文档一致性

**验证**:
- `docs/host/design.md` 已删除 "monotonic-to-wall" 表述，替换为真实 UTC per SQLite transaction。
- `tests/README.md` lane 覆盖描述已更新，包含 "外层取消 cleanup 有界等待与 late result 观测、TTL 时间真源不受 monotonic elapsed 前跳影响"。
- `docs/host/host-core-followup-implementation-control.md` 已更新 implementation commits 表（committed + uncommitted bookkeeping）。

### 9. Host truth / lease / fencing 泄漏检查

**验证**: lane 模块不包含 Host truth、lease、fencing、Attempt owner、EventLog ordering 或 recovery proof 的任何引用。所有 TTL / stale cleanup 语义仅影响 runtime capacity availability，不驱动 Host 状态机。

## Open Questions

无。

## Residual Risk

- **Wall clock jump residual risk**: 真实 UTC 修复了 monotonic anchor 漂移，但系统 wall clock 被手动大幅调快/调慢仍会影响 runtime capacity availability。该风险已在 plan 和 design.md 中明确记录，符合 "clock skew 只影响 runtime capacity availability，不影响 Host truth" 的设计边界。风险等级：低，可接受。
- **Cleanup timeout 后底层 task 继续运行**: timeout 后 `to_thread` task 和 SQLite 操作可能稍后完成。observer 通过 `add_done_callback` 消费 late result / exception，TTL cleanup 兜底可能插入但未释放的 claim。风险等级：低，已有明确兜底。
- **`_await_task_after_outer_cancellation` 循环中 `CancelledError` + `task.done()` 窗口**: 极端情况下 `task.done()` 返回 `True` 但 `task.result()` 重新抛出 task 内部异常（非 `CancelledError`），该异常会正确传播到调用方的 `RuntimeLaneError` catch 分支。这是正确行为，不是 bug。
- **`LaneClaimToken.released` public field**: plan 明确不处理该项，deferred to 独立 public contract 裁决。当前不影响 correctness。

## Conclusion: PASS

WU-RUNTIME-02 的两个核心决策（真实 UTC per SQLite transaction、有界外层取消 cleanup）均已正确实现。实现与 plan 一致，public API / schema 无变化，runtime import boundary 无泄漏，测试覆盖 failure path 和 boundary condition，pyright 0 errors。uncommitted control doc bookkeeping 正确记录了 slice2 commit。residual risks 均为低风险且已在设计文档中明确记录。
