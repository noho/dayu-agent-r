# WU-LIFE-01 + WU-LIFE-02 PR Review

日期：2026-06-01
Reviewer：AgentMiMo
Role：PR review
Gate：PR review
Controller：AgentController
Design source：docs/host/design.md
Control source：docs/host/host-core-followup-implementation-control.md
Plan：docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md
PR：https://github.com/noho/dayu-agent-r/pull/104
PR branch：feat/host-life-recovery-scheduler-hardening
Base：main

## Scope

- PR 标题：WU-LIFE recovery and scheduler lifecycle proof
- PR 内容：recovery lifecycle proof matrix + scheduler close/cancel_all lifecycle matrix + controller artifacts + residual risk tracking
- 变更文件：22 files changed, +3821 / -27 lines
  - `docs/host/host-core-followup-implementation-control.md`（modified）
  - `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`（new）
  - 18 new review artifact files in `docs/reviews/`
  - `tests/host/test_dispatch_scheduler.py`（modified）
  - `tests/host/test_recovery_scan.py`（modified）
- 生产代码变更：零（confirmed by `gh pr diff` grep）

## PR 相对 main 完整 Diff 验证

### 1. 生产代码零变更

```bash
gh pr diff 104 --repo noho/dayu-agent-r | grep "^diff --git" | grep -v "docs/" | grep -v "tests/"
```

输出为空。PR 严格遵守 plan 约束：tests-first，未修改任何生产代码。

### 2. 文件变更范围

| 类别 | 文件 | 变更类型 |
|---|---|---|
| Control doc | `docs/host/host-core-followup-implementation-control.md` | modified |
| Plan artifact | `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md` | new |
| Review artifacts | `docs/reviews/wu-life-01-02-*.md`（18 files） | new |
| Test (Slice A) | `tests/host/test_recovery_scan.py` | modified |
| Test (Slice B) | `tests/host/test_dispatch_scheduler.py` | modified |

无 `dayu/` 生产代码、无 schema、无 EventLog type、无 public API、无 README 变更。

### 3. 测试验证

```bash
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_recovery_multiprocess.py -q
```

结果：110 passed（与 PR 描述一致）。

```bash
python -m pyright dayu/ tests/ utils/
```

结果：0 errors, 0 warnings, 0 informations（与 PR 描述一致）。

### 4. 新增测试函数

**Slice A（test_recovery_scan.py）**：
- `test_recovery_lifecycle_proof_matrix_covers_slice_a_rows` — proof matrix 覆盖验证
- `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` — still-live integration
- `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows` — inconclusive integration（parametrized: process_probe_error + pid_live_no_identity）
- `test_scan_waiting_durable_read_state_remains_diagnostic_only` — WAITING durable read 语义
- `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation` — missing dispatch inconclusive

**Slice B（test_dispatch_scheduler.py）**：
- `test_scheduler_close_lifecycle_matrix_covers_slice_b_windows` — lifecycle matrix 覆盖验证
- `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel` — cancel_all 快照语义
- `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` — queue 非空不 drain
- `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact` — lane wait pre-worker close
- `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish` — close cancellation retry cleanup

全部 10 个新增测试通过。

## Plan 与 Aggregate Adjudication 对齐检查

### Slice A 对齐

| Plan Requirement | Status | Evidence |
|---|---|---|
| Recovery lifecycle matrix 常量 | ✓ | `_RECOVERY_LIFECYCLE_PROOF_MATRIX` 覆盖全部 Slice A 场景 |
| scanner still-live integration | ✓ | `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows` |
| scanner inconclusive integration | ✓ | `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows`（parametrized） |
| WAITING diagnostic-only semantic | ✓ | `test_scan_waiting_durable_read_state_remains_diagnostic_only` |
| missing attempt/dispatch test | ✓ | `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation` |
| RR-DUR-04 proof matrix row | ✓ | 纳入 proof matrix，不触发 production rewrite |
| 不新增 production recovery API | ✓ | 零生产代码变更 |
| 不改变 WAITING/Run/Attempt 状态机 | ✓ | 零生产代码变更 |

### Slice B 对齐

| Plan Requirement | Status | Evidence |
|---|---|---|
| Scheduler close lifecycle matrix 常量 | ✓ | `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` 覆盖全部 Slice B 场景 |
| `cancel_all` snapshot test | ✓ | `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel` |
| dispatch queue non-empty close | ✓ | `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` |
| promotion non-drain close | ✓ | 扩展已有 promotion close test |
| lane wait / pre-worker close | ✓ | `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact` |
| close cancellation retry cleanup | ✓ | `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish` |
| close 不 drain-until-empty | ✓ | 测试证明 queue 非空 close 不处理 pending work |
| close 不写 terminal facts | ✓ | 全部 5 个 focused tests 调用 `_assert_no_scheduler_close_terminal_events` |

### Aggregate Adjudication 对齐

| Adjudication Item | Status | Evidence |
|---|---|---|
| AG-MIMO (pass) | ✓ | 本次 PR review 确认无实质 finding |
| AG-DS-01 (accepted → RR-LIFE-01/02) | ✓ | control doc 已新增 RR-LIFE-01 / RR-LIFE-02 |
| AG-DS-02 (deferred → RR-LIFE-01) | ✓ | RR-LIFE-01 覆盖 close cancellation boundary |
| AG-DS-03 (deferred → RR-LIFE-02) | ✓ | RR-LIFE-02 覆盖 terminal event type list co-maintenance |

