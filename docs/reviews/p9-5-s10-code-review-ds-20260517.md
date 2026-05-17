# P9.5 S10 Code Review — Host Dispatch Lifecycle / RunInputBuilder Non-Recovery Cleanup

日期：2026-05-17
审查 agent：DS

## 审查范围

只审查当前工作区未提交的 S10 diff，文件清单：

- `dayu/host/dispatch.py`
- `dayu/host/waiting.py`
- `dayu/host/README.md`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_wait_cancel_late_result.py`

## 审阅依据

- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/implementation-control.md`
- 实现 artifact：`docs/reviews/p9-5-s10-dispatch-runinput-non-recovery-cleanup-implementation-20260517.md`
- S10 目标边界：收口 scheduler lane 竞争测试、`_drain_loop` 可观测性、RunInputBuilder optimistic TOCTOU、late `resolve_wait` rejection redundant catch-up cleanup、worker event consumption 异常路径 cleanup 证据。

## 停止条件检查

以下条件均已验证通过，无触发：

- **无 Phase 11 RECOVERING / orphan proof**：S10 diff 未引入 `RECOVERING` 状态、recovery dispatch、startup scan、orphan detection、RemoteProxy 或状态机语义变更。
- **lane token 未提升为 Host truth**：`LaneClaimToken` 仍只在 dispatch 路径作为 capacity claim 使用，`finally` 释放，不进入 EventLog、Attempt owner、Run / Attempt 状态机。`_safe_release_lane_token` 只做 best-effort `token.release()`。
- **late `resolve_wait` rejection 只保留 bounded diagnostic**：`_reject_late_result` 写入 `EventClass.DIAGNOSTIC` 的 `WAIT_LATE_RESULT_REJECTED`，不创建 resume Attempt、不推进 Run、不追加 canonical tool fact，不触发 projection catch-up。
- **无 public API 变更**：无新增 HostApiErrorCode、无新 public request/response/snapshot 类型、无 schema 迁移。

## 逐文件审查

### 1. dayu/host/dispatch.py

#### 1.1 `_drain_loop` 可观测性（line 500-535）

**入口**：`HostDispatchScheduler._drain_loop`

**已实现日志**：
- `_LOG_DRAIN_LOOP_EMPTY_SLEEPING`（line 118-120）：空队列 sleep，debug 级别，携带 `host_handle_id` 与 `interval_seconds`
- `_LOG_DRAIN_LOOP_CLOSE_EXIT`（line 121）：正常 close 退出，debug 级别
- `_LOG_DRAIN_LOOP_CANCELLED_FOR_CLOSE`（line 122-124）：close 触发取消，debug 级别，通过 `self._closed` 区分
- `_LOG_DRAIN_LOOP_CANCELLED_EXTERNALLY`（line 125-127）：外部取消，debug 级别
- `_LOG_DRAIN_LOOP_UNEXPECTED_EXCEPTION`（line 128-131）：未预期异常退出，warning 级别，携带 `error_type` 与 `exc_info=True`

**证据**：
- 日志常量全部定义为模块级字符串常量（line 118-131），无魔法字符串
- 异常路径使用 `exc_info=True` 保留完整 traceback
- 日志级别符合 `dayu/README.md` 日志级别语义：debug 用于正常流程分支，warning 用于异常但不阻断

**F1 (Info)**：`_drain_loop` 在捕获未预期异常（line 528-534）后直接返回，不重启。重启依赖 `wake_dispatch` 被后续外部事件触发。若长时间无新 dispatch 入队，drain loop 保持 dead 状态但 `_closed=False`。这是实现 artifact 已记录的残余风险，不属于 S10 scope，但值得在 Phase 11 recovery 或 P10 开始前确认期望行为。

#### 1.2 lane acquire 取消 + `_closed` 路径（line 555-558）

**入口**：`HostDispatchScheduler._dispatch_one` -> `LaneAcquireCancelled` 分支

```python
if isinstance(acquire, LaneAcquireCancelled):
    if self._closed:
        return "skipped"
    self._safe_closeout_worker_startup_timeout(
        record, reason=_WORKER_STARTUP_TIMEOUT_REASON
    )
    return "timed_out"
```

**分析**：当 scheduler 正在 close 时 lane acquire 被取消，直接返回 `"skipped"` 而不执行 terminal closeout。此时 Run 保持 `RUNNING` / Attempt 保持 `STARTING` / dispatch record 为 `WAITING_FOR_LANE`。这属于 scheduler shutdown 的合理语义——close 是进程退出路径，不应再写 durable state。Phase 11 recovery startup scan 可处理该残留状态。

