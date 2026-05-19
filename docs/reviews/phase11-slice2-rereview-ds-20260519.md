# Code Review — Phase 11 Slice 2 Fix Re-Review

## Scope

- Mode: current changes (re-review of Slice 2 fix)
- Branch: feat/host-phase-11-recovery
- Base: controller adjudication `docs/reviews/phase11-slice2-code-review-controller-adjudication-20260519.md`
- Fix target: `docs/reviews/phase11-slice2-fix-codex-20260519.md`
- Original reviews: `docs/reviews/phase11-slice2-code-review-mimo-20260519.md`, `docs/reviews/phase11-slice2-code-review-ds-20260519.md`
- Output file: docs/reviews/phase11-slice2-rereview-ds-20260519.md
- Included scope: current uncommitted diff (`recovery.py`, `run_transition.py`, `state.py`, `event_log.py`, `test_recovery_scan.py`, `test_run_attempt_transitions.py`, `README.md`, `implementation-control.md`)
- Excluded scope: Engine, public API, schema migration, dispatch implementation
- Parallel review coverage: 无

## Verification Targets

以下逐项验证 controller adjudication 要求的四个 fix 项及一个跟踪项。

### Fix 1: stale threshold `int()` 截断消除

- **入口/函数**: `_close_positive_orphan` → `StartupOrphanCloseInput` → `_invalid_startup_orphan_precondition`
- **文件(行号)**: `recovery.py:370` 传入 `stale_after=policy.stale_after`（`timedelta`）；`run_transition.py:163` `stale_after: timedelta`；`run_transition.py:573` `request.occurred_at - heartbeat_at > request.stale_after`
- **验证结果**: **已修复**。`StartupOrphanCloseInput.stale_after` 类型为 `timedelta`，recovery scanner 直接传递 `policy.stale_after`，CAS recheck 使用 `timedelta > timedelta` 比较，与 classifier 的 `classify_orphan_candidate` 阈值语义完全一致。`_validate_startup_orphan_close_input`（`run_transition.py:5145`）校验 `stale_after <= timedelta(0)` 拒绝非正阈值。
- **测试覆盖**: `test_startup_orphan_closeout_preserves_fractional_stale_threshold`（`test_run_attempt_transitions.py:1024-1064`）使用 `timedelta(seconds=30, milliseconds=500)` 验证亚秒边界不被截断，`occurred_at - heartbeat_at = 30.25s < 30.5s` 时 CAS recheck 返回 `INVALID_STATE`，0 个 `ATTEMPT_LOST` 事件。

### Fix 2: CANCELLING scanner-level positive orphan 测试覆盖

- **入口/函数**: `test_scan_cancelling_positive_orphan_loses_attempt_then_run`
- **文件(行号)**: `test_recovery_scan.py:153-202`
- **验证结果**: **已修复**。测试验证：
  - scanner decision = `RUN_LOST`
  - reason = `cancel_in_flight_attempt_lost`
  - 末尾两个 event type 为 `(ATTEMPT_LOST, RUN_LOST)`
  - `RUN_RECOVERING` 不在 event type 序列中
  - Run 状态变为 `LOST`
- **执行路径**: `_classify_run` → `_classify_active_or_cancelling` → `_classify_owner`（positive proof）→ `_close_positive_orphan`，其中 `recoverable` 因 `run.status is RunStatus.CANCELLING` 为 `False`，`_startup_closeout_reason` 对 `CANCELLING` 返回 `_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST`，`close_startup_orphan_attempt_in_transaction` 走 `RUN_LOST` 路径。

### Fix 3: ACCEPTED / QUEUED classification 测试覆盖

- **入口/函数**: `test_scan_accepted_does_not_mutate_or_create_attempt`、`test_scan_queued_does_not_mutate_or_create_attempt`
- **文件(行号)**: `test_recovery_scan.py:205-242`
- **验证结果**: **已修复**。两个测试均：
  - 在 scan 前通过 `_unstarted_scan_observation` 捕获 Run 状态、`updated_at`、Attempt row 数、EventLog 序列
  - 验证 decision 分别为 `ACCEPTED_WAKE` / `QUEUE_PROMOTION_CHECK`
  - 验证 scan 后观测值 `after == before`，即无任何状态变更、无新 Attempt row、无新 EventLog event

### Track 项: `lose_recovering_run_in_transaction` precondition 未变

- **文件(行号)**: `run_transition.py:1338-1344`
- **验证结果**: **按设计未变更**。precondition 仍为 `run.status != RunStatus.RECOVERING or run.current_attempt_id != request.source_attempt_id`，不检查 source_attempt 的 terminal 状态。Controller 已裁决此项为 rejected-current-fix / track in Slice 3 review。

## Verification Results

```bash
pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q
# 42 passed in 0.48s

python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations
```

## Findings

未发现实质性问题。

## No-New-Blocker 检查清单

- [x] 无 `int()` 截断：`stale_after` 全程 `timedelta`，CAS 比较无精度损失
- [x] CANCELLING scanner-level 测试覆盖 `ATTEMPT_LOST` → `RUN_LOST`、无 `RUN_RECOVERING`
- [x] ACCEPTED 测试覆盖无 mutation、无 recovery fact、无 Attempt 创建
- [x] QUEUED 测试覆盖无 mutation、无 recovery fact、无 Attempt 创建
- [x] rejected recovering precondition item 未变更
- [x] 未引入新文件、新 schema、新 public API、新 Engine 依赖
- [x] 42 tests 全部通过，pyright 零告警
- [x] diff 仅触及 controller 允许的文件范围

## Open Questions

无。

## Residual Risk

- `lose_recovering_run_in_transaction` precondition 简洁性风险已由 controller 显式推迟至 Slice 3 review，当前 Slice 2 独立行为下不构成正确性问题。
- 所有原有 residual risk（CANCELLING scanner 覆盖、ACCEPTED/QUEUED 覆盖）已通过本次 fix 关闭。

## Conclusion

PASS。Blocking count = 0。四项 fix 全部验证通过，未引入新问题。
