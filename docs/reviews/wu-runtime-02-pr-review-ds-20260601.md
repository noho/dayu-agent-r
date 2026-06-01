# Code Review

## Scope

- **Mode**: PR review
- **Repository**: noho/dayu-agent-r
- **PR**: https://github.com/noho/dayu-agent-r/pull/101
- **Title**: Fix runtime lane clock and cancellation cleanup
- **Author**: noho
- **Head branch**: fix/wu-runtime-02-lane-clock-cancellation
- **Base branch**: main
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Gate**: PR review (draft PR gate)
- **Output file**: docs/reviews/wu-runtime-02-pr-review-ds-20260601.md
- **Review date**: 2026-06-01
- **Design source**: docs/host/design.md
- **Control doc**: docs/host/host-core-followup-implementation-control.md
- **Plan**: docs/host/wu-runtime-02-lane-clock-cancellation-plan.md
- **Included scope**: full PR diff against main (commits fa34592, 1be0259, 5675886, ce36bff, eff32b7) — `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `tests/README.md`, `docs/host/design.md`, `docs/host/host-core-followup-implementation-control.md`, `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`, `docs/reviews/wu-runtime-02-*`
- **Excluded scope**: Host/Engine/Service/UI/Fins business layers, unrelated runtime modules, other work units
- **Parallel review coverage**: 无（单人逐链路走读）

## Evidence Summary

### CI / Checks

- `gh pr checks 101`: 无 CI 检查报告（repository 可能未配置 PR checks）

### Validation (locally reproduced)

- `pytest tests/runtime/test_lane.py -q`: **41 passed** (38 single-process + 3 multiprocess)
- `pytest tests/runtime/test_import_boundary.py -q`: **11 passed**
- `python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py`: **0 errors, 0 warnings, 0 informations**

### Key Implementation Checks

- `_LaneClock` 已删除 `monotonic_anchor` / `utc_anchor` 字段，`utc_now()` 直接返回 `datetime.now(UTC)`（lane.py:345-376）
- `_try_claim_once_sync()` 在每个 SQLite transaction 前读取真实 UTC，同一事务内复用做 stale cleanup、active count 和 insert（lane.py:649-695）
- `_refresh_token_sync()` 在每个 SQLite transaction 前读取真实 UTC，同一事务内复用做 update 和 `expires_at > now` 判断（lane.py:768-791）
- `_await_task_after_outer_cancellation()` 改为接收显式 `timeout_seconds`，使用 monotonic deadline 做有界等待（lane.py:1120-1173）
- `_outer_cancellation_cleanup_timeout_seconds()` 返回 `busy_timeout_seconds + 0.25` grace（lane.py:1176-1192）
- `_OuterCancellationCleanupTimeoutError` 是私有异常（不在 `__all__` 中），继承 `RuntimeLaneError`，且在所有调用方先于 `RuntimeLaneError` 捕获
- 被放弃等待的底层 task 通过 done callback observer 消费 late result/exception（lane.py:1195-1349）
- 所有 cleanup timeout 路径对外重新抛出原始 `CancelledError`，不丢失对外取消语义
- tracked release timeout 不标记 `token.released`，保留 retry 能力
- refresh timeout 不标记 token lost/released
- design.md 已清除旧 `monotonic-to-wall strategy` 表述，替换为真实 UTC per SQLite transaction（design.md:200, 204, 222）
- tests/README.md 已补充 lane 测试覆盖"外层取消 cleanup 有界等待与 late result 观测"和"TTL 时间真源不受 monotonic elapsed 前跳影响"（tests/README.md:78）
- runtime import boundary 通过：`dayu.runtime.lane` 不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`
- `__all__` 未变：无 public API 新增或删除（lane.py:1525-1539）
- control doc 状态一致：gate `ready-to-open-draft-PR`，WU-RUNTIME-02 已完成，RR-HCF-02 closed

## Findings

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

**Path 2: 外层取消后有界 cleanup — claim**

