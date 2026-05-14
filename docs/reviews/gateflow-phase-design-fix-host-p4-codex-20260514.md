# Gateflow Phase Design Fix - Host P4 Public API Command Path

## 来源

- design readiness artifact：`docs/reviews/gateflow-phase-design-host-p4-codex-20260514.md`
- controller adjudication：`docs/reviews/gateflow-phase-design-host-p4-controller-adjudication-20260514.md`
- controller 结论：accepted；Phase 4 进入 plan gate 前必须完成 design fix / write-back。

## 用户确认

- 接受新增 `HostApiErrorCode.UNSUPPORTED_OPERATION`，用于表达 public envelope 已冻结但完整语义由后续 phase 落地。
- 确认 `cancel_session_runs` 在 Phase 4 必须实现 Phase 1-3 可闭环子集：queued / pre-dispatch `STARTING` cancel。
- 确认 dispatching / active worker、`WAITING`、`RECOVERING` cancel deferred，并必须标明后续 owner。

## 改动文件

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`

## 逐 finding 修复状态

### P4-D1 - 已修复 - FollowupSnapshot queue 结果表达不足

- 将 `FollowupSnapshot` 写成 accepted follow-up result：`accepted_run_id` + `accepted_run_status`。
- 明确 `queued_run_id?` 只能作为真正 queued Run 的可选派生字段保留。
- 明确 queue follow-up 在无 active Run 时可以返回新接受的 `RUNNING` Run。

### P4-D2 - 已修复 - steer conflict / invalid_state 缺少结构化 detail

- 在公共错误分类中新增 `unsupported_operation`。
- 为 `HostApiError` 增加受限 typed detail union 要求。
- 定义第一版必须包含的 `SteerConflictDetail`。
- 明确禁止无结构 `extra` / `payload` / `metadata` god bag。

### P4-D3 - 已修复 - submit_followup(steer) Phase 4 行为边界未冻结

- 明确 Phase 4 只冻结 steer envelope、validation、错误码与 typed detail contract。
- 明确 Phase 4 public facade 对 steer 返回 `unsupported_operation`。
- 完整 `RUNNING` / `WAITING` Attempt switching 留给后续 steer / dispatch / wait owner。

### P4-D4 - 已修复 - public function 完整实现 / deferred 行为矩阵缺失

- 增加 Phase 4 behavior matrix，覆盖完整实现、子集实现与 stable unsupported / deferred。
- Phase 4 完整实现：`ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、`submit_followup(queue)`、`get_run`、`stream_run_events`、queued / pre-dispatch `cancel_run`。
- Phase 4 子集实现：`cancel_session_runs` queued / pre-dispatch `STARTING`。
- stable unsupported / deferred：`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、active dispatch cancel、wait cancel、recovery cancel。

### P4-D5 - 已修复 - stream_run_events cursor contract 不足

- 将 public signature 固定为包含可选 `limit`。
- 明确全局 EventLog `event_sequence` 是唯一 cursor truth。
- 写回 run filtering、默认 / 最大 limit、empty result `next_cursor` 与 `HostEventView` 映射规则。
- 明确 Phase 4 不引入 projection truth。

### P4-D6 - 已修复 - attach_active public audit / read-model 表达

- 明确第一版返回当前 active `RunSnapshot`。
- 明确 `attach_active` 不新增 canonical EventLog fact。
- 明确 audit / read-model 可由后续 projection 基于 idempotency 或 diagnostic refs 表达；若后续需要新增 canonical attach fact，必须先更新设计。

## 后续 owner

- Phase 5：dispatching / active WorkerProxy cancel propagation、dispatch record `dispatching`、active worker path。
- Phase 7：`WAITING` cancel、wait record cancel、`resolve_wait` 完整治理。
- Phase 11：`RECOVERING` cancel、recovery scan / dispatch cancellation、lifecycle hardening。
- Phase 15：`purge_session` destructive cleanup 与 purge tombstone persistence。
- 后续 steer / retry / replay owner：完整 steer Attempt switching 与 retry / replay execution semantics。

## 验证

- `git diff --check`：passed。
- 未运行 pytest / pyright：本次只修改设计文档与 review artifact。
