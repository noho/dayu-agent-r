# Host Design v2 Controller Adjudication

## 元信息

- 日期：2026-05-13
- Gate：draft design v2 review
- Review artifacts：
  - `docs/reviews/host-design-v2-review-mimo-20260513.md`
  - `docs/reviews/host-design-v2-review-ds-20260513.md`
  - `docs/reviews/host-design-v2-review-codex-20260513.md`
- 设计真源：
  - `docs/host/design.md`
  - `dayu/README.md`
- 流程状态参考：
  - `docs/host/implementation-control.md`

## 总体裁决

draft design v2 主架构方向成立，但本轮 review 未通过 phase-readiness gate。

Controller verdict：

- 不能直接进入 phase 编排。
- 必须先做一轮 design cleanup，至少写回 P0 findings。
- P0 写回后需要做针对性 re-review；re-review 通过后，才进入 phase 编排。

原因：

- AgentMiMo 与 AgentDS 均认为可进入 phase 编排，但 AgentCodex 提出的多进程 recovery blocker 成立。
- 该 blocker 不是 SQL schema、wire protocol 或实现细节问题，而是 Host lifecycle / recovery 的架构语义缺口。
- 当前设计同时要求“单机多客户端 / 多进程”和“Host startup recovery scan 标记不可确认 Attempt 为 LOST”。如果每个 Host 进程启动时都扫描全库，并把“当前进程不能确认控制”的 Attempt 标为 `LOST`，就可能误伤另一个仍存活进程控制的 active Attempt。

## 裁决分级

- **P0 / phase 编排前必须写回**：不写回会让 phase 编排建立在错误前提上，或让 phase agent 自行发明核心状态语义。
- **P1 / 对应 phase plan 前必须细化**：不阻塞总控 phase 编排，但进入对应 phase 的 discussion / implementation-ready plan 前必须写清。
- **P2 / phase-local**：属于正常 phase design / phase plan 细化，不需要污染架构级文档。
- **Rejected**：finding 不成立，或已被现有设计覆盖。

## P0 Findings

### P0-1. 多进程 recovery scan 不能仅因当前进程不可确认控制就标记其它 active Attempt 为 LOST

- 来源：AgentCodex C1，AgentDS H4。
- 裁决：接受，P0，phase 编排前必须写回 `docs/host/design.md`。
- 严重程度：严重。

当前问题：

- `docs/host/design.md` 支持单机多客户端 / 多进程。
- Recovery scan 写成 Host 启动时扫描 `RUNNING` / `CANCELLING` Run；如果 active Attempt 没有“当前 Host 可确认控制”的 dispatch record，则旧 Attempt 进入 `LOST`。
- 多进程下，进程 B 无法确认进程 A 控制的 dispatch channel，并不等于进程 A 的 Attempt 已丢失。

必须写回的设计语义：

- startup recovery scan 不得把“当前进程不可确认控制”当作 orphan proof。
- 多进程场景下，Host 只有在获得 positive orphan proof 后，才能通过 CAS 将 active Attempt 标为 `LOST`。
- positive orphan proof 第一版来自本机 Host 进程存活证据，而不是远端 lease。推荐最小机制：
  - dispatch record 记录 `owner_host_instance_id`。
  - Host 启动时登记 `host_instance` durable row，至少包含 `host_instance_id`、`pid`、`process_start_token` 或等价进程启动指纹、`heartbeat_at`、`status`。
  - orphan 判定必须同时证明 owner Host instance 已不可能继续治理该 Attempt，例如 pid 已不存在，或 pid 已复用但 process_start_token 不匹配，并且 heartbeat 已过期。
  - `heartbeat_at` 单独不构成 orphan proof；进程卡顿、调试暂停或长时间阻塞不能导致其它 Host 进程误杀 active Attempt。
  - `pid` 单独也不构成 orphan proof；pid 可能复用，必须配合 process_start_token / boot id / create time 等启动指纹。
  - 只有 positive orphan proof 成立后，才能 CAS `ATTEMPT_LOST` -> `RUN_RECOVERING` -> new Attempt。
  - 如果只能判断 owner heartbeat stale，但无法证明进程已死，Host 应记录 suspect / diagnostic，跳过 recovery，不得 append `ATTEMPT_LOST`。
