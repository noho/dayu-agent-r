# Host 设计讨论札记

## 文档状态

设计规范真源是 `docs/host/design.md`。本文只记录讨论来源、决议背景和设计脉络；若本文与 `design.md` 存在差异，以 `design.md` 为准，并应先修正 `design.md` 再进入计划或实施。

本文记录 Host 设计进入正式 Gateflow plan 前的需求与架构讨论。它不是正式设计文档，也不是实施计划；当前只记录讨论起点、设计目标和需要展开的问题空间。

## 当前目标

第一个 PR 只提交 Host 设计，不实现 Host 代码。

设计目标固定为：遵循“宿主强约束下的 LLM in the loop”范式，做生产级买方财报分析 Agent。

实现目标固定为：Host 作为治理真源，支持单机多客户端 / 多进程并发，并支持本地 Engine 与远程 Engine 作为并列执行环境。

## 当前需求

- 支持单机多客户端 / 多进程。
- 支持本地或远程执行环境；远程机器可以跑完整 `EngineWorker -> Engine`，但不能拥有 Host 治理真源。
- 取消治理需要支持 watchdog 或等价机制、取消超时后的升级路径、结构化取消终态，以及 Runner / SSE / 工具等待 / 后台 job 等资源在取消路径中的可观测与收口。

## 已吸收的需求主题

- 取消治理：Host 是取消真源；Engine 只观察 run-local cancellation token；取消不是普通 error，也不是工具失败。
- 等待协作：Engine 可以产出 `ToolAwaitingOutcome -> tool_awaiting -> run_suspended`，Host 负责 wait record、resume 输入、取消 / 超时 / 丢失治理。
- 工具结果截断与续读：Host / ToolRuntime 需要内置 TruncationManager，按工具声明的 `ToolTruncateSpec` 截断结果，并通过普通内置 tool `fetch_more` 支持续读。
- Run-time guidance：Host 需要支持在当前 run 内，于工具结果被接受后插入 Host-governed guidance，引导模型继续执行或修正上下文使用方式。
- Follow-up / Steer：Host 需要支持 run 运行中接收用户后续输入；输入可以排队为后续 run，也可以 steer 当前 run。
- 多轮会话记忆：记忆系统从财报 Agent 的会话不变量出发，包含 pinned state、单总池、recent raw turns 保底、context compaction 与 memory 克制原则。
- Context governance：Host 负责 provider-aware context budget、RunInputBuilder 各层输入预算、compact 触发、质量检查、失败收口、retry policy、trace / audit projection。
- EventLog projection：EventLog 需要 Observer / Sink 机制，让 audit、usage、tool trace、stream fanout、memory projection 等能力从同一事实源派生。
- Outbox delivery：final answer 等对外投递与 Host 正常治理链路隔离，避免 UI / 外部渠道投递失败影响 Run terminal。
- 长期 memory governance：长期记忆、跨 session / project / user scope、public edit / reset / forget、audit / privacy / permission / UI 可见性不阻塞第一版，但设计不能封死。
- 弱信号证据链：长期 summary 不能替代 evidence anchor；Host 保持业务中立，业务层负责原始证据、signal 抽取和 retrieval；Host 提供中立 evidence / provenance / trace 骨架。

## 远程执行拓扑

远程执行采用同一 WorkerProxy 抽象：

```text
Host -> LocalProxy -> EngineWorker -> Engine
Host -> RemoteProxy -> RemoteStub -> EngineWorker -> Engine
```

其中 `RemoteStub -> EngineWorker -> Engine` 可以运行在远程机器。远程执行环境只负责执行和回传事件 / 结果；
Session / Run / Attempt / EventLog 的治理真源仍在本地 Host。

## 执行路径与治理路径

无治理的执行路径是：

```text
Host -> Proxy / Stub -> EngineWorker -> Engine
```

该路径只表达“把一次执行请求送到某个执行环境，并拿回 Engine 事件 / 结果”。治理不应下沉到
EngineWorker 或 Engine 内部，而应由本地 Host 在执行路径外层包裹：

```text
Host API
  -> Session / Run admission
  -> durable transaction: create Run / Attempt / initial EventLog fact
  -> Attempt execution context: attempt_id + execution_id + cancellation source
  -> WorkerProxy / RemoteStub
  -> EngineWorker -> Engine
  -> EngineEvent stream
  -> Host event ingest: validate run_id / attempt_id / execution_id
  -> durable EventLog append
  -> terminal transaction: append terminal event + close Attempt + update Run
  -> Host event stream / projection / result read model
```

核心边界：Proxy / Stub 只做传输与执行环境适配；EngineWorker 只承载 Engine 执行；本地 Host 才能做
admission、EventLog append、Attempt close、Run 状态迁移、取消收口和恢复调和。

## Host 公共接口讨论入口

Host 公共接口采用函数式风格，但不应依赖全局隐式单例。公共函数接收明确的 Host handle / context 与 request，
返回稳定 snapshot 或 Host event stream。

第一版最小接口集合：

```text
ensure_session(host, request) -> SessionSnapshot
create_session(host, request) -> SessionSnapshot
get_session(host, session_id) -> SessionSnapshot
close_session(host, session_id, request) -> SessionSnapshot

start_run(host, request) -> RunSnapshot
get_run(host, run_id) -> RunSnapshot
stream_run_events(host, run_id, cursor) -> HostEventStream
cancel_run(host, run_id, request) -> RunSnapshot
submit_followup(host, session_id, request) -> FollowupSnapshot
retry_run(host, run_id, request) -> RunSnapshot
replay_run(host, run_id, request) -> RunSnapshot
resolve_wait(host, wait_id, request) -> RunSnapshot
```

`clear_session` 不进入第一版普通公共接口。EventLog 是不可篡改事实源，clear 容易被误解成删除历史或重写事实。
如果后续需要清理、遗忘或重置，应分别设计 close / new session / memory forget / purge 等具有明确审计语义的接口。

### Session Slot

Session slot 用于支持外部入口复用同一个当前会话。取得当前会话与显式新建会话拆成两个接口，避免把两种意图塞进 `create_policy`：

```text
EnsureSessionRequest:
  scope
  slot_key
  metadata

CreateSessionRequest:
  client_request_id
  bind_slot?
  scope?
  slot_key?
  metadata
```

语义：

- `(scope, slot_key)` 唯一映射到一个当前 session。
- `ensure_session(scope, slot_key)` 返回该 slot 当前 session；如果不存在，则原子创建并绑定一个。
- `ensure_session` 的幂等键是 `(scope, slot_key)`；它不需要 `client_request_id`。
- `create_session(client_request_id)` 明确创建新 session；同一 `client_request_id` 重试返回同一个新 session，不能重复创建。
- `create_session(..., bind_slot=true, scope, slot_key)` 创建新 session 后原子重绑定该 slot；旧 session 不删除，不改写 EventLog。
- 不同 `client_request_id` 调用 `create_session(..., bind_slot=true, scope, slot_key)` 表示不同的新建动作，允许创建更新的 session 并重绑定 slot。
- `scope` 是入口或身份命名空间，`slot_key` 是该命名空间下的会话槽位。

示例语义：

- WeChat 同一个稳定身份登录时，上层调用 `ensure_session(scope="wechat", slot_key=<stable_user_key>)`，重复调用拿到同一个 session。
- CLI 使用 `--label` 时，上层把 label 作为 `slot_key`；同一个 label 默认调用 `ensure_session` 复用同一个 session。
- UI 明确“新建 session”时，上层调用 `create_session(client_request_id=<click_id>, bind_slot=true, scope, slot_key)`，Host 创建新 session 并重绑定该 slot。

