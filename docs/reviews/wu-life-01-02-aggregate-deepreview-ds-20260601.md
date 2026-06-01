# WU-LIFE-01 + WU-LIFE-02 Aggregate Deepreview

## Meta

- **Reviewer**: AgentDS (deepreview).
- **Controller**: AgentController.
- **Gate**: aggregate deepreview.
- **Design source**: `docs/host/design.md`.
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`.
- **Accepted plan**: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`.
- **Slice A accepted commit**: `b8f4568`.
- **Slice B accepted commit**: `0e7caf8`.
- **Review target**: branch `feat/host-life-recovery-scheduler-hardening` relative to `main` full diff.
- **Aggregate review artifact**: `docs/reviews/wu-life-01-02-aggregate-deepreview-ds-20260601.md`.

## Scope

- Mode: current changes (aggregate of Slice A + Slice B).
- Branch: `feat/host-life-recovery-scheduler-hardening`.
- Base: `main`.
- Included: `tests/host/test_recovery_scan.py`, `tests/host/test_dispatch_scheduler.py`, `docs/host/*.md`, `docs/reviews/wu-life-01-02-*`.
- Excluded: production code (unchanged), stress suite, multiprocess tests (not in default validation).
- Prior Slice A reviews: Slice A code review → fix → re-review → controller adjudication (all passed).
- Prior Slice B reviews: Slice B code review → controller adjudication (passed, no fix needed).

## Cross-Slice Verification

### Slice A ↔ Slice B Non-Conflict

- Slice A modifies only `tests/host/test_recovery_scan.py`.
- Slice B modifies only `tests/host/test_dispatch_scheduler.py`.
- Both slices are tests-only; zero production code changes.
- Different test modules, different concerns (recovery scan vs. scheduler close), no shared mutable state, no import coupling between the two test files.
- No shared test fixtures, no shared constants between slices.
- Both slices independently pass against the same production code baseline.

### Plan Alignment

Slice A 逐项对照 plan 要求：

| Plan Requirement | Status | Direct Evidence |
|---|---|---|
| Recovery lifecycle matrix 常量 | ✓ | `_RECOVERY_LIFECYCLE_PROOF_MATRIX` 含 18 行，含 scenario_id、run_status、expected_decision、expected_durable_mutation、expected_reason、coverage_classification |
| scanner still-live integration test | ✓ | `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` (line 483) |
| scanner inconclusive integration test | ✓ | 参数化 `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows` (line 521)：process_probe_error + pid_live_no_identity |
| WAITING diagnostic-only semantic | ✓ | 增强 `test_scan_waiting_uses_diagnostic_only_fallback` + 新增 `test_scan_waiting_durable_read_state_remains_diagnostic_only` |
| missing attempt/dispatch scanner test | ✓ | `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation` (line 602) |
| RR-DUR-04 proof matrix row | ✓ | `rr-dur-04-short-transaction-durable-truth` (line 268)，NEW，不触发 production rewrite |
| 不新增 production recovery API | ✓ | 无生产代码变更 |
| 不改变 WAITING/Run/Attempt 状态机 | ✓ | 无生产代码变更 |

Slice B 逐项对照 plan 要求：

| Plan Requirement | Status | Direct Evidence |
|---|---|---|
| Scheduler close lifecycle matrix 常量 | ✓ | `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` 含 7 行 |
| `cancel_all` snapshot test | ✓ | `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel` |
| dispatch queue non-empty close | ✓ | `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` |
| promotion non-drain close | ✓ | 扩展 `test_scheduler_close_cancels_tracked_promotion_task` |
| lane wait / pre-worker close | ✓ | `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact` |
| close cancellation retry cleanup | ✓ | `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish` |
| 不把 close 改成 drain-until-empty | ✓ | 测试证明 queue 非空 close 不处理 pending work |
| 不让 scheduler close 写 terminal facts | ✓ | 全部 5 个 focused tests 调用 `_assert_no_scheduler_close_terminal_events` |

## Design Source Alignment (Section 27)