- design.md 必须区分：
  - current-process dispatch reconciliation：当前进程对自己可确认控制的 dispatch record 做收口或继续观察。
  - global orphan recovery：只有具备可证明 orphan 条件时，才允许标记 `ATTEMPT_LOST` / `RUN_RECOVERING`。
- dispatch record / `host_instance_id` / heartbeat 仍不是重 lease 或 fencing token。它们不授予远端执行所有权，不允许旧 Attempt takeover，只用于证明原 Host owner 是否已经不可能继续治理该 Attempt。

通俗解释：

一个新启动的 Host 进程看不到另一个进程手里的执行连接，不代表那次执行已经死了。它只能说“我接管不了”，不能直接说“它丢了”。要把 Attempt 标成 `LOST`，必须有额外证据证明原执行确实 orphan。

### P0-2. `Run RUNNING` 与 Attempt `STARTING` / `RUNNING` 的时机语义需要锚定

- 来源：AgentMiMo H1。
- 裁决：接受，P0。

必须写回的设计语义：

- `Run RUNNING` 表示该 Run 已占用 Session active slot，并已有 active Attempt lifecycle，不要求 worker 已 accepted。
- Attempt `STARTING` 表示 Host 已 durable 创建 dispatch intent；Attempt `RUNNING` 表示 worker 已 accepted。
- `RECOVERING -> RUNNING` 应锚定到 Host 已创建新 Attempt / dispatch intent 的语义；worker rejected / startup timeout 再按 startup failure 路径收口。
- 不需要新增 Attempt 状态。现有 Attempt `STARTING` / `RUNNING` 足够表达执行环境生命周期。
- 推荐状态转换：

```text
start_run admitted
  -> append USER_INPUT_ACCEPTED
  -> append RUN_ACCEPTED
  -> append RUN_STARTED
  -> create Attempt(status=STARTING)
  -> append ATTEMPT_STARTED
  -> Run.status = RUNNING
  -> commit

after commit dispatch
  -> WorkerProxy dispatch
  -> worker accepted
  -> append ATTEMPT_RUNNING
  -> Attempt.status = RUNNING
```

- 允许并且预期存在以下组合：

```text
Run.status = RUNNING
Attempt.status = STARTING
```

- 该组合表示用户 Run 已进入 Host 治理执行态，但执行环境尚未确认接住。
- startup failure 路径：

```text
Attempt STARTING
  -> dispatch rejected / startup timeout
  -> append ATTEMPT_FAILED or ATTEMPT_LOST
  -> Attempt terminal
  -> Run -> FAILED / RECOVERING / LOST by policy
```

- recovery 路径同理：

```text
Run RECOVERING
  -> rebuild messages
  -> create new Attempt(status=STARTING)
  -> append RUN_STARTED
  -> append ATTEMPT_STARTED
  -> Run RUNNING
  -> dispatch after commit
  -> ATTEMPT_RUNNING when worker accepted
```

通俗解释：

Run 的 `RUNNING` 是“这个用户问题正在被 Host 治理执行”，不等于远端或本地 worker 已经真正开始跑。真正开始跑由 Attempt `RUNNING` 表达。

### P0-3. `RUN_CANCELLING` canonical event 语义必须和 cancel 状态迁移对齐

- 来源：AgentCodex H2。
- 裁决：接受，P0。

必须写回的设计语义：

