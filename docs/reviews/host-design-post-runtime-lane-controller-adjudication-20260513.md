# Host Design Post-Runtime/Lane Review Controller Adjudication

- 日期：2026-05-13
- 总控：AgentController
- 输入 review：
  - `docs/reviews/host-design-post-runtime-lane-review-mimo-20260513.md`
  - `docs/reviews/host-design-post-runtime-lane-review-ds-20260513.md`
  - `docs/reviews/host-design-post-runtime-lane-review-codex-20260513.md`
- 被审文档：
  - `docs/host/design.md`
  - `docs/host/implementation-control.md`
- 裁决目标：判断当前设计是否足够进入 phase 编排，并给出需要写回的最终设计 / 总控修正。

## 总控结论

当前不应直接进入 phase orchestration。

原因不是整体架构方向错误，而是两个进入 phase 编排前必须先收口的阻塞项仍存在：

1. `docs/host/implementation-control.md` 尚未提供实际 phase map。它现在有流程规则和约束，但没有 phase 清单、依赖、入口、出口和交付物，无法作为后续 phase plan 的总控输入。
2. `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 的 canonical owner 仍存在冲突。Tool awaiting 是 wait record、cancel、resume、recovery 的核心边界，不能留给 phase implementation agent 重新解释。

完成本裁决列出的 P0 / P1 写回后，应再做一次短 re-review。P2 可以进入对应 phase discussion 或 implementation-control tracking。

## P0 裁决

### A1. implementation-control 缺少 Phase Map

裁决：成立，P0。

影响：这是进入 phase orchestration 的总控阻塞项，不是 Host 架构本身的失败。当前 `implementation-control.md` 负责 phase 编排，但没有实际 phase 清单，后续 planning agent 会自行切分 Storage、EventLog、State Machine、ToolRuntime、Recovery 等边界，容易造成越界实现和重复裁决。

建议写回：

- 在 `docs/host/implementation-control.md` 增加 `Phase Map`。
- 每个 phase 至少包含：
  - phase name。
  - design sections。
  - goal / success signal。
  - entry criteria。
  - exit criteria。
  - allowed files / modules。
  - explicit non-goals。
  - upstream dependencies。
  - required validation。
  - open questions / tracking items assigned to this phase。
- 推荐 phase 顺序：
  1. Public Contracts / Host API Surface。
  2. Durable Store / EventLog / State Transition。
  3. Session / Admission / Queue / Cancel。
  4. WorkerProxy / Lane Dispatch / EngineWorker Integration。
  5. ToolRuntime / ToolBundle / Accept Barrier / Truncation。
  6. Tool Awaiting / Wait Record / Resolve Wait / Resume。
  7. Projection / Audit / Usage / Tool Trace / Outbox。
  8. RunInputBuilder / Retry / Replay / Scene Inputs。
  9. Conversation Memory / Context Governance / Compaction。
  10. Recovery / Startup Scan / Orphan Proof。

写回位置：`docs/host/implementation-control.md`。

### A2. Tool Awaiting Canonical Owner 冲突

裁决：成立，P0。

问题：当前设计同时表达了三种容易冲突的语义：

- `TOOL_AWAITING` 是 canonical fact。
- Engine `tool_awaiting` 只是 preview / diagnostic / no-op。
- Engine `run_suspended` 又会映射 `RUN_WAITING + ATTEMPT_SUSPENDED`。

这会让 `ToolRuntime Host accept path` 和 `EngineEvent ingest` 都像是在推进 WAITING 状态。若 ToolRuntime 已 durable accepted awaiting，但 Engine 还没 emit `run_suspended` 就崩溃，Host 无法唯一判断 wait record 是否已创建、Attempt 是否已 suspended、Run 是否已 WAITING。

最终设计方案：

```text
ToolRuntime receives ToolAwaitingOutcome
  -> ToolRuntime submits awaiting candidate to Host accept path
  -> Host transaction validates attempt identity
  -> append TOOL_AWAITING
  -> append RUN_WAITING
  -> append ATTEMPT_SUSPENDED
  -> create active wait record
  -> update Run.status = WAITING
  -> close Attempt.status = SUSPENDED
  -> return accepted refs / ack
  -> ToolRuntime returns accepted awaiting outcome to Engine
  -> Engine may emit tool_awaiting / run_suspended with accepted refs
  -> Host ingests those EngineEvents as preview / diagnostic / idempotent confirmation only