**F2 (Info)**：`test_drain_loop_logs_empty_sleep_and_close` 间接覆盖了 close 路径，但无单独测试显式断言 `LaneAcquireCancelled + _closed` 返回 `"skipped"` 且不写入 terminal closeout。不作为 blocking，因为已有 close 集成测试覆盖了 scheduler 正常关闭，且该行为在 Phase 11 会被 recovery startup scan 处理。

#### 1.3 lane acquire 后 pre-accept cancel race（line 566-573, line 690-701）

**入口**：`HostDispatchScheduler._dispatch_one` -> `_dispatch_record_still_pre_accept`

**实现**：
1. `_mark_dispatching_after_recheck` 在 durable transaction 内 CAS 标记 `DISPATCHING`
2. `await asyncio.sleep(0)` 主动 yield event loop，让 pending cancel 有机会执行
3. `_dispatch_record_still_pre_accept` 重新读 durable dispatch row，检查 `status == DISPATCHING and worker_accept_event_id is None and cancelled_event_id is None`
4. 不满足时释放 lane token，返回 `"skipped"`

**最终 CAS 保护**：即使 `_dispatch_record_still_pre_accept` 通过，`_start_worker` -> `_accept_worker_running` 在单个 write transaction 内通过 `_is_worker_acceptable` 做最终 CAS。如果 worker accept 事务与 cancel 事务竞争，first-committer-wins。

**证据**：测试 `test_cancel_race_after_lane_acquire_releases_lane_without_worker`（dispatch_scheduler test line 919-987）通过 monkeypatch 在 pre-accept recheck 前注入 durable cancel，断言：
- `result.skipped == 1`
- `factory.created == 0`（未调用 worker）
- `run.status is CANCELLED`
- `attempt.status is CANCELLED`
- `dispatch_record.status is CANCELLED`
- lane token 已被释放（通过独立的 `LaneController` 验证可 re-acquire）

**F3 (Info)**：`await asyncio.sleep(0)` 在 line 570 与 `_start_worker` 在 line 574 之间，存在一个 yield 点无法被 `_dispatch_record_still_pre_accept` 覆盖——cancel 可能恰好在 recheck 返回 True 之后、`_start_worker` 调用之前的极短窗口内到达。此窗口由 `_accept_worker_running` 的 CAS 兜底（line 957-1024），不会产生错误状态。窗口内浪费的工作（memory catch-up、RunInput building）是效率问题，不涉及正确性或资源泄漏。当前无可行缩小该窗口的手段且不增加复杂度。

#### 1.4 `_consume_worker_events` cleanup（line 1111-1214）

**入口**：`HostDispatchScheduler._consume_worker_events` -> finally block

**单点 cleanup 闭环**（line 1205-1214）：
```python
finally:
    if run_terminal_closed:
        self._duplicate_governance_registry.clear_run(record.run_id)
    self._active_handles.discard(handle)
    self._active_registry.unregister(
        attempt_id=record.attempt_id,
        execution_id=record.execution_id,
    )
    await _safe_close_worker_handle(handle)
    await _safe_release_lane_token(token)
```

**已验证路径**：
- 正常 EOF（line 1152-1160）：`close_clean_eof` -> finally
- Worker stream 异常（line 1163-1173）：`close_worker_lost` -> finally
- Ingest 异常（line 1184-1194）：`close_worker_lost` -> finally
- Terminal accepted break（line 1201-1204）：break -> finally
- `CancelledError` 传播（line 1161-1162）：raise -> finally（但 close() 方法先 cancel handle，后 cancel task，finally 也会 close handle）
- Pre-event 异常（line 1128 前 `local_worker_id` 第二次读取抛错）：finally 仍执行，close handle + release lane

**证据**：
- `test_worker_stream_exception_closes_run_lost_from_scheduler`（dispatch line 1336-1405）：断言 LOST closeout 后 `handle.closed is True`、registry 已注销、lane token 已释放。
- `test_scheduler_close_during_active_events_releases_all_resources`（dispatch line 1448-1507）：断言 close 后 registry 已注销、lane token 已释放。
- `test_consume_pre_event_exception_releases_lane_and_unregisters`（dispatch line 1534-1573）：断言 pre-event 异常后 `handle.close_count == 1`、registry 已注销、lane token 已释放。
- `test_scheduler_close_lets_active_task_own_handle_close`（dispatch line 1428-1445）：断言 close 只触发 `cancel_count == 1`，`close_count == 1` 由 active task finally 执行一次。