- 若 `RUN_CANCELLING` 保留为 canonical event，则 active cancel 进入 `CANCELLING` 时必须 append `CANCEL_REQUESTED` + `RUN_CANCELLING`，并补齐 canonical event contract matrix。
- 若决定由 `CANCEL_REQUESTED` 直接承担状态副作用，则应删除或降级 `RUN_CANCELLING`，避免 EventLog replay 与 Run row state 双真源。
- 推荐采用第一种：`CANCEL_REQUESTED` 表达用户 / 上层取消意图，`RUN_CANCELLING` 表达 Run 状态迁移。
- 最终采用：保留 `RUN_CANCELLING`，并把它定义成独立 canonical state fact。
- active cancel 推荐路径：

```text
cancel_run on RUNNING active Attempt
  -> append CANCEL_REQUESTED
  -> append RUN_CANCELLING
  -> Run.status = CANCELLING
  -> commit
  -> after commit propagate cancel to Attempt
```

- 后续正常收口：

```text
Attempt accepted cancel
  -> append ATTEMPT_CANCELLED
  -> append RUN_CANCELLED
  -> Run.status = CANCELLED
```

- 后续超时 / 崩溃收口：

```text
cancel timeout / owner lost
  -> append ATTEMPT_LOST
  -> Run -> RECOVERING / LOST by policy
```

- 适用边界：
  - `QUEUED` cancel：直接 `CANCEL_REQUESTED` + `RUN_CANCELLED`，不需要 `RUN_CANCELLING`。
  - `WAITING` cancel：如果 Host 可以同步关闭 wait record，直接 `CANCEL_REQUESTED` + wait cancelled + `RUN_CANCELLED`，不需要 `RUN_CANCELLING`。
  - `RUNNING` / Attempt `STARTING` / 其它需要等待 Attempt 收口的场景：需要 `RUN_CANCELLING`。
  - terminal Run：拒绝 cancel，不追加 `RUN_CANCELLING`。
- 预期副作用：
  - EventLog 多一条 canonical event，但状态重放、audit、UI timeline 和 recovery 语义更清晰。
  - Host event stream 可以向 UI 暴露“正在取消”状态。
  - 同一 `(run_id, client_request_id)` cancel 重试必须返回既有结果，不重复 append `RUN_CANCELLING`。
  - Run 已是 `CANCELLING` 时，新的不同 cancel 请求不能重复制造状态迁移；可按 policy 返回当前状态或记录 diagnostic。

通俗解释：

取消请求和 Run 已进入取消中是两件事。EventLog 必须能重放出 Run 为什么处在 `CANCELLING`，不能只靠 Run 表里的当前状态。

### P0-4. `WAITING` steer 的 wait record 状态与 Run 回到 RUNNING 的 canonical sequence 必须硬化

- 来源：AgentMiMo H2，AgentCodex M1。
- 裁决：接受，P0。

必须写回的设计语义：

- wait record 状态集合目前没有 `abandoned`，design.md 不应使用未定义状态词。
- `WAITING` Run 被 steer 时，active wait record 应进入已有终态之一，推荐使用 `cancelled`，并通过 typed reason 区分 `steered` 与 user cancel。
- `WAITING -> RUNNING` 需要明确 canonical sequence。推荐：`STEER_REQUESTED`、wait record cancelled with reason `steered`、`RUN_STARTED`、`ATTEMPT_STARTED`。
- 迟到 wait result 只能进入 diagnostic / tool trace，不得进入 canonical EventLog。
- 该 finding 是文档澄清型修复，不需要新增 Run 状态、Attempt 状态或 wait record 状态。
- 最终采用：

```text
wait record status = cancelled
reason = steered
```

- `WAITING` steer canonical sequence：

```text
submit_followup(steer) on WAITING Run
  -> append STEER_REQUESTED
  -> mark active wait record cancelled(reason=steered)
  -> append RUN_STARTED
  -> create Attempt(status=STARTING)
  -> append ATTEMPT_STARTED
  -> Run.status = RUNNING
  -> commit
  -> dispatch after commit
```

- 旧 Attempt 保持：

```text
Attempt.status = SUSPENDED
```

- 旧 Attempt 不改写为 `STEERED`，因为它已经因 awaiting 正常 suspended。

