# WU-LIFE-01 + WU-LIFE-02 PR Review

## Meta

- **Reviewer**: AgentDS (PR review).
- **Controller**: AgentController.
- **Gate**: PR review.
- **PR URL**: https://github.com/noho/dayu-agent-r/pull/104
- **Branch**: `feat/host-life-recovery-scheduler-hardening`
- **Base**: `main`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Accepted plan**: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`
- **Accepted aggregate deepreview**: `docs/reviews/wu-life-01-02-aggregate-deepreview-ds-20260601.md`
- **Prior gate artifacts**: plan review → Slice A code review → fix → re-review → controller adjudication → Slice B code review → controller adjudication → aggregate deepreview → controller adjudication (all passed)
- **PR review artifact**: `docs/reviews/wu-life-01-02-pr-review-ds-20260601.md`

## Scope

- Mode: PR #104 relative to `main` full diff.
- Included: `tests/host/test_recovery_scan.py`, `tests/host/test_dispatch_scheduler.py`, `docs/host/host-core-followup-implementation-control.md`, `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`, 19 review artifacts in `docs/reviews/wu-life-01-02-*`.
- Excluded: production code (zero changes confirmed via `git diff main..HEAD --name-only -- 'dayu/'` → no output).
- Review lens:
  - PR 相对 main 的完整 diff 是否满足 WU-LIFE-01/02 plan 与 aggregate adjudication。
  - 是否存在测试误证明、脆弱 private coupling、遗漏 residual tracking、文档状态不一致。
  - 是否有 schema/EventLog/public API/state-machine/README 越界变化。
  - 是否足够支持 draft-PR-pass。

## Production Code Changes

**None.** `git diff main..feat/host-life-recovery-scheduler-hardening --name-only -- 'dayu/'` 输出为空。

所有 PR 变更均为测试补强与文档更新。现有 Host production code 已满足 WU-LIFE-01/02 的全部 plan 要求，无需生产代码修改。

## Plan Alignment Verification

### Slice A: Recovery Lifecycle Proof

逐项对照 plan Section "Slice A Implementation Decisions" 与 "Testing Matrix"：

| Plan Requirement | Status | Direct Evidence |
|---|---|---|
| Recovery lifecycle matrix 常量，≥18 rows，含 scenario_id/run_status/expected_decision/expected_durable_mutation/expected_reason/coverage_classification | ✓ | `_RECOVERY_LIFECYCLE_PROOF_MATRIX`: 18 rows，全部字段已填 |
| scanner still-live integration test | ✓ | `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` (line 483)：heartbeat recent → `OWNER_STILL_LIVE`，`_active_run_observation` before/after 全等，`_assert_no_recovery_or_terminal_facts` 通过 |
| scanner inconclusive integration test（参数化） | ✓ | `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows` (line 521)：`process_probe_error` + `pid_live_no_identity` 参数化，均返回 `ORPHAN_INCONCLUSIVE`，before/after 全等 |
| WAITING diagnostic-only 语义增强 | ✓ | 增强 `test_scan_waiting_uses_diagnostic_only_fallback` + 新增 `test_scan_waiting_durable_read_state_remains_diagnostic_only`：Attempt count 不变、Run 保持 WAITING、`_assert_no_recovery_or_terminal_facts` 通过 |
| missing attempt/dispatch scanner test | ✓ | `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation` (line 602)：dispatch row 删除 → `ORPHAN_INCONCLUSIVE`，reason `missing_current_attempt_or_dispatch`，无 durable mutation |
| RR-DUR-04 proof matrix row | ✓ | `rr-dur-04-short-transaction-durable-truth` (line 268)：`_COVERAGE_NEW`，标注 scanner 使用短事务 durable truth，不触发 production rewrite |
| matrix 覆盖分类验证 | ✓ | `test_recovery_lifecycle_proof_matrix_covers_slice_a_rows`：验证 7 个必需 scenario_id 在场，所有 coverage_classification 合法 |
| 不新增 production recovery API | ✓ | 零生产代码变更 |
| 不改变 WAITING/Run/Attempt 状态机 | ✓ | 零生产代码变更 |

### Slice B: Scheduler Close / cancel_all Lifecycle

逐项对照 plan Section "Slice B Implementation Decisions" 与 "Testing Matrix"：

| Plan Requirement | Status | Direct Evidence |
|---|---|---|
| Scheduler close lifecycle matrix 常量 | ✓ | `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX`: 7 rows，含 scenario_id/window/expected_close_action/expected_durable_mutation/expected_resource_cleanup/coverage_classification |
| `cancel_all` snapshot test | ✓ | `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel`：first_count==1，second_token not cancelled；second cancel_all covers second entry |
| dispatch queue non-empty close | ✓ | `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal`：qsize()==1，factory.created==0，Run/Attempt/dispatch 状态不变，wake/drain fail closed after close |
| promotion non-drain close | ✓ | 扩展 `test_scheduler_close_cancels_tracked_promotion_task`：新增 `promotion_queue.qsize()==1` 断言 + `_assert_no_scheduler_close_terminal_events` |
| lane wait / pre-worker close | ✓ | `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact`：dispatch 在 WAITING_FOR_LANE 时 close，不写 startup timeout，lane close 后 acquire fail |
| close cancellation retry cleanup | ✓ | `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`：lane close 处取消 → CancelledError 传播 → 再次 close 完成 cleanup → active registry empty / handle close once / lane closed / duplicate registry cleared |
| matrix 覆盖分类验证 | ✓ | `test_scheduler_close_lifecycle_matrix_covers_slice_b_windows`：验证 5 个必需 scenario_id 在场，所有 coverage_classification 合法 |
| 不让 scheduler close 写 terminal facts | ✓ | 全部 5 个 focused tests 通过 `_assert_no_scheduler_close_terminal_events` 断言 7 种 terminal event type count==0 |
| 不把 close 改成 drain-until-empty | ✓ | 测试证明 queue 非空 close 不处理 pending work；non-goal row 标注 `close-drain-until-empty` |
| 不修改 public cancel command | ✓ | 零生产代码变更 |

## Design Source Alignment (Section 27)

对照 `docs/host/design.md` Section 27 逐项验证：

| Design Requirement | Status | Evidence |
|---|---|---|
| `ACCEPTED` 不得进入 `RECOVERING` (line 2904) | ✓ | matrix row `accepted-startup-wake`：existing coverage |
| `QUEUED` 保持 `QUEUED` (line 2905) | ✓ | matrix row `queued-startup-promotion-check`：existing coverage |
| `WAITING` 保持 `WAITING`，不创建 Attempt (line 2906, 2935) | ✓ | 两个 WAITING tests：durable read 证明 Attempt count 不变，无 recovery/terminal facts |
| `RUNNING`/`CANCELLING` 只有 positive orphan proof 才进入 `LOST` (line 2907, 2938) | ✓ | still-live/inconclusive/positive-orphan 三向测试：only positive orphan writes `ATTEMPT_LOST` |
| Recovery 必须创建新 Attempt (line 2911) | ✓ | matrix row `recovering-under-dispatch-limit`：existing coverage in `test_recovery_dispatch.py` |
| Recovery truth 只能是 durable truth，不依赖 projection/read model (line 2913) | ✓ | `test_scan_running_positive_orphan_moves_to_recovering_without_projection`（existing）+ RR-DUR-04 matrix row |
| owner heartbeat stale 但 positive orphan proof 不成立 → 只 diagnostic，不写 recovery/terminal facts (line 2948) | ✓ | still-live + inconclusive tests：`_assert_no_recovery_or_terminal_facts` 全通过 |
| 上限 recovery dispatch → `LOST` (line 2947) | ✓ | matrix row `recovering-over-dispatch-limit-projection-lag`：existing coverage |
| positive orphan proof 才能写 `ATTEMPT_LOST` (line 2938) | ✓ | classifier tests（existing）+ still-live/inconclusive integration tests（new）|

### Host Close 语义对齐

对照 `docs/host/design.md` Line 902-904（Host opener close 语义）：

| Design Requirement | Status | Evidence |
|---|---|---|
| close 不得伪装成用户取消 | ✓ | `_SCHEDULER_CLOSE_REASON = "scheduler_close"`，所有 cancel_all 使用此 reason |
| close 不得写 `CANCEL_REQUESTED`/`RUN_CANCELLED`/`RUN_FAILED` (line 902) | ✓ | `_assert_no_scheduler_close_terminal_events` 覆盖 7 种 terminal type，全部 close-window tests 调用 |
| 未收口 active Attempt 通过 positive orphan proof 进入 `ATTEMPT_LOST` (line 902) | ✓ | design alignment：close 后 Run/Attempt/dispatch 保持非 terminal，由 next open recovery scan 解释 |

## Design Alignment Summary

WU-LIFE-01/02 完全满足 `docs/host/design.md` Section 27 全部要求：
- Recovery durable truth（不依赖 projection checkpoint / read model / memory lag / stress summary）
- Positive orphan proof（OwnerStillLive → skip；OrphanProofInconclusive → skip；PositiveOrphanProof → close orphan）
- WAITING 不恢复（run status unchanged，no new Attempt，no recovery/terminal facts）
- Host close 不写 terminal facts（全程无 EventLog append）
- Scheduler close 不无限 drain（cancel drain/promotion tasks，不遍历 queue）

## Contract / Schema / State-Machine / Public API Boundary Check

| Boundary | Status |
|---|---|
| Durable schema | unchanged ✓ |
| EventLog event type / payload contract | unchanged ✓ |
| Host public API / Service-facing behavior | unchanged ✓ |
| Run / Attempt state machine | unchanged ✓ |
| `WAITING` durable semantics | unchanged ✓ |
| Close terminal fact boundary | unchanged ✓ |
| Recovery truth source | unchanged ✓ |
| `dayu/host/README.md` | no trigger ✓ |
| `tests/README.md` | no trigger ✓ |
| Public cancel command (`cancel_session_runs`) | unchanged ✓ |

## Findings

### PR1-信息-Close-window 测试访问 scheduler 私有内部状态

- **入口**: `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal`、`test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`、`test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact`、扩展的 `test_scheduler_close_cancels_tracked_promotion_task`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:2625-2756, 2773-2840`
- **输入场景**: close-window deterministic tests 需要验证 scheduler 内部清理状态
- **实际行为**: 测试直接访问 `scheduler._closed`、`scheduler._close_cleanup_done`、`scheduler._active_tasks`、`scheduler._active_handles`、`scheduler._queue`、`scheduler._promotion_queue`、`scheduler._duplicate_governance_registry`、`scheduler._lane_controller`、`scheduler._drain_task`
- **影响**: 这些私有属性若在未来的 scheduler refactor 中改名或重组，测试会不必要地失败，即使行为仍然正确。属于实现细节的 private coupling
- **严重程度评估**: 低。这些属性是 `HostDispatchScheduler` 的稳定内部状态（`_closed`/`_close_cleanup_done` 自 2026-05 起存在），close lifecycle 是 Host 核心语义，不太可能在非破坏性 refactor 中剧烈改变。plan 已明确允许 monkeypatch/barrier 方式做 deterministic test；RR-LIFE-01 已记录若未来 close() refactor 改变 cleanup 顺序需补测试
- **建议**: 不要求修改。当前设计方案已在 plan 中明确接受并以 RR-LIFE-01 追踪

