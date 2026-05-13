# Dayu 开发手册总览

本文档是 `dayu/` 包的开发手册总览。

## Agent更新约束【必须遵守】

- 本文档只写当前代码已实现的整体架构、设计意图、稳定边界、扩展入口、代码阅读顺序。
- 本文档不写过程状态，不写未来计划，不写实现细节，只保留稳定说明。

## 设计目标

- 生产级买方财报分析 Agent
- 范式是“宿主强约束下的 LLM in the loop”
- 支持单机多客户端 / 多进程
- 支持本地 Engine 和远程 Engine 并列执行

## 整体架构

Dayu 的整体架构是：

```text
UI -> Service -> Host -> Engine
```

这条链路表达的是控制权和依赖方向：

- `UI` 负责用户交互入口，只处理展示、输入收集与命令触发。
- `Service` 负责业务请求受理与场景装配，把用户意图转成可执行请求。
- `Host` 负责 Agent 运行宿主边界，拥有 session / run / attempt 生命周期、admission、取消、恢复、EventLog、工具运行时、memory / context governance 与 projection。
- `Engine` 负责执行已准备好的模型交互、Runner / Agent 状态机与强类型事件流。

依赖只能沿 `UI -> Service -> Host -> Engine` 向下发生；下层不得反向依赖上层。Engine 不理解 UI、Service 或 Host 的治理细节；Host 不承载财报业务语义；Service 不绕过 Host 直接控制 Engine。

`dayu.contracts` 承载跨层共享协作契约。契约层不得依赖具体业务层或执行层实现。

`dayu.host` 承载 Host 公共 API 类型契约。当前已导出 request、snapshot、status、error、context、stream cursor 类型，以及 Host construction 的 `HostToolingOptions` 工具输入边界，供 UI / Service 按依赖方向向下引用；Host durable store、EventLog、dispatch、command path、ToolRuntime 与 policy provider 不属于当前公共命名空间。

财报领域能力属于独立领域边界；财报文档存取必须通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成，不应泄漏到 Engine 或 Host 内部。

## 术语约定

以下术语用于描述 Agent 执行链路。本节是后续 Host / Engine / Service 相关 phase discussion、phase plan、
implementation、review、fix 与 re-review 的项目级术语真源。包级 README 和设计文档必须使用这些词；
不得在计划或实现中自行重解释同一术语。若术语缺失、冲突或不足以指导实施，应先讨论并更新本节及对应设计文档。