通俗解释：

等待中的 Run 可以被用户改方向，但必须把原来的等待结果通道关掉，而且这个关闭动作要用已有状态表达，不能偷偷发明一个新状态。

### P0-5. HostCallContext 与操作级幂等键需要拆清

- 来源：AgentCodex H1，AgentMiMo H3 / M1。
- 裁决：接受，P0。

必须写回的设计语义：

- `HostCallContext` 应承载 actor / source / request_id / authorization 等责任链字段；不承载 delivery target / delivery hint。
- 操作级幂等键由具体 request 定义，不应强制所有 mutating operation 都使用 `HostCallContext.client_request_id`。
- `ensure_session` 的幂等范围仍是 `(scope, slot_key)`，不需要 `client_request_id`，但仍需要可记录 actor / source / request id 的 call context。
- `resolve_wait` 的幂等范围仍是 `(wait_id, idempotency_key)`。
- `start_run`、`submit_followup`、`cancel_run`、`create_session`、`retry_run`、`replay_run` 等客户端命令使用 `client_request_id`。
- `close_session` request shape 需要补齐，至少包含 operation id / reason，并服从上述 envelope 规则。
- `HostCallContext` 是 Host API 的调用上下文，通俗说是这次调用 Host 的“来路和责任信息”。它描述“谁、从哪里、以什么权限、要回到哪里”，但不描述“要做什么”。
- `HostCallContext` 不是业务请求本身，也不是统一幂等键。
- `HostCallContext` 典型字段：

```text
actor / principal       -> 谁发起或代表本次操作负责
source / client         -> 操作来自哪个入口，例如 CLI / Web / GUI / WeChat
request_id              -> 上层调用链路 trace id
authorization_claims?   -> 上层已验证的权限声明
```

- 具体 request 描述“要做什么”，并拥有自己的幂等字段或幂等范围。例如：

```text
ensure_session:
  context.actor = wechat_user_a
  context.source = wechat
  context.request_id = service_trace_abc
  request.scope = wechat
  request.slot_key = stable_user_key
  idempotency scope = (scope, slot_key)

start_run:
  context.actor = wechat_user_a
  context.source = wechat
  context.request_id = service_trace_abc
  request.session_id = ...
  request.input = ...
  request.client_request_id = wechat_msg_123
  idempotency scope = (session_id, client_request_id)
```

- `HostCallContext` 主要服务 audit、trace、authorization 和 source attribution；operation request 服务业务意图、状态机前置条件和幂等。
- delivery / channel 投递不属于 `HostCallContext`。Host 不从 call context 推断 UI / channel 收件人。

通俗解释：

“谁发起的请求”与“这个操作怎么防重”不是同一个字段。大多数客户端操作用 `client_request_id` 防重，但 `ensure_session` 和 `resolve_wait` 已经有自己的幂等键。

## P1 Findings

### P1-1. wait adapter recovery bootstrap

- 来源：AgentDS H1。
- 裁决：接受，P1，Tool Awaiting / Wait Adapter phase 前细化。
- 要点：wait record 需要足够 durable state，让 Host restart 后能恢复 poll / callback / manual adapter 观察；wait poller 只能作为 background trigger 调用 `resolve_wait` command path，不能直接写 EventLog / Run / Attempt。

### P1-2. ToolRuntime accept barrier 的 ack timeout / ack lost 幂等语义

- 来源：AgentDS H3。
- 裁决：接受，P1，ToolRuntime / RemoteProxy phase 前细化。
- 要点：Host 已 durable accept 但 ack 丢失时，ToolRuntime 应能用稳定 accept idempotency key 重试 accept，而不是直接把工具结果变成失败。accept key 可由 `execution_id`、tool call identity、result digest 等派生，具体格式在 phase design 定。

### P1-3. Memory projection freshness / atomic marker

- 来源：AgentDS H2。
- 裁决：接受，P1，Memory phase 前细化。
- 要点：如果 memory projection 不与 EventLog 在同一 SQLite transaction 内提交，需要定义等价 atomic commit marker；checkpoint 不能先于 snapshot durable。

