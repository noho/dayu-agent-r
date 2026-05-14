# Gateflow Phase Design Adjudication - Host P4 Public API Command Path

## 结论

Phase 4 design readiness artifact `docs/reviews/gateflow-phase-design-host-p4-codex-20260514.md`
的总体结论裁决为 accepted：当前不能直接进入 plan gate，必须先完成 design fix / write-back。

根因不是实现 agent 信心不足，而是 Phase 4 触及 public API contract、错误结构、snapshot shape 与 deferred
function 行为边界；这些内容若不先写入设计真源，implementation-ready plan 会被迫临时发明公共接口。

## Finding 裁决

### P4-D1 FollowupSnapshot queue 结果表达不足 - accepted

- 直接证据：`docs/host/design.md` 要求 `submit_followup(queue)` 在无 active Run 时直接创建并启动新 Run；但当前
  `dayu.host.api.FollowupSnapshot` 的 queue 分支强制要求 `queued_run_id`。
- 裁决：accepted。
- 设计修复方向：`FollowupSnapshot` 必须表达“accepted follow-up 产生的 Run”，而不是把 queue 结果绑定为 queued
  状态。推荐设计为 `accepted_run_id` + `accepted_run_status`，其中状态可为 `QUEUED` 或 `RUNNING`；若仍保留
  `queued_run_id`，必须只作为派生/可选字段，不能作为 queue 分支唯一结果字段。

### P4-D2 steer conflict / invalid_state 缺少结构化 detail - accepted

- 直接证据：`docs/host/design.md` 要求 steer target 不是当前 active Run 时返回 `conflict`，且错误响应包含当前
  active Run 与目标 Run 状态摘要；当前 `HostApiError` 只有 `code`、`message`、`retryable`。
- 裁决：accepted。
- 设计修复方向：引入受限 typed error detail，而不是无结构 extra payload。至少需要覆盖 steer conflict detail，
  包含 target/current active run 的 id 与状态摘要；该 detail 类型必须保持 Host 公共 API 类型边界，不进入
  `dayu.contracts`。

### P4-D3 submit_followup(steer) Phase 4 行为边界未冻结 - accepted

- 直接证据：完整 steer 依赖 cancellation source、wait record、Attempt stop、RunInputBuilder 与 dispatch，均不在
  Phase 4 范围内。
- 裁决：accepted。
- 设计修复方向：Phase 4 只冻结 steer request validation、public error/detail contract 与 deferred behavior，不实现
  Attempt switching。建议新增 `UNSUPPORTED_OPERATION` 或等价明确错误码，避免用 `invalid_state` 表达“能力未落地”。

### P4-D4 public function 完整实现 / deferred 行为矩阵缺失 - accepted

- 直接证据：Phase 4 总控要求确认哪些 public functions 完整实现、哪些只稳定公共契约；当前设计只列接口集合，
  未形成可直接计划的行为矩阵。
- 裁决：accepted。
- 设计修复方向：设计真源必须列出 Phase 4 matrix。可完整实现的函数应只依赖 Phase 1-3 能力；依赖 Phase 5/7/8/11/15
  的能力必须明确 deferred owner 和当前错误行为。

### P4-D5 stream_run_events cursor contract 不足 - accepted

- 直接证据：设计只要求从全局 `event_sequence` cursor 补读目标 Run 事件；现有 EventLog primitive 是全局读取。
  filtering、limit、empty result 与 `next_cursor` 规则未固定。
- 裁决：accepted。
- 设计修复方向：Phase 4 必须冻结 `stream_run_events` 的 public signature、limit 上限、过滤范围、empty result
  cursor 与 `HostEventView` 映射规则。Phase 4 可以实现 EventLog-backed read path，但不能引入 projection truth。

### P4-D6 attach_active public audit / read-model 表达 - accepted as design-fix input

- 直接证据：总控追踪区已把 `attach_active` public audit / read-model 表达转交 Phase 4。
- 裁决：accepted as design-fix input。
- 设计修复方向：如果 Phase 4 暴露 `start_run(queue_policy=attach_active)`，必须明确 attach 是否 append canonical fact。
  推荐第一版不为 attach request 发明新的 EventLog canonical fact；返回当前 active `RunSnapshot`，幂等记录解释 request，
  audit/read-model 可在后续 projection 中基于 idempotency / diagnostic refs 表达。

## Controller Proposed Decisions

以下设计修复建议进入用户确认：

1. `FollowupSnapshot` 改为以 `accepted_run_id` 与 `accepted_run_status` 表达 queue follow-up 结果，避免把 running
   Run 塞进 `queued_run_id`。
2. `HostApiError` 增加受限 typed `detail` union，并新增 steer conflict detail。
3. 新增 `HostApiErrorCode.UNSUPPORTED_OPERATION`，用于 Phase 4 已冻结 envelope 但语义由后续 phase 落地的函数。
4. Phase 4 完整实现：`ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、
   `submit_followup(queue)`、`get_run`、`stream_run_events`、queued / pre-dispatch `cancel_run`。
5. Phase 4 deferred with stable unsupported：`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、
   `purge_session`、active dispatch cancel、wait / recovery cancel。
6. `cancel_session_runs` 在 Phase 4 只实现当前 Phase 1-3 可闭环子集，或整体 deferred；该点需要 design fix 时进一步
   固定，因为它影响 session-scope cancel 的 public expectation。
7. `stream_run_events` 以全局 EventLog cursor 为唯一 cursor truth；Phase 4 不引入 projection cursor，不启动 projection。

## Blocking Open Questions For User

1. 是否接受新增 `HostApiErrorCode.UNSUPPORTED_OPERATION`，专门表达“public envelope 已冻结，但完整语义由后续 phase
   落地”？
2. `cancel_session_runs` 在 Phase 4 是否应实现 Phase 1-3 已支持的子集（queued / pre-dispatch STARTING），还是整体
   返回 `UNSUPPORTED_OPERATION` 直到 dispatch / wait / recovery cancel 都具备？

## Next Gate

在用户确认上述两个问题后，进入 design fix / write-back：

- 更新 `docs/host/design.md` 的 Phase 4 public API contract。
- 更新 `docs/host/implementation-control.md` 的 Phase 4 tracking / 当前状态。
- 生成 design fix artifact。
- 派 AgentMiMo / AgentDS 做 design fix re-review。

确认前不得进入 Phase 4 plan gate。
