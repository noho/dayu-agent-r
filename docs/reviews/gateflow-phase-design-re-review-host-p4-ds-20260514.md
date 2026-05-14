# Gateflow Phase Design Re-review - Host P4 - AgentDS

## 结论

accepted

P4-D1 到 P4-D6 均已在设计真源和总控文档中充分修复。未发现新的 blocking finding、过度设计、无结构 payload、反向依赖、Host truth 污染或 projection truth 替代 EventLog 问题。cancel_session_runs 后续完善提醒已嵌入多处，语义明确不可被 plan agent 误读为最终语义。FollowupSnapshot、HostApiError typed detail、unsupported_operation、stream_run_events cursor contract、attach_active 表达均已达到可进入 Phase 4 plan gate 的水平。

## 复核范围

- `docs/host/design.md`（设计真源）
- `docs/host/implementation-control.md`（实施总控）
- `docs/reviews/gateflow-phase-design-host-p4-codex-20260514.md`（原始 design readiness artifact）
- `docs/reviews/gateflow-phase-design-host-p4-controller-adjudication-20260514.md`（controller 裁决）
- `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`（design fix artifact）

## Findings

### P4-D1 - FollowupSnapshot queue 结果表达 - 已修复

**直接证据：**

- `docs/host/design.md:1055` 将 `FollowupSnapshot` 定义为 `accepted_run_id` + `accepted_run_status`，其中 `accepted_run_status` 使用公共 `RunStatus`，queue 分支可为 `QUEUED` 或 `RUNNING`。`queued_run_id?` 降级为真正处于 `QUEUED` 的 Run 的可选派生字段，"不能作为 queue 分支唯一结果字段"。
- `docs/host/design.md:1111` 明确写入："queue follow-up 的 public result 必须使用 `accepted_run_id` + `accepted_run_status` 表达被接受的新 Run。`queued_run_id` 不能承载 running Run id。"
- `docs/host/design.md:857` behavior matrix 行：`submit_followup(queue)` 结果用 `accepted_run_id` + `accepted_run_status` 表达。
- `docs/host/implementation-control.md:521` 总控记录相同约束。

**裁定：** 已充分修复。running Run id 不会再被塞进 `queued_run_id` 字段，plan agent 有明确的终态字段名和语义。

### P4-D2 - steer conflict / invalid_state 缺少结构化 detail - 已修复

**直接证据：**

- `docs/host/design.md:1066` 新增 `unsupported_operation` 错误码。
- `docs/host/design.md:1075` 明确 `unsupported_operation` 语义："public request / response envelope 已冻结，但完整语义由后续 phase 落地；它不表达目标对象状态错误，也不能伪装成 `invalid_state`。"
- `docs/host/design.md:1077-1087` 定义 `HostApiError` 为受限 typed contract：`code`、`message`、`retryable`、`detail?`。`detail` 是受限 typed detail union，第一版包含 `SteerConflictDetail(target_run_id, target_run_status?, current_active_run_id?, current_active_run_status?)`。明确禁止 `extra` / `payload` / `metadata` god bag。
- `docs/host/implementation-control.md:522` 总控记录相同约束。

**裁定：** 已充分修复。typed detail union 设计避免了 god bag，`SteerConflictDetail` 携带足够状态摘要而不暴露 durable row。`unsupported_operation` 与 `invalid_state` 的语义隔离清晰，implementation agent 不会用 `invalid_state` 伪装"能力未落地"。

### P4-D3 - submit_followup(steer) Phase 4 行为边界 - 已修复

**直接证据：**

- `docs/host/design.md:862` behavior matrix 行：`submit_followup(steer)` = stable unsupported / deferred，"Phase 4 只冻结 envelope、validation、error/detail contract；public facade 返回 `unsupported_operation`。"
- `docs/host/design.md:1028` 接口语义段："Phase 4 只冻结 steer envelope、validation 与 error/detail contract，public facade 对 steer 返回 `unsupported_operation`；完整 Attempt switching 后续落地。"
- `docs/host/design.md:1116` steer 语义段首句："Phase 4 只冻结 `submit_followup(steer)` 的 public envelope、request validation、错误码与 typed detail contract，不实现 Attempt switching。Phase 4 public facade 在 steer 路径返回 `unsupported_operation`，`retryable=false`；完整 `RUNNING` / `WAITING` steer 语义由后续 steer / dispatch / wait owner 落地。以下完整语义是后续 owner 的目标设计，不是 Phase 4 implementation scope。"
- `docs/host/implementation-control.md:517` 总控"不做"段相同约束。

**裁定：** 已充分修复。Phase 4 steer 边界被三重确认（behavior matrix、接口语义、steer 专段），plan agent 不可能误读为需要实现 Attempt switching。

### P4-D4 - public function 行为矩阵 - 已修复

**直接证据：**