### P1-4. proactive context compaction 迭代上限

- 来源：AgentDS M1。
- 裁决：接受，P1，Context Governance phase 前细化。
- 要点：compact 后仍超预算时必须有上限、降级策略和 `CONTEXT_COMPACTION_FAILED` 收口路径，不能无限 compact retry。

### P1-5. `replay(run)` 的无工具执行语义

- 来源：AgentDS M2。
- 裁决：接受，P1，Replay / ToolRuntime phase 前细化。
- 要点：replay 的外部语义是函数式 `replay(run)`，输入源 Run，输出关联的新 Run；不是 replay Attempt，也不是重开原 Attempt。
- replay 创建的新 Run 默认复用源 Run 已接受工具事实 / evidence anchors，但本次执行是一次 no-tool `run_agent_messages` / no-tool `AgentRunRequest.messages` 结构修复调用。
- replay 不允许新增工具事实，不允许重新执行工具，不允许通过 tool call 改变 evidence anchors。
- 如果 replay 执行期间模型仍发起 tool call，Host / ToolRuntime 必须按 replay policy 拒绝；默认治理动作应是 hard stop 或 governed tool error，并记录 diagnostic / tool trace。不得把该 tool call 当作普通工具执行。

### P1-6. Sink 幂等消费者契约

- 来源：AgentDS M3。
- 裁决：接受，P1，Observer / Sink phase 前细化。
- 要点：每个 Sink 必须是幂等消费者；重复消费同一 canonical `event_id` 不得产生重复副作用。

### P1-7. `close_session` 与 active Run / queue / recovery 的交互

- 来源：AgentDS M4，AgentMiMo H3。
- 裁决：接受，P1，Session / Public API phase 前细化。
- 要点：`close_session` 只关闭 Session 的新输入入口，不取消、不终止、不删除已有 Run。
- 推荐状态规则：

```text
Session OPEN
  -> close_session
  -> Session CLOSED
```

- `CLOSED` 后公共接口语义：

```text
start_run              reject invalid_state
submit_followup(queue) reject invalid_state
submit_followup(steer) reject invalid_state
ensure_session         returns current slot Session, snapshot marks CLOSED
create_session         allowed, especially UI / Service explicit new session
get_session/get_run    allowed
stream_run_events      allowed
cancel_run             allowed for existing Run
resolve_wait           allowed for existing WAITING Run
retry_run/replay_run   reject by default, unless explicit policy creates a new Session / Run elsewhere
```

- 已有 active Run 继续按 Host 状态机治理到终态：

```text
RUNNING / CANCELLING / RECOVERING
  -> continue governance to terminal
```

- `WAITING` Run 保持 `WAITING`；`resolve_wait` 与后续 resume 允许继续，final answer 仍可到达。
- close 不等于 cancel。若调用方希望停止已有工作，必须显式调用 `cancel_run`。
- close 前已 durable accepted 的 `QUEUED` Run 继续保留，并可在 active slot 释放后 promotion；close 后不得接受新的 queued Run。
- Run terminal 后仍按 frozen delivery target 投递 final answer；close 不改变已接受 Run 的 outbox delivery 语义。
- `ensure_session(scope, slot_key)` 可返回该 slot 当前 closed Session；如果 UI / Service 想继续聊天，应显式调用 `create_session(bind_slot=true, scope, slot_key)` 创建并重绑定新 Session。

### P1-8. delivery target 的 Session binding default

- 来源：AgentMiMo M4。
- 裁决：接受，P1，Session / Outbox phase 前细化。
- 架构边界写死：

```text
EventLog
  -> Host truth: terminal answer 已产生

Outbox
  -> Host 派生 durable item: 有 terminal result 可投递 / 可通知

Deliver to UI / external channel
  -> Service / UI / channel adapter 负责
```