Host 不自动猜测不同 `scope` 是否应该合并，也不把 session slot 当成权限模型。权限、认证和外部身份解析属于上层；
Host 只保证 `ensure_session` 的 slot 幂等与 `create_session` 的新建动作幂等。

### Run 幂等与 Attach

`start_run` 需要支持客户端重试幂等：

```text
StartRunRequest:
  session_id
  client_request_id
  input
  execution_target
  queue_policy
```

其它 Run 接口请求：

```text
CancelRunRequest:
  client_request_id
  reason
  mode: graceful

SubmitFollowupRequest:
  session_id
  client_request_id
  input
  behavior: queue | steer

RetryRunRequest:
  client_request_id
  reason
  policy_overrides?

ReplayRunRequest:
  client_request_id
  reason
  repair_instruction?
  reuse_policy

ResolveWaitRequest:
  idempotency_key
  outcome
  source: poll | callback | manual
  observed_at
```

语义：

- `(session_id, client_request_id)` 唯一映射到一个 run。
- 客户端因网络失败重发同一 `start_run` 时，Host 返回同一个 run，不创建第二个 run。
- 多个 UI 入口通过 `get_run` 与 `stream_run_events` attach 同一个 run；attach 不触发新执行。
- 同一 session 的 active run admission 由 Host 统一治理；`queue_policy` 决定遇到 active run 时 reject、enqueue 或返回当前 active run。
- `get_run` 只读取 RunSnapshot，不触发执行或状态迁移。
- `stream_run_events` 从 EventLog `event_sequence` cursor 补读，不依赖内存订阅。
- `cancel_run` 按 `(run_id, client_request_id)` 幂等，queued Run 直接 `CANCELLED`，active Run 进入 `CANCELLING`。
- `submit_followup(queue)` 创建后续 queued Run；`submit_followup(steer)` 作用于当前 active Run 并切换 Attempt。
- `retry_run` 与 `replay_run` 都是在同一 Run 下创建新 Attempt；区别是 retry 面向失败恢复，replay 面向输出重生成并默认复用已接受工具事实。
- `resolve_wait` 是 poll / callback / manual 等 wait adapter 的统一入口，不能让 adapter 各自改 Run 状态。

## 核心对象与生命周期不变量

Host 治理核心只保留四个一等对象：

```text
Session
Run
Attempt
EventLog
```

其它能力，例如 durable queue、wait record、memory snapshot、tool trace、audit、usage、outbox、projection checkpoint，
可以是表、投影或内部机制，但不提升为同级治理真源。

对象边界：

- `Session`：一条可持续会话上下文，包含多个 Run。
- `Run`：用户可见的一次 Agent 执行目标 / 问题 / follow-up，属于一个 Session。
- `Attempt`：Host 为完成某个 Run 派发给本地或远程 EngineWorker 的一次执行，属于一个 Run。
- `EventLog`：append-only canonical facts 真源，用于恢复、Host event stream、memory、audit、usage、tool trace 等派生能力。

关键分界：

- Run 是用户可见生命周期；Attempt 是执行生命周期。
- retry、resume、steer、replay 都不复用旧 Attempt；它们在同一个 Run 下创建新 Attempt。
- UI / Service 主要观察 Run；WorkerProxy / RemoteStub / execution_id 主要绑定 Attempt。
- 远端执行环境只回传 Attempt 事件，不拥有 Run 状态，不关闭 Attempt，不更新 EventLog。

Stream 术语约束：

- `EngineEvent stream` 是 EngineWorker 执行 Engine 时产出的事件流，只是 Host ingest 的输入来源之一。
- `Host event stream` 是 Host 对 UI / CLI / Web / GUI 暴露的订阅与补读事件流，只能从 EventLog `event_sequence` cursor 派生。
- `preview event` / `preview delta` 只服务 UI 流式体验，不能成为恢复、投递、RunResult、memory 或 audit 的事实来源。
- `stream fanout` 是把已提交 Host events 分发给多个客户端的 projection / sink；慢客户端通过 `event_sequence` cursor 补读，不能反压 EventLog append。

### Run 状态

第一版 Run 状态集合：

```text
QUEUED
RUNNING
WAITING
CANCELLING
RECOVERING
SUCCEEDED
FAILED
CANCELLED
LOST
```

Run 终态：

```text
SUCCEEDED
FAILED
CANCELLED
LOST
```

语义：

- `QUEUED`：Run 已被 Host durable accepted，但尚未创建 active Attempt。
- `RUNNING`：Run 当前有 active Attempt 正在执行。
- `WAITING`：当前 Attempt 已因外部等待条件收口为 `SUSPENDED`，Run 等待 Host 后续 resume。
- `CANCELLING`：Host 已接受取消请求，正在等待 active Attempt 收口或超时升级。
- `RECOVERING`：Host 已确认旧 Attempt 丢失，但用户请求和已提交事实仍可恢复；Host 正在或等待创建新 Attempt 继续同一 Run。
- `SUCCEEDED`：Run 产出已确认 final answer。
- `FAILED`：Run 已确认不可恢复执行失败。
- `CANCELLED`：Run 已按用户或上层取消请求收口。
- `LOST`：Host 无法恢复该 Run 的用户请求或必要事实，或 policy 明确放弃继续。

`LOST` 不是 `FAILED`。`FAILED` 表示已确认失败；`LOST` 表示治理无法恢复，不能伪装成普通失败。Host crash
导致旧 Attempt 丢失时，优先进入 `RECOVERING` 而不是直接让 Run 终态 `LOST`。

### Attempt 状态

第一版 Attempt 状态集合：

```text
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

Attempt 终态：

```text
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

语义：

- `STARTING`：Host 已创建 Attempt，并准备派发到 LocalProxy / RemoteProxy。
- `RUNNING`：EngineWorker 已开始执行，Host 正在接收事件。
- `SUCCEEDED`：Attempt 产出 final answer，Run 可进入 `SUCCEEDED`。
- `FAILED`：Attempt 以确认失败收口，Run 可进入 `FAILED`，或由 Host policy 创建 retry Attempt。
- `CANCELLED`：Attempt 响应 Run cancel 请求收口。
- `SUSPENDED`：Attempt 因工具等待或外部条件挂起，Run 进入 `WAITING`。
- `STEERED`：Attempt 被 steer 打断，Run 保持 active，并由 Host 创建新 Attempt。
- `LOST`：Attempt 的执行结果无法确认。

`WAITING` 是 Run 状态，`SUSPENDED` 是 Attempt 状态：

```text
Attempt SUSPENDED -> Run WAITING
wait resolved -> Host creates new Attempt -> Run RUNNING
```

旧 Attempt 不 resume。resume 永远是 Host 基于 canonical EventLog facts 创建新 Attempt。

`CANCELLING` 是 Run 状态，不是 Attempt 终态：

```text
Run RUNNING -> CANCELLING
Attempt RUNNING -> CANCELLED / LOST
Run -> CANCELLED / RECOVERING / LOST
```

如果 Attempt 因 Host crash、worker 断连或取消超时而 `LOST`，但用户输入和必要 canonical facts 已持久化，
Run 应优先进入 `RECOVERING`，由 Host 创建新 Attempt 继续；只有不可恢复或 policy 放弃继续时才进入 Run `LOST`。

### Admission 不变量

同一个 Session 同时最多一个 active Run。

active Run 状态：

```text
RUNNING
WAITING
CANCELLING
RECOVERING
```

`QUEUED` Run 是 durable accepted run，不占 active slot，但必须持久化。queued run 不是内存队列项；它应有稳定
`run_id`、`session_id`、`client_request_id`、输入 canonical fact 与 `Run.status=QUEUED`。

durable queue 语义：

