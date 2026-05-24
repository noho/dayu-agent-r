# Host 开发手册

本文档是 `dayu.host` 包的开发手册，只写当前代码已实现的 Host 接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制和扩展点。Host 稳定术语与边界以当前代码和 `docs/host/design.md` 为准。

## Agent更新约束【必须遵守】

- 本文档只服务 Host 开发者理解当前已实现的 Host 层契约，不写用户手册、安装运行命令、测试清单或文件级流水账。
- 本文档只记录当前代码已实现的 Host 接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制和扩展点。
- 本文档不写过程状态，不写路线图或时间表，不写实现细节，只保留稳定说明。
- Host README 的事实来源是 `dayu.host` 当前代码与 `docs/host/design.md`；设计文档中尚未由代码承载的内容不得写成当前能力。
- Service-facing public contract 与内部低层 / diagnostic 路径必须区分；普通 Service 不应依赖 durable store、dispatch scheduler、ToolRuntime factory、低层 command handle 或 run-level diagnostic stream。

## 设计意图

Host 是 `UI -> Service -> Host -> Engine` 分层中的治理边界。Service 负责业务入口、身份解析、场景装配和调用 Host public contract；Host 负责 Agent 运行宿主边界、状态治理、持久化、admission、dispatch、取消、重试、重放、等待恢复、ToolRuntime accept barrier、memory projection、context compaction、payload descriptor 和 terminal summary continuity；Engine 只执行单次 `AgentRunRequest`，不拥有 Session / Run / Attempt 治理状态。

Host 的核心设计意图是让 LLM 处于宿主强约束下运行：

- `Session`、`Run`、`Attempt`、`EventLog` 与同事务状态索引是 Host 治理真源。
- 同一 Session 的 active Run 由 Host admission 约束；queued Run 是 durable state，不是内存队列。
- EngineEvent 只是 Host ingest 的输入；Run / Attempt 终态必须由 Host 校验后写入 EventLog 与状态索引。
- 工具结果、工具等待、重复调用治理和截断治理必须经过 Host-owned ToolRuntime 与 accept barrier。
- Memory snapshot、timeline、projection、trace、outbox 与 diagnostic 都是派生视图，不能反向驱动 Run / Attempt 状态迁移。
- Host 不承载财报业务语义，不直接读取或管理财报原文仓储；财报文档存取属于 `dayu.fins.storage` 边界。

## 架构边界

依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

Host 可以在 LocalProxy 边界调用 Engine public entry；Engine 不导入 Host，不读取 Host durable store，不管理 Session / Run / Attempt。Host 不导入 `dayu.service`、`dayu.ui` 或 `dayu.fins`，也不把财报业务规则写入 Host 状态机。

Host 内部职责按语义分层：

- Public API：定义 request、snapshot、status、error、context、opener options、HostEvent typed view 和异步 `Host` 协议。
- Opener / composition root：由 `open_host(options)` 装配 durable store、admission、dispatch scheduler、active worker registry、memory catch-up、context compaction 和本地 worker typed port。
- Admission：负责 Session active Run 判定、queue / steer、cancel、retry、replay、wait resolution 与幂等边界。
- EventLog / state transition：负责 canonical facts、全局 `event_sequence`、Run / Attempt / wait / dispatch 状态索引的同事务推进。
- Dispatch：只消费已提交的 accepted / queued / pending dispatch facts，负责本地 lane capacity、worker accept、cancel 传播和 EngineEvent ingest 编排。
- RunInputBuilder：只从 durable EventLog、Run / Attempt / dispatch snapshot、memory snapshot、compact artifact 和 ToolRuntime handle 构造 `AgentRunRequest`。
- ToolRuntime：负责业务工具 bundle 投影、工具调用治理、截断、等待、重复调用治理和工具事实 accept barrier。
- Conversation Memory：只消费 committed canonical EventLog facts，维护可重建的 Session memory read model。
- Context Governance：负责上下文预算、compact 编排、candidate 校验与 compact 事件收口，不直接改写 memory snapshot。

## Public Contract