**F4 (Info)**：pre-event 异常路径（line 1128 前）如果 `handle.local_worker_id` 在第二次读取时抛错，`handle.close()` 仍会被 finally 调用。但 `_FlakyLocalWorkerIdHandle` 在 close 时调用 `super().close()` 设置 `self.closed = True`，测试已验证 `handle.close_count == 1`。此路径已覆盖。

#### 1.5 `_safe_closeout_worker_startup_timeout`（line 1075-1109）

**入口**：`HostDispatchScheduler._safe_closeout_worker_startup_timeout`

**双层保护**：内层 `_closeout_worker_startup_timeout` 在 try 中调用；外层 catch 所有 Exception 并 log warning，不向调用方传播错误。无论 durable closeout 成功与否，finally 在 `_dispatch_one`（line 598）中都会释放 lane token。

**F5 (Medium)**：`_closeout_worker_startup_timeout`（line 1026-1073）在 durable write transaction 成功后调用 `self._duplicate_governance_registry.clear_run(record.run_id)`（line 1073）。此清理发生在 `run_write` 之外，不是事务的一部分。若 `clear_run` 抛错（非 Exception），该 Run 的 duplicate governance 残留不会被清理。但由于 `InMemoryRunScopedDuplicateGovernanceRegistry.clear_run` 是纯内存操作，实际上不会失败。风险极低，降级为 Info。

#### 1.6 scheduler close 与 active task 的竞态（line 479-497）

**入口**：`HostDispatchScheduler.close`

**分析**：
1. `close()` 先 cancel drain task
2. 再遍历 `tuple(self._active_handles)` 逐条 cancel handle
3. 再 cancel 所有 active tasks
4. active task 的 finally 也会 close handle + release lane

`_active_handles` 在 iterate 时做 `tuple()` 快照，避免 iteration 中 discard 导致 RuntimeError。cancel handle 与 task cancel 的双重清理是冗余但安全的，因为 `_safe_cancel_worker_handle` 与 `_safe_close_worker_handle` 都吞异常。

**证据**：
- `test_scheduler_close_lets_active_task_own_handle_close` 验证了 `cancel_count == 1, close_count == 1`（handle 级别的幂等清理）
- `test_scheduler_close_suppresses_handle_close_exception` 验证了异常不阻断 close

### 2. dayu/host/waiting.py

#### 2.1 late `resolve_wait` rejection 不触发 projection catch-up（line 570-598）

**入口**：`DefaultHostResolveWaitService.resolve_wait`

**实现**：
```python
result = self._transaction_runner.run_write(
    lambda transaction: self._resolve_in_transaction(
        transaction, wait_id, request
    )
)
if isinstance(result, _LateRejectResult):
    raise HostApiError(
        code=HostApiErrorCode.INVALID_STATE,
        message=result.message,
        retryable=False,
    )
catch_up_projection_best_effort(self._projection_catchup_port)
return result
```

`_LateRejectResult` 在 `catch_up_projection_best_effort` 之前被转换为 `HostApiError` 并 raise，因此 late rejection 路径**确定不会**触发 projection catch-up。

**Late rejection 触发场景**（`_resolve_in_transaction`，line 606-762）：
| 条件 | rejection_reason | 输出 |
|---|---|---|
| wait.status in (RESOLVED, FAILED) + 不同 key 无 replay | — | HostApiError(INVALID_STATE)（不写 diagnostic） |
| wait.status == LOST + 不同 key 无 replay | WAIT_LOST | _LateRejectResult（写 diagnostic） |
| wait.status == CANCELLED | WAIT_CANCELLED | _LateRejectResult（写 diagnostic） |
| wait.status not WAITING | INVALID_WAIT_STATE | _LateRejectResult（写 diagnostic） |
| owner_run.status in terminal (SUCCEEDED, FAILED, CANCELLED, LOST) | RUN_TERMINAL | _LateRejectResult（写 diagnostic） |