- 如果同一 Session 没有 active Run，Host 可以把最早可执行的 `QUEUED` Run 迁移为 `RUNNING`，并创建 Attempt。
- Host 崩溃恢复后，`QUEUED` Run 保持 `QUEUED`，调度器恢复后继续按 durable 顺序启动，不得丢弃。
- `RUNNING` / `CANCELLING` 的 active Attempt 在崩溃恢复时不能假装成功；旧 Attempt 进入 `LOST`。
- 如果 Run 的用户输入和必要 canonical facts 已 durable accepted，Run 进入 `RECOVERING`，随后由 Host policy 或用户动作创建新 Attempt 继续。
- 用户可见语义是 prompt 已提交并会继续处理；Run / Attempt 是 Host 内部治理对象，不应成为用户心智负担。
- `WAITING` Run 在崩溃恢复后继续 `WAITING`，等待条件由 durable facts 表达。

用户输入持久化顺序：

```text
append USER_INPUT_ACCEPTED
append RUN_ACCEPTED / RUN_STARTED or RUN_QUEUED
create Attempt when admitted
commit
dispatch EngineWorker
```

Host 不允许先 dispatch EngineWorker 再补写用户输入事实。否则崩溃窗口会导致用户 prompt 真正丢失。

多进程持久化方向：

- 第一版明确不引入重 lease / fencing 系统。
- 多进程一致性依赖 SQLite durable store、事务、唯一约束、CAS-style state transition、event id / sequence 去重。
- `execution_id` 只用于拒绝迟到 Attempt 事件，不是远端 lease，也不表示远端拥有治理状态。
- 不做旧 Attempt takeover；不做远端 worker 自治恢复；新执行必须创建新 Attempt 和新 `execution_id`。
- `lane` 是层中立 named semaphore，归 `dayu.runtime`，可服务非真源资源的容量控制，但不能替代 Host admission、SQLite 事务或 CAS。
- `filelock` 是 `dayu.runtime` 对 `from filelock import FileLock` 的统一封装，用于多进程访问普通文件时的互斥保护；业务层和 Host phase 实施不得各自手写文件锁或散落直接依赖。

新输入 admission：

- `queue`：当前 Session 有 active Run 时，输入进入 durable queue，成为后续 Run。
- `reject`：当前 Session 有 active Run 时，拒绝创建新 Run，并返回 active run conflict。
- `attach_active`：当前 Session 有 active Run 时，返回 active Run，不触发新执行。
- `steer`：必须命中 active Run precondition；它在同一 Run 内切换 Attempt，不创建新 Run。

幂等不变量：

- `ensure_session` 由 `(scope, slot_key)` 幂等映射到当前 Session。
- `create_session` 由 `client_request_id` 幂等映射到一次明确的新建 Session 动作；绑定 slot 时，同一 `client_request_id` 重试不能重复创建或重复重绑定。
- `start_run` 由 `(session_id, client_request_id)` 幂等映射到同一个 Run。
- queued follow-up / queued run 也必须按 `(session_id, client_request_id)` 幂等，客户端重发不能创建重复队列项。

### Follow-up 与 Steer

运行中的 session 可能收到新的用户输入。Host 需要支持两种行为：

```text
SubmitFollowupRequest:
  session_id
  client_request_id
  input
  behavior: queue | steer
```

`queue` 语义：

- 当前 session 有 active run 时，follow-up 输入排队为后续 run 的输入，不打断当前 active run。
- 当前 session 没有 active run 时，follow-up 可按普通 `start_run` 语义创建新 run。
- 排队输入也需要 `(session_id, client_request_id)` 幂等，避免客户端重发创建重复 queued item / run。

`steer` 语义：

- steer 不是另起一个并列新 run；它是对当前 active run 的控制输入。
- 对调用方可见的语义是：把用户输入追加到当前 active run，用于重定向正在进行的工作，而不是启动新的 run。
- Host 对当前 active attempt 发起受治理的停止请求，并记录 steer input canonical fact。
- 当前 attempt 收口后，Host 为同一个 run 创建新 attempt 和新 `execution_id`。
- Host 基于 EventLog canonical facts 重建完整 `AgentRunRequest.messages`，其中包含已接受的工具事实、已确认输出边界和 steer 输入。
- Engine 仍只看到一次新的 `AgentRunRequest`；它不理解 steer 策略，也不恢复旧 Agent / Runner。

讨论中的 steer 路径：

```text
user submits follow-up with behavior=steer
  -> Host appends steer requested fact
  -> Host requests current attempt stop through cancellation source
  -> current attempt emits run_cancelled or equivalent terminal event
  -> Host closes current Attempt as STEERED / CANCELLED_BY_STEER
  -> Host creates new Attempt for the same Run with new execution_id
  -> Host rebuilds complete messages from canonical EventLog facts + steer input
  -> Host dispatches through LocalProxy / RemoteProxy
```

边界约束：

- steer 不破坏同一 session active run admission；它在同一个 active run 内切换 attempt。
- steer 必须带 active run precondition；如果没有 active run、目标 run 不匹配、或当前 run 已经进入不可 steer 状态，Host 应拒绝 steer，而不是隐式创建新 run。
- steer 不撤回已经提交的 EventLog facts；已接受 tool result、usage、trace 和 preview 边界仍按事实保留。
- 如果当前 attempt 已接近终态，Host 需要定义 steer 与 terminal event 的竞态规则；终态已提交后，steer 应降级为 queued follow-up 或新 run。
- steer 输入不是 verified fact；它是用户意图 / 约束 / 修正，应由 RunInputBuilder 放入下一次 attempt 的 messages。
- queue 与 steer 的选择来自上层 UI / Service，不由 Engine 判断。

## EventLog Observer / Sink 讨论入口

EventLog 是 Host 的 append-only 事实源，但它不能被设计成业务逻辑总线。更合适的边界是：Host 在同一个持久化事务内完成
canonical event append 以及必要的 Run / Attempt 状态更新；Observer / Sink 只消费已提交事件，派生可重建的 read model
或外部投递。

基本路径：

```text
Host event ingest
  -> validate run_id / attempt_id / execution_id / sequence
  -> durable transaction:
       append canonical EventLog fact
       update required Host state indexes
       record projection wakeup / outbox marker when needed
  -> committed event notification
  -> Observer / Sink dispatch
  -> sink-specific checkpoint / retry / replay
```

Observer / Sink 的第一批目标包括：

- audit projection：记录谁在什么时候请求、取消、恢复、审批或触发了哪些治理动作。
- usage projection：从模型、工具、provider 与上下文构造事件中统计 token、耗时、重试、成本和资源占用。
- tool trace projection：记录工具调用、参数摘要、结果摘要、截断、等待、取消、超时、失败与证据纳入路径。
- stream fanout：让多个 UI 入口 attach / subscribe 同一个 run，而不是各自触发执行。
- memory projection：从 canonical facts 构造 session memory snapshot；snapshot 可重建，不能反向成为事实源。
- outbox delivery：把 final answer、terminal summary 或需要通知 UI / 外部入口的结果投递出去，投递状态与 Run terminal 解耦。

tool trace 需要明确冷热数据分离：

- 热数据使用结构化 JSON projection，保存近期可查询、可展示、可关联的 tool trace summary，例如 tool_call_id、tool name、normalized args digest、result digest、evidence anchors、truncate info、await info、policy decision、error code、duration、attempt refs。
- 冷数据使用 append-only JSONL，保存归档、批处理、离线审计所需的 trace detail，例如长参数摘要、长结果摘要、provider / tool raw diagnostic refs、截断诊断、重复治理上下文、等待 / 取消 / 超时细节。
- JSON 与 JSONL 都必须携带 `event_id` / `event_sequence`、`session_id`、`run_id`、`attempt_id`、`execution_id` 和必要 digest / ref，保证能从 EventLog 对齐。
- EventLog 只记录 canonical fact、ref 与 digest；tool trace JSON / JSONL 都不能反向成为恢复、resume、memory 或 Run 状态迁移真源。