普通 Service-facing 入口是 `open_host(options)` 返回的异步 `Host` handle。Service 只持有该 handle，不持有 durable store、command handle、scheduler、registry、wakeup port 或 ToolRuntime 内部对象。

包根 `dayu.host` 当前导出这些稳定类别：

- public constants：Host event stream limit 常量，以及 wait record、wait adapter、external job、provider status ref 等 wait / payload 引用字段的公共长度上限常量。
- opener / handle：`open_host`、`OpenHostOptions`、`Host`、`HostClosedError`。
- construction baseline：`OrdinaryRunExecutionBaseline`、`CompactorRunnerBaseline`、`LocalEngineWorkerFactory`、`LocalEngineWorker`、`LocalWorkerHandle`。
- session / deferred request and snapshot：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`SessionSnapshot`、`SessionSlotRef`、`SessionStatus`、`PurgeSessionResult`。
- run request / snapshot：`SubmitFollowupRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`RetryRunRequest`、`ReplayRunRequest`、`RunSnapshot`、`FollowupSnapshot`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`SourceRunRelation`。
- wait request / outcome：`ResolveWaitRequest`、`ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome`、`ResolveWaitOutcome`、`WaitResolutionSource`、`WaitAdapterKey`、`WaitProviderStatusRef`。
- event / read view：`HostEvent`、`HostEventClass`、`HostEventKind`、`HostTerminalStatus`、`HostFinalAnswerView`、`HostStreamCursor`、`TerminalResultSummary`、`OutboxSummary`、`HostPayloadRef`。
- error / context：`HostApiError`、`HostApiErrorCode`、`HostApiErrorDetail`、`SteerConflictDetail`、`HostCallContext`、`OperationContext`、`AuthorizationClaim`、`HostMetadataEntry`。
- tooling construction：`HostToolingOptions`、`ToolBundleSourceKind`、`ToolBundleSourceRef`、`FrameworkToolName`、`FrameworkToolPolicyView`、`default_framework_tool_policy_view`。

`Host` handle 提供的普通 public 方法是：

- `ensure_session(request)`：按 `(scope, slot_key)` 原子确保当前 Session。
- `create_session(request)`：显式创建新 Session，可选择重绑定 slot。
- `get_session(session_id)`：读取 Session snapshot。
- `get_run(run_id)`：读取 Run snapshot。
- `submit_followup(session_id, request)`：提交普通 queue 或 steer follow-up。
- `cancel_run(run_id, request)`：取消单个可治理 Run，覆盖未启动、pre-dispatch、active、waiting 与 recovering 状态。
- `cancel_session_runs(session_id, request)`：取消 Session 下可治理的非终态 Run，覆盖未启动、pre-dispatch、active、waiting 与 recovering 状态。
- `retry_run(run_id, request)`：基于失败源 Run 创建关联的新 Run。
- `replay_run(run_id, request)`：基于成功源 Run 创建 no-tool 结构修复 Run。
- `resolve_wait(wait_id, request)`：接收外部 wait result，并由 Host 恢复或收口 Run。
- `close_session(session_id, request)`：关闭 Session 的新输入入口，不取消既有 Run。
- `watch_session_events(session_id)`：订阅 Session-level Host-owned typed events。
- `close()`：关闭当前 opener runtime，不写 cancel / failed terminal facts。

`purge_session`、`PurgeSessionRequest` 与 `PurgeSessionResult` 仍属于包根 deferred 契约；当前语义是 structured unsupported：返回 `UNSUPPORTED_OPERATION`，不追加 EventLog，不写幂等记录，也不删除 Host durable facts。

## Opener 与 Options

`OpenHostOptions` 是普通本地多轮 Host 的 construction boundary。它显式接收 Host durable SQLite 路径、artifact root、durable payload inline threshold、SQLite busy / retry policy、runtime lane 配置、本地 worker factory、ordinary run execution baseline、业务工具选项、context budget policy、compactor baseline、memory projection policy 和 truncation manager 开关。

`ContextBudgetPolicy` 是 ratio-first typed policy：调用方显式传入 `context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、compaction 次数上限与 `policy_ref`，Host 内部按 `context_window_size * ratio` 派生 soft / hard threshold token 数。`OpenHostOptions` 的字段名保持 public surface freeze；Host policy 本身不暴露输出预留、safety margin、显式 hard threshold token 或 minimum protection token 字段。