**证据**：测试 `test_late_result_after_cancel_writes_bounded_diagnostic`（wait test line 116-179）断言：
- `first_error.value.code is HostApiErrorCode.INVALID_STATE`
- `projection.calls == 0`（line 171）
- `_attempt_count(...)` 不变（line 172）
- 无 `RESUME_REQUESTED`（line 176）
- 无 `ATTEMPT_STARTED`（line 177）
- 同 key 重放不重复写 diagnostic（line 169）
- 不同 key 冲突返回 `IDEMPOTENCY_CONFLICT`（line 166）

#### 2.2 `_reject_late_result` 幂等 scope 独立性（line 795-853）

**入口**：`DefaultHostResolveWaitService._reject_late_result`

**实现**：使用独立 `_WAIT_LATE_REJECTION_SCOPE_KIND = "wait_late_rejection"`（line 100）与 `_WAIT_LATE_REJECTION_RESULT_KIND = "wait_late_rejection_diagnostic"`（line 101），不与 `_WAIT_RESOLUTION_SCOPE_KIND` 共享幂等空间。

**证据**：测试中同 key 同 outcome 重放返回 `INVALID_STATE`（line 165），同 key 不同 outcome 返回 `IDEMPOTENCY_CONFLICT`（line 166）。这说明 idempotency 在 late rejection scope 内正确工作。

**F6 (Info)**：`_resolve_in_transaction` 中 `_reject_late_result` 内部 `HostApiError(IDEMPOTENCY_CONFLICT)`（line 824）直接在 transaction 内 raise，不经过 `resolve_wait` 的 `except HostIdempotencyConflictError` 转换（line 599）。传播路径不同但最终 error code 正确。功能等价，仅代码路径不一致。

#### 2.3 成功的 `resolve_wait` 后 best-effort catch-up（line 597）

**入口**：`resolve_wait` line 597

`resolve_wait` 在非 late rejection 路径（即 `_resolve_resume`、`_resolve_failed`、`_resolve_lost` 成功返回或幂等重放）后调用 `catch_up_projection_best_effort`。失败不抛出异常。

**证据**：`test_wait_after_commit_catchup_failure_tolerance` 在 `tests/host/test_resolve_wait_command.py` 中已覆盖该路径（该测试不在 S10 scope，但验证了历史行为）。

### 3. tests/host/test_dispatch_scheduler.py

**新增 S10 测试**：

| 测试 | 覆盖场景 | 断言要点 |
|---|---|---|
| `test_drain_loop_logs_empty_sleep_and_close`（line 735-766） | drain loop 空队列 debug 日志 + close 取消日志 | caplog 包含两个关键消息 |
| `test_drain_loop_logs_unexpected_exception`（line 679-732） | drain loop 未预期异常退出 warning 日志 | caplog 含 "unexpectedly" |
| `test_cancel_race_after_lane_acquire_releases_lane_without_worker`（line 918-987） | lane acquire 后 cancel race：释放 lane、不调 worker、durable 为 CANCELLED | 5 个断言 + lane 可 re-acquire |
| `test_worker_stream_exception_closes_run_lost_from_scheduler`（line 1336-1405，增强） | worker stream 异常后 handle close + registry unregister + lane release | 新增 handle.closed、registry.cancel=False、lane re-acquire 断言 |

**已有但 S10 相关的测试**：
- `test_scheduler_close_during_active_events_releases_all_resources`：close 期间资源释放全面断言
- `test_consume_pre_event_exception_releases_lane_and_unregisters`：pre-event 异常路径资源释放

**F7 (Info)**：测试文件总长度 2267 行，_SeededRun 和 _options 等 helper 在多个测试文件中重复定义（`test_dispatch_scheduler.py`、`test_run_input_builder.py`、`test_resolve_wait_command.py` 均有自己的 `_SeededRun` 与 `_options`）。这不属于 S10 scope 新增债，但增加未来维护成本。不阻塞当前 gate。

### 4. tests/host/test_run_input_builder.py

**新增 S10 测试**：

`test_current_facts_reject_stale_snapshot_identity`（line 939-1001）使用 `@pytest.mark.parametrize` 覆盖三种 stale identity：

| 字段 | stale 值 | 期望错误 |
|---|---|---|
| `execution_id` | `"execution-stale"` | `HostDurableError("attempt identity mismatch")` |
| `dispatch_record_id` | `"dispatch-stale"` | `HostDurableError("dispatch identity mismatch")` |
| `execution_target` | `"target-stale"` | `HostDurableError("execution_target mismatch")` |

