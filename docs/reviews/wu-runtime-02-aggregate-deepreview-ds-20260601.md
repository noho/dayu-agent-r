# Code Review

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: fix/wu-runtime-02-lane-clock-cancellation
- Base: main
- Work Unit: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- Output file: docs/reviews/wu-runtime-02-aggregate-deepreview-ds-20260601.md
- Design source: docs/host/design.md
- Control doc: docs/host/host-core-followup-implementation-control.md
- Plan: docs/host/wu-runtime-02-lane-clock-cancellation-plan.md
- Included scope: full branch diff against main (commits fa34592, 1be0259, 5675886) plus unstaged control_doc bookkeeping diff
- Excluded scope: other work units, Host/Engine/Service/UI/Fins business layers, unrelated runtime modules
- Review date: 2026-06-01

## Evidence Summary

### Tests

- `pytest tests/runtime/test_lane.py -q`: 38 passed
- `pytest tests/runtime/test_lane_multiprocess.py -q`: 3 passed
- `pytest tests/runtime/test_import_boundary.py -q`: 11 passed
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations

### Key Implementation Checks

- `_LaneClock` 已删除 `monotonic_anchor` / `utc_anchor` 字段（lane.py:346-376），`utc_now()` 直接返回 `datetime.now(UTC)`（lane.py:368）
- `_try_claim_once_sync()` 在每个 SQLite transaction 前读取一次真实 UTC `now`，同一事务内复用做 stale cleanup、active count 和 insert（lane.py:649, 653-688）
- `_refresh_token_sync()` 在每个 SQLite transaction 前读取一次真实 UTC `now`，同一事务内复用做 update 和 `expires_at > now` 判断（lane.py:768, 773-786）
- `_await_task_after_outer_cancellation()` 改为接收显式 `timeout_seconds`，使用 monotonic deadline 做有界等待（lane.py:1120-1173）
- `_outer_cancellation_cleanup_timeout_seconds()` 返回 `busy_timeout_seconds + 0.25` grace（lane.py:1176-1192）
- `_OuterCancellationCleanupTimeoutError` 是 private 异常（不在 `__all__` 中），正确地位于 `RuntimeLaneError` 继承链上，且在所有调用方先于 `RuntimeLaneError` 捕获
- 被放弃等待的底层 task 通过 done callback observer 消费 late result/exception（lane.py:1195-1349）
- 所有 cleanup timeout 路径对外重新抛出原始 `CancelledError`，不丢失对外取消语义
- design.md 已清除旧 `monotonic-to-wall strategy` 表述，替换为真实 UTC per SQLite transaction（design.md:200, 204, 221-222）
- tests/README.md 已补充 lane 测试覆盖"外层取消 cleanup 有界等待与 late result 观测"和"TTL 时间真源不受 monotonic elapsed 前跳影响"（tests/README.md:78）
- runtime import boundary 通过：`dayu.runtime.lane` 不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`
- `__all__` 未变：无 public API 新增或删除

## Findings

未发现实质性问题。

### 已审查的关键路径

**Path 1: TTL 时间真源**

```
LaneController.acquire() -> _try_claim_once() -> asyncio.to_thread(_try_claim_once_sync)
  -> _LaneClock.utc_now() (datetime.now(UTC))
  -> _connect() + BEGIN IMMEDIATE
  -> DELETE stale (expires_at <= formatted_now)
  -> SELECT COUNT(*) (expires_at > formatted_now)
  -> INSERT (created_at=now, heartbeat_at=now, expires_at=now+TTL)
  -> COMMIT