`open_host(options)` 进入时会装配：

- Host durable store 与内部 command handle。
- 共享 `ActiveWorkerRegistry`，用于 active worker cancel 传播。
- `HostDispatchScheduler`，用于 accepted / queued / pending dispatch wakeup。
- startup recovery scan，用于在 ready 前基于 durable truth 收口 positive orphan 并创建可恢复 Run 的 pending dispatch。
- admission service，负责 public command 的 durable mutation。
- memory projection catch-up port，供 dispatch 前与 close 阶段追平 memory projection。
- Host-owned LLM compactor baseline，包含 runner 配置、compactor AgentPolicy、compact artifact root、Service 按 execution profile compactor scene 装配的 system prompt，以及 Service 按 compactor baseline prompt asset 读取的 user prompt template，供 Context Governance 执行 compact。

调用方不传入也不依赖 Host runtime 诊断 id，不直接持有 scheduler、durable store、active registry、compactor port 或 wakeup port。`Host.close()` 与 async context manager 退出只关闭当前 opener runtime；关闭顺序是 public lifecycle guard、scheduler、memory projection flush、durable store。重复关闭幂等；关闭后的 public handle 方法抛出 `HostClosedError`。

## Session 契约

`Session` 是持续会话上下文。状态集合：

- `OPEN`：允许创建新 Run、queue follow-up、steer active Run、读取 snapshot 与 event stream。
- `CLOSED`：关闭新输入入口；既有 Run、EventLog、memory、timeline 与 read path 保留。

`ensure_session(scope, slot_key)` 按 slot 原子创建或复用当前 Session。`create_session(client_request_id, bind_slot=...)` 表示显式新建动作；绑定 slot 时会把 `(scope, slot_key)` 重绑定到新 Session，旧 Session 不删除、不改写 EventLog。

`close_session` 是状态迁移，不是 cancel、purge 或 UI hide。它不取消 active / queued / waiting Run，不清空 EventLog，不删除 memory。需要停止执行时，调用方必须显式使用 `cancel_run` 或 `cancel_session_runs`。

## Run 与 Attempt 状态机

`Run` 是用户可见目标，`Attempt` 是 Host 为完成某个 Run 派发给 EngineWorker 的一次执行。旧 Attempt 永不 resume；steer、wait resolution、replay、retry 和恢复执行都会创建新的 Attempt 或新的关联 Run。

Run 状态：

- `ACCEPTED`：输入已 durable accepted，等待 scheduler / pre-start governance。
- `QUEUED`：输入已 durable accepted，但同 Session 有 active 或 start-blocking Run。
- `RUNNING`：Run 已进入 active Attempt lifecycle；当前 Attempt 可以是 `STARTING` 或 `RUNNING`。
- `WAITING`：Attempt 已因工具等待挂起，Run 等待 Host `resolve_wait` 或 cancel。
- `CANCELLING`：Host 已接受取消并向 active worker best-effort 传播。
- `RECOVERING`：Host 已收口旧 Attempt，正在基于同一 Run 的 canonical facts 创建新的 recovery Attempt；新 recovery dispatch 提交前可被 cancel 直接收口为 `CANCELLED`，不追加旧 Attempt terminal fact。
- `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST`：Run 终态。

Attempt 状态：

- `STARTING`：Host 已创建 Attempt 与 dispatch record，worker 尚未确认接住。
- `RUNNING`：worker 已接受 dispatch。
- `SUSPENDED`：工具等待挂起，对应 Run `WAITING`。
- `STEERED`：旧 Attempt 被 steer 收口，同一 Run 创建新 Attempt。
- `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST`：Attempt 终态。

关键不变量：

- 同一 Session 同时最多一个 active Run。
- queued Run 按 accepted `event_sequence` FIFO promotion。
- Run terminal fact 与 Run 终态索引必须同事务提交。
- Attempt terminal fact 与 Attempt 终态索引必须同事务提交。
- `execution_id` 用于拒绝迟到 Attempt 事件，不是 lease、fencing token 或远端 ownership。
- Engine final answer、failure、cancelled、lost、context overflow 与 awaiting confirmation 都必须经 Host envelope identity 和 durable state 校验后才能影响 canonical facts。

