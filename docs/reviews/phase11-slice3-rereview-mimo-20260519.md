# Code Review — Phase 11 Slice 3 Fix Re-review

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: `feat/host-phase-11-recovery`
- Base: Slice 2 accepted commit `2e89558`
- Output file: `docs/reviews/phase11-slice3-rereview-mimo-20260519.md`
- Included scope: `dayu/host/recovery.py`, `tests/host/test_recovery_dispatch.py`
- Excluded scope: Engine, Fins, Service, UI, public API, schema — no changes
- Parallel review coverage: 无

## Review Context

本 review 是 Phase 11 Slice 3 fix 的 re-review。原始 review 由 AgentMiMo（`phase11-slice3-code-review-mimo-20260519.md`）和 AgentDS（`phase11-slice3-code-review-ds-20260519.md`）完成，Controller 裁决（`phase11-slice3-code-review-controller-adjudication-20260519.md`）要求两项 fix：

1. **MiMo 001**：更新 `dayu.host.recovery` 模块 docstring 以反映 Slice 3 职责
2. **DS 1**：orphan closeout 成功但 recovery dispatch CAS 返回 `INVALID_STATE` 时，scanner 应返回 `RECOVERING_READY` 而非 `INVALID_STATE`，并补充聚焦测试

DS 2（`lose_recovering_run_in_transaction` 前置条件）裁决为 no-action。

## Verification Checklist

### 1. 模块 docstring 与 Slice 3 职责一致

**要求**：docstring 描述 startup scan、orphan closeout、recovery dispatch Attempt / execution / dispatch 创建、commit 后 scheduler wake；明确不直接调用 WorkerProxy。

**验证**：`dayu/host/recovery.py:1-9` 更新为：

> Slice 3 起，本模块还负责为可恢复 Run 创建 recovery Attempt、execution 与 pending dispatch record，并在事务提交后唤醒 scheduler。它不实现 public API、不直接调用 WorkerProxy，也不读取 projection/read-model。

✅ 通过。docstring 准确描述当前职责，明确排除 WorkerProxy 直接调用。

### 2. closeout-succeeded dispatch-invalid 路径返回 RECOVERING_READY

**要求**：orphan closeout 成功后，若 dispatch 创建返回 `INVALID_STATE`，scanner 应返回 `RECOVERING_READY` 或等效非终态 recovery decision，而非 plain `INVALID_STATE`。不得改变 durable mutation 语义。

**验证**：`dayu/host/recovery.py:463-468`：

```python
if dispatch_action.decision is StartupRecoveryDecision.INVALID_STATE:
    return _action(
        result.run,
        StartupRecoveryDecision.RECOVERING_READY,
        _REASON_RECOVERY_DISPATCH_PENDING_FOLLOW_UP,
    )
```

逻辑链路：
1. orphan closeout 成功（`result.status is UPDATED`）→ `result.run` 处于 `RECOVERING` 状态 → durable 事务内已提交 `ATTEMPT_LOST` + `RUN_RECOVERING`
2. dispatch 创建返回 `INVALID_STATE` → `_start_recovery_dispatch_or_ready` 返回 `INVALID_STATE` decision
3. `_close_positive_orphan` 拦截该 decision，返回 `RECOVERING_READY` + reason `startup_recovery_dispatch_pending_follow_up`

durable mutation 语义不变：orphan closeout 事务正常提交，dispatch 失败仅影响 scanner 返回值。

✅ 通过。

### 3. 聚焦测试覆盖 partial-success 路径

**要求**：新增聚焦测试，验证 orphan closeout 成功 + dispatch INVALID_STATE 的 partial-success 路径。

**验证**：`tests/host/test_recovery_dispatch.py:219-249` — `test_orphan_closeout_dispatch_invalid_state_reports_recovering_ready`：

- monkeypatch `start_recovery_run_with_starting_attempt_in_transaction` 返回 `INVALID_STATE`（通过 `_return_invalid_recovery_dispatch` helper，读取当前 run 但不写入事件）
- 断言 scanner action 为 `RECOVERING_READY`
- 断言 action status 为 `RECOVERING`（反映 closeout 后的 durable 状态）
- 断言 `pending_dispatches == ()`，`wakeup.dispatches == []`
- 断言 durable Run 状态为 `RECOVERING`
- 断言 `ATTEMPT_LOST` = 1、`RUN_RECOVERING` = 1（closeout 写入）
- 断言 `RUN_STARTED` = 1（seed 写入，非 recovery dispatch）

monkeypatch 目标正确：`dayu.host.recovery.start_recovery_run_with_starting_attempt_in_transaction`，是 recovery 模块内的导入名。

✅ 通过。

### 4. lose_recovering precondition 保持 no-action

**要求**：不修改 `lose_recovering_run_in_transaction`，不改变 RECOVERING lost/cancel 语义。

**验证**：diff 中 `dayu/host/durable/run_transition.py` 的 `lose_recovering_run_in_transaction` 函数无变更。fix codex 确认 no-action。

✅ 通过。

### 5. 无新 blocker

**验证**：
- 测试：40 passed in 0.47s
- pyright：0 errors, 0 warnings, 0 informations
- diff 不引入新的架构违反、安全风险或状态损坏路径
- fix 改变的仅是 scanner decision 的可观测分类，不改变 durable closeout 或 recovery dispatch helper 的写入语义

✅ 通过。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

与原始 review 一致：

1. **RECOVERING cancel 尚未实现（Slice 4）**：当前 RECOVERING Run 无法通过 public `cancel_run` / `cancel_session_runs` 取消。
2. **多进程并发 scan 测试覆盖**：当前为单进程测试，SQLite write transaction 串行化理论安全但缺乏多进程直接证据。
3. **WorkerKind 硬编码为 LOCAL**：recovery dispatch 硬编码 `worker_kind=WorkerKind.LOCAL`，remote worker 场景下 recovery 行为可能不完整（符合 Phase 11 non-goal）。

以上均在 Slice 3 scope 外，已 deferred 到对应 slice。

## Conclusion

**PASS — blocking count = 0**

Controller 裁决的两项 fix 均正确实现：
- 模块 docstring 已更新，准确反映 Slice 3 职责边界
- orphan closeout 成功 + dispatch INVALID_STATE 的 partial-success 路径已返回 `RECOVERING_READY`，durable mutation 语义不变
- 聚焦测试覆盖该路径，断言完整
- `lose_recovering_run_in_transaction` 前置条件保持 no-action
- 无新 blocker