### Recovery Durable Truth

- `StartupRecoveryScanner.scan()` 在单一 `run_write` transaction 内读取 `read_non_terminal_runs()` 并分类（`recovery.py` line 197-212）。
- Scanner 读取 Run / Attempt / dispatch / liveness / EventLog truth，不读取 projection checkpoint、read model、memory snapshot lag 或 stress summary。
- 测试 `test_scan_running_positive_orphan_moves_to_recovering_without_projection`（line 422）插入 projection lag marker（`_insert_projection_lag_marker`），断言 scanner 仍基于 durable truth 做出 `RUN_RECOVERING` 决策。
- 测试 `test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag`（line 758）证明 RECOVERING limit 只看 canonical EventLog count，projection lag 不影响 LOST 决策。

### Positive Orphan Proof

- `_classify_active_or_cancelling()`（`recovery.py` line 341）只在 `isinstance(classification, PositiveOrphanProof)` 时进入 `_close_positive_orphan()`；`OwnerStillLive` 和 `OrphanProofInconclusive` 不写 recovery/terminal facts。
- `_classify_stale_owner()`（`recovery_process.py` line 279）严格区分：pid missing → positive proof (L317-323)、start_token mismatch → positive proof (L324-333)、boot_id mismatch → positive proof (L334-344)、process identity matched → still-live (L345-351)、pid live without identity → inconclusive (L352-358)。
- 测试覆盖：still-live（heartbeat recent）、inconclusive（process probe error / pid live without identity）、positive orphan（pid missing）均通过 fake probe + 固定时间戳 deterministic 验证。

### WAITING 不恢复

- `_classify_run()`（`recovery.py` line 271-276）对 `RunStatus.WAITING` 返回 `WAITING_DIAGNOSTIC_ONLY`，reason `waiting_adapter_observation_unavailable`，不创建 Attempt。
- 测试 `test_scan_waiting_uses_diagnostic_only_fallback`（line 552）和 `test_scan_waiting_durable_read_state_remains_diagnostic_only`（line 574）证明 Attempt count 不变、Run 状态保持 WAITING、无 recovery/terminal facts。

### Host Close 不写 Terminal Facts

- `HostDispatchScheduler.close()`（`dispatch.py` line 1659-1698）只执行：mark stopping、cancel heartbeat/drain/promotion tasks、`cancel_all`、cancel active tasks、close lane controller、clear duplicate registry、mark stopped。全程无 EventLog append。
- `_best_effort_mark_host_instance_stopping/stopped` 只写 `host_instances` 表（instance lifecycle diagnostic），不写 EventLog。
- `_consume_worker_events()` 中对 `cancellation_token.is_cancelled() and not self._closed` 的 guard（`dispatch.py` 相关路径）确保 scheduler close 期间 (`_closed=True`) 不把 active worker EOF 映射为 user cancel terminal fact。
- Slice B 全部 5 个 close-window tests 通过 `_assert_no_scheduler_close_terminal_events` 断言 7 种 terminal event type count == 0。

### Scheduler Close 不无限 Drain

- `close()` 通过 cancel drain/promotion tasks（line 1679-1686）停止处理，不遍历 queue。
- 测试 `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` 证明 queue 非空 close 后 `qsize() == 1`。
- 测试 `test_scheduler_close_cancels_tracked_promotion_task`（扩展版）证明 promotion task cancelled 后 `_promotion_queue.qsize() == 1`。
- close 后 `wake_dispatch`/`drain_once` fail closed（`RuntimeError("HostDispatchScheduler is closed")`）。

## Findings

### AG1-未修复-低-Control Doc 未追踪 Slice B Deferred Residual Risk