## Admission 路径

普通聊天式输入统一通过 `submit_followup(queue)` 进入 Host admission。该路径在同一 durable transaction 内写入用户输入 canonical fact、Run accepted fact 与必要状态索引；commit 后唤醒 scheduler。

`submit_followup(queue)` 的语义：

- 无 active / start-blocking Run 时创建 `ACCEPTED` Run。
- 有 active / start-blocking Run 时创建 `QUEUED` Run。
- `tool_names=None` 表示使用 construction-time 全量业务工具；空集合表示禁用业务工具；非空集合表示只启用指定工具名。
- `runner_spec`、`runner_options`、`agent_policy` 是完整 typed override；缺省时使用 opener 的 ordinary baseline。
- unknown tool name 在 canonical facts 写入前返回结构化错误。

`submit_followup(steer)` 的语义：

- 必须指定 `target_run_id`。
- 只接受同 Session 当前 active `RUNNING` 或 `WAITING` Run。
- 在同一 Run 内追加 steer 输入，并创建新的 Attempt / dispatch record。
- 目标缺失、Session 不匹配或状态非法时返回 `HostApiError`，可携带 `SteerConflictDetail`。

幂等作用域按操作语义固定：session 创建、follow-up、cancel、retry、replay 与 wait resolution 都使用显式 request id 或 idempotency key。显式请求字段不得塞入 metadata 或 extra payload 来影响语义 digest。

## Dispatch 路径

dispatch 只消费已提交事实。标准本地执行路径是：

```text
submit_followup(queue)
  -> durable admission commit
  -> scheduler wakeup
  -> pre-start context governance
  -> RUN_STARTED / ATTEMPT_STARTED / dispatch record commit
  -> runtime lane acquire
  -> durable recheck
  -> LocalEngineWorker accept
  -> ATTEMPT_RUNNING
  -> consume EngineEvent stream
  -> EngineEvent ingest closes or advances Run / Attempt
```

runtime lane 只表达资源容量，不表达 Host ownership、lease、fencing、EventLog ordering 或 recovery proof。worker accept 前后都要依赖 durable recheck 与 Host state transition；worker stream 的 finally 路径负责 active registry 注销、worker handle close 与 lane release。

Dispatch scheduler 打开时会注册当前 Host instance liveness row：`host_instance_id` 使用当前 opener runtime 诊断 id，`process_start_token` 是独立高熵随机值，不从 handle id、pid 或时间派生。后台 heartbeat 只刷新当前 scheduler 自己的 instance row；关闭时 best-effort 标记 `STOPPING` / `STOPPED`，这些状态只服务 lifecycle 诊断和 recovery 输入，不是 lease、fencing 或 takeover proof。`dayu.host.recovery_process` 提供只读 orphan proof classifier：只有 durable owner、stale heartbeat、进程证据与策略时间共同满足 positive proof 时才输出可接管证明；heartbeat stale 单独不构成 proof，classifier 不写数据库、不推进 Run / Attempt 状态。`dayu.host.recovery` 的 startup scanner 读取 durable Run / Attempt / dispatch / liveness truth；`ACCEPTED`、`QUEUED`、`WAITING` 保持原状态，其中 `ACCEPTED` 与 `QUEUED` 会在 scan 事务提交后唤醒 queue promotion，让 pre-start governance 重新接管；`RUNNING` / `CANCELLING` 只有 positive orphan proof 与 CAS recheck 同时成立才收口旧 Attempt；可恢复的 `RUNNING` orphan 或既有 `RECOVERING` Run 会在 recovery dispatch count 未超限时创建新的 Attempt / execution / dispatch record 并唤醒 scheduler，超限或不可恢复时转为 `LOST`。