- `Session` / `session`：一条可持续的会话上下文。它属于 Host / 上层语义，Engine 不持有 session 生命周期。Session 状态只表达 `OPEN` / `CLOSED`。
- `session slot`：外部入口复用当前 Session 的槽位，由 `(scope, slot_key)` 标识。WeChat 稳定身份、CLI `--label`、GUI 当前会话都可以映射到 slot。
- `ensure_session`：Host 公共接口，表示“返回这个 slot 当前 Session，不存在则创建并绑定”。它按 `(scope, slot_key)` 幂等，不需要 `client_request_id`。
- `create_session`：Host 公共接口，表示“明确创建一个新 Session”。它按 `client_request_id` 幂等；可选把新 Session 绑定到某个 session slot。
- `purge_session`：Host 公共接口，表示“彻底清理一个已关闭且全部 Run 已终态的 Session 的 Host 本地数据”。它是 destructive purge，不是 close、cancel、archive、memory forget 或 UI hide；purge 后不再支持恢复、resume、retry、replay、timeline 补读或 final answer 找回。purge 不删除已写入的 append-only audit JSONL；必须保留 purge tombstone，并让 audit 查询能识别源 EventLog facts 已被 purge。
- `start_run`：Host 公共接口，表示显式创建一个新的独立 Run 目标。它不是聊天界面每次发送普通 prompt 的默认入口。
- `submit_followup`：Host 公共接口，表示向同一 Session 提交一条会话延续输入。聊天界面的普通 prompt 入口应统一使用 `submit_followup`；`behavior=queue` 由 Host admission 在事务内决定排队或直接启动，`behavior=steer` 必须携带 `target_run_id` / expected active Run precondition。
- `cancel_run`：Host 公共接口，表示取消指定 Run。它按 `(run_id, client_request_id)` 幂等；terminal 已提交时不能改写 terminal。
- `cancel_session_runs`：Host 公共接口，表示取消指定 Session 下所有未终态 Run。它按 `(session_id, client_request_id)` 幂等，用于客户端退出、supervisor shutdown 或用户明确停止该 Session 下全部未完成工作；它不关闭 Session、不删除事实、不表达客户端拥有的所有 Session。
- `Run` / `run`：用户可见的一次 Agent 目标 / 问题 / follow-up，属于一个 Session。一个 Session 可以包含多个 Run；Engine 只处理单次 `AgentRunRequest` 的执行语义。
- `Attempt` / `attempt`：Host 为完成某个 Run 派发给本地或远程 EngineWorker 的一次执行。resume、steer、recovery 等同一 Run 内继续执行路径会创建新 Attempt；retry / replay 创建关联的新 Run，新 Run 再创建自己的 Attempt。任何路径都不复用旧 Agent / Runner / EngineWorker。
- `retry_run` / `retry(run)`：公开 Host control API，由调用方主动发起，用于重新尝试完成一个失败或 policy 判定可重试的源 Run。Retry 创建关联的新 Run，不重开源 Run；新 Run 可以按 retry policy 使用工具，也可以复用源 Run 已 accepted 的工具事实。Retry 修的是执行失败或可恢复失败。
- `replay_run` / `replay(run)`：公开 Host control API，由调用方主动发起，用于在源 Run 已 `SUCCEEDED` 但 final answer 格式、schema、结构或输出 envelope 脏时，基于源 Run 已 accepted 的事实创建关联新 Run 做 no-tool 结构修复。Replay 不重新查证、不重新执行工具、不修正事实内容；幻觉、事实错误、证据不足、归因错误不属于 replay 场景。Replay 修的是输出结构失败。主防线是 RunInputBuilder 不向 replay Attempt 暴露 tool schemas；ToolRuntime 拒绝 replay 中的 tool call 只是 defense-in-depth。
- `Run status`：Host 管理的 Run 生命周期状态。当前设计集合为 `QUEUED`、`RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST`；其中 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 是终态。`RUNNING` 表示 Run 已占用 Session active slot，并已有 active Attempt lifecycle，不要求 worker 已 accepted。
- `Attempt status`：Host 管理的一次执行尝试状态。当前设计集合为 `STARTING`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`SUSPENDED`、`STEERED`、`LOST`；Attempt 终态不等于 Run 必然终态。`STARTING` 表示 Host 已 durable 创建 dispatch intent，`RUNNING` 表示 worker 已接受执行。
- `active Run`：同一 Session 内当前占用执行槽位的 Run。Host 设计语义是同一 Session 同时最多一个 active Run。
- `durable queue`：Host 已接受但尚未启动的 queued Run 集合。queued Run 必须持久化，不是内存队列项。
- `promotion`：把一个已持久化的 `QUEUED` Run 提升为 `RUNNING` 并创建 Attempt。promotion 只在同一 Session 没有 active Run 时发生；active Run 存在时仍可接受 queue 或 steer，但不能启动另一个 queued Run。
- `admission`：Host 对同一 Session 的并发入口治理。它决定新输入是直接启动、排队、拒绝、attach active，还是 steer 当前 Run。
- `queue`：`submit_followup(behavior=queue)` 的 admission 行为。Host 必须在同一事务内吸收 active Run 竞态：有 active Run 时创建 queued Run；无 active Run 时创建并启动新 Run。
- `steer`：`submit_followup(behavior=steer)` 的控制行为，把用户输入作用于指定的当前 active Run，并通过新 Attempt 继续；它不创建并列 Run。Steer 必须携带 `target_run_id` 或等价 expected active precondition；目标已 terminal、active 已切换、无 active 或状态不可 steer 时返回 `invalid_state` / `conflict`，Host 不自动换目标。
- `iteration`：Engine 内一次模型调用与后续决策循环。一次 run 可以包含多次 iteration，例如普通 tool loop 或 final-answer continuation。
- `final_answer`：Engine terminal event，表示 assistant role 产出的最终回答。它不是 user role message 的返回值，也不是自动验证事实。
- `assistant conclusion`：Memory 语境中对 `final_answer` 的保守称呼，表示助手结论。它可以作为 raw turn 的 assistant 输出参与追问连续性，但绝不能自动升级为 verified fact。
- `verified fact`：Host / memory 中可作为事实使用的稳定信息。Host 只接受工具事实；用户输入、assistant final answer、summary、projection 都不能自动升级为 verified fact。
- `EventLog`：Host 持有的 append-only 事件事实源。Run / Attempt 状态、RunResult、Session timeline、trace、audit、outbox 等能力只能从 EventLog 或同一持久化事务内的事实派生，不反向成为恢复输入真源。`purge_session` 是第一版唯一 destructive retention 例外，且只在严格前置条件成立后删除对应 Session 的可恢复事实并保留 tombstone。
- `canonical event`：EventLog 中 `event_class=canonical_fact` 的事实事件，可恢复、可审计、可投影。Host resume 构造新的 `AgentRunRequest.messages` 时，应以 canonical EventLog facts 为真源。
- `USER_INPUT_ACCEPTED`：Host canonical event，表示某次用户输入已经被 durable accepted，并绑定到具体 Session / Run。它通常包含输入正文或 ref / digest、`session_id`、`run_id`、`client_request_id`、actor、source 和 accepted time；它不是 UI 临时文本，也不是仅一段裸 prompt。已 accepted 的用户输入不能原地修改、覆盖或删除；取消后编辑再发送必须生成新的 `USER_INPUT_ACCEPTED` 与新的 Run，旧 Run 保留 `CANCELLED` 历史。
- `HostCallContext`：Host API 的调用上下文，描述这次调用的来路和责任信息，例如 actor / principal、source / client、request_id、authorization_claims 和 `OperationContext`。它不携带 delivery target，也不是统一幂等键；具体 request 定义状态机前置条件和自己的幂等范围。
- `OperationContext`：HostCallContext 中的业务 / 操作上下文，用于让 audit、tool trace、timeline 和诊断知道“这是什么业务的什么操作”。它由 UI / Service 解析并传入，Host 不从 prompt 猜业务对象。最小语义包含 operation name / kind、business domain、business object type / id、scenario 和 correlation id；它不是 policy override，不替代 authorization claims，也不承载大业务 payload。
- `client operation id` / `client_request_id`：客户端或上层入口为一次 Host API 调用提供的幂等身份，用于断线重发、超时重试或重复提交时返回同一个操作结果。它标识的是“客户端操作”，不是 Host EventLog 事件，也不是远端 EngineWorker 事件。
- `remote event identity`：Proxy / Stub / EngineWorker 回传的来源事件身份，用于 Host 识别远端重放、重复回传或乱序诊断。它可以参与 canonical event identity 的派生，但不能替代 Host 分配的 canonical event identity 或 `event_sequence`。
- `canonical event identity` / `event_id`：Host EventLog 中单条 canonical fact 的幂等身份。一个远端事件如果映射为多个 canonical events，每个 canonical event 都必须有独立、稳定、可去重的 identity，例如由 `execution_id`、remote event identity、canonical event type 和 sub-index 派生。Host-generated state transition event 也必须有明确的幂等来源，不能混用 `client_request_id` 或 remote event identity。
- `EngineEvent stream`：EngineWorker 执行 Engine 时产出的事件流。它是 Host ingest 的输入来源之一，不是 Host 事实真源。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流，只在 Engine 内部消费，不直接暴露给 Engine 调用方，也不是 Host 事实真源。
- `SSE stream` / `provider streaming`：Runner 与 provider 之间的传输能力，由 Runner 规约和单次 Runner 调用参数控制。它不是 `EngineEvent stream`，也不是 `Host event stream`。
- `Host event stream`：Host 对 UI / CLI / Web / GUI 暴露的订阅与补读事件流。它来自 EventLog `event_sequence` cursor，不触发执行。
- `preview event`：面向流式展示的临时事件。preview event 可以改善 UI 体验，但不能作为恢复、投递或 RunResult 的唯一事实来源。
- `preview delta`：模型 content / reasoning / tool-call 的增量片段，只服务 UI 流式体验，默认不是 canonical fact。
- `stream fanout`：把已提交 Host events 分发给多个 UI 客户端的 projection / sink。慢客户端必须用 `event_sequence` cursor 补读，不能反压 EventLog append。
- `event_sequence`：Host durable store 分配的全局单调事件序列，是 Host event stream cursor、projection checkpoint、outbox、audit replay 和 recovery scan 的主 cursor。远端 ordering hint 不能替代 Host 分配的 `event_sequence`。
- `execution_id`：Host 为一次 attempt 分配的执行 epoch，用于校验 Proxy / Stub / EngineWorker 回传事件是否属于当前 active attempt。它用于拒绝迟到事件污染 EventLog，不代表远端执行环境拥有 Host 治理状态。
- `host_instance_id`：Host 进程启动时生成的本机实例标识，用于 dispatch record 与 host instance liveness record 关联。它不是 lease、不是 fencing token、不是远端 owner，也不允许旧 Attempt takeover；只服务 positive orphan proof。
- `positive orphan proof`：Host recovery 将 active Attempt 标为 `LOST` 前必须具备的正向孤儿证明。第一版来自本机 Host 进程存活证据，例如 owner `pid` 已不存在或 pid 已复用但 process_start_token 不匹配，并且 heartbeat 已过期；heartbeat stale 或当前进程不可确认控制都不能单独证明 orphan。
- `dispatching`：dispatch record 的调度中状态，表示 Attempt Dispatch 已拿到所需 lane，并在短事务 recheck 后准备调用 WorkerProxy。`dispatching` / `dispatcher_instance_id` 只用于本机调度诊断、重复派发抑制和 recovery 判断，不是 lease，不是 fencing token，也不授权旧 Attempt takeover。
- `RunSnapshot` / `SessionSnapshot`：Host read model 快照。它们用于读取当前状态和游标，不是事实真源。
- `RunResult`：Run 终态结果投影，不是事实真源；事实真源仍是 EventLog 与同事务状态索引。
- `Session timeline`：面向 UI / read model 的会话展示视图，不是 RunInputBuilder 的事实真源。
- `Observer` / `Sink` / `Projection`：消费已提交 EventLog 的派生机制。audit、usage、tool trace、stream fanout、memory snapshot、outbox 都属于 projection / sink；sink 失败不能回滚 EventLog。
- `LogAuditSink`：Audit 第一版默认 sink。它按 `event_sequence` checkpoint 消费 committed EventLog，写本地 append-only JSONL audit log file；路径由 Host composition root typed options 传入。每条 audit 记录必须携带 operation context refs / digest，用于回答“这是什么业务的什么操作产生的审计记录”。它不写大 payload，不复制 tool trace 冷数据，失败不能回滚 EventLog，也不影响 Host command path。`NoopAuditSink` 只作为测试 / 开发显式配置。
- `tool trace hot data`：tool trace 的热数据层，使用结构化 JSON projection 保存近期可查询、可展示、可关联的工具调用摘要、策略决策、证据锚点和错误 / 截断 / 等待信息。热数据必须携带 operation context refs / digest。
- `tool trace cold data`：tool trace 的冷数据层，使用 append-only JSONL 保存归档、批处理、离线审计所需的长诊断明细。JSON / JSONL 都是 EventLog 派生 projection，不是恢复、resume、memory 或 Run 状态迁移真源。冷数据必须携带 operation context refs / digest。
- `Outbox`：离线 / 外部投递路径的 durable terminal delivery queue。它让离线客户端或外部渠道不必回放中间过程，也能拿到 final answer / terminal notification。Outbox 只表达 terminal delivery intent，不是完整 run timeline、不是 UI read model，也不决定 final answer 是否存在；投递失败不能回滚 Run terminal，也不参与 resume / memory 事实重建。在线 / 已 attach 客户端的阅读路径是 Host event stream、Session timeline、RunSnapshot 或 read model，不是 Outbox。在线阅读路径和 Outbox 离线投递路径必须共享同一个 terminal identity；UI / Service 用 `terminal_event_id` / `event_sequence` / `run_id` 去重，并维护自己的 seen cursor 或 delivery ledger。
- `command path`：Host 同步治理命令路径，例如 `start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run`。它负责校验、事务、EventLog append、状态索引更新、commit 和 after-commit wakeup，是写 Host truth 的路径。
- `background runtime`：Host 已提交事实的追平和投影运行时，例如 Observer / Sink、audit、usage、tool trace、memory projection、outbox projection、stream fanout、wait poller。它按 `event_sequence` checkpoint 消费 EventLog，不 append canonical facts，不更新 Run / Attempt governance state。
- `WorkerProxy`：Host 到执行环境的适配边界。LocalProxy 与 RemoteProxy 只负责传输、启动、取消控制和事件回传，不拥有 Session / Run / Attempt / EventLog 真源。
- `EngineWorker`：承载一次 Engine 执行的执行环境能力。EngineWorker 可以位于本机或远端；无论位置如何，它只执行并回传事件 / 结果，不 append EventLog、不关闭 attempt、不更新 Run 状态。
- `RemoteStub`：远端执行环境中的代理端点，负责把 RemoteProxy 的请求转为 EngineWorker 执行并回传事件 / 结果。RemoteStub 不拥有 Host 治理状态。
- `ToolBundle`：`dayu.contracts` 中已定义的工具声明集合，包含 `ToolDefinition` 元组，校验工具名唯一，并可投影为 Engine 可见的 `ToolSchema` 列表或 ToolRuntime 使用的 truncate specs。Host 的工具输入是外部传入的业务 `ToolBundle`；Host 不负责工具发现、模块扫描或注册生命周期。业务 `ToolBundle` 通过 `HostToolingOptions` 作为 Host construction / composition root 的显式输入，不是普通 UI / Service per-run request payload。
- `HostToolingOptions`：`dayu.host.tooling` 中已实现的 Host construction typed options，包含业务 `ToolBundle`、非空来源 refs 与 framework tool policy view。它会拒绝业务工具占用 Host / ToolRuntime 预留的 framework tool 名称，例如 `fetch_more`；它不计算 durable tool snapshot，不注入 framework tool，也不解析 ToolRuntime policy。
- `effective ToolBundle`：ToolRuntime factory 基于业务 `ToolBundle` 和启用的 framework tools 生成的 attempt-local runtime bundle。`fetch_more` 由 ToolRuntime factory 在启用 TruncationManager 时注入 effective ToolBundle，不要求外部业务 ToolBundle 提供。
- `ToolRuntime`：Host-owned 工具治理模块，作为 `ToolExecutor` 提供给 EngineWorker / Engine。它消费 Host 传入的业务 `ToolBundle`，生成 attempt-local effective `ToolBundle`，负责 policy、awaiting、truncation / fetch_more、语义级重复调用治理、通过 `ToolTraceDiagnosticEmitter` 发出工具诊断，以及工具级幂等。ToolRuntime Host accept path 是工具事实 canonical 写入所有者；ToolRuntime 必须通过 Host accept barrier 让工具事实先被 Host durable accepted，收到 accepted ack 后才能把结果返回给 Engine。EngineEvent ingest 不能为同一工具 outcome 再写第二条工具 canonical fact。
- `ToolTraceDiagnosticEmitter`：ToolRuntime 内部 typed interface，用于提交结构化工具诊断记录 / refs，供 tool trace projection 生成 hot JSON 与 cold JSONL。它不是 EventLog appender，不拥有 canonical fact，不写 audit，不直接写 trace 文件，也不更新 Run / Attempt 状态。
- `ToolExecutor`：Engine 可见的工具执行协议。Engine 只调用 `ToolExecutor.execute(...)`；Host / ToolRuntime 负责把工具注册、权限、截断、等待、幂等、审计和重复调用治理包装成该协议。
- `semantic duplicate tool governance` / `语义级重复工具调用治理`：Host / ToolRuntime 对同一个 Run 内模型复读导致的重复工具调用治理，目标是减少无意义 token 和工具执行浪费。它使用 run-local in-memory duplicate index；不治理跨 Run / 跨 Session 历史相似证据，也不把同一轮正常工具调用视为需要治理的问题。Engine 只处理结构性工具调用协议，不理解工具语义、业务幂等性、历史证据质量或重复读取是否有意义。
- `TruncationManager`：ToolRuntime 内的工具结果截断治理能力，按工具声明的 `ToolTruncateSpec` 工作，并负责生成可恢复的 truncation cursor descriptor 与 scope binding。Engine 不读取 `ToolTruncateSpec`，也不理解截断策略。
- `truncation cursor`：被截断工具结果的续读句柄，标识从哪个结果、哪个位置继续读。进入 messages 或 EventLog 后，必须可由 Host-governed durable descriptor、artifact ref 或等价 snapshot 恢复；不能只存在于远端进程内存。
- `scope_token`：`fetch_more` 使用的 opaque capability / scope binding，用来证明某次续读只允许访问对应工具结果的后续内容。它可以是持久化映射或可验证 token，但不能变成远端 ToolRuntime 的治理状态。
- `fetch_more`：Host / ToolRuntime 内置 framework tool，用普通 `@tool` 方式暴露和执行，用于通过 `cursor` 与 `scope_token` 读取被截断结果的后续内容。它不能有 Host / Engine 特化分支。
- `ToolAwaitingOutcome` / `wait record`：长事务或外部等待进入 Host 的边界。ToolRuntime 通过 Host accept path 提交 awaiting candidate；Host durable accepted 后同事务追加 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`，持久化 wait record，并让 Run 进入 `WAITING`、Attempt 进入 `SUSPENDED`。Engine 只消费已 accepted 的 awaiting / suspended 语义 refs；Engine `tool_awaiting` / `run_suspended` 只能作为 preview / diagnostic / idempotent confirmation，不拥有 wait record 或 WAITING 状态迁移。Host 通过统一 `resolve_wait` pipeline 创建新 Attempt 继续。
- `resolve_wait`：Host 的等待结果接收与治理入口，用于把 poll / callback / manual 带回来的长事务结果原子纳入 EventLog，并在通过校验后继续原 Run。它不是等待机制本身，不负责死等外部任务；结果未到时不应阻塞等待，应返回结构化错误或拒绝。它是短事务 command，最多只因 SQLite transaction / CAS / busy timeout 做短等待和重试。poll、callback、manual 等等待结果来源都必须走同一个 resolution pipeline，不能各自改 Run 状态。
- `retry(run)`：调用方主动发起的函数式 Host 操作，用于 confirmed failure / recoverable failure。它不重开原终态 Run，而是创建一个关联的新 Run；新 Run 可以按 policy 复用旧 Run 已接受工具事实，并创建自己的 Attempt。
- `replay(run)`：调用方主动发起的函数式 Host 操作，用于 final answer 的格式、schema、结构、输出 envelope 或引用格式违反输出 policy。它不重开原 `SUCCEEDED` Run；它创建一个关联的新 Run，默认复用旧 Run 已接受工具事实。replay 是 no-tool 结构修复调用，不重新执行工具，不新增工具事实。事实内容脏、幻觉、业务归因错误、证据不足或证据冲突不属于 replay 场景。
- `RunInputBuilder`：Host 内部组件，负责从当前 `USER_INPUT_ACCEPTED` canonical fact、当前 Run 语义 facts、连续性所需历史 canonical EventLog facts、memory snapshot、Service 场景参数、tool schemas snapshot 和 policy config 构造新的 `AgentRunRequest.messages`。它不能从 UI 临时文本、request 临时字段或 Session timeline 旁路读取当前 prompt。
- `Conversation Memory`：Host read model / projection，服务多轮追问连续性。它消费 canonical facts，可重建、可修复，不是事实真源。
- `Context Governance`：Host 对上下文预算、compaction、pinned state、tool facts、open questions、assumptions 和 compact 事件的治理 orchestrator。Host 应在 dispatch 前根据 provider-aware budget 主动触发 compact；Engine emit `context_compaction_requested` 是 provider context overflow 后的 reactive fallback，且 provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator / policy 记录预算并做 compact 决策。Context Governance 不直接写 memory、audit、trace 或 outbox projection；这些 projection 只消费已提交 EventLog。
- `compact events`：Host canonical event family，用于记录 context compaction 触发、成功或失败。当前设计包含 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`；它们解释为什么后续 Attempt 的 messages 被压缩或重建。
- `evidence anchor` / `provenance`：财报分析证据链的中立引用。长期归因必须能追到工具事实和 evidence anchor；summary 只能导航，不能替代证据。
- `lane`：Host 设计要求沉淀到 `dayu.runtime` 的层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的具名容量治理。它不绑定 Host、Run、Tool 或财报业务语义，不表达 Host truth、lease / fencing、Attempt owner、EventLog ordering 或 recovery proof。lane acquire 是可取消的耗时操作；调用方 / supervisor 退出时必须同时触发 Host cancel 与 lane cancel。
- `filelock`：`dayu.runtime.filelock` 提供对第三方 `FileLock` 的同步统一封装，用于多进程访问普通文件时的互斥保护。业务层、Host、Service、Fins 等不应各自直接封装或手写文件锁。
- `ToolsDiscovery`：暂定名，独立于 Host 的工具发现 / 注册组件，收集工具声明、provider 或配置绑定，生成业务 `ToolBundle` 并显式传给 Host。若后续放入 `dayu.runtime`，它只能依赖标准库和 `dayu.contracts`，不得 import 具体业务工具包。
- `ScenePrepare`：独立于 Host 的场景准备组件，根据 scene manifest 组装 system prompt 与场景约束，产出 typed scene inputs。若后续放入 `dayu.runtime`，它只能是通用 manifest assembly helper；具体财报 scene manifest、业务 prompt 文案和场景策略属于 Service / 业务配置。

