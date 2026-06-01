# Code Review

## Scope

- Mode: PR
- Branch: fix/wu-runtime-02-lane-clock-cancellation
- Base: main
- PR: https://github.com/noho/dayu-agent-r/pull/101
- PR title: Fix runtime lane clock and cancellation cleanup
- PR author: noho
- Work Unit: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- Gate: PR review
- Output file: docs/reviews/wu-runtime-02-pr-review-mimo-20260601.md
- Included scope:
  - `dayu/runtime/lane.py`（核心实现变更：+385 行）
  - `tests/runtime/test_lane.py`（+380 行新增 / 更新测试）
  - `docs/host/design.md`（6 行 lane clock 表述更新）
  - `docs/host/host-core-followup-implementation-control.md`（22 行状态更新）
  - `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`（plan artifact 全量新增）
  - `tests/README.md`（1 行 lane 测试覆盖描述更新）
  - `docs/reviews/wu-runtime-02-*`（review artifacts 全量新增）
- Excluded scope: `dayu/engine/**`、`dayu/host/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/config/**`、runtime lane 以外的 `dayu/runtime/**`
- CI status: no checks reported on the branch
- Review date: 2026-06-01

## Evidence Summary

### 本地验证

- `pytest tests/runtime/test_lane.py -q`: 38 passed（1.18s）
- `pytest tests/runtime/test_lane_multiprocess.py -q`: 3 passed（0.93s）
- `pytest tests/runtime/test_import_boundary.py -q`: 11 passed（0.39s）
- `python -m pyright dayu/runtime/lane.py`: 0 errors, 0 warnings, 0 informations

### PR diff 统计

- 25 files changed, 2744 insertions, 50 deletions
- 生产代码变更仅 `dayu/runtime/lane.py`，其余为文档、plan、review artifacts 和测试

## Findings

未发现实质性问题。

## 详细走读

### 1. _LaneClock 简化：删除 monotonic-to-UTC anchor

**文件**: `dayu/runtime/lane.py:346-376`

`_LaneClock` 已删除 `monotonic_anchor` / `utc_anchor` 字段，`utc_now()` 直接返回 `datetime.now(UTC)`。`start()` 返回无状态 clock instance。`monotonic()` 仅用于 acquire timeout / deadline 计算，不参与跨进程 TTL 判断。

验证：`_try_claim_once_sync()`（lane.py:649）和 `_refresh_token_sync()`（lane.py:768）均在 SQLite transaction 前读取一次 `utc_now()`，同一事务内复用同一个 bound value。

测试 `test_lane_ttl_uses_real_utc_not_monotonic_elapsed` 和 `test_refresh_uses_real_utc_not_monotonic_elapsed` 通过 monkeypatch `time.monotonic()` 大幅前跳证明 TTL 不受影响。

### 2. _await_task_after_outer_cancellation：从无限等待改为有界等待

**文件**: `dayu/runtime/lane.py:1120-1173`

函数接收显式 `timeout_seconds`，使用 `time.monotonic()` deadline 做有界等待。每次循环：

1. 检查 `remaining_seconds <= 0`，超时则抛 `_OuterCancellationCleanupTimeoutError`
2. `asyncio.wait_for(asyncio.shield(task), timeout=remaining_seconds)` — 有界等待
3. `TimeoutError` → `_OuterCancellationCleanupTimeoutError`
4. `CancelledError` → 检查 `task.done()` 读取结果；未完成则 capped sleep 后 continue

关键设计：timeout 后不取消底层 shielded task，由 observer 消费 late result。

### 3. 4 个调用点的 cleanup timeout 处理

所有调用点均遵循相同模式：

- `_try_claim_once`（lane.py:613-626）：注册 claim observer → warning → `raise cancelled from exc`
- `_refresh_token`（lane.py:730-741）：注册 refresh observer → warning → `raise cancelled from exc`；**不标记 token released/lost**
- `_release_token`（lane.py:824-840）：注册 release observer → warning → `raise cancelled from exc`；**不标记 token released**
- `_release_untracked_claim`（lane.py:907-923）：注册 release observer → warning → `raise cancelled from exc`