### PR2-信息-`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 不含 successful completion event types

- **入口/函数**: `_assert_no_scheduler_close_terminal_events`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:164-172, 4395`
- **输入场景**: 若未来代码变更使 scheduler close 错误写入 `RUN_COMPLETED` 或 `ATTEMPT_COMPLETED`
- **实际行为**: `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 定义的 7 种 type 不含 `RUN_COMPLETED` 和 `ATTEMPT_COMPLETED`
- **影响**: 极低。当前生产代码 `close()` 全程无 EventLog append，且 `RUN_COMPLETED` 不可能由 close 触发。此 gap 在当前代码中不会产生漏检
- **建议**: 不要求修改。已由 RR-LIFE-02 追踪，建议未来改成 close 前后 EventLog event type set 不变断言以自动覆盖新增 type

### PR3-信息-Close cancellation retry test 仅覆盖 lane close 边界

- **入口/函数**: `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:2773`
- **输入场景**: scheduler close 仅 lane close 处被外层取消
- **实际行为**: `_CloseOnceBlockedLaneClose` 在 `lane_controller.close()` 处阻塞（`close()` line 1691），close task 被取消后再次调用 close 完成 cleanup
- **影响**: 低。close() 中其他步骤（cancel heartbeat/drain/promotion tasks、cancel_all、cancel active tasks、clear duplicate registry）在 retry 时均为 idempotent no-op，且 `_closed=True` 阻止新 worker 注册。但若未来 close() 顺序变化或插入非幂等步骤，当前测试不会捕获回归
- **建议**: 不要求修改。plan 已在 stop condition 中明确：若 close() refactor 改变 cleanup 顺序或增加非幂等步骤，必须补对应取消边界 retry test。此风险已在 aggregate deepreview AG2 中记录，属于 coverage completeness observation