```
_try_claim_once() CancelledError catch
  -> cleanup_timeout_seconds = _outer_cancellation_cleanup_timeout_seconds(self._coordinator)
  -> _await_task_after_outer_cancellation(claim_task, timeout_seconds=cleanup_timeout_seconds)
     -> while True:
        -> remaining_seconds = deadline - time.monotonic()
        -> if <= 0: raise _OuterCancellationCleanupTimeoutError
        -> asyncio.wait_for(asyncio.shield(task), timeout=remaining_seconds)
           -> 成功: return result
           -> TimeoutError: raise _OuterCancellationCleanupTimeoutError
           -> CancelledError: task.done() => return; else => capped sleep + continue
  -> timeout 时: _observe_abandoned_claim_task() 注册 done callback
  -> raise original CancelledError from _OuterCancellationCleanupTimeoutError
```

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

在 `_try_claim_once()`（lane.py:613-626）中：
```python
except _OuterCancellationCleanupTimeoutError as exc:  # 先捕获私有子类
    ...
except RuntimeLaneError as exc:                        # 后捕获父类
    ...
```
`_OuterCancellationCleanupTimeoutError` 继承 `RuntimeLaneError`，先捕获子类后捕获父类，顺序正确。`_refresh_token`（lane.py:727-750）和 `_release_token`（lane.py:824-849）同样正确。

### Observer 完整性检查

三类 observer 均通过 `task.add_done_callback()` 注册，不 cancel 底层 task：

- **Claim observer** (`_consume_abandoned_claim_task`, lane.py:1215-1241): 先检查 `task.cancelled()`，然后 `task.result()`。success + acquired 时 log TTL fallback warning；exception 时 log error。
- **Release observer** (`_consume_abandoned_release_task`, lane.py:1270-1298): 先检查 `task.cancelled()`，然后 `task.result()`。exception 时 log error。
- **Refresh observer** (`_consume_abandoned_refresh_task`, lane.py:1322-1349): 先检查 `task.cancelled()`，然后 `task.result()`。exception 时 log warning with error_type。

所有 observer 正确消费 late result/exception，避免未取回异常。fix 后均已改为 `except Exception`（不捕获 `BaseException`），防御性覆盖非 `RuntimeLaneError` 的普通异常类型。

### 异常链统一检查

所有 cancel 路径的 `raise cancelled` 均已统一为 `raise cancelled from exc`：

| 函数 | 行号 | 分支 | 状态 |
|---|---|---|---|
| `_try_claim_once` | 626, 628, 637 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` / claim release fail | ✓ |
| `_refresh_token` | 729, 741, 750 | `RuntimeLaneClaimLostError` / `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ |
| `_release_token` | 840, 849 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ |
| `_release_untracked_claim` | 923, 929 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ |

### 架构约束检查

- **Runtime import boundary**: `dayu/runtime/lane.py` 仅 import 标准库 + `dayu.contracts.cancellation.CancellationToken`；无 `dayu.engine/host/service/ui/fins` import ✓
- **Public API**: `__all__` 未变化；`_OuterCancellationCleanupTimeoutError` 正确排除在 public API 之外 ✓
- **DB Schema**: `runtime_lane_claims` 表字段、主键、索引无变化 ✓
- **Host truth/lease/fencing leakage**: lane 模块不含 Host truth、lease、fencing、Attempt owner、EventLog ordering 或 recovery proof 的任何引用 ✓
- **Layering**: 所有变更在 `dayu/runtime/lane.py` 内，属于 `dayu.runtime` 包的自包含扩展，未跨层穿透 ✓

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
| `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` | untracked release 取消后失败 + cause | pass |
| `test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire` | crash TTL cleanup 多进程 | pass |
| `test_capacity_invariant_across_processes` | 多进程 capacity invariant | pass |

### 文档一致性