**Token 状态保留验证**：`_release_token` cleanup timeout 后 `token.released` 保持 `False`，保留 held token 供后续 release / close 重试（测试 `test_release_token_cleanup_timeout_preserves_held_token_for_retry` 覆盖）。

### 4. Observer late result handling

三类 observer 均通过 `task.add_done_callback()` 注册：

- `_consume_abandoned_claim_task`（lane.py:1215-1241）：`task.cancelled()` → `task.result()` → success+acquired 时 log TTL fallback warning
- `_consume_abandoned_release_task`（lane.py:1270-1298）：`task.cancelled()` → `task.result()` → exception 时 `LOGGER.exception`
- `_consume_abandoned_refresh_task`（lane.py:1322-1349）：`task.cancelled()` → `task.result()` → exception 时 `LOGGER.warning`（含 `error_type`）

refresh observer 使用 `warning` 而非 `exception` 的差异是合理的：refresh failure 可能是 claim 自然过期导致的预期场景。

### 5. 异常链修复

`_release_token` 和 `_release_untracked_claim` 中 `RuntimeLaneError` 分支从 `raise cancelled` 改为 `raise cancelled from exc`（lane.py:849, 929），修复了原有异常链丢失问题。

### 6. _OuterCancellationCleanupTimeoutError 继承与 catch 顺序

- 继承 `RuntimeLaneError`（lane.py:114-119），不加入 `__all__`
- 所有调用点先捕获 `_OuterCancellationCleanupTimeoutError`（子类），后捕获 `RuntimeLaneError`（父类），顺序正确

### 7. Cleanup timeout 计算

`_outer_cancellation_cleanup_timeout_seconds()`（lane.py:1176-1192）返回 `coordinator.busy_timeout_seconds + 0.25`。覆盖 SQLite busy timeout，再给事件循环调度余量。测试 `test_outer_cancellation_cleanup_timeout_seconds_adds_grace` 验证。

### 8. Public API / Schema 一致性

- `__all__` 未变化（lane.py:1525-1539），无新增 / 删除 public symbol
- DB schema 未变化：`runtime_lane_claims` 表字段、主键与索引保持现状
- `LaneConfig`、`LaneOwner`、`SQLiteLaneCoordinatorConfig`、`LaneClaimToken`、`LaneAcquireOutcome` 等 public type 签名未变

### 9. Runtime import boundary

`dayu/runtime/lane.py` 仅 import `dayu.contracts.cancellation.CancellationToken`，不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。`test_import_boundary.py` 通过（11 passed）。

### 10. Host truth / lease / fencing 边界

- lane module 不持有 Host / Engine / Service / UI / Fins 语义
- TTL stale cleanup 只释放 runtime capacity，不证明 Host orphan，不驱动 recovery
- observer 只做 diagnostic logging，不写 EventLog，不推进 Host state machine
- design.md 已明确："clock skew 只影响 runtime capacity availability，不能影响 Host truth / EventLog / Attempt lifecycle"

### 11. 设计真源同步

`docs/host/design.md` 已更新三处 lane clock 表述：
- acquire 生命周期（line 200）：每个 SQLite transaction 前读取真实 UTC
- heartbeat / refresh（line 204）：每次 refresh 在 transaction 前读取真实 UTC
- clock 策略（line 222）：lane TTL 使用真实 UTC，monotonic 只用于本进程等待 timeout

旧 `monotonic-to-wall strategy` 表述已全部清除。

### 12. Control doc 状态一致性

- `gate`: `ready-to-open-draft-PR`
- `active work unit`: WU-RUNTIME-02
- `implementation status`: current work unit completed：WU-RUNTIME-02
- RR-HCF-02: `closed`
- WU-RUNTIME-02: `已完成`
- implementation commits 记录完整（9 个 accepted commits）
- review artifacts 列表完整（26+ 条）
- aggregate review artifacts 记录完整
- `blocking open questions`: none

### 13. 测试覆盖矩阵