边界约束：

- 是否挂载 Observer / Sink 不能改变 EventLog 的行为：同一输入在同一 Host 状态下，append 成功条件、事件顺序、状态迁移、恢复语义和对调用方可见的结果都必须一致。
- Observer / Sink 不拥有 Session / Run / Attempt 状态，不 append canonical EventLog，不关闭 attempt，不更新 Run 终态。
- Sink 失败不能回滚已经提交的 EventLog。需要可靠性的 sink 必须用 checkpoint / replay / retry 保证最终追平。
- Sink 必须按 `event_id` 或等价序列幂等消费；重复通知、进程重启、远端事件重放不能产生重复投影。
- Run / Attempt 状态索引、terminal result 等强一致状态不应依赖异步 sink 才成立；它们属于 Host append 事务或等价的强一致更新。
- preview / reasoning / display-only event 可以被 Host event stream sink 使用，但不能进入 canonical projection，也不能成为 memory / audit 的事实来源。

性能边界：

- Host 主链路只做最小同步工作：事件校验、EventLog append、必要状态索引更新，以及可选的轻量 projection wakeup / outbox marker。
- audit、usage、tool trace 等 sink 必须异步消费已提交 EventLog；sink 慢、失败或重放只能表现为 projection lag，不能拖慢 Host append、run admission、cancel、resume 或 terminal 收口。
- 第一版不需要引入重型消息系统；SQLite EventLog 加 projection checkpoint 表，再配合本地后台 worker / 任务循环，应足以表达可靠追平语义。
- 多 UI Host event stream 的 fanout 也应避免让慢客户端反压 EventLog append；慢客户端通过 `event_sequence` cursor 从 EventLog 补读。

Outbox 边界：

- Run terminal fact 提交后，final answer 已成为 Host 真源中的结果；投递给 UI、Web、WeChat、CLI 或其它外部入口属于 outbox delivery。
- Outbox 可以由 EventLog canonical terminal fact 派生，也可以在同一事务内记录轻量 outbox marker；无论哪种，投递失败都不能回滚 Run terminal。
- Outbox 必须具备幂等投递键、投递状态、重试次数、last error 和 delivery target；重复投递不能让用户收到不一致的 answer。
- Outbox 只负责外部投递，不参与 resume、memory 事实重建或 Run 状态迁移。
- 如果 outbox 长期失败，表现为 delivery lag / delivery failed，不改变 Run 的 `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST` 终态。

Payload 存储原则：

- EventLog 不做大对象仓库，但也不把每个 payload 强制拆成独立表。
- canonical 小 payload 内联在 EventLog 中，确保状态恢复、resume、memory projection 和 audit 不依赖额外 join 才能理解事实。
- 大工具结果、财报 chunk、binary、长网页正文、provider raw response、完整 prompt / messages、trace 明细等大内容应外移到 artifact / blob / tool trace / 领域仓储，并由 EventLog 记录引用、摘要或 digest。
- 外移 payload 不能成为判断 Run / Attempt 状态迁移的唯一信息；如果缺失或损坏，只能影响展示、深度审计或 trace 细节，不能破坏状态恢复。
- 对财报证据，原文和大正文归业务工具与财报领域仓储管理；EventLog 记录 evidence anchor / ref / digest，而不是复制整份材料。
- 该原则也是跨多年弱信号证据保全与业务归因召回链的基础：Host 保留可审计 anchor / ref / digest，长期原文和大证据由领域仓储保全，后续分析通过 query-time retrieval 召回，而不是无限扩大 session memory。

建议的事件形态：

```text
event_log
  event_id
  event_sequence
  session_id
  run_id
  attempt_id?
  execution_id?
  event_type
  occurred_at
  payload_json
  payload_ref?
  payload_digest?
```

`event_sequence` 是 Host durable store 分配的全局单调序列，作为 Host event stream cursor、projection checkpoint、outbox、audit replay 和 recovery scan 的主 cursor；远端 ordering hint 不能替代 Host canonical sequence。

### Canonical EventLog 最小分类

Canonical facts 的判定标准：它是否参与状态恢复、resume 输入重建、memory projection、audit 责任链或治理决策。
不满足这些条件的内容应作为 preview、projection、trace 或外部 blob。

第一版 canonical facts 至少包括：

```text
SESSION_CREATED
SESSION_CLOSED

RUN_ACCEPTED
RUN_QUEUED
RUN_STARTED
RUN_WAITING
RUN_CANCELLING
RUN_RECOVERING
RUN_SUCCEEDED
RUN_FAILED
RUN_CANCELLED
RUN_LOST

ATTEMPT_STARTED
ATTEMPT_SUCCEEDED
ATTEMPT_FAILED
ATTEMPT_CANCELLED
ATTEMPT_SUSPENDED
ATTEMPT_STEERED
ATTEMPT_LOST

USER_INPUT_ACCEPTED
FOLLOWUP_QUEUED
STEER_REQUESTED
CANCEL_REQUESTED
RESUME_REQUESTED
RETRY_REQUESTED
REPLAY_REQUESTED

TOOL_CALL_REQUESTED
TOOL_CALL_GOVERNED
TOOL_RESULT_ACCEPTED
TOOL_AWAITING
TOOL_TERMINAL_RESULT
GUIDANCE_INSERTED
```

参与恢复 / resume / memory 的事实：

- session / run / attempt 生命周期事实。
- user input、follow-up、steer、cancel、resume 请求事实。
- accepted tool result、tool awaiting、tool terminal result。
- final answer、run failed、run cancelled、run suspended 等终态事实。
- guidance inserted，如果它影响后续 `AgentRunRequest.messages`。
- evidence anchor / ref / digest，以及 memory projection 需要消费的用户输入、assistant final answer、工具事实和验证状态。

不参与恢复的内容：

- content delta、reasoning delta、UI preview。
- stream fanout 状态。
- usage 统计投影。
- tool trace 展示明细。
- audit read model 本身。

audit 原则：

- audit 不是事实真源；audit sink 消费 canonical EventLog 生成 audit projection。
- canonical event 需要携带足够 audit 可追溯字段，例如 actor / principal、source / client、request id、session / run / attempt id、policy decision、reason、payload ref / digest。
- audit 重点记录治理动作和责任链：session / run 创建、cancel、steer、resume、工具调用、外部材料访问、policy 允许 / 拒绝 / 截断 / 等待、语义级重复工具调用治理、evidence 纳入、外部副作用 idempotency key。
- audit projection 可以为了查询而重组，但不能反向成为恢复、resume 或 memory 的真源。

## ToolRuntime TruncationManager 讨论入口

Host / ToolRuntime 需要内置 TruncationManager。它的动机成立：财报工具结果可能很大，Engine 不应理解工具语义或上下文预算细节；
截断、cursor、续读、审计和 trace 都属于 Host / ToolRuntime 的工具治理边界。

ToolRuntime 边界：

```text
Host
  -> builds ToolRuntime
  -> ToolRuntime implements ToolExecutor
  -> ToolRuntime wraps tool registry / dispatcher / policies
  -> optional TruncationManager
  -> optional built-in fetch_more tool
  -> EngineWorker receives ToolRuntime as ToolExecutor
  -> Engine calls ToolExecutor.execute(...)
```

核心语义：

