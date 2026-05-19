# Code Review — Phase 11 Slice 3 Fix Re-review

## Scope

- Mode: current changes (unstaged diff, re-review of fix)
- Branch: `feat/host-phase-11-recovery`
- Base: Slice 3 accepted post-review fix
- Output file: `docs/reviews/phase11-slice3-rereview-ds-20260519.md`
- Input fix artifact: `docs/reviews/phase11-slice3-fix-codex-20260519.md`
- Original reviews:
  - `docs/reviews/phase11-slice3-code-review-mimo-20260519.md`
  - `docs/reviews/phase11-slice3-code-review-ds-20260519.md`
- Controller adjudication: `docs/reviews/phase11-slice3-code-review-controller-adjudication-20260519.md`
- Included scope: `dayu/host/recovery.py`, `tests/host/test_recovery_dispatch.py`
- Excluded scope: Engine, public API, schema, WorkerProxy, RECOVERING cancel, multi-process
- Parallel review coverage: 无

## Verification Target

逐项核对 controller-adjudicated fix scope：

1. recovery.py 模块 docstring 匹配 Slice 3 职责，说明不直接调用 WorkerProxy
2. closeout-succeeded dispatch-invalid 路径返回 RECOVERING_READY 而非 INVALID_STATE，不改变 durable mutation 语义
3. 聚焦测试覆盖 partial-success 路径
4. lose_recovering_run_in_transaction 前置条件保持 no-action
5. 无新 blocker

## Per-Item Verification

### 1. 模块 docstring 更新 (MiMo 001)

**逐行走读**: `dayu/host/recovery.py:1-8`

```text
"""Host startup recovery scan 编排。

本模块负责启动时读取 durable Run/Attempt/dispatch/liveness truth，调用
只读 orphan proof classifier，并在 positive proof 成立时通过 durable
transition helper 完成旧 Attempt closeout。Slice 3 起，本模块还负责为
可恢复 Run 创建 recovery Attempt、execution 与 pending dispatch record，
并在事务提交后唤醒 scheduler。它不实现 public API、不直接调用 WorkerProxy，
也不读取 projection/read-model。
"""
```

**验证**: docstring 完整描述了 Slice 3 职责——startup scan、orphan closeout、recovery Attempt/execution/dispatch 创建、post-commit scheduler wake，明确声明不直接调用 WorkerProxy、不读取 projection/read-model。与旧 docstring "不创建新的 recovery Attempt" 对比，已消除 stale 信息。

**结论**: FIX VERIFIED.

### 2. closeout-succeeded dispatch-invalid 路径 (DS 1)

**逐行走读**: `dayu/host/recovery.py:446-469`

```python
# line 446-451: 如果不可恢复、mutation 非 UPDATED 或 run 为 None，直接返回 close_action
if (
    not recoverable
    or result.status is not StateMutationStatus.UPDATED
    or result.run is None
):
    return close_action
# line 452-456: 如果 wakeup port 或 owner host instance id 不可用，返回 close_action
if (
    self.dispatch_wakeup_port is None
    or self.recovery_owner_host_instance_id is None
):
    return close_action
# line 457-462: 尝试创建 recovery dispatch
dispatch_action = self._start_recovery_dispatch_or_ready(...)
# line 463-468: **关键 fix** — dispatch INVALID_STATE 时返回 RECOVERING_READY
if dispatch_action.decision is StartupRecoveryDecision.INVALID_STATE:
    return _action(
        result.run,
        StartupRecoveryDecision.RECOVERING_READY,
        _REASON_RECOVERY_DISPATCH_PENDING_FOLLOW_UP,
    )
return dispatch_action
```

**证据链**:
1. orphan closeout 在同一事务内已成功执行（`result.status is StateMutationStatus.UPDATED`），Run 状态已转为 RECOVERING，`ATTEMPT_LOST` + `RUN_RECOVERING` 事件已追加到 EventLog
2. `_start_recovery_dispatch_or_ready` 调用 `start_recovery_run_with_starting_attempt_in_transaction`，其内部 CAS 可能因 Session 级 active-run 约束失败，返回 `INVALID_STATE`
3. 此时 `_close_positive_orphan` 的 dispatch 路径（line 463）检测到 `INVALID_STATE`，返回 `RECOVERING_READY` 而非直接透传 `INVALID_STATE`
4. reason 为 `startup_recovery_dispatch_pending_follow_up`（line 70），清晰表达"closeout 成功、dispatch 待重试"