## Prior Review Findings Status

### Slice A Findings (6 total)

| ID | 描述 | 裁决 | 最终状态 |
|---|---|---|---|
| A-MIMO-01 | `_active_run_observation` 应用 `run_read` | accepted | re-review 确认已修复 |
| A-MIMO-02 | 机械格式化 churn 回退 | accepted | re-review 确认已修复 |
| A-DS-01 | 无关格式化 churn 回退 | accepted | re-review 确认已修复 |
| A-DS-02 | WAITING matrix row 拆分 | accepted | re-review 确认已修复 |
| A-DS-03 | missing attempt/dispatch scanner test | accepted | re-review 确认已修复 |
| A-DS-04 | durable-read WAITING 测试名修正 | accepted | re-review 确认已修复 |

Slice A: 6/6 accepted → fixed → re-review passed. ✓

### Slice B Findings (6 total)

| ID | 描述 | 裁决 | 最终状态 |
|---|---|---|---|
| B-MIMO-01 | `_run_scheduler_drain_once` 语义薄 | rejected | closed ✓ |
| B-MIMO-02 | worker-started-but-not-accepted window | deferred-with-owner | → RR-LIFE-01 ✓ |
| B-DS-01 | `_SCHEDULER_CLOSE_REASON` 重复私有常量 | rejected | closed ✓ |
| B-DS-02 | close cancellation test 访问私有状态 | rejected | closed ✓ |
| B-DS-03 | terminal event type list 维护 | deferred-with-owner | → RR-LIFE-02 ✓ |
| B-DS-04 | `_RegisteringCancelHandle.cancel_reasons` 自定义属性 | rejected | closed ✓ |

