# WU-LIFE-01 + WU-LIFE-02 Aggregate Deep Review

日期：2026-06-01
Reviewer：AgentMiMo
Role：aggregate deepreview
Gate：aggregate deepreview
Controller：AgentController
Design source：docs/host/design.md
Control source：docs/host/host-core-followup-implementation-control.md
Plan：docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md
Slice A commit：b8f4568
Slice B commit：0e7caf8
Selected base：main

## Scope

- Mode: current changes
- Branch: feat/host-life-recovery-scheduler-hardening
- Base: main
- Output file: docs/reviews/wu-life-01-02-aggregate-deepreview-mimo-20260601.md
- Included scope: tests/host/test_recovery_scan.py, tests/host/test_dispatch_scheduler.py, docs/host/, docs/reviews/
- Excluded scope: dayu/host/ production code (no diff against main)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 证据摘要

#### 1. 生产代码零变更验证

`git diff main...HEAD -- dayu/host/recovery.py dayu/host/dispatch.py dayu/host/open_host.py dayu/host/recovery_process.py dayu/host/durable/run_transition.py` 输出为空。本次 work unit 严格遵守 plan 约束：tests-first，未修改任何生产代码。

#### 2. Recovery Lifecycle Proof Matrix（Slice A）正确性

`_RECOVERY_LIFECYCLE_PROOF_MATRIX`（test_recovery_scan.py:88-259）覆盖 20 行场景，分类正确：

| scenario_id | coverage | 证据 |
|---|---|---|
| accepted-startup-wake | existing | test_scan_accepted_does_not_mutate_or_create_attempt 已存在 |
| queued-startup-promotion-check | existing | test_scan_queued_does_not_mutate_or_create_attempt 已存在 |
| waiting-diagnostic-only-low-level | existing | test_scan_waiting_uses_diagnostic_only_fallback 已存在，新增 reason 断言 |
| waiting-durable-read-diagnostic-only | new | test_scan_waiting_durable_read_state_remains_diagnostic_only 新增 |
| running-positive-orphan-projection-lag | existing | test_scan_running_positive_orphan_moves_to_recovering_without_projection 已存在 |
| running-owner-heartbeat-recent | new | test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows 新增 |
| running-process-probe-error | new | test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows parametrize 新增 |
| running-stale-heartbeat-only | new | 同上 parametrize，pid live without identity |
| running-missing-current-attempt-or-dispatch | new | test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation 新增 |
| cancelling-positive-orphan | existing | test_scan_cancelling_positive_orphan_loses_attempt_then_run 已存在 |
| recovering-under-dispatch-limit | existing | recovery dispatch 测试已存在 |
| recovering-over-dispatch-limit-projection-lag | existing | test_scan_recovering_loses_when_eventlog_recovery_limit_reached 已存在 |
| rr-dur-04-short-transaction-durable-truth | new | proof matrix row，scanner 使用 run_write 短事务 |
| stress / rr-dur-01 | non-goal | 按 plan 明确排除 |

#### 3. Still-live / Inconclusive 集成测试正确性

- `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows`：seed 默认 heartbeat_at=03:00:00（stale），`_mark_owner_heartbeat` 更新为 03:04:00（距 _NOW=03:04:05 仅 5 秒，stale_after=30s）。`classify_orphan_candidate` 在 line 269 先检查 `policy.now - heartbeat_at <= policy.stale_after`，命中后返回 `OwnerStillLive(reason="owner_heartbeat_recent")`，不进入 `_classify_stale_owner`。测试使用 `_PidMissingProbe()` 但 probe 不参与决策——heartbeat check short-circuit 正确。断言 `_active_run_observation(before) == _active_run_observation(after)` + `_assert_no_recovery_or_terminal_facts` 证明无 durable mutation。

- `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows`：默认 heartbeat_at=03:00:00（stale），`_PidProbeErrorProbe` 返回 `probe_error_code="permission_denied"`，`_classify_stale_owner` line 309 命中 `evidence.probe_error_code is not None` → `OrphanProofInconclusive(reason="process_probe_error")`。`_PidLiveNoIdentityProbe` 返回 `exists=True` 但 `observed_start_token=None`，`_classify_stale_owner` line 327+ 命中 `not evidence.observed_start_token` → `OrphanProofInconclusive(reason="owner_pid_live_without_identity_proof")`。均不写 recovery/terminal facts。

- `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation`：通过 `_delete_dispatch_record_for_attempt` 删除 dispatch row，`_classify_active_or_cancelling` line 360 命中 `dispatch_record is None` → `ORPHAN_INCONCLUSIVE`。reason 字符串 `"missing_current_attempt_or_dispatch"` 与生产代码 recovery.py:364 一致。

#### 4. WAITING 不恢复证明

- 既有 `test_scan_waiting_uses_diagnostic_only_fallback` 已证明 WAITING 不创建 Attempt、不推进状态。本次新增 reason 断言 `_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE` 与生产代码 recovery.py:275 一致。
- 新增 `test_scan_waiting_durable_read_state_remains_diagnostic_only` 构造 WAITING Run 后 scan，断言 Run 仍 WAITING、Attempt 数不变、无 recovery/terminal facts。使用 `_mark_run_status` 从 RUNNING 转为 WAITING 后 scan，覆盖 durable read 语义。

#### 5. Scheduler Close / cancel_all Lifecycle（Slice B）正确性