`turn` 不用于描述 Engine / Runner 执行路径；如需表达用户视角的多轮对话，应在 UI / Service / Host 语义内明确其与 `session`、`run` 的关系。

`resume` 不表示恢复旧 Agent / Runner / EngineWorker 实例。`run_suspended` 或 `run_cancelled` 后若要继续原目标，Host 必须基于 canonical EventLog facts 构造新的 `AgentRunRequest.messages`，并用新的 attempt 重新进入 Engine。

## Runtime

`dayu.runtime` 是层中立运行期基础设施包，不属于 `UI / Service / Host / Engine` 任一业务层。

公共运行时能力应优先沉淀在 `dayu.runtime`，但不得把业务语义、Host 治理状态或 Engine 协议状态机放入 runtime。

`dayu.runtime` 当前已有以下层中立能力：

- 日志装配与日志 level。
- 取消等待 / race helper。
- `lane`：cross-process named semaphore / capacity guard。调用方显式传入独立 SQLite runtime lane DB 路径，并通过
  `LaneController` 获取、刷新和释放具名容量 claim；等待 acquire 支持 timeout、协作式 cancellation 与
  `Task.cancel()` 透传，controller close 会取消 pending acquire 并尽力释放当前 tokens。lane 只表达 runtime capacity
  claim，不保存 Session / Run / Attempt / EventLog / Tool / Fins 字段，也不承诺 FIFO、公平性、lease / fencing、
  Attempt owner、Host admission 或 recovery proof。