```

不变量：

- `ToolRuntime Host accept path` 是 awaiting canonical owner。
- Engine `tool_awaiting` / `run_suspended` 不能创建 wait record。
- Engine `tool_awaiting` / `run_suspended` 不能把 Run 推入 `WAITING`。
- Engine `tool_awaiting` / `run_suspended` 不能关闭 Attempt。
- 如果 accepted ack 丢失，ToolRuntime 以 accept idempotency key 重试，Host 返回既有 accepted refs。
- 如果 Engine 后续事件丢失，Host 状态仍然完整。
- 如果 Engine 后续事件迟到，Host 只能做 diagnostic / idempotent confirmation。

写回位置：

- `docs/host/design.md` §9.1 状态迁移表。
- `docs/host/design.md` §13.3 Canonical Event Contract Matrix。
- `docs/host/design.md` §13.4 EngineEvent 映射。
- `docs/host/design.md` §20 Tool Awaiting / Wait Record。
- `dayu/README.md` `ToolAwaitingOutcome` / `wait record` 术语。

## P1 裁决

### B1. Context Compaction 需要区分 Proactive / Reactive

裁决：成立，P1。

最终设计方案：

- `proactive` compaction 是 pre-dispatch input governance。
- `reactive` compaction 是 provider / Engine 已进入 Attempt 后的 overflow recovery。
- 两者可以共享 compact artifact、quality check 和 `CONTEXT_COMPACTED` 语义，但不能共享同一个状态迁移路径。

Proactive path：

```text
Run accepted / before Attempt dispatch
  -> Host budget estimator detects over threshold
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)
  -> compact messages / memory / fact refs
  -> append CONTEXT_COMPACTED
  -> build AgentRunRequest
  -> append RUN_STARTED / ATTEMPT_STARTED
  -> dispatch
```

Reactive path：

```text
Engine / provider reports context overflow
  -> event must include attempt_id + execution_id
  -> Host validates active Attempt
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)
  -> close current Attempt according to policy
  -> Run -> RECOVERING
  -> compact
  -> append CONTEXT_COMPACTED
  -> append RUN_STARTED(start_reason=recovery)
  -> append ATTEMPT_STARTED
  -> dispatch new Attempt
```

Required fields：

- `trigger_source=proactive`：`attempt_id` / `execution_id` may be absent.
- `trigger_source=reactive`：`attempt_id` / `execution_id` required.

写回位置：`design.md` §13.3、§25.1。

### B2. Cancel 对 `RECOVERING` / waiting-for-lane / dispatching 的状态路径需要拆开

裁决：成立，P1。

最终设计方案：

`RECOVERING` 尚未 dispatch：

```text
cancel_run on Run RECOVERING
  -> append CANCEL_REQUESTED
  -> append RUN_CANCELLED
  -> Run -> CANCELLED
  -> no new Attempt
  -> no RUN_CANCELLING
```

Attempt `STARTING` 且 dispatch record 为 `pending` / `waiting_for_lane`：

```text
cancel_run
  -> append CANCEL_REQUESTED
  -> append ATTEMPT_CANCELLED
  -> append RUN_CANCELLED
  -> mark dispatch record cancelled
  -> cancel lane wait / wake dispatch scheduler
  -> release Session active slot
  -> trigger queue promotion check
```

dispatch record 已进入 `dispatching` 或 Attempt 已 `RUNNING`：

```text
cancel_run
  -> append CANCEL_REQUESTED
  -> append RUN_CANCELLING
  -> propagate cancel through WorkerProxy
  -> terminal / suspended / lost race follows existing rules