## Residual Risk Tracking 验证

### 变更前状态（main）

- RR-DUR-01：`deferred-with-owner` → WU-LIFE-01 recovery lifecycle proof
- RR-DUR-04：`deferred-with-owner` → WU-LIFE-01 recovery lifecycle proof
- RR-LIFE-01：不存在
- RR-LIFE-02：不存在

### 变更后状态（PR branch）

- RR-DUR-01：`closed` — WU-LIFE code inspection 证明 recovery scanner 不依赖 projection checkpoint ✓
- RR-DUR-04：`closed` — Slice A proof matrix 证明 recovery scanner 使用 durable truth ✓
- RR-LIFE-01：`deferred-with-owner` — worker-started-but-not-accepted window，future scheduler hardening ✓
- RR-LIFE-02：`deferred-with-owner` — terminal event type list co-maintenance，future EventLog work unit ✓

按 control doc 追踪规则，`ready-to-open-draft-PR` 前所有 tracking items 必须处于 `closed` / `deferred-with-owner` / `transferred-to-issue`。当前表中所有 items 满足该约束。

## Schema / EventLog / Public API / State-machine / README 越界检查

| 边界 | 状态 | 证据 |
|---|---|---|
| Durable schema | 未变更 ✓ | diff 仅含 test + docs 文件 |
| EventLog event type | 未变更 ✓ | 无新 event type |
| Host public API | 未变更 ✓ | 无 api.py / open_host.py 修改 |
| Run / Attempt state machine | 未变更 ✓ | 无状态转换逻辑修改 |
| WAITING durable semantics | 未变更 ✓ | 无 WAITING 语义变更 |
| Close terminal fact boundary | 未变更 ✓ | close 不写 terminal facts 由测试证明 |
| Recovery truth source | 未变更 ✓ | scanner 使用 durable truth 由测试证明 |
| README / doc sync | 不需要 ✓ | 仅新增 tests 与 docs，未改变 public contract 或测试入口 |

## 测试质量检查

- **无 sleep / race / timing 依赖**：所有新测试使用 deterministic barriers（`asyncio.Event`）、monkeypatch 和直接 durable reads ✓
- **无私有耦合过度**：Slice B 测试访问 `_closed`、`_close_cleanup_done`、`_queue`、`_drain_task` 等内部状态，但这是 focused lifecycle test 验证 close cleanup 完整性的最小可行证据（Slice B controller adjudication 已接受） ✓
- **reason 字符串一致性**：所有测试中的 reason 常量与生产代码私有常量精确匹配 ✓
- **Cross-slice 非冲突**：Slice A 仅修改 `test_recovery_scan.py`，Slice B 仅修改 `test_dispatch_scheduler.py`，无文件重叠 ✓

## Findings

### PR1-未修复-信息-`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 不含 `RUN_COMPLETED`/`ATTEMPT_COMPLETED`

- **入口/函数**: `_assert_no_scheduler_close_terminal_events`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py`
- **输入场景**: scheduler close 写入 `RUN_COMPLETED` 或 `ATTEMPT_COMPLETED`（假设未来代码变更引入）
- **实际分支**: `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 检查 7 种 terminal type，不含 `RUN_COMPLETED` / `ATTEMPT_COMPLETED`
- **预期行为**: scheduler close 不应写入任何 terminal canonical fact，包括 successful completion
- **实际行为**: 当前生产代码 close 不写任何 EventLog event，因此该 gap 不产生实际错误
- **直接证据**: 生产 `close()`（`dispatch.py` line 1659-1698）全程无 EventLog append
- **影响**: 极低。当前 close 不写任何 EventLog，且 close 写入 successful completion 属于极端异常变更
- **建议改法**: 将 `RUN_COMPLETED` 和 `ATTEMPT_COMPLETED` 加入 `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES`，或改用 close 前后 EventLog set 不变断言
- **修复风险（低）**: 测试常量扩展，不改变生产行为
- **严重程度（信息）**: RR-LIFE-02 已追踪该列表维护职责

## Blocking Open Questions

无。

## Conclusion

**Pass.** 无 blocking finding。

- **Finding count**: 1（信息级，0 blocking）
- **Production code**: 零变更；全部测试基于现有生产代码行为
- **Plan alignment**: Slice A / Slice B 全部 plan requirement 已满足
- **Aggregate adjudication**: AG-MIMO / AG-DS-01 / AG-DS-02 / AG-DS-03 全部对齐
- **Residual risk tracking**: RR-DUR-01 / RR-DUR-04 正确关闭；RR-LIFE-01 / RR-LIFE-02 正确新增
- **Design alignment**: WU-LIFE-01/02 满足 `docs/host/design.md` Section 27 全部要求
- **Contract boundary**: 无 schema/EventLog/public API/state-machine/README 越界变化
- **Test determinism**: 全部新增测试使用 deterministic barriers，无 sleep/race 依赖
- **Validation**: 110 passed, pyright 0 errors