Host 设计要求以下层中立能力沉淀到 `dayu.runtime` 或保持为 runtime 边界约束：

- `filelock`：对第三方 `FileLock` 的同步 wrapper，只用于普通文件访问互斥。调用方传入显式 lock file 路径，可选择创建 parent directory，并通过 wrapper 自有 timeout / runtime error 语义处理 acquire 失败；它不提供 async wrapper、stale takeover、强制 break lock 或锁文件删除。`dayu.runtime` 不能依赖 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 等项目内上层 package；统一封装纯 infra 第三方依赖不违反这一边界。业务层不得散落 `from filelock import FileLock`，也不得用 file lock 兜底数据库事务、EventLog 顺序或 Host 状态机。
- `ToolsDiscovery`：工具发现 / 注册的层中立装配边界。它可以接收外部传入的 provider / 配置绑定并产出 `ToolBundle`，但不能持有 Host 状态，不能 import 具体业务工具包，也不能决定 Run / Attempt 生命周期。具体 adapter、provider 注册生命周期和业务工具扫描不属于 Host Phase 1。
- `ScenePrepare`：scene manifest 的层中立组装边界。它可以把 manifest 与模板输入组装为 typed scene inputs，但不能内置财报业务规则、不能 import Service / Fins / Host，也不能绕过 Service 把场景 prompt 写入 Host 状态机。具体 manifest schema、财报 prompt 文案和业务场景策略不属于 Host Phase 1。