- Host 持有 ToolRuntime 的治理 ownership。
- ToolRuntime 是 `ToolExecutor`，EngineWorker 可以拿到 ToolRuntime as ToolExecutor。
- Engine 只看见 `ToolExecutor` protocol，不知道 `@tool`、`ToolDefinition`、TruncationManager 或 `fetch_more`。
- ToolRuntime 可选持有 TruncationManager；没有 TruncationManager 时仍可执行普通工具，只是不提供 truncate / `fetch_more` 能力。
- ToolRuntime 可以随 EngineWorker 部署在本地或远端执行环境，但它的治理配置和真源来自 Host attempt snapshot。
- 远端 ToolRuntime 可以执行、截断并返回结果，但不能 append EventLog、不能关闭 Attempt、不能更新 Run。

ToolRuntime 同时负责语义级重复工具调用治理。Engine 只负责结构性工具调用协议，不理解业务幂等性、工具结果等价性、当前财报分析目标或历史证据质量。

语义级重复治理的基本口径：

- 判定信号包括 tool identity、normalized arguments、evidence scope、result digest / evidence anchor、工具级 idempotency key、当前 run / session / memory context。
- policy action 分为 `allow`、`reuse`、`hint`、`require_justification`、`hard_stop`。
- 工具调用 intent 进入 `TOOL_CALL_REQUESTED`；治理决策进入 `TOOL_CALL_GOVERNED`；真正执行并被接受的结果进入 `TOOL_RESULT_ACCEPTED` / `TOOL_TERMINAL_RESULT`。
- `reuse` 引用 prior accepted tool fact，不伪造新的工具事实。
- 财报读取类 read-only 工具默认优先 `reuse` / `hint`；外部写入或付费工具必须依赖工具 schema / policy 的 idempotency key。
- 该治理不能进入 Engine，也不能让 RemoteStub 拥有 Host 状态。

声明与执行路径：

```text
@tool(..., truncate=ToolTruncateSpec(...))
  -> ToolDefinition
  -> Host / ToolRuntime keeps ToolTruncateSpec
  -> Engine only receives ToolSchema
  -> Engine emits normal tool call
  -> ToolExecutor executes ToolCallable
  -> TruncationManager applies declared ToolTruncateSpec
  -> ToolExecutor returns normal tool result with truncation hint when needed
  -> truncation hint carries opaque cursor + scope_token for ordinary fetch_more
```

核心约束：

- `ToolTruncateSpec` 是截断的显式触发条件。工具没有声明 spec、spec 未启用、策略未知或 limit 非法时，默认不截断。
- Engine / Runner 不接收 `ToolTruncateSpec`，也不理解截断策略；它只看见普通 tool schema、普通 tool call 和普通 tool result。
- TruncationManager 只按工具声明和 Host / ToolRuntime policy 工作，不根据工具名做业务语义猜测。
- 截断后的 LLM-facing tool result 可以携带普通 `fetch_more` 所需 opaque 参数：`cursor` 与 `scope_token`。`cursor` 标识从哪个被截断结果、哪个位置继续读；`scope_token` 是 opaque capability / scope binding，用来证明本次 `fetch_more` 只能读取对应工具结果的后续内容。
- LLM-facing result 不暴露 Host 内部 cursor store、artifact path、payload layout 或远端 cache key；payload 摘要、artifact ref、digest、截断原因和完整诊断进入 tool trace / durable descriptor。
- `cursor` / `scope_token` 进入 messages 或 EventLog 后，必须可恢复到足以完成后续 `fetch_more` 校验与读取的 durable descriptor；不能只存在于远端 ToolRuntime 进程内存。
- durable descriptor 保存 handle metadata、scope binding、artifact ref、digest、offset / page / path、expiry / retention policy 和 access policy；不要求 Host 持久化完整 raw payload。
- 截断不能让 assistant conclusion 变成 verified fact；财报事实仍必须追到工具事实与 evidence anchor。

`fetch_more` 是 Host / ToolRuntime 内置的 framework tool，但必须作为普通 tool 暴露和执行：

```text
Host / ToolRuntime registers built-in @tool("fetch_more", ...)
  -> effective tool schemas include business tools + fetch_more
  -> model emits normal tool_call(name="fetch_more", arguments=...)
  -> ToolExecutor dispatches as a normal tool call
  -> fetch_more callable validates cursor + scope_token through TruncationManager
  -> ToolExecutor returns normal tool result
```

`fetch_more` 边界约束：

- `fetch_more` 必须通过普通 `@tool` 声明进入生效工具集合；不能为它设计 Host / Engine 特化分支、专属 Engine event 或专属 WorkerProxy 协议。
- `fetch_more` 的执行也走普通 ToolExecutor dispatch；Host / ToolRuntime 只能通过普通工具注册表和普通 dispatcher 找到它，不能出现面向 `fetch_more` 的特化编码路径。
- `fetch_more` callable 内部可以通过闭包或协议访问 TruncationManager；这是普通 tool callable 的依赖注入，不是 Host 执行链路特化。
- EventLog 视角下，`fetch_more` 只是一次普通 tool request / result；tool trace 可以识别和展示续读诊断，但不能改变 EventLog 的事实模型。
- `fetch_more` 不能变成业务工具注册表的 public API，也不能让业务层依赖 Host 内部 cursor 结构。
- `fetch_more` 必须校验 `cursor` 与 `scope_token` 的绑定关系；scope 不匹配、过期、被撤销或 artifact digest 不匹配时，应返回普通工具错误结果，不得旁路读取。
- 当 truncation cursor / `scope_token` 的 ref 进入 messages 或 EventLog 后，该句柄必须可由 Host-governed durable cursor descriptor、artifact ref 或等价 snapshot 恢复；不能只存在于远端进程内存。
- Remote ToolRuntime 可以持有 attempt-local TruncationManager 和 short-lived cache，服务同一 Attempt 内的快速续读；这是优化，不是正确性前提。
- durable 不要求远端 ToolRuntime 在每次 truncate 或每次 `fetch_more` 前同步请求 Host。远端 ToolRuntime 可以随工具结果一次性回传 cursor descriptor / artifact ref / digest / scope binding；Host 接受工具事实时持久化该 descriptor。
- 跨 Host restart、Attempt `LOST`、resume、steer 或 replay 后，`fetch_more` 必须依赖 Host attempt snapshot / Host-governed cursor descriptor / artifact ref 恢复读取权限，而不是依赖旧远端内存。
- 远端不能把 cursor 或 `scope_token` 变成远端治理状态；Host 才能决定该句柄是否仍可用于当前 Run / Attempt / tool result。
- cursor 生命周期、TTL、单次读取 limit、重复续读、错误 envelope 和取消时资源收口属于 TruncationManager / ToolRuntime policy。

## Tool Awaiting / Wait Record 讨论入口

长事务或外部等待以 `ToolAwaitingOutcome` 为边界进入 Host。Engine 只负责产出 `tool_awaiting` 与 `run_suspended`；
Host 负责持久化等待、后续 resume 和资源治理。

基本路径：

```text
ToolExecutor returns ToolAwaitingOutcome(await_spec, snapshot)
  -> Engine emits tool_awaiting
  -> Engine emits run_suspended
  -> Host appends TOOL_AWAITING canonical fact
  -> Host closes Attempt as SUSPENDED
  -> Host marks Run WAITING
  -> Host persists wait record
```

wait record 最小语义：

```text
run_id
attempt_id
tool_call_id
tool_name
await_spec
snapshot_ref?
external_job_id?
idempotency_key?
resume_policy: callback | poll | manual
deadline / expires_at?
status: waiting | resolved | failed | cancelled | lost
```

Resume 策略分层：

```text
wait signal source
  -> poll | callback | manual
  -> common Host resolve_wait pipeline
  -> append tool terminal/result fact
  -> create new Attempt
  -> rebuild messages
  -> resume Run
```

`poll`、`callback`、`manual` 只是等待结果进入 Host 的 adapter；稳定核心是 Host 内部统一的
`resolve_wait(wait_id, outcome, source, idempotency_key)` pipeline。所有来源都必须走同一套幂等、状态校验、
EventLog append、wait record close、resume Attempt 创建和 messages 重建逻辑。