Slice B: 4 rejected + 2 deferred-with-owner. 全部已裁决并关闭或追踪. ✓

### Aggregate Deepreview Findings (3 total)

| ID | 描述 | 严重程度 | 当前状态 |
|---|---|---|---|
| AG1 | Control Doc 未追踪 Slice B deferred residual risk | 低 | **已修复**：control doc Residual Risk 表现含 RR-LIFE-01 和 RR-LIFE-02（line 191-192） |
| AG2 | Close cancellation retry test 仅覆盖单一取消边界 | 信息 | 保持观察（本文档 PR3） |
| AG3 | `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 不含 completion events | 信息 | 保持观察（本文档 PR2） |

AG1 确认已在 PR 中修复。AG2/AG3 为 informational，不阻塞。

## Residual Risk Tracking Status

Control doc Residual Risk 表（line 182-192）：

| ID | 状态 | 验证 |
|---|---|---|
| RR-STRESS-01 | deferred-with-owner | 不变 ✓ |
| RR-STRESS-02 | deferred-with-owner | 不变 ✓ |
| RR-DUR-01 | **closed** | 从 deferred-with-owner 更新为 closed，echoes WU-LIFE discussion ✓ |
| RR-DUR-02 | deferred-with-owner | 不变 ✓ |
| RR-DUR-03 | deferred-with-owner | 不变 ✓ |
| RR-DUR-04 | **closed** | 从 deferred-with-owner 更新为 closed，echoes Slice A proof ✓ |
| RR-DUR-05 | deferred-with-owner | 不变 ✓ |
| RR-LIFE-01 | **deferred-with-owner** | 新增，对应 B-MIMO-02 + AG2 ✓ |
| RR-LIFE-02 | **deferred-with-owner** | 新增，对应 B-DS-03 + AG3 ✓ |

全部 tracking items 处于 `closed` 或 `deferred-with-owner`，满足 control doc "ready-to-open-draft-PR 前所有 items 必须有 owner" 规则。✓

## Document Consistency Check

| 文档 | 检查项 | 结果 |
|---|---|---|
| control doc gate | "discussion-ready" → "ready-to-open-draft-PR" | ✓ |
| control doc implementation status | WU-LIFE-01/02 完成状态更新 | ✓ |
| control doc plan artifacts | 新增 `wu-life-01-02-recovery-scheduler-lifecycle-plan.md` | ✓ |
| control doc implementation commits | 新增 accepted plan/sliceA/sliceB/deepreview | ✓ |
| control doc review artifacts | 新增 19 个 review artifact 引用 | ✓ |
| control doc aggregate review artifacts | 新增 aggregate deepreview 引用 | ✓ |
| control doc WU-LIFE gate artifacts table | 新增，覆盖所有 gate 的 artifact + validation | ✓ |
| control doc Residual Risk | RR-DUR-01/04 closed，RR-LIFE-01/02 added | ✓ |
| control doc Work Units table | WU-LIFE-01/02 状态更新为 "已完成本地 gate；ready-to-open-draft-PR" | ✓ |
| plan document | 新建在 `docs/host/`，符合 plan artifacts 目录约定 | ✓ |
| README | 无触发更新条件（无 production code change、无 public contract change、无 test entry/marker/convention change） | ✓ |

## Validation

Plan-defined aggregate validation（control doc line 143）：

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py \
  tests/host/test_recovery_orphan_classifier.py tests/host/test_dispatch_scheduler.py \
  tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py \
  tests/host/test_public_cancel_session_runs.py tests/host/test_recovery_multiprocess.py -q
# → 110 passed

python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings
```