## 日志与可观测性

Dayu 的日志用于诊断系统执行过程，不承担 UI 输出职责。面向用户的命令行输出、smoke 汇总、交互界面展示应走各自的 UI / stdout 通道；日志只表达系统内部执行路径、细节、告警和错误。

日志级别语义如下：

| 级别 | 用途 |
| --- | --- |
| `DEBUG` | 看清执行细节。用于 Engine / Runner 的有界策略分支、事件分类、计数、finish reason、usage token、retry 判断等诊断信息。不得输出大 prompt、大 tool result、delta 全量、provider secret 或大段响应。 |
| `VERBOSE` | 看清执行路径。用于 Engine run 开始 / 结束、iteration 边界、Runner 调用开始 / 结束、tool loop 进入 / 退出、fallback / continuation 与 terminal 产出等骨架日志。它应比 `DEBUG` 更安静，适合人工跟踪一次 run 的主路径。 |
| `INFO` | 汇报重要信息。用于进程启动、smoke 摘要、run finished 摘要等调用方或运维人员需要知道的非异常信息。生产默认 `INFO` 应保持克制。 |
| `WARN` | 汇报可恢复异常。用于 provider 临时失败后 retry、可降级协议差异等需要关注但本次执行仍可继续的情况。 |
| `ERROR` | 汇报本次操作失败。用于 Engine run failed、provider 协议错误导致执行失败等。 |
| `CRITICAL` | 汇报系统 invariant / contract 被破坏。用于按设计绝不应发生的断言级事件，例如 EngineEvent stream 结束但没有 terminal event。 |