- Host 不负责 deliver to UI。
- Host 不判断哪些客户端应该收到。
- Host 不记录“投递成功到 GUI / CLI / WeChat / Web”的业务完成状态。
- Host 只保证 terminal fact 进入 EventLog，并可由 Outbox projection 派生 outbox item。
- 多客户端 attach 同一个 Session 时，answer 是 Session / Run 事实，不是发起客户端私有消息。
- 在线 / 已 attach 客户端的阅读路径是 Host event stream / Session timeline / RunSnapshot / read model；断线后通过 cursor 或 snapshot 补读。
- Outbox 不是客户端阅读 final answer 的通用接口，也不是 UI read model。
- 这不依赖 delivery target，也不依赖客户端直接读 Outbox。
- Outbox 只服务主动推送、离线通知或外部渠道投递的上游工作项。
- Outbox 的准确产品语义是离线 / 外部投递路径的 durable terminal delivery queue。它解决的问题是：离线客户端不需要回放中间过程，也不能丢 final answer。
- 对离线客户端而言，preview / progress / reasoning / streaming content 等中间过程可以不补；terminal answer / terminal notification 必须可投递。
- Outbox contains durable terminal delivery intent, not full run timeline.
- 具体投递目标、投递成功状态、channel retry、WeChat / Web / notification binding 属于 Service / UI / channel adapter。
- Session 不持有唯一 default delivery target。
- `HostCallContext` 不包含 `delivery_target_hint`。
- Host Outbox 不表达 UI 客户端收件人，只表达 terminal result delivery intent / notification item；Service / UI 从 outbox item 和自身 channel binding 决定如何投递。
- 推荐读 / 投递路径：

```text
Host EventLog
  -> Host event stream / Session timeline / RunSnapshot
      -> UI read path: GUI / Web / CLI / attached clients read here

Host EventLog
  -> Outbox projection item
      -> Service / channel delivery path: WeChat / Web push / notification / offline delivery / retry
```

### P1-9. request policy 字段与 mode 字段最小语义

- 来源：AgentMiMo M2 / M3。
- 裁决：接受，P1，对应 Public API / Retry / Replay / Cancel phase 前细化。
- 要点：
  - `CancelRunRequest.mode` 第一版若只有 `graceful`，应明确唯一值或移除。
  - `RetryRunRequest.policy_overrides`、`ReplayRunRequest.reuse_policy` 需要最小枚举或明确 phase-local policy view。
- 最终口径：第一版公共 API 不暴露开放式 policy knobs。可以有 Host policy 默认值，但调用方不应传无结构 `policy_overrides` 大口袋。
- `CancelRunRequest.mode` 若保留，第一版唯一值是 `graceful`。它表示 Host 发出治理取消，请 active Attempt 自己收口；不强杀本地进程、不强杀远端 job、不强制取消外部 job。
- `RetryRunRequest.policy_overrides` 第一版建议不暴露。retry 是否复用 accepted tool facts、重试次数、退避等由 Host retry policy 决定；如必须暴露，只能暴露明确 typed 字段，例如 `reuse_accepted_tool_facts?: bool = true`，不能开放任意 override。
- `ReplayRunRequest.reuse_policy` 第一版建议删除。`replay(run)` 语义已经固定：复用源 Run accepted tool facts / evidence anchors，no tools，只做结构修复，不重新执行昂贵工具。
- phase plan 不得自行发明 `force`、`immediate`、`rerun_tools`、`reuse_all` 等未在 design 明确的 public API 行为。

### P1-10. Run / Session snapshot cursor 与 source relation 字段

- 来源：AgentMiMo L2，AgentDS L2。
- 裁决：接受，P1，Read Model / Public API phase 前细化。
- 要点：
  - `SessionSnapshot.timeline cursor` 应说明是否为全局 `event_sequence` cursor。
  - `RunSnapshot` 应包含可选 `source_run_id` / `source_run_relation`，用于 retry / replay 链。

## P2 Findings

