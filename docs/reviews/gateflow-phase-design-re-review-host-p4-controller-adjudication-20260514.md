# Gateflow Phase Design Re-review Adjudication - Host P4 Public API Command Path

## 结论

accepted

AgentMiMo 与 AgentDS 的 Phase 4 design fix re-review 均为 accepted，均确认 P4-D1 至 P4-D6 已修复，未发现
blocking finding。Controller 裁决：Phase 4 design fix / write-back 通过，可以进入 plan gate。

## Re-review Artifacts

- AgentMiMo: `docs/reviews/gateflow-phase-design-re-review-host-p4-mimo-20260514.md`
- AgentDS: `docs/reviews/gateflow-phase-design-re-review-host-p4-ds-20260514.md`
- Design fix: `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`

## Finding 裁决

| Finding | Controller decision | Evidence |
| --- | --- | --- |
| P4-D1 FollowupSnapshot queue 结果表达 | fixed | `docs/host/design.md` 已使用 `accepted_run_id` + `accepted_run_status` 表达 accepted follow-up result，`queued_run_id?` 仅为真正 queued 的可选派生字段。 |
| P4-D2 HostApiError 结构化 detail | fixed | `HostApiErrorCode.UNSUPPORTED_OPERATION` 与受限 typed `HostApiError.detail` 已写回；第一版 detail 包含 `SteerConflictDetail`，禁止无结构 extra payload。 |
| P4-D3 `submit_followup(steer)` Phase 4 边界 | fixed | Phase 4 只冻结 steer envelope / validation / error-detail contract，public facade 返回 `unsupported_operation`；Attempt switching deferred。 |
| P4-D4 public function behavior matrix | fixed | `docs/host/design.md` 与 `docs/host/implementation-control.md` 均已列出完整实现、子集实现、stable unsupported / deferred 的函数矩阵。 |
| P4-D5 `stream_run_events` cursor contract | fixed | EventLog 全局 `event_sequence` 是唯一 cursor truth；`limit`、过滤、empty result `next_cursor` 与 `HostEventView` 映射规则已冻结。 |
| P4-D6 `attach_active` public 表达 | fixed | 第一版返回当前 active `RunSnapshot`，不新增 canonical EventLog fact；后续如需 attach fact 必须先更新设计。 |

## Deferred Owner 裁决

`cancel_session_runs` 的 Phase 4 子集不能成为最终语义。Controller 接受并固定以下 owner：

- Phase 5：dispatching / active worker cancel propagation。
- Phase 7：`WAITING` cancel、wait record cancel、`resolve_wait` 完整治理。
- Phase 11：`RECOVERING` cancel、recovery scan / dispatch cancellation。

后续 phase plan 必须显式处理对应路径，不能把 Phase 4 queued / pre-dispatch `STARTING` 子集当作 complete
session-scope cancel。

## Plan Gate Requirements

Phase 4 plan 必须以以下真源为硬边界：

- `docs/host/design.md` 中 Phase 4 public function behavior matrix。
- `FollowupSnapshot.accepted_run_id` / `accepted_run_status` contract。
- `HostApiErrorCode.UNSUPPORTED_OPERATION` 与受限 typed error detail contract。
- `stream_run_events(host, run_id, cursor, limit?)` EventLog-backed cursor contract。
- `cancel_session_runs` Phase 4 子集与 Phase 5 / 7 / 11 deferred owner。

Plan agent 不得扩大 scope 到 Engine execution、scheduler / lane acquire、ToolRuntime、Projection worker、wait adapter、
destructive purge、full steer、retry / replay execution、active worker cancel、wait cancel 或 recovery cancel。

## Next Gate

进入 Phase 4 handoff implementation-ready plan gate。