`dayu.runtime.log_levels` 是层中立日志 level 数值真源，统一定义 Dayu 使用的标准级别整数常量与 `VERBOSE=15` 数值；该模块无装配副作用，不注册 stdlib level name、不安装 handler、不读取配置。

当前 `dayu.runtime.log` 负责把 `VERBOSE=15` 注册为 stdlib level name `VERBOSE`，位于 `DEBUG=10` 与 `INFO=20` 之间。启用 `DEBUG` 时应同时看到执行路径和细节；启用 `VERBOSE` 时应主要看到执行路径骨架；启用 `INFO` 时不应看到单次 iteration / tool call 的内部过程。

执行路径日志的归属原则：

- Engine 负责记录自身状态机路径：run 开始、iteration 边界、Runner 调用、Runner event 分类后的关键决策、tool loop、fallback、continuation、terminal。
- Runner / provider 层负责记录传输诊断信息：HTTP attempt、响应状态、provider request id、retry / backoff、SSE idle heartbeat / timeout 等。
- Engine / Runner 日志不得泄漏 provider secret、完整 prompt、完整工具参数、完整工具结果、delta 全量或大段响应。

日志字段命名统一使用以下词汇：

- `run_id`：一次 Engine run 标识。
- `iteration_id` / `iteration_index`：Engine 内一次模型调用与后续决策循环。
- `provider` / `request_id`：Runner / provider 传输诊断标识。