```

每个 SQLite 短事务内使用同一个 `now` bound value。monotonic 仅用于 acquire 的 `deadline` 计算（lane.py:499-504, 546-551）。

**Path 2: 外层取消后有界 cleanup**

```
_try_claim_once() CancelledError catch
  -> _await_task_after_outer_cancellation(claim_task, timeout_seconds=busy+0.25)
     -> while True:
        -> remaining_seconds = deadline - time.monotonic()
        -> if <= 0: raise _OuterCancellationCleanupTimeoutError
        -> asyncio.wait_for(asyncio.shield(task), timeout=remaining_seconds)
           -> 成功: 返回 result
           -> TimeoutError: raise _OuterCancellationCleanupTimeoutError
           -> CancelledError:
              -> task.done(): return task.result()
              -> 否则: asyncio.sleep(min(0.01, remaining)); continue
  -> timeout 时: _observe_abandoned_claim_task() 注册 done callback
  -> raise original CancelledError from _OuterCancellationCleanupTimeoutError
```

cleanup 有明确上限、失败语义和有界重试；对外始终保留 `CancelledError`。

**Path 3: tracked release cleanup timeout**

```
_release_token() CancelledError catch
  -> _await_task_after_outer_cancellation(release_task, timeout_seconds)
  -> timeout: _observe_abandoned_release_task() + log warning
  -> raise CancelledError from _OuterCancellationCleanupTimeoutError
  -> 注意: 不调用 _mark_token_released(token)，token.released 保持 False
```

**Path 4: refresh cleanup timeout**

```
_refresh_token() CancelledError catch
  -> _await_task_after_outer_cancellation(refresh_task, timeout_seconds)
  -> timeout: _observe_abandoned_refresh_task() + log warning
  -> raise CancelledError from _OuterCancellationCleanupTimeoutError
  -> 注意: 不标记 token released/lost
```

### Catch 顺序检查

在 `_try_claim_once()`（lane.py:613-638）中：
```python
except _OuterCancellationCleanupTimeoutError as exc:  # 先捕获私有子类
    ...
except RuntimeLaneError as exc:                        # 后捕获父类
    ...