worker startup timeout、worker accept failure、worker stream crash 和未知 terminal 都由 Host closeout 为结构化终态或 diagnostic。worker stream 在 Host 已请求 active cancel 后 clean EOF 时，Host 以 cancel terminal 收口；非取消 clean EOF 仍按 lost closeout 处理。terminal closeout 后会触发同 Session queued Run promotion。

## EventLog 与 HostEvent

EventLog 是 append-only ledger。`canonical_fact` 子集是恢复、memory、tool governance、terminal summary 和状态索引的事实来源；非 canonical 的展示事件、`diagnostic` 与 `projection_signal` 只能服务展示、诊断或投影追平。

`event_sequence` 是 Host 全局单调游标，供 read model、watch、projection catch-up、memory snapshot cursor 和 outbox 类能力对齐。EventLog append 与必要状态索引更新必须在同一 transaction 内完成。

`watch_session_events(session_id)` 是普通 Service-facing session-level live event entry，返回 Host-owned typed `HostEvent` async iterator。它不接收 cursor，不做离线补读；terminal event 不结束 iterator；consumer 取消订阅只关闭本次 watch，不取消 Run、不写 EventLog。

`HostEvent` 是比 EventLog 更克制的 public view：

- `PROGRESS` 表达非终态进度。
- `SUCCEEDED` 内联 `HostFinalAnswerView`。
- `FAILED` 提供 typed 展示错误字段。
- `CANCELLED` 提供 typed cancel reason。

低层 `stream_run_events` 是 run-level diagnostic / 低层测试路径，不属于普通 Service-facing 包根 contract。它暴露的是 EventLog view 和 cursor 语义，不替代 `watch_session_events`。

## ToolRuntime

`HostToolingOptions` 是 Host construction 阶段接收业务工具的 typed boundary。业务工具发现、provider 绑定、包入口扫描和 Service composition 发生在 Host 外部；Host 只接收已经装配好的 `ToolBundle` 与来源引用，不导入具体财报工具模块。

ToolRuntime 的稳定语义：

- 将业务 `ToolBundle` 与 framework tool policy 投影为同一个 effective tool bundle。
- 同一个 `ToolRuntimeHandle` 同时提供 Engine 可见 `tool_schemas` 与实际 `ToolExecutor`，避免 schema / executor 不同源。
- no-tool replay 或显式禁用工具路径输出空 schema、no-tool executor 和禁止工具调用的 Agent policy。
- 工具结果、工具失败、工具取消、工具等待、治理拒绝、重复调用复用与截断结果必须经过 Host accept barrier。
- accept barrier 校验 run / attempt / execution identity、schema digest、payload descriptor、幂等与 stale execution，接受后写入 canonical tool result facts。
- side-effect 或付费工具必须具备工具级幂等依据；缺失时不调用实际 callable。
- `ToolTruncateSpec` 是 declaration/effective 分离契约：工具声明允许启用截断但省略策略 limit 或 TTL，层中立 runtime helper 按 policy defaults 补齐 effective spec 后交给 ToolRuntime 消费。
- ToolRuntime 只在显式 truncation spec 或 truncation manager 存在时改写 LLM 可见工具结果；durable payload inline threshold 不作为 LLM inline result 限制。
- truncation cursor 是 run-scoped、短生命周期、单次使用的本地补读引用；一次 `fetch_more` 成功后同一 cursor 即失效。
- `fetch_more` 是 framework tool 预留名，默认保留但不启用；业务工具不得占用预留 framework tool 名。

ToolRuntime 内部 factory、run-scoped duplicate governance registry、truncation manager 和 accept port 不从 `dayu.host` 包根导出。

## Wait 与 Resolve

工具等待由 Host accept path 创建 active wait record，并把 Run / Attempt 推进为 `WAITING` / `SUSPENDED`。Engine `TOOL_AWAITING` 或 `RUN_SUSPENDED` 事件只能作为 Host 已接受等待事实的 confirmation；Host 不从 EngineEvent 临时创建 wait record。

`resolve_wait(wait_id, request)` 接收外部等待结果。`ResolveWaitRequest` 必须包含 UTC-aware `observed_at`、结果来源、幂等键和强类型 outcome。

当前 outcome 语义：