- `docs/host/design.md:848-869` 完整 behavior matrix 覆盖 16 行：`ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、`submit_followup(queue)`、`get_run`、`stream_run_events`、`cancel_run` queued/pre-dispatch、`cancel_session_runs` queued/pre-dispatch、`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、active dispatch cancel、wait cancel、recovery cancel。每行标注 Phase 4 行为和后续 owner。
- `docs/host/implementation-control.md:507-509` 三层分类：完整实现 9 项、子集实现 1 项（`cancel_session_runs`）、stable unsupported/deferred 8 项。

**裁定：** 已充分修复。plan agent 可以据此矩阵逐函数确定实现范围，不会把 deferred 函数当完整实现处理，也不会遗漏需冻结 envelope 的 deferred 函数。

### P4-D5 - stream_run_events cursor contract - 已修复

**直接证据：**

- `docs/host/design.md:1089-1097` 完整 cursor contract：
  - 全局 EventLog `event_sequence` 是唯一 cursor truth（`docs/host/design.md:1091`）。
  - public signature 包含可选 `limit`，默认/最大值以公共常量暴露（`docs/host/design.md:1092`）。
  - 只返回目标 `run_id` 相关事件（`docs/host/design.md:1093`）。
  - `next_cursor` 以扫描过的最大全局 `event_sequence` 为准，即使过滤后结果为空也前进（`docs/host/design.md:1094`）。
  - 无新 EventLog row 时 `next_cursor` 等于输入 cursor（`docs/host/design.md:1095`）。
  - `HostEventView` 映射规则已定义（`docs/host/design.md:1096`）。
  - Phase 4 不引入 projection truth（`docs/host/design.md:1097`）。
- `docs/host/design.md:859` behavior matrix 行：`stream_run_events` 完整实现 EventLog-backed read path。
- `docs/host/design.md:1239` EventLog 设计段重申 cursor contract。
- `docs/host/implementation-control.md:524` 总控记录相同约束。

**裁定：** 已充分修复。cursor contract 覆盖了 filtering、limit、empty result、next_cursor 和 HostEventView 映射，plan agent 可以直接编码实现。

### P4-D6 - attach_active public audit / read-model 表达 - 已修复

**直接证据：**

- `docs/host/design.md:490`："`attach_active`：当前 Session 有 active Run 时，返回当前 active `RunSnapshot`，不触发新执行，不新增 canonical EventLog fact。第一版只通过幂等记录、diagnostic refs 或后续 audit/read-model projection 解释 attach request；如果后续需要把 attach 作为可查询业务事实，必须先补充新的 canonical event shape，不能由 public facade 临时发明事件。"
- `docs/host/design.md:856` behavior matrix 行：`start_run` 支持 `attach_active`，"返回 active `RunSnapshot`，不新增 canonical fact"。
- `docs/host/implementation-control.md:525` 总控记录相同约束。

**裁定：** 已充分修复。不新增 EventLog fact 的约束明确写回设计真源，plan agent 不会临时发明 canonical event。

### cancel_session_runs 后续完善提醒 - 无歧义

**直接证据：**

- `docs/host/design.md:861` behavior matrix 行标注"子集实现并追踪后续完善"，deferred 范围列在说明中。
- `docs/host/design.md:1027` 接口语义段："Phase 4 只实现 queued / pre-dispatch `STARTING` 子集，完整 dispatching / active worker、`WAITING`、`RECOVERING` cancel 必须由 Phase 5 / 7 / 11 补齐。"
- `docs/host/design.md:2156` cancel 治理段："Phase 4 只实现 `cancel_session_runs` 的 Phase 1-3 可闭环子集：`QUEUED` Run 与 pre-dispatch Attempt `STARTING`。dispatch record 已进入 `dispatching`、Attempt 已 `RUNNING`、`WAITING`、`RECOVERING`、active worker propagation、wait record cancel 与 recovery dispatch cancel 都是 stable deferred 行为；Phase 5 / Phase 7 / Phase 11 必须分别补齐，不能把 Phase 4 子集解释为最终语义。"
- `docs/host/design.md:2166-2168` 逐场景标注 owner："已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy；Phase 5 owns 该路径"、"`WAITING` Run 取消 wait record；Phase 7 owns 该路径"、"`RECOVERING` Run 的取消由 Phase 11 recovery owner 接入"。
- `docs/host/implementation-control.md:508` 总控："子集实现：`cancel_session_runs` 只覆盖 queued / pre-dispatch `STARTING`；dispatching / active worker、`WAITING`、`RECOVERING` cancel 必须追踪到 Phase 5 / 7 / 11。"
- `docs/host/implementation-control.md:1312` 追踪段："Phase 4 `cancel_session_runs` 只允许实现 queued / pre-dispatch `STARTING` 子集；Phase 5 / 7 / 11 owner 必须在各自 phase 补齐 dispatching / active worker、`WAITING`、`RECOVERING` 的完整 session-scope cancel 能力。"