### P2-1. Payload digest canonicalization algorithm

- 来源：AgentDS L1。
- 裁决：接受，P2，EventLog / payload phase 定。
- 要点：需要在实现阶段选定 deterministic serialization / canonicalization 算法。

### P2-2. Tool trace 冷热分离阈值

- 来源：AgentDS L3。
- 裁决：接受，P2，Tool Trace phase 定。
- 要点：热 JSON 与冷 JSONL 的字段边界和 size threshold 属于 phase-local policy。

### P2-3. policy view 类型补齐

- 来源：AgentMiMo L3。
- 裁决：接受，P2。
- 要点：补齐 `CancelPolicyView`、`SinkOutboxPolicyView` 或在 phase design 中明确合并视图。

## Residual Risks Tracking

### RR-1. SQLite 多进程写入竞争的实际表现

- 来源：AgentDS residual risk。
- 裁决：接受为低风险 validation item，不阻塞 design v2。
- 归属：Host Storage / Durable Store phase。
- 跟踪口径：
  - 当前架构依赖 SQLite WAL、busy timeout、显式重试、唯一约束和 CAS-style state transition 支撑单机多进程。
  - 作为买方财报分析 Agent，一次 Run 主要由 LLM 调用、工具读取、财报解析和外部 I/O 主导；SQLite 写入多为短事务。
  - 同一 Session 又受 admission 限制为最多一个 active Run，多客户端 attach 更多是读 / stream / 补读，不是持续高频写。
  - 因此不预设 SQLite 会成为核心瓶颈，不提前引入服务化 DB、消息队列、分库或重型写入架构。
  - Host storage phase 必须定义合理 busy timeout、短事务边界、显式重试、CAS 失败返回语义，并用多进程并发测试验证 correctness。
  - RR-1 的重点是防止 SQLite 写竞争破坏正确性；性能瓶颈只有在压测或生产观察证明明显后才升级为容量治理问题。
  - 后续统一写入 `docs/host/implementation-control.md` 追踪区。

### RR-2. Remote worker 孤儿执行

- 来源：AgentDS residual risk。
- 裁决：接受为已知 tradeoff，不阻塞 design v2。
- 归属：RemoteProxy / ToolRuntime / External Side Effect phase。
- 跟踪口径：
  - 第一版不保证 exactly-once 远程物理执行。
  - Host crash 或断连后，旧远端 worker 可能继续运行；Host 通过 `execution_id` 拒绝迟到事件污染 canonical EventLog。
  - 外部副作用不能依赖 Host attempt ownership 兜底，必须依赖工具级 idempotency key / tool policy / best-effort cancel。
  - Remote phase 测试必须覆盖：Host 已放弃旧 execution_id 后，远端迟到 tool result / terminal event 只能进入 diagnostic / trace，不能进入 canonical facts。
  - 该结论后续统一写入 `docs/host/implementation-control.md` 追踪区，作为 Remote phase 的明确 non-goal / validation item。

### RR-3. EventLog 无限增长的存储压力

- 来源：AgentDS residual risk。
- 裁决：接受为第一版需要提供 session-level destructive cleanup 的容量治理需求，不阻塞 design v2。
- 归属：EventLog Storage / Retention / Archive phase。
- 跟踪口径：
  - EventLog 是 append-only truth，canonical facts 不能因普通清理而丢失。
  - preview / diagnostic / projection_signal 可按 retention policy 降级、压缩或清理，但不得影响 recovery、resume、memory、audit 主链。
  - 第一版加入 `purge_session`，用于彻底清理一个已经结束、不会再恢复的 Session 的 Host 数据，释放本地空间。
  - `purge_session` 是 destructive purge API，不是 close、cancel、archive、memory forget 或 UI hide。
  - `purge_session` 前置条件：

