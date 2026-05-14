# Phase 5 Design Refinement: RunInputBuilder / LocalProxy / EngineEvent Ingest

## Scope

Work unit: Host Phase 5. RunInputBuilder 与本地执行 Dispatch。

Design truth:

- `docs/host/design.md` §13.4 EngineEvent 映射
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §22 Cancel
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/implementation-control.md` Phase 5

Controller judgment: Phase 5 的目标真实存在且严重性评估成立。Phase 4 只完成 public command path 和 pre-dispatch cancel 子集，当前 Host 还没有 RunInputBuilder、dispatch scheduler、LocalProxy、EngineEvent ingest 和 terminal closeout 的执行闭环；如果直接写 plan，会在 Attempt identity、dispatch record 状态和 ToolRuntime / WAITING 边界上让 implementation agent 自行设计，这是架构敏感风险。

## User-Confirmed Decisions

### P5-D1. Engine contract remains Host-agnostic

Decision: accepted.

Phase 5 不修改 Engine 公共 `EngineEvent` 契约来携带 `attempt_id` / `execution_id`。Host-owned LocalProxy / EngineWorker envelope 绑定 `session_id`、`run_id`、`attempt_id`、`execution_id`、dispatch record 和 cancellation source；Host ingest 在 envelope 边界校验 `attempt_id + execution_id`。

Reasoning:

- Engine 只执行单次 `AgentRunRequest`，不应理解 Host Attempt、dispatch record、recovery 或 durable state。
- LocalProxy 是 Phase 5 的语义基准；RemoteProxy 后续替换 transport，不替换治理边界。
- 该决策满足 `UI -> Service -> Host -> Engine` 分层，并避免把 Host 状态机反向泄漏到 Engine。

Design write-back:

- `docs/host/design.md` §17 增加 LocalProxy / EngineWorker identity boundary。

### P5-D2. Dispatch record state expands in Phase 5

Decision: accepted.

Phase 5 fresh schema / typed enum 必须把 dispatch record 状态扩展为至少 `pending`、`waiting_for_lane`、`dispatching`、`cancelled`。`waiting_for_lane` 表示 scheduler 已开始等待 runtime lane；`dispatching` 表示 lane acquire 后已通过 durable recheck，并准备调用 WorkerProxy。

Reasoning:

- Phase 5 design 已要求 lane acquire 前后有可恢复、可诊断的 durable dispatch 状态。
- 现有 Phase 3 schema 只允许 `pending` / `cancelled`，这是前置 phase 子集，不足以实现 Phase 5。
- 项目按全新 schema 起库处理；不需要旧库兼容读取或迁移分支。

Design write-back:

- `docs/host/design.md` §17 明确 `waiting_for_lane` / `dispatching` 进入 Phase 5 schema 与 typed enum。

### P5-D3. ToolRuntime / WAITING remains out of Phase 5

Decision: accepted.

Phase 5 只允许 no-tool 或最小 fake ToolExecutor 支撑本地 Engine 执行闭环；不实现 ToolRuntime governance、ToolBundle snapshot、Host accept barrier、`fetch_more`、语义级重复工具调用治理、wait record 或 `resolve_wait`。如果本 phase 遇到 Engine `tool_awaiting` / `run_suspended`，只能按 unsupported execution path 记录诊断并结构化失败，或在 plan 中证明 fake executor 不会产生该路径。

Reasoning:

- ToolRuntime owner 是 Phase 6，Tool Awaiting / `resolve_wait` owner 是 Phase 7。
- 让 Phase 5 临时实现 wait table 或 ToolRuntime wrapper 会破坏 phase ownership，并可能把 EngineEvent `tool_awaiting` 错误升级为 canonical owner。
- Phase 5 的 success signal 是本地 Engine 执行闭环，不是工具治理闭环。

Design write-back:

- `docs/host/design.md` §17 增加 Phase 5 ToolRuntime / wait boundary。

## Plan Gate Readiness

Phase 5 design refinement 后，下一步可以进入 handoff implementation-ready plan gate，但 plan 必须覆盖以下内容，否则应被 plan review 拒绝：

- RunInputBuilder typed provider protocols 的第一版最小集合，且当前用户输入只能来自 `USER_INPUT_ACCEPTED` canonical fact。
- LocalProxy / EngineWorker envelope 类型、Host ingest candidate 类型、以及不修改 Engine 公共 contract 的 import boundary。
- Dispatch record fresh schema / enum 扩展、`pending -> waiting_for_lane -> dispatching -> ATTEMPT_RUNNING` 的事务边界、lane acquire timeout / cancel / close 行为。
- EngineEvent terminal / non-terminal / preview / diagnostic / canonical 映射，以及 stream EOF / worker crash / startup reject 的 terminal closeout 策略。
- Phase 5 active dispatch cancel 与 `cancel_session_runs` dispatching / active worker 子集，不触碰 `WAITING` 或 `RECOVERING`。
- Validation matrix：RunInputBuilder determinism、dispatch recheck races、fake local Engine success / failure / cancel、stream EOF failure、pyright、README sync。

## Residual Risks

- RemoteProxy 等价语义仍属于 Phase 14 owner；Phase 5 plan 只能定义 LocalProxy semantic baseline。
- ToolRuntime accept ack、`fetch_more`、duplicate governance 属于 Phase 6 owner。
- `WAITING` cancel、wait record cancel 和 external job result rejection 属于 Phase 7 owner。
- `RECOVERING` dispatch cancellation 和 positive orphan proof 属于 Phase 11 owner。