第一版策略：

- 第一版设计覆盖 `poll`、`callback`、`manual` 三种 resume policy 的语义。
- 第一版实现优先 internal / manual resolve 与 poll adapter。
- callback 作为后续 adapter 预留，因为它需要外部入口、认证、重放防护和额外暴露面。
- manual 可用于人工审批、调试或业务流程介入，但不应成为唯一自动恢复机制。

边界约束：

- 如果工具启动外部 job，必须返回稳定 `external_job_id` 或等价 ref。
- 外部副作用必须先有工具级 idempotency key，再启动外部 job；Host attempt 生命周期不能替代工具幂等。
- wait record 是 Host durable 状态，不是 remote worker 状态。
- job 完成后，Host append tool terminal / result canonical fact，再创建新 Attempt resume。
- 如果 job 状态无法确认，应进入结构化 failed / lost，而不是让远端 worker 接管旧 Attempt。
- Engine 不读取 wait record，也不恢复旧 Agent / Runner。

## Run-time Guidance 讨论入口

Host 需要支持在当前 run 内插入 guidance。典型触发点是在某个工具结果被接受后，Host / ToolRuntime 根据治理策略、
工具结果形态、截断状态、证据质量或上下文预算，向后续模型输入追加一段受控引导。

基本语义：

```text
tool result accepted
  -> Host / ToolRuntime evaluates guidance policy
  -> optional guidance message is appended to current run input sequence
  -> next model iteration sees tool result + guidance
```

边界约束：

- guidance 不改写原始 tool result；工具事实仍以 tool result / EventLog canonical fact 为准。
- guidance 不是 verified fact，不能让 assistant conclusion 或 Host 提示自动升级为财报事实。
- guidance 应作为 Host-governed input artifact 进入当前 run，可被 EventLog / tool trace / audit 观察；是否成为 canonical fact 需要在 EventLog taxonomy 中明确。
- guidance 不应进入 Engine 特化分支。Engine 只消费构造好的 messages，不理解 guidance 的策略来源。
- guidance policy 归 Host / ToolRuntime；业务工具可以通过结构化结果或 metadata 暴露需要引导的信息，但不能直接改写 Host 治理状态。
- guidance 只影响当前 run 的后续 iteration；是否进入 session memory 需要由 memory projection policy 决定，不能默认沉淀为长期事实。

## Terminal / Cancel / Steer 竞态规则

竞态规则必须保持“已提交事实不被覆盖”：

- terminal 永远优先。Run terminal fact 一旦提交，后续 steer 输入不能改写该 Run；它应作为普通 query / follow-up 进入 admission。
- cancel 只阻止未来工作，不覆盖已接受事实。已经接受的 tool result、awaiting outcome、final decision 和 canonical facts 继续保留。
- cancel 与 suspend 同时发生时，若 awaiting outcome 已被 Engine 接受并产生 `run_suspended`，late cancel 不覆盖 suspended；Host 将 Run 置为 `WAITING`，后续取消该 waiting run 走 Host cancel 语义。
- cancel 在 tool outcome 被接受前赢得 race 时，Engine 以 `run_cancelled` 收口，Host 关闭 Attempt 并将 Run 收口到 `CANCELLED`。
- queued run 被 cancel 时，Host 直接把 Run 收口为 `CANCELLED`，不创建 Attempt。
- 在未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，Run / Attempt 进入 `LOST`。
- steer 必须命中 active run precondition；terminal 已提交时 steer 降级为普通 query / follow-up。

## Read Model / Host Event Stream 边界

EventLog 是真源；Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot 都是 read model 或投影。

公共读取语义：

```text
get_run(run_id)
  -> RunSnapshot
  -> status, terminal result summary, active attempt, cursors

stream_run_events(run_id, cursor)
  -> ordered Host event stream
  -> attach / reconnect / replay from EventLog event_sequence cursor

get_session(session_id)
  -> SessionSnapshot
  -> session status, active run, queued runs, recent timeline summary
```

边界约束：

- `RunResult` 是 Run 终态投影，不是事实真源。
- `Session timeline` 是 UI / read model，不是事实真源。
- `stream_run_events` 从 EventLog `event_sequence` cursor 补读，不触发新执行。
- 投影损坏或缺失时应能从 EventLog 重建。
- UI 展示可以读取 timeline；resume、memory、audit 责任链必须读取 canonical EventLog facts。

## Remote 执行控制边界

LocalProxy 与 RemoteProxy 应保持语义等价。RemoteProxy 只是 transport boundary，不是治理 boundary。

设计边界：

- design 前只定义 remote semantic contract，不定义 wire protocol。
- LocalProxy 是语义基准。
- RemoteProxy 是 transport substitution。
- 具体 RPC、ack、replay、heartbeat、wire envelope、版本协商和连接保活属于 Remote phase discussion，不是当前 design 前置 blocker。

远程执行不变量：

- Host 创建 Run、Attempt 与 `execution_id`。
- Host 通过 LocalProxy / RemoteProxy dispatch Attempt。
- RemoteStub / EngineWorker 只执行并回传带 `run_id`、`attempt_id`、`execution_id`、sequence / event id 的事件。
- Host 校验 `attempt_id + execution_id` 后决定是否 append canonical EventLog。
- RemoteStub / EngineWorker 不 append EventLog，不关闭 Attempt，不更新 Run，不 takeover，不 resume。
- 迟到事件、重复事件或 `execution_id` 不匹配事件不能污染 canonical EventLog；最多进入诊断 / trace。
- cancel 由 Host 发起，通过 Proxy / Stub 传递到 EngineWorker 的 run-local cancellation token；远端不自行决定 Run 终态。

## Suspend / Resume / Resend 讨论入口

`suspend`、`resume` 和 `resend` 需要拆成不同语义，避免把等待、重试、断线补发混在同一个机制里。

### Suspend

`suspend` 表示当前 attempt 已经无法继续同步完成，但 Run 还没有失败或成功。典型来源是 Engine 收到
`ToolAwaitingOutcome` 并产出 `run_suspended`，或者执行环境报告需要等待外部条件。

讨论中的治理路径：

```text
EngineWorker / Engine emits suspended fact
  -> Host ingest validates attempt_id + execution_id
  -> Host appends suspend / waiting canonical EventLog fact
  -> Host closes current Attempt as SUSPENDED
  -> Host updates Run to WAITING
  -> Host persists wait record or equivalent waiting fact
```

### Resume

`resume` 不复用旧 Agent / Runner / EngineWorker，也不让远端 worker 自己接管。恢复应由本地 Host 在等待条件满足后显式发起：

```text
wait condition satisfied
  -> Host appends resume requested fact
  -> Host creates a new Attempt with new execution_id
  -> Host rebuilds complete AgentRunRequest.messages from canonical EventLog facts
  -> Host dispatches through LocalProxy / RemoteProxy
```

Engine 边界已经固定：`run_suspended` 或 `run_cancelled` 之后若要继续原目标，Host 必须构造新的
`AgentRunRequest`，把恢复输入、工具终态结果或用户意图显式放回 `messages`。Engine 不恢复旧 Agent /
Runner，也不读取 Host wait record。

恢复输入真源应是 EventLog 的 canonical facts。Run / Attempt 表提供状态索引与并发治理；Session timeline、
trace、audit、outbox 等是投影或派生视图，不应反过来成为恢复 messages 的真源。

### Resend

`resend` 至少有三类不同含义：