```

`CANCELLING -> RECOVERING`：

- If `CANCEL_REQUESTED` is durable accepted and no terminal fact has already won, recovery must not continue the user goal.
- A lost active Attempt after cancel should close toward `CANCELLED` or `LOST` by policy, not create a new normal execution Attempt.
- Terminal already committed still wins.

`cancel_session_runs` uses the same per-Run rules and applies them to every non-terminal Run in the target Session.

写回位置：`design.md` §9.1、§17 dispatch contract、§22 Cancel。

### B3. `close_session` 与既有非终态 Run 的关系

裁决：成立，P1。

最终设计方案：

`close_session` 只阻止新的 user input / run creation，不取消 close 前已 durable accepted 的工作。

Closed Session 中这些既有 Run 仍继续按状态机完成：

- `QUEUED`：active slot 释放后仍可 promotion。
- `WAITING`：`resolve_wait` 后仍可 resume。
- `RECOVERING`：recovery dispatch 仍可继续。
- `RUNNING` / `CANCELLING`：继续收口到 terminal。

如果调用方希望停止这些工作，必须显式调用 `cancel_run` 或 `cancel_session_runs`。

写回位置：`design.md` §5 Session 生命周期。

### B4. Replay No-Tool 主防线

裁决：成立，P1。

最终设计方案：

- 主防线在 RunInputBuilder：`replay_run` 创建的新 Run / Attempt 构造 `AgentRunRequest` 时不暴露 tool schemas。
- ToolRuntime 是 defense-in-depth：如果 replay Attempt 仍收到 tool call，必须按 replay policy 拒绝，记录 diagnostic / tool trace，不执行工具。
- Replay 不执行工具、不新增工具事实、不修正事实内容，只做 final answer 格式 / schema / envelope / 引用结构修复。

写回位置：

- `design.md` §21 Replay。
- `design.md` §23 RunInputBuilder。
- `dayu/README.md` `replay_run` / `replay(run)` 术语。

### B5. `resolve_wait` 幂等范围与 Resume Chain 原子性

裁决：成立，P1。

最终设计方案：

`resolve_wait` 是 Host 的等待结果接收与治理入口，不是等待机制本身。它接收的是 poll / callback / manual 已经拿到的结果，然后在 Host 内做状态校验、幂等校验、EventLog append、wait record 收口和 resume attempt 创建。

`resolve_wait` 不死等外部长事务。结果未到时，poll adapter / callback endpoint / manual operator 不应调用它，或调用后得到结构化拒绝，例如 `outcome_not_ready` / `invalid_state` / `wait_not_found`。`resolve_wait` 本身只允许因 SQLite transaction / CAS / busy timeout 做短等待和重试。

固定边界：

```text
wait record = Host durable 记录“现在在等什么”
poll / callback / manual = 发现结果到了
resolve_wait = 把已到结果纳入 Host 真源，并触发 resume
```

`resolve_wait(wait_id, outcome, source, idempotency_key)` 的 committed 幂等结果必须覆盖整条 resolution chain：

```text
wait record terminal state
RESUME_REQUESTED
tool terminal / result canonical fact
RUN_STARTED(start_reason=resume)
new Attempt row
ATTEMPT_STARTED
dispatch record
```

规则：

- 幂等判断只基于 committed durable state。
- 如果事务未 commit，重试应重新执行完整 resolution chain。
- 如果事务已 commit，同一 `(wait_id, idempotency_key)` + same outcome 返回既有 RunSnapshot / Attempt refs，不追加第二份 canonical facts。
- 同一 idempotency key + different outcome 返回 `idempotency_conflict`。

写回位置：`design.md` §20。

### B6. ToolBundle / Effective ToolBundle 的显式装配契约

裁决：部分成立，P1。

Review 中“必须进入每个 public run request”这一点不采纳。`ToolBundle` 包含 callable binding，不适合让 UI / Service 每次普通 `start_run` / `submit_followup` 都携带。用户已经明确倾向：外部组件收集 tools 后把 `ToolBundle` 传给 Host。

最终设计方案：

```text
ToolsDiscovery / external assembly
  -> business ToolBundle
  -> create_host(..., tool_bundle=business_tool_bundle, ...)
  -> Host stores tool_bundle_digest / schema_digest / source refs in Host runtime snapshot
  -> Attempt assembly freezes attempt-local tool refs
  -> ToolRuntime factory injects framework tools such as fetch_more
  -> effective ToolBundle
  -> RunInputBuilder projects tool_schemas from effective ToolBundle
  -> ToolRuntime executes callable binding from same effective ToolBundle
```

Rules：

- Host public construction / composition API must accept `ToolBundle` explicitly.
- Host packages do not import concrete business tool modules.
- Start / follow-up requests do not carry raw `ToolBundle` by default.
- If future multi-scene tool profiles are needed, Service may pass a typed `tool_profile_ref` or create separate Host handles; this is a phase design decision, not current default.
- Attempt snapshot must record enough refs / digests to explain which business bundle and effective bundle were used.
- Retry / resume reuse the source Run / Attempt accepted tool snapshot unless policy explicitly creates a new associated Run with a new snapshot.
- Replay uses no tool schemas regardless of bundle.

写回位置：

- `design.md` §3 `ToolsDiscovery`。
- `design.md` §11 Host handle / construction options if present.
- `design.md` §18.1 ToolBundle Input / Runtime Tool View。
- `dayu/README.md` `ToolBundle` / `effective ToolBundle` terms。

### B7. Dispatching Failure / Recovery Path

裁决：成立，P1。

最终设计方案：

```text
dispatch record = dispatching
  -> WorkerProxy call fails / rejects / startup timeout
  -> release lane token
  -> append diagnostic
  -> Attempt -> FAILED or LOST by failure type
  -> Run -> FAILED / RECOVERING / LOST by Host policy and recoverability