- completed 或工具级 cancelled：关闭 wait record，写入恢复所需 canonical facts，创建新的 resume Attempt，并唤醒 dispatch。
- failed：关闭 wait record，并把 Run 收口为 `FAILED`。
- lost：写入 lost 工具事实，并把 Run 收口为 `LOST`。

late result、terminal Run 上的结果或已取消 wait 的结果不会恢复 Run；这些路径只写入受控 diagnostic 或返回结构化幂等冲突。Wait poller 对已取消 wait 的 adapter abandon 只保留当前仍可观察且已成功通知的去重记忆；adapter abandon 失败会记录 warning，并在后续 poll 中继续重试。

## Memory Projection

Conversation Memory 是 Session-level read model，不是 Host governance truth。它只消费 committed canonical EventLog facts，维护 stable layer、history pool、`evidence_backed_facts`、working assumptions、recent raw turns、episode summaries、minimum preserve continuity 和 projection cursor。

`MemoryProjectionPolicy` 使用 `context_window_size` 加 ratio / floor / cap 模型派生 stable layer、history pool 与 raw turn 的内部 size units；调用方只表达策略比例和上下限，Host memory projection 内部负责计算 effective size units。

RunInputBuilder 通过 memory snapshot provider 接线读取 memory snapshot，构造 `AgentRunRequest.messages` 时必须带着 snapshot cursor 与 policy digest；snapshot 缺失、损坏或滞后超过策略阈值时，Host 进入 projection repair path。dispatch 前会追平 memory projection；catch-up 失败或 snapshot 大滞后时走 rebuild / retry，不把 lag repair 映射为 Run / Attempt 终态迁移，也不把 Run 推入 `RECOVERING`。stable fact block 的稳定 id 是 `stable:evidence_backed_facts`，渲染时必须包含 `claim_text`、`evidence_refs`、`evidence_kind`、extraction operation ref 和 extraction event id / sequence，不能退化为 digest-only fact。evidence-backed facts 按 normalized claim text、排序后的 canonical evidence refs 与 evidence kind 去重；重复项保留较新的 extraction event sequence 并记录 superseded diagnostic。open questions 按 normalized text 去重，working assumptions 按 normalized assumption summary 去重后再进入 policy-bounded working set；重复项保留较新的 committed EventLog view。ordinary Run 和 compactor 只消费 policy-bounded fact working set，不把历史 facts 全量注入。minimum preserve item 在 recent raw turns 之后、episode summaries 之前作为 continuity block 注入，并渲染 label、text、source refs 与 preserve reason；它不进入 stable facts，也不保留整段长输入。minimum preserve 若已被后续 stable fact 或 episode summary 覆盖，会从可见 continuity working set 中移除。episode summaries 只保留 policy-bounded recent summaries；更旧 summary 通过 refs / diagnostics 保持可解释，不继续渲染全文。

Memory 的边界是 Host-neutral：它不导入 Engine / Fins / Service / UI，不表达财报业务字段，不让 assistant final answer、用户输入、working assumption 或 episode summary 自动成为 evidence-backed fact。`TOOL_RESULT_ACCEPTED` 只提供 accepted tool evidence 的 canonical source；stable evidence-backed facts 采用 compaction-gated extraction，只从 accepted `CONTEXT_COMPACTED.evidence_backed_fact_candidates` 物化，并使用该 `CONTEXT_COMPACTED` event 的 id / sequence 作为 provenance。accepted tool evidence 没有通过 compact accept barrier 的 fact candidate 时只记录诊断，不合成 fallback fact；minimum preserve candidates 只进入 continuity。没有 compaction 的短链路追问继续依赖 recent raw turns / older raw turns / 已有 memory，这只是 continuity，不是 stable fact。

## Context Compaction