- 客户端因网络失败重发 `start_run`：应由 `(session_id, client_request_id)` 幂等返回同一个 Run。
- 客户端断线后重拉事件：应由 `stream_run_events(run_id, after=cursor)` 从 EventLog 补发，不触发新执行。
- Worker / RemoteStub 因连接抖动重发事件：Host ingest 必须用 `attempt_id + execution_id + event_id / sequence`
  去重，已接受事件不重复 append，迟到或不匹配事件不污染 canonical EventLog。

失败后的“重新执行”不应叫 resend；它应是 retry / replay / new run 中的一种，需要由 Host policy 或用户动作显式触发。

## Cancel 讨论入口

取消由 Host 发起和治理，Engine 只观察 run-local cancellation token 并以 `run_cancelled` 收口。取消不是普通 error，
也不是工具失败。

初始取消路径：

```text
client requests cancel
  -> Host appends cancel requested canonical fact
  -> Host marks Run as CANCELLING when an attempt is active
  -> Host sends cancel through LocalProxy / RemoteProxy control channel
  -> EngineWorker maps it to run-local cancellation token
  -> Engine emits run_cancelled when cancellation wins an execution boundary
  -> Host validates attempt_id + execution_id
  -> Host appends cancelled terminal fact
  -> Host closes Attempt + updates Run to CANCELLED
```

已确定的取消规则：

- `QUEUED` 且尚未创建 Attempt 的 Run 被取消时，直接进入 `CANCELLED`，不创建 Attempt。
- terminal fact 已提交后，cancel 不能改写 terminal；新的用户输入按普通 query / follow-up 处理。
- cancel 与 suspend 同时发生时，遵循 Engine 已接受事实不被覆盖的规则；已接受 awaiting outcome 和 `run_suspended` 不被 late cancel 覆盖。
- cancel 控制消息最小携带 `run_id`、`attempt_id`、`execution_id`，用于避免误伤新的 Attempt。
- 未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，旧 Attempt 进入 `LOST`；若 Run 仍可基于 durable facts 继续，则 Run 进入 `RECOVERING`，否则才进入终态 `LOST`。
- 强制终止执行环境、后台 job reconcile、细粒度资源收口失败事实属于后续 cancel governance 强化；第一版不能让这些缺口阻塞基本 cancel 收口。

## Conversation Memory 讨论入口

多轮会话记忆子系统从买方财报分析 Agent 的第一性原理出发设计。

### 财报 Agent 会话不变量

- 目标稳定：一个 session 通常围绕某公司、某期间、某个财务问题持续追问；当前目标、确认对象、用户口径和未决问题应稳定保留。
- 工具结果即事实：财报数字、章节定位、XBRL facts、证据来源和工具观察不能被 LLM 二次摘要丢失精度。
- 追问连续性是刚需：用户经常基于上一轮结论继续展开、换口径或要求细化；最近 raw turns 需要反退化保底。
- 跨轮一致性优先于上下文丰富度：pinned state、confirmed facts、evidence anchors 和显式验证来源是反幻觉核心。
- memory 应克制：长上下文优先留给当前财报材料、检索结果、章节片段和工具结果；memory 只提供必要连续性和稳定事实。
- 展示态与运行态分离：reasoning、preview delta、UI timeline、trace 展示不能回流到运行态 memory。

### 基本结构

Conversation Memory 分为稳定层与历史池：

```text
Conversation Memory
  -> stable layer
      -> pinned_state
      -> tool-verified facts
      -> assumptions / open questions
      -> evidence anchors / tool facts
  -> history pool
      -> recent raw turns floor
      -> older raw turns
      -> episode summaries
```

`pinned_state` 至少包含：

- `current_goal`
- `confirmed_subjects`
- `user_constraints`
- `open_questions`

`pinned_state` 与 tool-verified stable facts 应全量注入，不参与历史池预算竞争。`final_answer` 是 assistant role 产出的最终回答；在 memory 中只能作为 raw turn / assistant conclusion 参与连续性，绝不能自动升级为 verified fact。verified fact 只接受工具事实；用户输入进入 pinned state、约束或待验证候选，不直接成为 verified fact。

### 事实真源与投影路径

Memory 的事实真源是 canonical EventLog。Memory snapshot 是 Host 内部 read model，可重建、可修复，但不是事实真源。

```text
current USER_INPUT_ACCEPTED canonical fact
current run semantic canonical facts
session / prior-run canonical EventLog facts needed for continuity
  -> required memory projection
  -> session memory snapshot
  -> RunInputBuilder
  -> AgentRunRequest.messages
  -> Engine
```

不变量：

- memory projection 只消费 canonical facts。
- preview / reasoning / display-only facts 不进入 memory。
- Session timeline、trace、audit、outbox 与 memory 都是 EventLog 派生视图；memory 不读取其它投影来构造下一轮输入。
- snapshot 写入与 projection checkpoint 应具备同事务或等价一致性；checkpoint 已推进但 snapshot 未写入会造成恢复洞。
- snapshot 缺失时应能从 EventLog 重建；snapshot 损坏时不能覆盖或篡改 EventLog。

### RunInputBuilder 路径

RunInputBuilder 是 memory 进入 Engine 的唯一运行态入口。

```text
current USER_INPUT_ACCEPTED canonical fact
  + current run semantic canonical facts
  + session / prior-run canonical EventLog facts needed for continuity
  + session memory snapshot
  + caller system messages
  -> RunInputBuilder
  -> complete AgentRunRequest.messages
```

`USER_INPUT_ACCEPTED` 是当前用户 prompt 进入 RunInputBuilder 的唯一事实入口。RunInputBuilder 不从 UI 临时文本、
request 临时字段或 Session timeline 旁路读取当前 prompt。

RunInputBuilder 需要：

- 把 pinned state 与 stable facts 放在明确的 Host Memory system block 中。
- 对 recent raw turns 做下限保底，而不是固定上限。
- 对 older raw turns、episode summaries、tool facts、evidence anchors 做预算选择。
- 不创建独立 RunInputBuildTrace 子系统；上下文构造和证据纳入的观测统一进入 tool trace / trace 体系。

普通下一轮输入、suspend 后 resume、cancel 后继续原目标都应通过同一路径，从 canonical EventLog facts 重建完整 `AgentRunRequest.messages`。

RunInputBuilder 归属和输入标准：

- RunInputBuilder 是 Host 内部组件。
- Service / caller 可以提供 system messages 或场景装配参数，但不能绕过 Host 直接拼装恢复 messages。
- RunInputBuilder 消费 session memory snapshot 与当前 run 需要的 canonical facts；不是所有 memory facts 都原样进入 messages。
- 判断某个 fact 是否进入 `AgentRunRequest.messages` 的标准是：模型是否需要看到该 fact，才能正确继续当前目标、resume、steer 或 follow-up。

应进入 messages 的典型事实：

- 用户输入：`USER_INPUT_ACCEPTED`、steer input、resume input、follow-up input。
- assistant final answer / assistant conclusion：作为对话连续性进入，但不是 verified fact。
- accepted tool result，尤其是工具事实、evidence anchor / ref / digest、工具终态结果。
- tool awaiting resolved 后的 terminal / result fact。
- Host memory block：pinned state、tool-verified facts、open questions、assumptions。
- guidance inserted，如果它影响后续 iteration。
- 必要的 cancel / resume / steer 说明，如果它影响当前继续目标。

不应进入 messages 的事实：

- audit-only facts。
- usage-only facts。
- stream fanout 状态。
- projection checkpoint。
- raw preview delta / reasoning delta。
- 内部 state transition 本身，除非它需要被模型理解为用户语义。

## Run Replay 讨论入口

Run 需要支持 replay。典型场景是 final answer 返回脏数据、格式错误、违反输出约束或需要重新生成，但当前 Run
messages 已经包含历次工具事实和 tool messages；完整重跑工具代价过高，也可能重复外部副作用。