```

Recovery scan：

```text
dispatch record = dispatching
Attempt = STARTING
  -> require positive orphan proof before marking LOST
  -> Attempt -> LOST
  -> Run -> RECOVERING or LOST by recovery policy
```

写回位置：`design.md` §17。

### B8. Purge 与 Audit JSONL

裁决：成立，P1。

最终设计方案：

- `purge_session` does not delete append-only audit JSONL records already written.
- `purge_session` must write a purge tombstone audit record.
- Existing audit JSONL rows for the purged Session may reference EventLog rows that no longer exist.
- Audit query / analyze tooling must recognize purge tombstone and report that source EventLog facts were purged.
- Purge tombstone durable location must not be inside the purged Session EventLog. Storage phase must choose a tombstone table or equivalent durable area that supports lookup by `session_id`.

写回位置：`design.md` §5 and §15。

### B9. Memory Snapshot Lag Handling

裁决：成立，P1。

最终设计方案：

- Memory projection lag is not Run recovery.
- If memory snapshot cursor is behind but EventLog delta is within policy threshold, RunInputBuilder may rebuild the required stable layer from EventLog and record diagnostic / trace.
- If snapshot is missing, corrupt, or lag exceeds policy threshold, Host enters structured context governance / projection repair path, not crash recovery.
- Projection lag must not silently change messages for the same EventLog + policy input.
- Rebuilt snapshot checkpoint must not advance ahead of durable snapshot content.

写回位置：`design.md` §24。

## P2 / Phase Discussion Items

以下项成立，但不阻塞 design 写回后进入 phase map / phase discussion。它们应进入对应 phase 的 open items 或 tracking，而不是现在扩展成细节设计。

| ID | Item | 归属 |
| --- | --- | --- |
| C1 | `GUIDANCE_INSERTED` 是否进入 messages 需要显式 `affects_messages` / typed flag | EventLog / RunInputBuilder phase |
| C2 | Recovery scan 顺序：RECOVERING、WAITING adapter recovery、QUEUED promotion | Recovery phase |
| C3 | `payload_json` vs `payload_ref` event type-level rule | EventLog / Storage phase |
| C4 | HostPolicy typed views 的最小字段 / questions answered | Policy / Public API phase |
| C5 | Tool fact accept idempotency key stable tuple / fact_kind enum | ToolRuntime phase |
| C6 | Outbox online-to-offline seen cursor crash window | Projection / Outbox phase |
| C7 | Context compaction `start_reason=recovery` 诊断区分 | Context Governance phase |
| C8 | `purge_session` tombstone exact table / storage location | Storage phase |

## Rejected / Adjusted Findings

### R1. “ToolBundle 必须进入每个 run request”

不采纳原建议，采纳调整版。

原因：

- `ToolBundle` carries callables and runtime bindings; it is not a normal UI / Service per-request payload.
- Host construction / composition root is the right boundary for the base business `ToolBundle`.
- Attempt snapshot records digests / refs; public run requests should not carry raw callable bundles by default.

Adjusted requirement is B6.

### R2. “所有 P1 都可只留到 phase discussion”

不采纳。

原因：

- A2 awaiting owner is a core state-machine ownership conflict and must be written back before phase orchestration.
- B1 / B2 / B4 / B5 affect contract surfaces that later phase plans depend on.

## Required Write-Back Summary

Before re-review, write back:

- `docs/host/implementation-control.md`
  - Add phase map.
  - Assign P2 / residual items to phases.
- `docs/host/design.md`
  - Awaiting canonical owner.
  - proactive vs reactive context compaction.
  - cancel paths for RECOVERING, waiting-for-lane, dispatching.
  - close_session with existing non-terminal Runs.
  - replay no-tool primary defense.
  - resolve_wait committed idempotency chain.
  - ToolBundle construction / effective bundle snapshot semantics.
  - dispatching failure / recovery.
  - purge audit JSONL and tombstone.
  - memory snapshot lag behavior.
- `dayu/README.md`
  - Any term changed above, especially ToolAwaitingOutcome, replay, ToolBundle / effective ToolBundle, dispatching / lane cancel if wording changes.

## Final Verdict

`not ready / fail` for entering phase orchestration.

The design direction remains sound. The failure is localized to unresolved state-machine ownership and missing phase control structure. After the required write-back, run a focused re-review on `docs/host/design.md`, `docs/host/implementation-control.md`, and `dayu/README.md`.