**裁定：** 提醒已嵌入至少 6 处（behavior matrix、接口语义、cancel 治理、逐场景 owner、总控范围、总控追踪），每处都明确 Phase 5/7/11 的具体职责划分和"不能把 Phase 4 子集解释为最终语义"的禁令。plan agent 不可能误读。

### 过度设计 / 无结构 payload 检查

**直接证据：**

- `docs/host/design.md:1077`："`HostApiError` 必须是受限 typed contract：`code`、`message`、`retryable` 与 `detail?`。`detail` 只能是 Host 公共 API 中显式定义的 detail union 成员，禁止无结构 `extra` / `payload` / `metadata` god bag。"
- `docs/host/design.md:1087`："后续新增错误 detail 时必须新增具体 typed detail，不得把显式参数塞进无结构 payload。"
- behavior matrix 无 row 引入无结构 payload 或 `policy_overrides` bag。
- `docs/host/design.md:1033`："第一版公共 API 不暴露开放式 policy knobs。Host policy 可以有默认值，但 request 不能携带无结构 `policy_overrides`。"

**裁定：** 无过度设计。typed detail union 是受限设计，不是 god bag。无结构 payload 被显式禁止。

### 反向依赖检查

**直接证据：**

- `docs/host/design.md:36-41`：依赖方向 `UI -> Service -> Host -> Engine`，禁止反向依赖。
- `docs/host/design.md:63`：`dayu.runtime` 不得 import 业务层。
- 本次 fix 未引入任何跨层 import 或反向引用。

**裁定：** 无反向依赖。

### Host truth 污染 / projection truth 替代 EventLog 检查

**直接证据：**

- `docs/host/design.md:1091`："全局 EventLog `event_sequence` 是唯一 cursor truth；projection checkpoint、session-local cursor、client sequence 或内存订阅位置都不能替代它。"
- `docs/host/design.md:1097`："Phase 4 不引入 projection truth；Phase 8 可以基于同一 cursor contract 建 projection / read model，但不能改变本接口的 truth 来源。"
- `docs/host/design.md:1053`：timeline cursor 使用全局 `event_sequence` cursor，"session-local cursor 只能作为 read model 优化，不能替代全局 cursor"。
- `docs/host/design.md:490`：`attach_active` 不新增 EventLog fact，audit 走 idempotency/diagnostic refs。

**裁定：** EventLog truth 未被污染，projection 未替代 EventLog。所有 read path 以 EventLog cursor 为唯一真源。

## Residual Risks / Deferred Owners

以下风险不阻塞 Phase 4 plan gate，但需在对应 phase 进入前确认：

1. **SteerConflictDetail 与 FollowupSnapshot steer 分支的交互**：Phase 4 steer 返回 `unsupported_operation`，不会产生 accepted steer snapshot。但 `FollowupSnapshot` 已预留 `target_run_id?` 字段给 steer 分支（`docs/host/design.md:1055`）。后续 steer owner 接入时，需要确认 `FollowupSnapshot` 的 steer 分支 shape 是否仍满足需求，届时可能需要微调。

2. **HostApiError detail union 的运行时反序列化**：typed detail union 需要在 Phase 4 implementation 中落地反序列化 / 类型区分机制（tagged union 或 `isinstance` check）。plan 应将此纳入 Slice 1 public types 的实施范围。

3. **cancel_session_runs 子集与完整语义的边界测试**：Phase 4 测试需要验证 queued/pre-dispatch cancel 子集正确，同时验证 deferred 场景（dispatching/active/WAITING/RECOVERING）不会 silent no-op 而是返回明确错误或 deferred 信号。若 plan 未覆盖 deferred 场景的 API 行为测试，应在 plan review 阶段捕获。

4. **stream_run_events limit 公共常量命名**：设计要求"默认值和最大值必须以公共常量暴露"（`docs/host/design.md:1092`），但未指定常量名。plan 需固定命名（如 `DEFAULT_EVENT_STREAM_LIMIT` / `MAX_EVENT_STREAM_LIMIT`），避免 implementation agent 自行命名导致后续 phase 不一致。

## Plan Gate Recommendation

Phase 4 可以进入 plan gate。前置条件均已满足：

- 6 个 design findings 全部在真源文档中修复。
- cancel_session_runs 后续完善提醒已多处嵌入，不可被误读。
- FollowupSnapshot、HostApiError typed detail、unsupported_operation、stream_run_events cursor contract、attach_active 表达均已足够具体，可直接编码。
- 未引入过度设计、god bag、反向依赖、Host truth 污染或 projection truth 替代 EventLog。

plan 生成时应以 `docs/host/design.md:848-869` behavior matrix 为范围真源，以 `docs/host/design.md:1055-1097` 的 snapshot shape、错误 contract 和 cursor contract 为类型真源，以 `docs/host/implementation-control.md:487-551` 的范围/交付物/验证为交付真源。plan 必须逐行对齐 behavior matrix 的实现/deferred 分类，不得自行升级或降级任何函数的 Phase 4 行为。
