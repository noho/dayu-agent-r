# Gateflow Phase Design Re-review - Host P4 - AgentMiMo

## 结论

accepted

P4-D1 至 P4-D6 六个 design readiness finding 均已在设计真源与总控文档中充分修复；`cancel_session_runs` 后续完善提醒明确且不可被 plan agent 误读为最终语义；所有新增公共类型与错误契约表达足够进入 Phase 4 plan gate。无 blocking finding。

## 复核范围

- `docs/host/design.md`：§11 Host 公共接口（lines 960-1097）、§12 Follow-up 与 Steer（lines 1099-1134）
- `docs/host/implementation-control.md`：Phase 4 条目（lines 487-551）
- `docs/reviews/gateflow-phase-design-host-p4-codex-20260514.md`
- `docs/reviews/gateflow-phase-design-host-p4-controller-adjudication-20260514.md`
- `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`

## Findings

无 blocking finding。

逐项复核如下：

### P4-D1 FollowupSnapshot queue 结果表达 - fixed

- 直接证据：`docs/host/design.md:1055` 已写入 `accepted_run_id` + `accepted_run_status`，`accepted_run_status` 使用公共 `RunStatus`，queue 分支可为 `QUEUED` 或 `RUNNING`。`queued_run_id?` 明确为派生可选字段，不能作为 queue 分支唯一结果字段。
- 控制文档对齐：`docs/host/implementation-control.md:521` 已同步。
- 代码对齐现状：`dayu/host/api.py:990-1044` 的 `FollowupSnapshot` 仍使用旧 shape（`queued_run_id` 强制存在），需要在 Phase 4 implementation 中按设计真源更新。这一点是 implementation scope 内的正常工作，不阻塞 plan gate。

### P4-D2 HostApiError 结构化 detail - fixed

- 直接证据：`docs/host/design.md:1077-1087` 已定义 `HostApiError` 为受限 typed contract：`code`、`message`、`retryable` 与 `detail?`。`detail` 只能是显式定义的 detail union 成员，禁止无结构 god bag。第一版包含 `SteerConflictDetail(target_run_id, target_run_status?, current_active_run_id?, current_active_run_status?)`。
- 控制文档对齐：`docs/host/implementation-control.md:522` 已同步。
- `SteerConflictDetail` 字段粒度合理：只携带 steer precondition 失败的 Run id 与状态摘要，不嵌入完整 `RunSnapshot`，不暴露 durable row。

### P4-D3 submit_followup(steer) Phase 4 行为边界 - fixed

- 直接证据：`docs/host/design.md:1116-1117` 明确 Phase 4 只冻结 steer envelope、request validation、错误码与 typed detail contract，不实现 Attempt switching。Phase 4 public facade 在 steer 路径返回 `unsupported_operation`，`retryable=false`。
- 控制文档对齐：`docs/host/implementation-control.md:523` 已同步，且 line 517 在"不做"中显式列出。
- 后续完整 steer 语义（lines 1118-1134）已明确标注为"后续 owner 的目标设计，不是 Phase 4 implementation scope"，不会被 plan agent 误读。

### P4-D4 public function 行为矩阵 - fixed

- 直接证据：`docs/host/implementation-control.md:507-509` 已形成明确的三层矩阵：
  - 完整实现（line 507）：`ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、`submit_followup(queue)`、`get_run`、`stream_run_events`、queued / pre-dispatch `cancel_run`
  - 子集实现（line 508）：`cancel_session_runs` 只覆盖 queued / pre-dispatch `STARTING`
  - stable unsupported / deferred（line 509）：`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、active dispatch cancel、wait / recovery cancel
- 设计真源对齐：`docs/host/design.md:1026-1028` 对 `cancel_run`、`cancel_session_runs`、`submit_followup` 的 Phase 4 边界有逐函数说明。
- 矩阵清晰、无歧义，plan agent 可直接据此确定每个函数的实现深度与错误行为。

### P4-D5 stream_run_events cursor contract - fixed

- 直接证据：`docs/host/design.md:1089-1097` 已冻结完整 cursor contract：
  - 全局 `event_sequence` 是唯一 cursor truth（line 1091）
  - public signature 包含可选 `limit`，默认值和最大值以公共常量暴露（line 1092）
  - 只返回与目标 `run_id` 相关的 `HostEventView`（line 1093）
  - `next_cursor` 以扫描过的最大全局 `event_sequence` 为准，过滤后空结果也前进（line 1094）
  - 无扫描推进时 `next_cursor` 等于输入 cursor（line 1095）
  - `HostEventView` 是 EventLog row 的公共视图映射，不暴露 durable row 私有列，不从 projection 派生（line 1096）
  - Phase 4 不引入 projection truth（line 1097）
- 控制文档对齐：`docs/host/implementation-control.md:524` 已同步。
- cursor contract 足够编码，plan agent 可直接据此实现 read path 与测试。

### P4-D6 attach_active public audit / read-model 表达 - fixed

- 直接证据：`docs/host/implementation-control.md:525` 明确 `attach_active` 第一版不新增 canonical EventLog fact，返回当前 active `RunSnapshot`，幂等记录可解释 request，audit/read-model 由后续 projection 基于 refs 表达。
- 设计真源对齐：`docs/host/design.md:1021` 的 `start_run` 语义已包含 attach active 分支。
- 该决策避免了 Phase 4 临时发明 EventLog 事件，保持 EventLog canonical fact 的干净边界。

