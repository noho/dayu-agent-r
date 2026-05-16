# P1-P7 Design Goals Fix Controller Adjudication

日期：2026-05-16

分支：`fix/host-p1-p7-awaiting-production-wiring`

设计真源：`docs/host/design.md`

Controller decision：`docs/reviews/p1-p7-design-goals-controller-decision-20260516.md`

Fix artifact：`docs/reviews/p1-p7-design-goals-fix-codex-20260516.md`

Review artifacts：

- `docs/reviews/p1-p7-design-goals-fix-review-mimo-20260516.md`
- `docs/reviews/p1-p7-design-goals-fix-review-ds-20260516.md`

## Verdict

**PASS。**

用户明确决定 `fetch_more` cursor 只存在内存；本轮不再将 durable cursor descriptor 缺失作为偏离。除该明确决定外，其它项已按当前 `docs/host/design.md` 的设计目标与最佳实践完成裁决和修复。

MiMo verdict PASS，0 Blocking / 0 High / 0 Medium。DS verdict PASS，0 Blocking / 0 High / 1 Medium / 3 Low；Controller 接受 DS Medium 为 control document stale risk，并已在 `docs/host/implementation-control.md` 当前 diff 中关闭。

## Final Decisions

### D2 active worker registry

结论：closed。

`DEFAULT_ACTIVE_WORKER_REGISTRY` 模块级 mutable singleton 与 `cancel_active_worker()` helper 已从生产代码移除。`create_host_command_handle(..., active_registry=None)` 与 `HostDispatchScheduler.open(..., active_registry=None)` 默认各自创建 fresh `ActiveWorkerRegistry`；需要 active cancel 传播时，production composition root 必须显式向 command handle 与 scheduler 传入同一个 registry。

### D3 resolve_wait idempotency

结论：closed。

`_wait_resolution_digest()` 只按 `wait_id`、`idempotency_key` 与 typed outcome 判定同 outcome；`observed_at` / `source` 保留在首次提交的 payload / audit / diagnostic 中，不参与同 outcome conflict。测试已覆盖同 key + 同 outcome + 不同 observed_at 的重放，以及同 key + 不同 outcome 的冲突。

### D4 TOOL_TERMINAL_RESULT

结论：closed by design update。

`docs/host/design.md` 已明确 P1-P7 的 accepted waiting terminal result 使用 `TOOL_RESULT_ACCEPTED` 作为唯一 accepted tool result canonical event，通过 wait-specific payload 字段表达等待完成来源；不再要求独立 `TOOL_TERMINAL_RESULT` canonical fact。

### D5 FOLLOWUP_QUEUED

结论：closed by design update。

`docs/host/design.md` 已明确 `submit_followup(queue)` 不引入独立 `FOLLOWUP_QUEUED` canonical event；canonical 表达是 `USER_INPUT_ACCEPTED` + `RUN_ACCEPTED`，并按 active Run 竞态结果追加 `RUN_QUEUED` 或 `RUN_STARTED`。

### D6 WAITING cancel docstring

结论：closed。

`cancel_run` / `cancel_session_runs` docstring 已同步当前行为：当前覆盖 active worker 与 `WAITING` cancel，`RECOVERING` cancel 仍由 Phase 11 负责。

## Reviewer Findings Disposition

- DS-P1P7-M1：接受并已修复。`implementation-control.md` 已关闭旧 `DEFAULT_ACTIVE_WORKER_REGISTRY` residual risk，记录本轮 fix 事实。
- DS-P1P7-L1：deferred。`ActiveWorkerRegistry` 暂不从 `dayu.host` 包根 re-export；当前属于 dispatch/scheduler composition helper，保持窄导出更符合内部边界。
- DS-P1P7-L2：rejected as issue。`_propagate_active_cancel_targets()` 与 `HostCommandHandle` 同模块，访问同模块私有字段不构成边界泄漏；如未来需要 audit hook，可再内聚为 handle 方法。
- DS-P1P7-L3：deferred / accepted as design note。late rejection 是 diagnostic event，不是 successful resolution 幂等语义；保留 `source` / `observed_at` 作为审计区分合理。后续如产品化 callback retry 需要更强重放语义，再单独细化 design。
- MiMo Low/Info：接受为说明。`_wait_late_rejection_digest` 保留 `source` / `observed_at` 是 diagnostic idempotency 口径，不影响 D3。

## Residual Risks

- active cancel 仍是进程内 best-effort；跨进程 physical cancel、watchdog、stuck `CANCELLING` 与 orphan recovery 归 Phase 11。
- production composition 必须显式把同一个 `ActiveWorkerRegistry` 传给 command handle 与 scheduler，才能让 public cancel 传播到 active worker。
- late rejection diagnostic digest 的保守口径后续可在 callback 产品化时再细化。

## Gate Status

本轮 design-goals fix review 通过。可以进入本地 accepted checkpoint。