**分析**：这三个字段覆盖了 `AttemptDispatchSnapshot` 中与 durable truth 交叉校验的关键身份字段。`session_id`、`run_id`、`attempt_id` 在 `DurableCurrentRunFactProvider.load_current_run_facts` 中已有交叉校验（校验 run/attempt 存在性）。`policy_snapshot_ref` 与 `cancellation_token` 是 runtime 注入值，不参与 durable identity 校验。

**F8 (Info)**：测试未覆盖 `session_id` 与 `run_id` 的 stale 场景——当前 `DurableCurrentRunFactProvider` 通过 `read_run_by_id` 校验 run 存在性，若 `session_id` 不匹配，当前实现是通过 `run.session_id != snapshot.session_id` 拒绝（在 `_is_dispatchable` 中）。但此测试文件中的 `build()` 调用链不经过 `_is_dispatchable`，而是通过 `load_current_run_facts` -> `_validate_snapshot`。`session_id` mismatch 实际会触发 "run is not in RUNNING" 而非 "session mismatch"。该行为虽正确（fail-closed），但错误消息不够精确。不阻塞 S10。

### 5. tests/host/test_wait_cancel_late_result.py

**新增 S10 测试**：

`test_late_result_after_cancel_writes_bounded_diagnostic`（line 116-179）综合验证 late rejection 完整语义：

| 断言 | 行号 | 类型 |
|---|---|---|
| `first_error.value.code is INVALID_STATE` | 164 | 错误码 |
| `replay_error.value.code is INVALID_STATE` | 165 | 重放不变 |
| `conflict_error.value.code is IDEMPOTENCY_CONFLICT` | 166 | 冲突检测 |
| `len(diagnostics) == 1` | 167 | 单条 diagnostic |
| `diagnostics[0].reason_json == '{"reason_code":"wait_cancelled"}'` | 168 | reason 正确 |
| `after_replay == after_first` | 169 | 重放不追加事件 |
| `projection.calls == 0` | 171 | 不触发 catch-up |
| `_attempt_count(...) == attempt_count_before_late` | 172 | 不创建 Attempt |
| `"RESUME_REQUESTED" not in late_event_types` | 176 | 不创建 resume |
| `"ATTEMPT_STARTED" not in late_event_types` | 177 | 不创建新 Attempt |

**F9 (Info)**：测试仅覆盖 `WAIT_CANCELLED` 一种 late rejection reason。其他 late rejection reason（`WAIT_LOST`、`WAIT_ALREADY_RESOLVED`、`WAIT_ALREADY_FAILED`、`RUN_TERMINAL`、`INVALID_WAIT_STATE`）在 `test_different_key_after_resolved_or_failed_does_not_write_late_diagnostic` 中部分覆盖了 `WAIT_ALREADY_RESOLVED` / `WAIT_ALREADY_FAILED` 的非 diagnostic 路径，但 `WAIT_LOST` 的 diagnostic 写入路径和 `RUN_TERMINAL` 路径无专项测试。这些路径的代码逻辑与 `WAIT_CANCELLED` 路径共享同一 `_reject_late_result` 方法，复用其 idempotency 与 diagnostic 写入，风险可控。

### 6. dayu/host/README.md

**S10 相关变更**：

1. **Line 75**：late result rejection 描述更新
   > "取消后的 late result、`LOST` wait 的 late result 或 terminal Run 上的 late result 只写入 `WAIT_LATE_RESULT_REJECTED` diagnostic，不创建 resume Attempt，不触发 projection catch-up，并使用独立 `wait_late_rejection` 幂等 scope"

   核对：与 `waiting.py` `_reject_late_result` 行为一致。`EventClass.DIAGNOSTIC`、独立幂等 scope `_WAIT_LATE_REJECTION_SCOPE_KIND`、无 resume Attempt、无 projection catch-up。

2. **Line 122**：projection catch-up 范围描述更新
   > "成功的 `resolve_wait` 会在对应 write transaction commit 后 best-effort 调用"

   核对：`resolve_wait` line 597 只在非 `_LateRejectResult` 路径调用 `catch_up_projection_best_effort`。描述精确。

3. **Line 141**：RunInputBuilder durable recheck 描述
   > "只接受同一 snapshot identity 下的 Run `RUNNING`、Attempt `STARTING`、dispatch record `DISPATCHING` 当前事实"

   核对：`DurableCurrentRunFactProvider` 校验 run/attempt/dispatch 状态与 id 一致性。stale snapshot 测试覆盖了 execution_id、dispatch_record_id、execution_target 三个字段的 fail-closed。