- `docs/host/design.md`: 旧 "monotonic-to-wall strategy" 已清除，替换为真实 UTC per SQLite transaction（line 200, 204, 222）。`rg -n "monotonic-to-wall|monotonic.*TTL"` 无匹配 ✓
- `tests/README.md`: lane 覆盖描述已更新，包含 "外层取消 cleanup 有界等待与 late result 观测、TTL 时间真源不受 monotonic elapsed 前跳影响" ✓
- `docs/host/host-core-followup-implementation-control.md`: WU-RUNTIME-02 状态正确更新为 completed，RR-HCF-02 closed，gate `ready-to-open-draft-PR` ✓

## Open Questions

- `LaneClaimToken.released` 仍为 public writable field（lane.py:252）。plan 和 control doc 已明确 defer 该项到独立 public contract 裁决，不影响本 WU 的 correctness 判定。
- 无其他 blocking open questions。

## Residual Risk

1. **系统 wall clock jump**: 真实 UTC 修复了 monotonic anchor 漂移的 root cause，但系统 wall clock 被手动大幅调快/调慢仍会影响 runtime capacity availability。风险已在 plan 和 design.md 中明确记录为 "clock skew 只影响 runtime capacity availability，不能影响 Host truth"。**风险等级：低，可接受。**

2. **Late claim 依赖 TTL cleanup**: cleanup timeout 后底层 claim task 成功插入的 claim 依赖 TTL stale cleanup 释放。由于 `_try_claim_once_sync` 使用 short-lived SQLite connection 且 `_LaneClock.utc_now()` 在 transaction 前读取，late claim 的 `expires_at` 为首次 `utc_now() + claim_ttl_seconds`，最多等待一个 TTL 周期即可被清理。**风险等级：低，可接受。**

3. **Cleanup timeout 后底层线程继续运行**: 这是 approved plan 的明确设计决策。observer 通过 `add_done_callback` 消费 late result/exception，TTL cleanup 兜底可能插入但未释放的 claim。**风险等级：低，已有明确兜底。**

4. **Control doc bookkeeping**: 所有字段已在 committed diff 中同步更新——gate `ready-to-open-draft-PR`、WU-RUNTIME-02 完成、RR-HCF-02 closed。当前状态一致，无需额外 bookkeeping。**风险：无。**

5. **Observer done callback 执行时延**: done callback 通过 event loop 调度；若 event loop 长时间阻塞，late result 可能在 observer 执行前保持未消费。这是 asyncio done callback 的通用特性，observer 函数不进行阻塞 I/O，不会加剧该风险。**风险等级：低。**

6. **CI 检查缺失**: `gh pr checks 101` 无报告。建议确认 repository 是否需要配置 CI（如 GitHub Actions），或手动在 PR 前验证 pyright + pytest 通过。本地验证已全部通过。

## Conclusion: PASS

实现在 WU-RUNTIME-02 的目标范围内没有 blocking finding。两个核心 design decision（真实 UTC per SQLite transaction、bounded outer-cancellation cleanup）均已正确实现：

- `_LaneClock` 已删除进程内 monotonic-to-UTC anchor，`utc_now()` 直接返回 `datetime.now(UTC)`
- 所有 SQLite TTL 操作在 transaction 前读取一次真实 UTC 并在事务内复用
- monotonic 仅用于本进程等待 timeout/deadline，不参与跨进程 TTL 判断
- `_await_task_after_outer_cancellation` 改为有界等待，timeout 后不取消底层 task
- 所有 4 个 cancel cleanup 调用点正确处理 timeout、保留对外 `CancelledError`、注册 observer 消费 late result/exception
- tracked release timeout 不误标 `token.released`，refresh timeout 不误标 lost
- observer 防御性捕获 `Exception`，异常链统一为 `raise cancelled from exc`
- 41 个 lane 测试全部通过，pyright 零错误，import boundary 通过
- `__all__` 未变化，DB schema 未变化，无 public API regression
- design.md 已同步为真实 UTC 表述，tests/README.md 已更新
- 无 Host truth/lease/fencing/EventLog/Attempt lifecycle 泄漏
- control doc residual risk RR-HCF-02 已关闭

Residual risks（wall clock jump、late claim TTL 兜底、observer 执行时延）均为低风险且已在 plan 和 design.md 中明确记录边界。