**语义**:
- orphan closeout 的 durable mutation 语义未变（`close_startup_orphan_attempt_in_transaction` 未修改）
- recovery dispatch 的 CAS 语义未变（`start_recovery_run_with_starting_attempt_in_transaction` 未修改）
- 仅改变 scan action 的分类：从 `INVALID_STATE`（丢失 closeout 成功的可观测信号）变为 `RECOVERING_READY`（正确反映 Run 已处于 RECOVERING，后续 scan 可重试 dispatch）

**结论**: FIX VERIFIED.

### 3. 聚焦测试覆盖 partial-success 路径 (DS 1)

**逐行走读**: `tests/host/test_recovery_dispatch.py:219-249`

测试 `test_orphan_closeout_dispatch_invalid_state_reports_recovering_ready`：

```python
monkeypatch.setattr(
    "dayu.host.recovery.start_recovery_run_with_starting_attempt_in_transaction",
    _return_invalid_recovery_dispatch,
)
```

monkeypatch 将 recovery dispatch helper 替换为返回 `INVALID_STATE` 的替身（line 264-282），替身不写入任何新事件。

测试断言：
- `result.actions[0].decision == RECOVERING_READY` — action 决策为 recovering_ready ✓
- `result.actions[0].status is RunStatus.RECOVERING` — action 状态反映 Run 当前为 RECOVERING ✓
- `result.pending_dispatches == ()` — 不产生 pending dispatch wake ✓
- `wakeup.dispatches == []` — 不唤醒 scheduler ✓
- `_run_status(...) is RunStatus.RECOVERING` — durable Run 状态确为 RECOVERING ✓
- `_event_count(..., "ATTEMPT_LOST") == 1` — orphan closeout 的 ATTEMPT_LOST 已写入 ✓
- `_event_count(..., "RUN_RECOVERING") == 1` — RUN_RECOVERING 已写入 ✓
- `_event_count(..., "RUN_STARTED") == 1` — 仅有原始 seed 的 1 个 RUN_STARTED，未创建新 recovery RUN_STARTED ✓

**结论**: FIX VERIFIED. 测试精确覆盖 partial-success 路径：closeout 成功 + dispatch 失败的场景下，验证 durable facts 正确写入、action 决策正确分类、无错误唤醒。

### 4. lose_recovering_run_in_transaction 前置条件 (DS 2)

**逐行走读**: `dayu/host/durable/run_transition.py:1415-1419`

```python
if (
    source_attempt is None
    or run.status != RunStatus.RECOVERING
    or run.current_attempt_id != request.source_attempt_id
):
    return RunTransitionResult(
        status=StateMutationStatus.INVALID_STATE,
        ...
    )
```

CAS 条件与 Slice 2 实现一致，未修改。函数仅当 Run 确为 RECOVERING 且 `current_attempt_id` 与调用方提供的 `source_attempt_id` 匹配时才允许转为 LOST。该前置条件对终态化 RECOVERING Run 的语义充分。

**结论**: NO_ACTION VERIFIED — 函数未修改，controller 裁决 respected.

### 5. 无新 blocker

- pyright: `0 errors, 0 warnings, 0 informations`
- 测试: `40 passed in 0.48s`
- 未修改 Engine、public API、schema、WorkerProxy 行为
- 未新增 RECOVERING cancel 或多进程逻辑
- 未改变 durable mutation 语义
- 未引入新文件或新依赖

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `RECOVERING` public cancel 和 `cancel_session_runs` 支持归属 Slice 4，当前未实现。
- 多进程并发 scan 测试覆盖归属 Slice 5，当前单进程测试已覆盖 CAS 正确性路径。
- `WorkerKind` 硬编码为 `LOCAL`（`dayu/host/recovery.py:516`），remote worker recovery 不在 Phase 11 scope。

## Conclusion

**PASS — blocking count = 0**

Phase 11 Slice 3 fix 正确完成了 controller-adjudicated 的全部三项修复：
1. 模块 docstring 已更新，准确描述 Slice 3 职责并声明不直接调用 WorkerProxy；
2. orphan closeout 成功但 dispatch CAS 返回 `INVALID_STATE` 时，scanner 返回 `RECOVERING_READY`（reason: `startup_recovery_dispatch_pending_follow_up`），durable mutation 语义未变；
3. 聚焦测试 `test_orphan_closeout_dispatch_invalid_state_reports_recovering_ready` 覆盖 partial-success 路径，验证 durable facts 写入与 action 决策正确性；
4. `lose_recovering_run_in_transaction` 保持不修改。

pyright 0 errors，40 tests passed。无新 blocker 引入。