**F10 (Info)**：README line 75 未列出 `_WAIT_LATE_REJECTION_SCOPE_KIND` / `_WAIT_LATE_REJECTION_RESULT_KIND` 的具体常量值，也未说明 `WAIT_LATE_RESULT_REJECTED` 使用 `EventClass.DIAGNOSTIC`。对内部开发者的可发现性有轻微影响。不阻塞。

## 测试汇总

S10 targeted tests 覆盖情况：

| 测试文件 | 新增/增强测试 | 覆盖 S10 目标 |
|---|---|---|
| `test_dispatch_scheduler.py` | 3 新增 + 1 增强 | drain loop 可观测性、pre-accept cancel race、worker stream exception cleanup |
| `test_run_input_builder.py` | 1 新增（3 parameterized cases） | stale snapshot identity TOCTOU fail-closed |
| `test_wait_cancel_late_result.py` | 1 新增（综合） | late rejection 不触发 catch-up、不创建 Attempt、不写 resume |

现有 65 tests passed + 0 pyright errors（按实现 artifact 报告）。

## Findings 汇总

| ID | 严重程度 | 文件 | 行号 | 简述 |
|---|---|---|---|---|
| F1 | Info | dispatch.py | 528-534 | `_drain_loop` 异常退出后无自动重启，依赖外部 wakeup |
| F2 | Info | dispatch.py | 555-558 | `LaneAcquireCancelled + _closed` 路径无独立测试 |
| F3 | Info | dispatch.py | 570-574 | pre-accept check 与 `_start_worker` 之间存在 TOCTOU 窗口，由 CAS 兜底 |
| F4 | Info | dispatch.py | 1128+ | pre-event 异常后 finally 仍执行 cleanup，已验证 |
| F5 | Info | dispatch.py | 1073 | `clear_run` 在 durable write 事务外调用（纯内存操作，无实际风险） |
| F6 | Info | waiting.py | 824 | `_reject_late_result` 内 `HostApiError` 传播路径与主路径不一致（功能等价） |
| F7 | Info | 测试 | — | `_SeededRun` / `_options` 在多个测试文件中重复定义 |
| F8 | Info | test_run_input_builder.py | 939-1001 | stale session_id/run_id 场景未显式测试（现有校验已覆盖但错误消息不精确） |
| F9 | Info | test_wait_cancel_late_result.py | 116-179 | 仅覆盖 `WAIT_CANCELLED` 一种 late rejection reason |
| F10 | Info | README.md | 75 | 未列出 late rejection 的具体 scope kind / event class 常量名 |

**无 blocking（high/medium severity）finding。**

## 残余风险

1. `_drain_loop` 异常退出后依赖外部事件重启（F1），在低流量场景下可能长时间 dead。Phase 11 或 P10 前应确认是否需后台 watchdog 或 `asyncio.create_task` 自重启。
2. late rejection diagnostic 写入后 caller 不能通过 `resolve_wait` 再次刷新 projection。若 caller 依赖 rejection 后即时最新 projection，需通过后续成功 command 或显式 repair/catch-up 获得。已写入 README。
3. `_dispatch_record_still_pre_accept` 与 `_accept_worker_running` 之间的 work（memory catch-up、RunInput building）在并发 cancel 下浪费，属于效率问题。当前无低复杂度改进方案。
4. S10 范围内未覆盖的 late rejection reason（`WAIT_LOST` diagnostic 路径、`RUN_TERMINAL` 路径）逻辑与已覆盖的 `WAIT_CANCELLED` 路径共享同一 `_reject_late_result`，代码路径一致但缺少直接测试。

## 结论

- **Finding 数量**：0 block / 0 medium / 10 info
- **Artifact 路径**：`docs/reviews/p9-5-s10-code-review-ds-20260517.md`
- **建议**：**通过**。S10 实现符合设计真源与总控真源约束，drain loop 可观测性正确接入，lane 竞争测试覆盖 pre-accept cancel race 关键路径，RunInputBuilder TOCTOU fail-closed 语义通过参数化测试验证，late `resolve_wait` rejection 不触发 projection catch-up 且不创建 resume Attempt（9 项断言），worker event consumption 异常路径的 finally 单点 cleanup（active registry 注销 + handle close + lane release）均有测试覆盖。所有 finding 为 Info 级别，无 correctness / 状态机 / 架构边界 / 资源释放的 blocking 问题。