```
`_OuterCancellationCleanupTimeoutError` 继承 `RuntimeLaneError`，先捕获子类后捕获父类，顺序正确。注册 cleanup timeout 的 observer 不会被错误归类为普通 RuntimeLaneError。

### Observer 完整性检查

三类 observer 均通过 `task.add_done_callback()` 注册，不 cancel 底层 task：

- **Claim observer**: `_consume_abandoned_claim_task()` — 先检查 `task.cancelled()`，然后 `task.result()` 获取结果。success + acquired 时 log TTL fallback warning；exception 时 log error。
- **Release observer**: `_consume_abandoned_release_task()` — 先检查 `task.cancelled()`，然后 `task.result()`。exception 时 log error。
- **Refresh observer**: `_consume_abandoned_refresh_task()` — 先检查 `task.cancelled()`，然后 `task.result()`。exception 时 log warning with error_type。

所有 observer 正确消费了 late result/exception，避免未取回异常。

### 测试覆盖矩阵

| 测试 | 覆盖场景 | 状态 |
|---|---|---|
| `test_lane_ttl_uses_real_utc_not_monotonic_elapsed` | monotonic 前跳不清理真实 UTC 未过期 claim | pass |
| `test_refresh_uses_real_utc_not_monotonic_elapsed` | monotonic 前跳不导致 refresh 误判 lost | pass |
| `test_outer_cancellation_cleanup_timeout_seconds_adds_grace` | cleanup timeout = busy + grace | pass |
| `test_await_task_after_outer_cancellation_times_out_without_cancelling_task` | helper 超时不取消底层 task | pass |
| `test_await_task_after_outer_cancellation_yields_before_retry` | 取消后先 yield 再 retry | pass |
| `test_abandoned_release_observer_logs_non_runtime_exception` | observer 消费普通异常并 log | pass |
| `test_refresh_waits_for_shielded_success_after_outer_cancel` | refresh 取消后等底层成功并更新状态 | pass |
| `test_refresh_cancel_cleanup_marks_lost_after_claim_lost` | refresh 取消后 claim lost 标记 token | pass |
| `test_refresh_cancel_cleanup_logs_runtime_error_and_preserves_cancel` | refresh 取消后 runtime error 保留取消 | pass |
| `test_cancel_during_claim_cleanup_timeout_preserves_cancelled_error_and_observes_late_claim` | claim cleanup timeout + late claim observer | pass |
| `test_release_token_cleanup_timeout_preserves_held_token_for_retry` | tracked release timeout 保留 held token | pass |
| `test_release_token_failure_after_outer_cancel_preserves_cause` | tracked release 失败保留 cause | pass |
| `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` | untracked release 取消后失败 | pass |
| `test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire` | crash TTL cleanup 多进程 | pass |
| `test_capacity_invariant_across_processes` | 多进程 capacity invariant | pass |

## Open Questions

- `LaneClaimToken.released` 仍为 public writable field（lane.py:252），但 plan（line 55-56）和 control doc（WU-RUNTIME-02 non-goals）已明确 defer 该项到独立 public contract 裁决。不影响本 WU 的 correctness 判定。
- control doc 中 RR-HCF-02 状态为 `deferred-with-owner`（line 172），WU-RUNTIME-02 状态表仍为"未开始"（line 192）。这两个字段与当前 `gate: review` / `current work unit aggregate deepreview pending：WU-RUNTIME-02` 状态事实不一致。属于 control doc bookkeeping 滞后，不是代码缺陷，应由 controller 在 gate 推进时更新。

## Residual Risk

1. **系统 wall clock jump**: 真实 UTC 修复了 monotonic anchor 漂移的 root cause，但系统 wall clock 被手动大幅调快/调慢仍会影响 runtime capacity availability。风险已记录在 plan 和 design.md 中，明确 "clock skew 只影响 runtime capacity availability，不能影响 Host truth"。风险等级：低，可接受。

2. **Late claim 依赖 TTL cleanup**: cleanup timeout 后底层 claim task 成功插入的 claim 依赖 TTL stale cleanup 释放，observer 只记录 diagnostic 不做 release。由于 `_try_claim_once_sync` 使用 short-lived SQLite connection 且 `_LaneClock.utc_now()` 在 transaction 前读取，late claim 的 `expires_at` 为首次 `utc_now() + claim_ttl_seconds`，最多等待一个 TTL 周期即可被清理。风险等级：低，可接受。

3. **Control doc bookkeeping lag**: 如上 Open Questions 第 2 条，RR-HCF-02 状态和 WU-RUNTIME-02 完成状态字段尚未同步。应由 controller 在 aggregate adjudication 时更新，不是代码缺陷。

4. **Observer done callback 执行时延**: done callback 通过 event loop 调度；若 event loop 长时间阻塞，late result 可能在 observer 执行前保持未消费。这是 asyncio done callback 的通用特性，不是本实现的特有风险。`_consume_abandoned_claim_task` 等 observer 函数不进行阻塞 I/O，不会加剧该风险。

5. **测试未覆盖 path**: `_await_task_after_outer_cancellation` 中 sleep 被取消后 task 仍 not done 的分支（lane.py:1170-1172 的 `except asyncio.CancelledError` 内 `task.done()` 为 False 的 fall-through 到 `continue`）在 `test_await_task_after_outer_cancellation_yields_before_retry` 中被间接覆盖：第一次 cancel 命中 sleep，task 未完成，continue 回到循环顶部。该路径在 sleep 被取消、task 恰好完成的边界情况（`task.done()` 返回 True 时直接 return result）也已覆盖。风险等级：低，已充分覆盖。

## Conclusion: PASS

实现在本 WU 的目标范围内没有 blocking finding。两个 design decision（真实 UTC per SQLite transaction、bounded outer-cancellation cleanup）均已正确实现，所有测试通过，pyright 零报错，runtime import boundary 干净，design.md 已同步，无 public API/schema regression，无 Host truth/lease/fencing 泄漏。