验证范围覆盖：
- Slice A 全部 affected tests + existing regression（recovery scan, recovery dispatch, orphan classifier）
- Slice B 全部 affected tests + existing regression（dispatch scheduler, open_host_runtime, public lifecycle, public cancel）
- Cross-slice regression（multiprocess recovery）
- pyright 全量类型检查
- Stress suite 按 plan 不在默认 validation 中

## Test Determinism Audit

全部新增测试使用确定性机制，未发现 sleep/race 依赖：

| Test | Determinism Mechanism |
|---|---|
| `test_recovery_lifecycle_proof_matrix_covers_slice_a_rows` | 纯数据验证，无 I/O |
| `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` | `_PidMissingProbe` + `_mark_owner_heartbeat`（固定 timestamp） |
| `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows` | `_PidProbeErrorProbe` / `_PidLiveNoIdentityProbe`（固定 probe response） |
| `test_scan_waiting_durable_read_state_remains_diagnostic_only` | `_mark_run_status` + `_PidMissingProbe`（确定性状态转换） |
| `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation` | `_delete_dispatch_record_for_attempt`（确定性 row 删除） |
| `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel` | `_RegisteringCancelHandle.on_cancel` 同步注册（无并发） |
| `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` | `wake_dispatch` 后直接 close（无 drain loop 启动） |
| `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact` | `_BlockedLaneAcquire` + `asyncio.Event` barrier |
| `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish` | `_CloseOnceBlockedLaneClose` + `_ControlledBlockingHandle` + `asyncio.Event` barrier |
| 扩展 `test_scheduler_close_cancels_tracked_promotion_task` | `asyncio.Event` barrier + `_promotion_queue.put_nowait` |

## Blocking Open Questions

**None.**

## Conclusion

**Pass.** No blocking findings.

- **Finding count**: 3（0 blocking, 0 low-severity unfixed, 3 informational）
- **Production code**: 零变更 — 现有 Host 实现已满足 WU-LIFE-01/02 全部 plan 要求
- **Design alignment**: 完全满足 `docs/host/design.md` Section 27 全部要求
- **Plan alignment**: Slice A 与 Slice B 所有 plan requirements 均已满足
- **Cross-slice conflict**: none（不同 test files，不同 concerns，零 production code change）
- **Contract boundary**: 无 schema/EventLog/public API/state-machine/README 越界变化
- **Prior review findings**: Slice A 6/6 fixed + re-review passed；Slice B 2 deferred（均已进入 control doc Residual Risk）；aggregate deepreview AG1 已修复
- **Residual risk**: 全部 tracked（closed 或 deferred-with-owner），无无主 open item
- **Test determinism**: 全部使用 deterministic barrier/probe/timestamp，无 sleep/race 依赖
- **Validation**: 110 tests passed, pyright 0 errors
- **draft-PR-pass**: 是，PR 满足 draft-PR-pass 条件