Replay 与 retry / resume 的区别：

- retry 偏向重新执行失败路径，可能重新进入工具调用。
- resume 偏向等待条件满足后继续未完成目标。
- replay 偏向复用已接受事实和已构造的工具上下文，只重新执行后续模型决策或最终回答生成。

基本语义：

```text
final answer invalid / dirty output detected
  -> Host appends REPLAY_REQUESTED canonical fact
  -> Host creates new Attempt for the same Run with new execution_id
  -> RunInputBuilder rebuilds messages from canonical facts
  -> previously accepted tool facts / tool messages are reused
  -> replay guidance or output repair instruction is added
  -> Engine reruns model decision without repeating expensive accepted tools unless policy explicitly allows
```

边界约束：

- replay 不复用旧 Agent / Runner / Attempt；它创建新 Attempt。
- replay 不撤回旧 final answer fact；旧 final answer 作为 assistant conclusion / dirty output fact 保留，不升级为 verified fact。
- replay 默认复用已接受 tool result、tool terminal result、evidence anchor / ref / digest 和必要 tool messages。
- replay 默认不重新执行已接受工具，避免重复成本和外部副作用；若 policy 允许重新执行，必须通过工具级幂等和新 Attempt 明确表达。
- replay 的触发原因应进入 canonical fact，例如 output schema invalid、dirty data、用户要求重答、policy validation failed。
- replay 生成的新 final answer 才能成为 Run 当前 terminal result projection；EventLog 保留历史 terminal / replay 链。
- replay 仍受同一 Session active Run admission 约束；它在同一个 Run 内切换 Attempt，不创建并列 Run。

### 参数与策略

Memory 参数需要从财报场景重新论证，但具体默认值属于 memory 实施阶段决策：

- `memory_token_budget_ratio`：历史池占模型窗口比例。
- `memory_token_budget_floor`：短窗口模型下的最低连续性预算。
- `memory_token_budget_cap`：长窗口模型下 memory 克制上限。
- `recent_turns_floor`：最近 raw turns 下限保底。
- `compaction_trigger_context_ratio`：context compaction 触发阈值。
- `compaction_tail_preserve_turns`：压缩时保留的 raw tail。
- `compaction_context_episode_window`：生成 episode summary 时参考的近邻 episode 数量。
- `compaction_scene_name`：压缩专用 scene。

这些参数需要通过财报场景目标来定。长窗口模型下 cap 应选择 32K、48K、60K 还是其它值，compaction trigger 应偏早保护财报材料空间还是偏晚减少额外成本，都留到 memory 实施计划中结合测试与样例决定。

### Context governance

Context governance 是生产级财报 Agent 的必要能力，第一版设计应一步到位覆盖完整治理范围：

- Host 负责 provider-aware context budget policy；Engine 不做 Host-side compact retry。
- RunInputBuilder 的输入层需要可测试的预算分配，包括 current user、pinned state、recent raw turns、older raw turns、episode summaries、tool facts、evidence anchors、tool-verified facts / assumptions。
- compact 触发、LLM episode summary compaction、pinned_state patch、compact 后保真检查、失败收口、retry policy、context overflow retry、compact event、trace、audit projection 都属于 Host context governance。
- provider tokenizer adapter 可以后续接入；当前 token estimator 只能作为 Host 预算治理的估算实现，不是 provider tokenizer 真源。
- compact 质量与丢弃原因必须可审计，不能污染 EventLog 事实真源或让 summary 替代 evidence anchor。

Compact event 响应路径：

- proactive trigger：Host / RunInputBuilder 在 dispatch Attempt 前根据 provider-aware budget、tool facts、memory snapshot、当前用户输入和场景参数判断即将超预算。
- reactive trigger：Engine 在 Runner 报告 context length exceeded 后 emit `context_compaction_requested` EngineEvent，并以 recoverable `run_failed(context_compaction_required)` 收口本次 Engine run。
- Host 响应 reactive trigger 时，先校验 `attempt_id + execution_id`，append `CONTEXT_COMPACTION_REQUESTED`，关闭当前 Attempt，并按 policy 让 Run 进入 `RECOVERING` 或 `FAILED`。
- 如果 policy 允许恢复，Host 执行 ContextGovernance compact，append `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`。
- compact 成功后，RunInputBuilder 从 `USER_INPUT_ACCEPTED`、canonical facts、memory snapshot 和 compacted artifacts 重建完整 messages，再创建新 Attempt / 新 `execution_id` dispatch Engine。
- Engine 不做 Host-side compact retry；旧 Attempt 不 takeover、不 resume。
- compact 不能改写历史 EventLog facts，也不能让 summary 替代 evidence anchor；tool trace / audit 必须能解释保留、压缩、丢弃和失败原因。

### Long-term memory governance

长期 memory 不在第一版实现。第一版只做 session memory 与当前 run 的上下文治理，但设计不能封死后续长期记忆能力：

- session memory read model 与长期 memory 不是同一层级；长期 memory 需要单独讨论 durable semantic memory、scope、permission、audit、privacy 和 UI 控制。
- 跨 session / project / user memory scope 不能默认从 session memory 外溢；必须有明确 policy 与权限边界。
- public memory edit / reset / forget API 属于长期 memory 后续能力，不能直接改写 canonical EventLog；若需要改变运行态 memory，应通过可审计的 patch / tombstone / projection 机制表达。
- preview / reasoning / display-only 事实不得进入运行态 memory。
- Host / Engine 不承载财报业务语义，长期业务 signal 的抽取与原始证据存取归业务工具和财报领域仓储边界。
- 后续长期 memory 可以由 Service 层发起写入或召回编排，但写入内容必须来自工具事实或业务仓储引用，不能让 Service 直接把自然语言结论写入运行态 session memory。

### Cross-year weak-signal evidence chain

跨多年弱信号归因是买方财报分析的高风险场景。设计需要区分 Host 中立 memory 与业务证据检索：

- Host 可提供 evidence anchor、provenance、事实候选 / 验证标记等中立骨架；具体类型命名与状态形状留到 memory 实施阶段决定。
- 原始网页新闻、公告、研报摘录、财报 chunk、source metadata、业务 event type、company / product / business-line ref 由业务工具和财报领域仓储管理。
- 早期 signal 先进入 assumption / candidate 状态，不能因为被 summary 或 memory 收录就变成 verified attribution。
- 后续财报分析时，应通过 query-time retrieval 召回相关 signal anchors / evidence chunks / prior assumptions，而不是无限扩大 memory pool。
- EventLog payload 设计需要支持这条链路：canonical fact 内联可审计 anchor / ref / digest，大原文与长证据外移保全，memory 只保存导航和必要连续性。
- 长期 summary 只能做导航；关键归因必须追到当前 run 已召回并验证过的工具事实。
- 如果召回失败、证据不足、证据冲突、signal stale 或因预算未进入 RunInput，tool trace / trace 体系必须能解释。

## 讨论范围

本轮讨论先聚焦需求与架构，不进入实施计划。

需要展开的主题包括：

- Host 对外应暴露哪些稳定概念。
- Session、Run、Attempt、EventLog 是否是合适的核心对象，以及它们各自的边界。
- 多入口访问同一本地 Host 时，session / run 的并发与幂等语义应如何定义。
- Host durable store 是否作为状态真源，以及它需要承载哪些事实。
- Host 与 Local / Remote EngineWorker、Tool execution 的边界如何划分。
- Host 崩溃、worker 断连、迟到事件、retry / resume 的责任边界。
- 工具外部副作用、幂等和只读财报工具的治理边界。
- EventLog、RunResult、Session timeline、trace / audit / outbox projection 之间的事实关系。
- 哪些能力属于第一版设计，哪些只应作为后续扩展点。