## Contract Ownership

公共契约只承载层间协作协议，不承载业务语义真源、治理语义真源或某一层的内部状态机。

设计任何 contract 时，必须先回答语义真源在哪一层：

- UI 展示语义归 UI；公共契约只表达 UI 需要调用下层的稳定输入输出。
- Service 业务受理语义归 Service；公共契约不沉淀业务流程细节。
- Host 治理语义归 Host；session / run 生命周期、取消、恢复、工具治理等不进入 Engine 契约。
- Engine 执行语义归 Engine；Runner / Agent 事件流和模型交互状态机不向上泄漏内部实现。
- 财报领域语义归领域能力边界；公共契约不直接表达财报存储、解析或指标规则。

因此，`dayu.contracts` 只能放跨层都需要理解的协作对象，例如工具调用请求、工具执行结果、取消观察 token 等。若一个类型只有某一层理解，或者携带该层私有状态，它应留在该层内部；如果多层都需要读写它，应优先重新审视边界，而不是把它提前公共化。

## 工具定义与执行边界

工具能力分为声明、治理和执行三个边界。

- `@tool(...)` 是工具声明入口，用于在工具现场同源声明 `ToolSchema`、截断声明、展示 metadata、标签和单工具 callable。
- `ToolDefinition` 是 Host / ToolRuntime 的装配输入，包含 schema、truncate、display、tags 与 `ToolCallable`；它不进入 Engine request，也不作为 Engine 稳定接口。
- 外部工具注册组件是工具发现 / 注册边界，产出业务 `ToolBundle` 并通过 `HostToolingOptions` 传给 Host construction。Host 包不得 import 具体业务工具模块；新增工具应通过外部注册组件 / 配置 / Service composition 接入。
- `fetch_more` 不由外部业务 `ToolBundle` 提供；ToolRuntime factory 根据 TruncationManager 注入 framework tool，生成 attempt-local effective `ToolBundle`。RunInputBuilder 投影给 Engine 的 `tool_schemas` 必须来自 effective ToolBundle。
- `ToolCallable` 是单工具调用协议，形状是 `async (call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome`。工具函数可以通过闭包捕获 Web client、仓储、manager 等 Host 私有依赖。
- `ToolExecutor` 是 Host / ToolRuntime 治理后的 batch 执行入口，形状是 `execute(BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。Engine 只调用这个入口，不调用单工具 callable。

Host 接收业务 `ToolBundle`；ToolRuntime factory 生成 effective `ToolBundle`，把其中的 `ToolSchema` 投影给 Engine，并把 `ToolCallable` 包装进受治理的 `ToolExecutor`。权限、审批、限流、并发、内部 timeout、审计、长事务 awaiting、orphan cleanup 和工具级取消都属于 Host / ToolRuntime；`dayu.contracts` 不提供默认执行器，也不定义 batch 内部执行策略。

Engine 只接收 `tool_schemas` 和 `tool_executor`。Engine 不导入、不持有、不分支判断 `@tool`、`ToolDefinition`、`ToolCallable`、具体工具实现或工具运行时治理对象。