- **入口/函数**: control doc Residual Risk 表 (`docs/host/host-core-followup-implementation-control.md` line 181-189)
- **文件(行号)**: `docs/host/host-core-followup-implementation-control.md:181-189`
- **输入场景**: Slice B controller adjudication 将两项 finding 裁决为 `deferred-with-owner`
- **实际分支**: control doc 的 Residual Risk 表仅有 RR-STRESS-01/02 和 RR-DUR-01/02/03/04/05，无 Slice B deferred items
- **预期行为**: 按 control doc 追踪规则（line 167-172），`ready-to-open-draft-PR` 前所有 deferred-with-owner items 必须进入 Residual Risk 表
- **实际行为**: B-MIMO-02（worker-started-but-not-accepted deterministic window gap）和 B-DS-03（`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 需随未来 terminal event type 同步维护）仅在 controller adjudication artifact 中记录，未进入 control doc Residual Risk 表
- **直接证据**: 
  - `docs/reviews/wu-life-01-02-code-controller-adjudication-sliceB-20260601.md` line 22-25：B-MIMO-02 deferred-with-owner，B-DS-03 deferred-with-owner
  - `docs/host/host-core-followup-implementation-control.md` line 181-189：Residual Risk 表无对应 tracking items
- **影响**: 两项已知 deferred risk 未进入统一追踪表，后续 work unit 或 PR reviewer 可能遗漏；不产生 correctness 或 stability 问题
- **建议改法和验证点**: 在 control doc Residual Risk 表增加两条 tracking item：`RR-LIFE-01`（worker-started-but-not-accepted window，deferred-with-owner → future scheduler hardening owner）和 `RR-LIFE-02`（terminal event type list co-maintenance，deferred-with-owner → future schema/event type work unit）。更新后检查 control doc 的 Residual Risk 表无遗漏
- **修复风险（低）**: 纯文档追踪，不改变代码行为
- **严重程度（低）**: 不影响 correctness，属于可维护性/追踪完备性

### AG2-未修复-信息-Close Cancellation Retry Test 仅覆盖单一取消边界

- **入口/函数**: `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:2665`
- **输入场景**: scheduler close 在 lane controller close 处被外层取消
- **实际分支**: `_CloseOnceBlockedLaneClose` 在 `lane_controller.close()` 处阻塞（`close()` line 1691），此后 close_task 被取消
- **预期行为**: close retry 机制在 close() 的任意步骤被取消后都能完成 cleanup
- **实际行为**: 测试只证明了 lane close 处取消后 retry 成功。close() 中其他可能在取消点（`cancel_all` 传播期间、active task cancellation await 期间、duplicate governance clear 期间）未被独立覆盖
- **直接证据**: 
  - `close()` 执行顺序（`dispatch.py` line 1665-1698）：mark stopping → cancel heartbeat → cancel drain → cancel promotion → cancel_all → cancel active tasks → close lane → clear duplicate → mark stopped
  - 测试只在 lane close（倒数第三步）插入 barrier（`_CloseOnceBlockedLaneClose`）
  - 其他步骤的取消 resilience 依赖"前序步骤 idempotent re-execution"（cancel done task no-op、cancel_all on empty registry returns 0、iterate empty active_tasks no-op），但未被直接测试
- **影响**: 低。所有前序步骤在 retry 时均为 idempotent no-op（done task cancel 无副作用、空 registry cancel_all 返回 0、空 active_tasks 不迭代），且生产代码中 `_closed=True` 阻止新 worker 注册。但若未来有人修改 close() 顺序或在前序步骤中插入非幂等操作，该测试不会捕获回归
- **建议改法和验证点**: 当前不需要修复。在 plan 或 control doc 中记录：若 future close() refactor 改变 cleanup 顺序或增加非幂等步骤，必须补对应取消边界 retry test
- **修复风险（低）**: 无需代码修改
- **严重程度（信息）**: 不影响当前 correctness；属于测试覆盖完备性观察

### AG3-未修复-信息-`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 不含 `RUN_COMPLETED`/`ATTEMPT_COMPLETED`