```text
Session must be CLOSED
No active Run
No QUEUED Run
No WAITING / RECOVERING / CANCELLING Run
All Runs terminal
```

  - 不满足前置条件时返回 `invalid_state`。
  - `purge_session` 删除范围包括 Session / slot binding、Run、Attempt、该 Session 的 EventLog rows、payload descriptors / local payloads、memory snapshot、projection rows、outbox items、tool trace hot data 等由该 Session 独占的 Host 数据。
  - `purge_session` 必须保留 minimal tombstone / audit record：

```text
SESSION_PURGED
session_id
actor
reason
purged_at
counts / digest
```

  - purge 后不能 resume / retry / replay / 读取原 timeline / 恢复原 final answer；`get_session` / `get_run` 返回 `not_found` 或 purged tombstone snapshot，具体读语义在 phase design 定。
  - `archive_session` 作为 tracking item，不进第一版实现。archive 语义是把冷 Session 从 hot SQLite / hot projections 移到 archive storage，保留可审计 / 可查询 / 可按需恢复的只读档案；archive 不等于 purge，不删除事实。
  - 后续统一把 `archive_session` 写入 `docs/host/implementation-control.md` 追踪区。

### RR-4. 跨层测试复杂性

- 来源：AgentDS residual risk。
- 裁决：接受为测试策略风险，不阻塞 design v2。
- 归属：每个 phase plan 的 validation section，以及最终 integration phase。
- 跟踪口径：
  - Host 关键路径跨 durable transaction、dispatch、EngineEvent ingest、ToolRuntime accept barrier、projection / outbox 和 recovery。
  - phase plan 必须明确 fake / mock 边界，避免只靠端到端测试覆盖所有状态机。
  - 必须分层测试：state transition unit tests、SQLite transaction tests、multi-process tests、WorkerProxy fake integration、recovery crash simulation、projection replay tests。
  - integration phase 必须覆盖 crash、timeout、late event、idempotent retry、remote stale execution、cancel / suspend / terminal races。

## Rejected / Already Covered

### R1. 整体架构需要重做

- 来源：无 reviewer 明确要求，但需要裁决。
- 裁决：拒绝。
- 理由：三份 review 均认可 Host 作为治理真源、Engine 单次 request 执行、Remote 不拥有 Host 状态、EventLog canonical facts 驱动恢复、Projection / Sink / Outbox / Memory 不反向成为真源的主轴。

### R2. 需要在 draft design v2 阶段定义 SQL schema / wire protocol / dataclass / 完整测试矩阵

- 来源：review residual risks。
- 裁决：拒绝作为当前 gate blocker。
- 理由：这些属于 phase design / phase plan 内容。当前 blocker 是架构语义缺口，而不是实现细节缺失。

## 后续动作

必须先执行 design cleanup：

1. 更新 `docs/host/design.md`：
   - multi-process recovery authority / orphan proof 语义。
   - Run `RUNNING` 与 Attempt `STARTING` / `RUNNING` 时机。
   - `RUN_CANCELLING` canonical event contract。
   - `WAITING` steer canonical sequence 与 wait record 状态。
   - HostCallContext 与 operation idempotency key 拆分。
2. 同步 `dayu/README.md` 中相关术语：
   - HostCallContext / client operation id。
   - Run `RUNNING` 与 Attempt `STARTING` / `RUNNING`。
   - wait record cancelled reason if needed。
3. 更新 `docs/host/implementation-control.md`：
   - 当前状态改为 design v2 review 未通过，P0 design cleanup required。
   - P1 / P2 findings 可作为后续 phase tracking 项。
4. 做 targeted re-review：
   - 只 review P0 写回是否解决本裁决文档中的 blocker 与 P0 语义缺口。
   - re-review 通过后，才进入 phase 编排。

## 当前 Gate 状态

当前 gate 结果：未通过。

下一 gate：design cleanup for P0 findings。

禁止事项：

- 在 P0 写回和 re-review 通过前，不进入 phase 编排。
- 不把 P1 / P2 当作立即实现任务。
- 不修改 Engine 代码；如果后续 cleanup 发现必须触及 Engine，必须先停下来让用户确认。