## cancel_session_runs 后续完善提醒复核

- 直接证据：`docs/host/design.md:1027` 明确"Phase 4 只实现 queued / pre-dispatch `STARTING` 子集，完整 dispatching / active worker、`WAITING`、`RECOVERING` cancel 必须由 Phase 5 / 7 / 11 补齐"。
- 控制文档同步：`docs/host/implementation-control.md:508` 在"范围"中写明子集实现与后续追踪；line 518 在"不做"中写明不得把 Phase 4 子集写成最终语义；line 551 在"后续依赖"中列出 Phase 5 / 7 / 11 的补齐职责。
- 追踪区对齐：`docs/host/implementation-control.md:1312-1313` 已有明确追踪项，指出 Phase 4 `cancel_session_runs` 只允许实现 queued / pre-dispatch `STARTING` 子集，Phase 5 / 7 / 11 owner 必须在各自 phase 补齐。
- 提醒充分且分布在设计真源、控制文档范围/不做/后续依赖三处，plan agent 不可能将其误读为最终语义。

## 公共类型与错误契约进入 plan gate 评估

| 契约要素 | 设计真源位置 | 表达充分性 |
|---|---|---|
| `FollowupSnapshot` | design.md:1055 | 充分：`accepted_run_id` + `accepted_run_status` + 可选 `queued_run_id?` + 可选 `target_run_id?` |
| `HostApiErrorCode.UNSUPPORTED_OPERATION` | design.md:1066, 1075 | 充分：语义定义明确，区分于 `invalid_state` |
| `HostApiError.detail` | design.md:1077-1087 | 充分：受限 typed detail union，`SteerConflictDetail` 字段完整 |
| `stream_run_events` cursor | design.md:1089-1097 | 充分：limit、过滤、next_cursor、HostEventView 映射规则均已冻结 |
| `attach_active` | control.md:525 | 充分：不新增 canonical fact，返回 active RunSnapshot |
| `cancel_session_runs` 子集边界 | design.md:1027, control.md:508/518/551 | 充分：三处一致声明，后续 owner 明确 |

所有契约要素均有设计真源定义、控制文档对齐和后续 phase owner 追踪，plan agent 可直接据此生成 implementation-ready plan。

## Residual Risks / Deferred Owners

1. **`FollowupSnapshot` 代码对齐**：`dayu/host/api.py:990-1044` 的当前 `FollowupSnapshot` 仍使用旧 shape（`queued_run_id` 强制存在）。Phase 4 Slice 2 必须按设计真源更新该类型。不阻塞 plan gate，属于 implementation scope。

2. **`HostApiError.detail` 代码对齐**：`dayu/host/api.py:1148-1178` 的当前 `HostApiError` 只有 `code`、`message`、`retryable`，无 `detail` 字段。Phase 4 Slice 1 或 Slice 4 必须扩展。不阻塞 plan gate。

3. **`HostApiErrorCode.UNSUPPORTED_OPERATION` 代码对齐**：`dayu/host/api.py:176-187` 的当前 `HostApiErrorCode` 缺少该枚举值。Phase 4 必须新增。不阻塞 plan gate。

4. **Phase 4 `cancel_session_runs` 子集实现后的用户体验**：当 `cancel_session_runs` 只取消 queued / pre-dispatch STARTING Run 时，dispatching / active worker / WAITING / RECOVERING Run 不受影响。调用方可能期望 session-scope cancel 是全量的。Phase 4 plan 必须在测试和文档中明确这一边界，避免用户误解。

5. **`stream_run_events` 默认 / 最大 limit 常量值**：设计真源要求以公共常量暴露，但未指定具体数值。Phase 4 plan 阶段需确定合理默认值（如 100 / 1000），属于 plan agent 可自行决定的实现细节，不阻塞 plan gate。

6. **后续 phase owner 追踪完整性**：
   - Phase 5：dispatching / active worker cancel propagation
   - Phase 7：`WAITING` cancel / wait record cancel / `resolve_wait` 完整治理
   - Phase 11：`RECOVERING` cancel / recovery dispatch cancellation
   - Phase 15：`purge_session` destructive cleanup
   - 后续 steer / retry / replay owner：完整 Attempt switching 与 execution semantics

   以上均已在控制文档追踪区有明确 owner，无悬空项。

## Plan Gate Recommendation

**推荐进入 Phase 4 plan gate。**

理由：
1. P4-D1 至 P4-D6 六个 design readiness finding 均已在设计真源与控制文档中充分修复，无遗留 blocking question。
2. `cancel_session_runs` 后续完善提醒分布在设计真源、控制文档范围/不做/后续依赖与追踪区四处，plan agent 不可能误读为最终语义。
3. 所有新增公共类型（`FollowupSnapshot`、`HostApiError.detail`、`SteerConflictDetail`、`HostApiErrorCode.UNSUPPORTED_OPERATION`、`stream_run_events` cursor contract、`attach_active` 表达）均有设计真源定义，表达足够进入 plan gate。
4. 未引入过度设计、无结构 payload、反向依赖、Host truth 污染或 projection truth 替代 EventLog 等问题。
5. 代码与设计真源之间的 gap 均属于 Phase 4 implementation scope 内的正常类型更新工作，不构成 plan gate blocker。