- **入口/函数**: `_assert_no_scheduler_close_terminal_events`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:164-172, 4395`
- **输入场景**: scheduler close 写入 `RUN_COMPLETED` 或 `ATTEMPT_COMPLETED` canonical fact（假设未来代码变更引入）
- **实际分支**: `_assert_no_scheduler_close_terminal_events` 检查的 7 种类型不含 `RUN_COMPLETED` / `ATTEMPT_COMPLETED`
- **预期行为**: scheduler close 不应写入任何 terminal canonical fact，包括 successful completion
- **实际行为**: 当前生产代码 close 不写任何 EventLog event，因此该 gap 不产生实际错误。但若未来 close() 错误地写入 `RUN_COMPLETED`，该 helper 不会捕获
- **直接证据**:
  - `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES`（line 164-172）定义：`CANCEL_REQUESTED, ATTEMPT_CANCELLED, RUN_CANCELLED, ATTEMPT_FAILED, RUN_FAILED, ATTEMPT_LOST, RUN_LOST`
  - 缺少：`RUN_COMPLETED`、`ATTEMPT_COMPLETED`
  - 当前生产代码 `close()`（`dispatch.py` line 1659-1698）全程无 EventLog append
- **影响**: 极低。当前 close 不写任何 EventLog，且 close 写入 successful completion 属于极端异常的代码变更，正常情况下不会发生
- **建议改法和验证点**: 将 `RUN_COMPLETED` 和 `ATTEMPT_COMPLETED` 加入 `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES`，或改用更完备的方法：检查 close 前后全部 EventLog event type 集合不变（`before_event_types == after_event_types`）。后一种方法自动覆盖未来新增的 terminal type
- **修复风险（低）**: 测试常量扩展，不改变生产行为
- **严重程度（信息）**: 不影响当前 correctness；B-DS-03 已 deferred 该列表维护职责

## Slice A / Slice B Cross-Review Finding 追踪

以下列出 Slice A 和 Slice B code review + controller adjudication 中所有 finding 的当前状态：

### Slice A Findings

| ID | 来源 | 描述 | 裁决 | 状态 |
|---|---|---|---|---|
| A-MIMO-01 | AgentMiMo | `_active_run_observation` 应用 `run_read` | accepted | 已修复（re-review 确认） |
| A-MIMO-02 | AgentMiMo | 机械格式化 churn 回退 | accepted | 已修复（re-review 确认） |
| A-DS-01 | AgentDS | 无关格式化 churn 回退 | accepted | 已修复（re-review 确认） |
| A-DS-02 | AgentDS | WAITING matrix row 拆分 | accepted | 已修复（re-review 确认） |
| A-DS-03 | AgentDS | missing attempt/dispatch scanner test | accepted | 已修复（re-review 确认） |
| A-DS-04 | AgentDS | durable-read WAITING 测试名修正 | accepted | 已修复（re-review 确认） |

Slice A: 6/6 accepted → fixed → re-review passed.

### Slice B Findings

| ID | 来源 | 描述 | 裁决 | 状态 |
|---|---|---|---|---|
| B-MIMO-01 | AgentMiMo | `_run_scheduler_drain_once` 语义薄 | rejected | closed |
| B-MIMO-02 | AgentMiMo | worker-started-but-not-accepted window | deferred-with-owner | → future scheduler hardening owner（见 AG1） |
| B-DS-01 | AgentDS | `_SCHEDULER_CLOSE_REASON` 重复私有常量 | rejected | closed |
| B-DS-02 | AgentDS | close cancellation test 访问私有状态 | rejected | closed |
| B-DS-03 | AgentDS | terminal event type list 维护 | deferred-with-owner | → future schema/event type work unit（见 AG1） |
| B-DS-04 | AgentDS | `_RegisteringCancelHandle.cancel_reasons` 自定义属性 | rejected | closed |

Slice B: 4 rejected, 2 deferred-with-owner.

### Deferred Items Cross-Reference

两项 deferred 在 AG1 中已建议进入 control doc Residual Risk 表：
- **RR-LIFE-01**: worker-started-but-not-accepted deterministic window gap → future scheduler hardening owner（来源 B-MIMO-02）
- **RR-LIFE-02**: `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` co-maintenance with terminal event type additions → future schema/event type work unit（来源 B-DS-03）

## Contract / Schema / State-Machine / Public API Boundary Check

| Boundary | Slice A | Slice B | Aggregate |
|---|---|---|---|
| Durable schema | unchanged ✓ | unchanged ✓ | unchanged ✓ |
| EventLog event type | unchanged ✓ | unchanged ✓ | unchanged ✓ |
| Host public API | unchanged ✓ | unchanged ✓ | unchanged ✓ |
| Run / Attempt state machine | unchanged ✓ | unchanged ✓ | unchanged ✓ |
| WAITING durable semantics | unchanged ✓ | n/a | unchanged ✓ |
| Public cancel command | n/a | unchanged ✓ | unchanged ✓ |
| Close terminal fact boundary | n/a | unchanged ✓ | unchanged ✓ |
| Recovery truth source | unchanged ✓ | n/a | unchanged ✓ |
| `dayu/host/README.md` | no trigger ✓ | no trigger ✓ | no trigger ✓ |
| `tests/README.md` | no trigger ✓ | no trigger ✓ | no trigger ✓ |

## Validation Commands Adequacy

Plan-defined Slice A validation:
```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q
python -m pyright dayu/ tests/ utils/
```

Plan-defined Slice B validation:
```bash
source .venv/bin/activate
pytest tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