Context Governance 是 Host 责任。它根据 `ContextBudgetPolicy`、conservative estimator、memory snapshot、compact material pack、当前用户输入和 compact artifact refs 进行上下文预算治理。compact input 使用与 RunInputBuilder 同源的 ordinary input material block view；segment selection 在给定 trigger、input cursor、memory snapshot cursor、policy digest 与 material list 时确定性输出 selected block ids、excluded reason codes 与 selection digest。proactive pre-start material 会补入当前输入 cursor 之前、当前 Session 内、未被 stable fact / compact artifact 表示的 bounded accepted tool evidence；proactive selection 排除 current input anchor、protected recent raw turns floor、stable input 和已充分代表的 block；reactive selection 消费冻结的 overflow material list。`CompactMaterialPack` 由 selected segment、memory stable view、inline delta repair view、accepted evidence material 和 bounded current input anchor 构造，stable input、history input、accepted tool evidence input 与 current input anchor 分区使用 prompt-local labels，Host 内部用 provenance map 把 labels 映射回 canonical source refs / evidence refs；LLM-facing JSON 不暴露 EventLog ledger wrapper、payload descriptor、digest、cursor 或 Host provenance key。selection 没有 accepted tool evidence 时使用显式空 evidence input。

Runner usage 进入 Host 后只写 `USAGE_REPORTED` projection signal，并附带 Session / Run / Attempt / execution、policy ref、estimator digest、估算输入 token 与 observation digest 等诊断字段。usage 是 post-call observation，只用于后续估算校准、diagnostic 和后续治理参考；缺少 policy、input event 或估算失败时 projection 仍提交为 `estimate_unavailable`，不改变当前 Run / Attempt 状态，也不回改当前 dispatch decision。

当前已实现两类 compaction 路径：

- proactive：dispatch Attempt 前执行输入治理，必要时写入 compact request / compacted / failed canonical facts，再创建 Attempt。
- reactive：Engine 报告 context compaction required 后，由 Host 校验 attempt / execution identity，按 policy 关闭当前 Attempt，执行 bounded compaction operation，并用新的 Attempt 继续。

LLM compactor 只提出 structured candidate；Host 负责 prompt-local label 校验、canonical provenance 映射、质量校验、proactive 预算硬阈值校验、artifact 写入、canonical event 写入和状态推进。compactor system prompt 与 AgentPolicy 来自 Service 按 execution profile compactor scene 的装配结果，user prompt template 来自 Service 按 compactor baseline prompt asset 的读取结果；Host 不读取 prompt config，只把 `CompactionRequest` 渲染为 typed data block 并替换 user template 中的 compaction request 占位符。compact 后预算按统一 Host token 估算常数计算，覆盖 structured summary 文本、pinned patch 文本、fact claim、minimum preserve 文本、当前输入、保留的 recent refs、canonical evidence refs、evidence-backed fact refs、已有 summary refs 与 post-compact 系统提示的保守估算，不用 hard threshold 反向截断估算值。reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源；若真实 recovery dispatch 再次触发 Engine overflow，可在 `max_reactive_compactions_per_run` 范围内继续下一次 reactive compact，超过上限后 fail closed；reactive compact request 会把 overflow 当时的 frozen material list digest 和 frozen material refs 写入 durable payload，后续 compaction request 与 pass queue 均以该冻结列表为输入边界；同一 reactive operation 内的 material pass 共享 proposal attempt 预算，只有所有 pass 成功后才提交一个 merged `CONTEXT_COMPACTED`，任一 pass 最终失败只提交一个 `CONTEXT_COMPACTION_FAILED`。compactor 的 Engine runner 调用受独立 timeout 边界约束，并接收 Host lifecycle 的真实 cancellation token：proactive compaction 通过 durable Run 状态观察 request 是否失效，reactive compaction 复用 Engine envelope 的 run-local token。非 final outcome 的错误摘要会先脱敏，`finish_reason=length` 的 final proposal 视为截断脏 proposal，不会被接受为 compact 成功。质量校验会拒绝缺失 accepted tool evidence coverage、非法 pinned state patch、越权 evidence-backed fact candidate，以及 source refs 不在 compact material provenance map 内的 minimum preserve item。compact 不改写历史 EventLog facts，不让 summary 替代 evidence-backed extraction，也不直接写 memory snapshot。memory 是否吸收 compacted summary、fact candidate 或 minimum preserve item 由 memory projection policy 消费已提交 facts 决定。

## Payload 与 Terminal Continuity