| 测试 | 覆盖场景 | 状态 |
|---|---|---|
| `test_lane_ttl_uses_real_utc_not_monotonic_elapsed` | monotonic 前跳不清理真实 UTC 未过期 claim | pass |
| `test_refresh_uses_real_utc_not_monotonic_elapsed` | monotonic 前跳不导致 refresh 误判 lost | pass |
| `test_outer_cancellation_cleanup_timeout_seconds_adds_grace` | cleanup timeout = busy + grace | pass |
| `test_await_task_after_outer_cancellation_times_out_without_cancelling_task` | helper 超时不取消底层 task | pass |
| `test_await_task_after_outer_cancellation_yields_before_retry` | 取消后先 yield 再 retry | pass |
| `test_abandoned_release_observer_logs_non_runtime_exception` | observer 消费普通异常并 log | pass |
| `test_cancel_during_claim_cleanup_timeout_preserves_cancelled_error_and_observes_late_claim` | claim cleanup timeout + late claim observer | pass |
| `test_release_token_cleanup_timeout_preserves_held_token_for_retry` | tracked release timeout 保留 held token | pass |
| `test_release_token_failure_after_outer_cancel_preserves_cause` | tracked release 失败保留 cause | pass |
| `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` | untracked release 取消后失败 | pass |
| `test_refresh_waits_for_shielded_success_after_outer_cancel` | refresh 取消后等底层成功并更新状态 | pass |
| `test_refresh_cancel_cleanup_marks_lost_after_claim_lost` | refresh 取消后 claim lost 标记 token | pass |
| `test_refresh_cancel_cleanup_logs_runtime_error_and_preserves_cancel` | refresh 取消后 runtime error 保留取消 | pass |
| `test_release_token_waits_for_shielded_release_after_outer_cancel` | release 取消后等底层成功并更新状态 | pass |
| `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim` | 重复外层取消不打断 cleanup | pass |
| `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails` | claim cleanup 失败仍透传 CancelledError | pass |
| 现有多进程测试 | capacity invariant / TTL cleanup / release 后 acquire | pass (3) |
| 现有 import boundary | runtime 不反向依赖上层 | pass (11) |

## Open Questions

- `LaneClaimToken.released` 仍为 public writable field（lane.py:252）。plan（line 55-56）和 control doc（WU-RUNTIME-02 non-goals）已明确 defer 到独立 public contract 裁决。不影响本 WU 的 correctness 判定。
- PR 无 CI checks 配置（`no checks reported`）。本地验证已手动覆盖所有 validation commands。

## Residual Risk

1. **系统 wall clock jump**: 真实 UTC 修复了 monotonic anchor 漂移的 root cause，但系统 wall clock 被手动大幅调快 / 调慢仍会影响 runtime capacity availability。风险已在 plan 和 design.md 中记录，明确 "clock skew 只影响 runtime capacity availability，不能影响 Host truth"。风险等级：低，可接受。

2. **Late claim 依赖 TTL cleanup**: cleanup timeout 后底层 claim task 成功插入的 claim 依赖 TTL stale cleanup 释放。`_try_claim_once_sync` 使用 short-lived SQLite connection，late claim 的 `expires_at` 为首次 `utc_now() + claim_ttl_seconds`，最多等待一个 TTL 周期即可被清理。风险等级：低，可接受。

3. **Observer done callback 执行时延**: done callback 通过 event loop 调度；若 event loop 长时间阻塞，late result 可能在 observer 执行前保持未消费。这是 asyncio done callback 的通用特性，不是本实现的特有风险。observer 函数不进行阻塞 I/O。风险等级：低，可接受。

## Conclusion: PASS

PR 就绪，可通过 draft PR gate。

两个 design decision（真实 UTC per SQLite transaction、bounded outer-cancellation cleanup）均已正确实现。所有本地验证通过（38 lane tests + 3 multiprocess tests + 11 import boundary tests + pyright 零报错）。runtime import boundary 干净，design.md 已同步，无 public API / schema regression，无 Host truth / lease / fencing 泄漏，control doc 状态一致。