Aggregate 建议追加 cross-slice regression：
```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

验证命令覆盖充分：包含 Slice A 和 Slice B 全部 affected tests、public lifecycle regression、pyright 全量检查。Stress suite 和 multiprocess tests 按 plan 不在默认 validation 中。

## Residual Risk

1. **RR-DUR-04**（projection/long read transaction governance scan）—— 已通过 Slice A proof matrix 和 scanner 代码证据关闭。扫描 `scan()` 使用 `run_write` 短事务，projection lag 不影响 recovery decision。control doc 标记为 `closed`。✓

2. **RR-DUR-01**（true multiprocess projection checkpoint CAS race）—— recovery scanner 不依赖 projection checkpoint。control doc 标记为 `closed`。✓

3. **worker-started-but-not-accepted window**（B-MIMO-02 deferred）—— 当前 lane-wait test 覆盖 pre-acquire window，existing active worker close tests 覆盖 post-accept window。中间窗口（acquire 返回后、worker accept event 到达前）deterministic fixture 难度高。建议进入 control doc Residual Risk 表（AG1 / RR-LIFE-01）。

4. **`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` co-maintenance**（B-DS-03 deferred）—— 未来新增 EventLog terminal event type 时需同步检查该列表。建议进入 control doc Residual Risk 表（AG1 / RR-LIFE-02）。

5. **close cancellation retry boundary coverage**（AG2）—— 当前只覆盖 lane close 处取消。其他步骤依赖 idempotent re-execution，未被独立测试但逻辑正确。低风险。

6. **terminal event type list 不包含 successful completion types**（AG3）—— 当前无实际影响，建议增强为 before/after event type set comparison 以自动覆盖未来新增类型。

## Blocking Open Questions

None.

## Conclusion

**Pass.** No blocking findings.

- **Finding count**: 3（1 low, 2 informational, 0 blocking）
- **Production code**: 零变更；全部测试基于现有生产代码行为
- **Design alignment**: WU-LIFE-01/02 满足 `docs/host/design.md` Section 27 全部要求：recovery durable truth、positive orphan proof、WAITING 不恢复、Host close 不写 terminal facts、scheduler close 不无限 drain
- **Cross-slice conflict**: Slice A 与 Slice B 互不冲突（不同 test files，不同 concerns，零 production code change）
- **Contract boundary**: 无 schema/EventLog/public API/state-machine/README 越界变化
- **Test determinism**: 全部新增测试使用 fake probe / deterministic barrier / 固定时间戳，无 sleep/race 依赖
- **Prior review findings**: Slice A 6 项 accepted → 全部已修复并 re-review 通过；Slice B 4 项 rejected + 2 项 deferred-with-owner（建议进入 control doc Residual Risk 表）