Host payload descriptor 用于把较大或需要引用的 payload 从 EventLog inline JSON 中分离出来。当前 helper 支持按 EventLog payload ref 解析 SQLite payload descriptor，并校验 descriptor、digest 与 JSON object 形状。

terminal summary continuity 的稳定语义是：RunInputBuilder 和 memory projection 可以从 terminal summary 或 `RUN_SUCCEEDED` payload 中按策略提取 assistant summary，形成后继输入 continuity。该 helper 只读取受控字段，不从 UI 临时文本、provider raw payload 或未持久化上下文恢复回答。

`HostFinalAnswerView` 只在 public `SUCCEEDED` terminal HostEvent 中内联最终回答。失败和取消 terminal event 不携带 final answer。

## 低层与 Diagnostic 路径

以下路径存在于内部模块或低层测试 / diagnostic 边界，不是普通 Service-facing contract：

- 低层 command handle factory 与 command handle options。
- 内部新 Run admission primitive 和 `start_run`。
- run-level `stream_run_events`。
- durable store、transaction runner、schema、state row codec、payload table helper。
- dispatch scheduler、ToolRuntime factory、projection runner、memory repair runner。
- recovery scanner、orphan proof classifier、Host instance liveness helper 与 startup recovery diagnostic。
- `HostLocalExecutionOptions`、low-level local execution composition helper 与 run input provider internals。

普通 Service 通过 `open_host(options)` 与异步 `Host` handle 使用 Host。需要诊断 EventLog 或 run-level stream 时，应在内部工具或测试边界显式导入对应模块，不应把这些路径提升为业务 public API。

## 扩展点

- 新业务工具：在 Host 外部装配 `ToolBundle`，通过 `HostToolingOptions` 传入 Host construction；不要让 Host 扫描业务包或导入具体财报工具。
- 新本地执行适配：实现 `LocalEngineWorkerFactory` / `LocalEngineWorker` / `LocalWorkerHandle`，通过 `OpenHostOptions.worker_factory` 装配。
- 新 Engine runner baseline：通过 `OrdinaryRunExecutionBaseline` 或 per-run typed override 提供完整 `RunnerSpec`、`RunnerCallOptions` 和 `AgentPolicy`。
- 新 context compaction 能力：通过 `ContextBudgetPolicy` 与 `CompactorRunnerBaseline` 装配 Host-owned compactor，不把 compact 生命周期放入 Service 或 UI。
- 新 memory projection policy：扩展 Host-neutral memory policy 与 projection consumer，仍以 committed EventLog facts 为输入。
- 新 projection / sink / trace：消费 EventLog cursor 和 projection checkpoint，不写 canonical facts，不改变 Run / Attempt 状态。
- 新财报数据能力：在 `dayu.fins.storage` 仓储协议与实现内扩展；Host 和 Engine 不直接读取财报文件或数据库。

## 代码阅读顺序

1. `dayu.host.__init__` 与 `dayu.host.api`：理解包根 public contract、request / snapshot / event / error 类型。
2. `dayu.host.open_host`：理解 ordinary Service-facing opener、options 和 async Host handle。
3. `dayu.host.admission`：理解 Session / Run admission、queue / steer、cancel、retry、replay、resolve wait 的治理入口。
4. `dayu.host.dispatch` 与 `dayu.host.engine_ingest`：理解本地 dispatch、worker accept、EngineEvent ingest 和 terminal closeout。
5. `dayu.host.run_input`：理解 durable facts、memory snapshot、compact artifact 与 ToolRuntime handle 如何构造 `AgentRunRequest`。
6. `dayu.host.tool_runtime` 与 `dayu.host.waiting`：理解工具执行治理、accept barrier、等待与截断。
7. `dayu.host.memory`、`dayu.host.memory_repair` 与 `dayu.host.compaction_operation`：理解 memory projection 和 context compaction 的 Host-owned 边界。
8. `dayu.host.recovery_process` 与 `dayu.host.recovery`：理解 positive orphan proof、startup recovery scan、RECOVERING dispatch 与 recovery truth source。
9. `dayu.host.durable`：理解 EventLog、payload descriptor、state transition、transaction 和 schema foundation。