- `test_scheduler_close_lifecycle_matrix_covers_slice_b_windows`：验证 5 个 required_ids 存在且 coverage_classification 包含 existing / new / non-goal 三类。
- `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel`：使用 `_RegisteringCancelHandle` 在 cancel 回调中注册 second entry，断言 first `cancel_all` 只取消 first entry（count=1），second `cancel_all` 取消 second entry（count=2）。证明快照语义。
- `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal`：queue 非空 close 后 `_queue.qsize() == 1`、`factory.created == 0`、Run/Attempt/dispatch 状态不变、`_assert_no_scheduler_close_terminal_events`。close 后 `wake_dispatch` / `drain_once` 抛 RuntimeError。
- `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact`：`_BlockedLaneAcquire` 阻塞 drain path，close 取消 drain task 后 drain task done、factory 未创建、dispatch 状态保持 WAITING_FOR_LANE、`cancelled_event_id is None`、lane controller closed。
- `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`：`_CloseOnceBlockedLaneClose` 阻塞第一次 lane close，close_task.cancel() 后 `_closed is True`、`_close_cleanup_done is False`。第二次 `await scheduler.close()` 完成 cleanup：`blocked_close.calls == 2`、`_close_cleanup_done is True`、active tasks/handles 清空、duplicate governance cleared、lane closed、无 terminal facts。
- `test_scheduler_close_cancels_tracked_promotion_task` 扩展：新增 `_promotion_queue.put_nowait("session-promotion-pending")` 断言 close 后 `_promotion_queue.qsize() == 1`（不 drain）+ `_assert_no_scheduler_close_terminal_events`。

#### 6. Close re-entrancy 生产代码验证

`HostDispatchScheduler.close()`（dispatch.py:1659-1698）：
- Line 1665: `if self._closed and self._close_cleanup_done: return` — 只有两者都为 True 才跳过。
- Line 1667: `self._closed = True` — 首先设置。
- Line 1694: `self._close_cleanup_done = True` — 最后设置。

若 close 在中途被 CancelledError 中断（如 lane close await），`_closed=True` 但 `_close_cleanup_done=False`。再次 close 时 guard 不命中，重新执行所有步骤。已完成的 cancel 操作为 no-op（task already done），lane close 第二次正常执行。`_suppress_task_cancel`（dispatch.py:3449-3459）对已完成 task 的 `await task` 立即返回。设计正确。

#### 7. Schema / EventLog / Public API / State-machine 越界检查

| 边界 | 状态 | 证据 |
|---|---|---|
| Durable schema | 未变更 | diff 仅含 test 文件与 docs |
| EventLog event type | 未变更 | 无新 event type |
| Host public API | 未变更 | 无 api.py 修改 |
| Run / Attempt state machine | 未变更 | 无状态转换逻辑修改 |
| WAITING durable semantics | 未变更 | 无 WAITING 语义变更 |
| Close terminal fact boundary | 未变更 | close 不写 terminal facts 由测试证明 |
| README / doc sync | 不需要 | 仅新增测试与 docs，未改变 public contract 或测试入口 |

#### 8. Slice A / Slice B 互不冲突

- Slice A 仅修改 `tests/host/test_recovery_scan.py`
- Slice B 仅修改 `tests/host/test_dispatch_scheduler.py`
- 无文件重叠，无生产代码交叉，无 import 冲突

#### 9. 测试质量检查

- 无 sleep / race / timing 依赖：所有新测试使用 deterministic barriers（`asyncio.Event`）、monkeypatch 和直接 durable reads
- 无私有耦合过度：Slice B 测试访问 `_closed`、`_close_cleanup_done`、`_queue`、`_drain_task`、`_active_tasks`、`_active_handles`、`_duplicate_governance_registry` 等内部状态，但这是 focused lifecycle test 验证 close cleanup 完整性的最小可行证据（Slice B controller adjudication 已接受）
- reason 字符串一致性：所有测试中的 reason 常量与生产代码私有常量精确匹配

#### 10. RR-DUR-04 Proof Matrix

`rr-dur-04-short-transaction-durable-truth` row 标注为 `_COVERAGE_NEW`，description 明确 scanner 使用 `run_write` 短事务。结合既有 projection-lag recovery tests（test_scan_running_positive_orphan_moves_to_recovering_without_projection、test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag），recovery scanner 不依赖 projection lag 作为 truth 已被证明。

## Open Questions

无。

## Residual Risk

- RR-STRESS-01 / RR-STRESS-02：stress suite 边界与 pytest-timeout 限制，由 WU-STRESS-01 residual risk tracking 覆盖，不属本 work unit。
- RR-DUR-02 / RR-DUR-03 / RR-DUR-05：deferred to future work units，已在 control doc 追踪。
- `worker-started-but-not-accepted` window（Slice B controller adjudication B-MIMO-02）：plan 允许 deterministic fixture 不可得时 stop/report，当前 lane-wait 与 active-worker close tests 覆盖相邻稳定窗口。deferred-with-owner。
- `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES`（Slice B controller adjudication B-DS-03）：需随未来 terminal event type 扩展同步维护。deferred-with-owner。
- 测试对 scheduler 私有状态的访问：当前是 focused lifecycle test 的最小可行证据，若后续 scheduler 内部重构可能需要同步测试。风险低，因为测试覆盖的是 close cleanup 完整性的不变量，不是实现细节。

## Verification Commands

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q
pytest tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
pytest tests/host/test_recovery_multiprocess.py -q
python -m pyright dayu/ tests/ utils/
```
