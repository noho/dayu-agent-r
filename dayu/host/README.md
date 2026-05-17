# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 当前提供 Host 公共 API 的类型契约、Session / Run public command facade、Host construction 的业务工具输入边界、本地执行配置契约、ToolRuntime typed boundary、本地 dispatch scheduler 与 LocalProxy 基线能力，供 UI / Service 按 `UI -> Service -> Host -> Engine` 的依赖方向向下引用。

当前包根导出包含以下类型：

- constants：`HOST_EVENT_STREAM_DEFAULT_LIMIT`、`HOST_EVENT_STREAM_MAX_LIMIT`，以及 wait record / wait adapter / wait snapshot / external job / payload ref 的公共长度上限常量。
- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostEventClass`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`、`HostPayloadRef`。
- command handle：`HostCommandHandle`、`create_host_command_handle`、`HostCommandFacet`；public handle 只暴露稳定 `host_handle_id` 与幂等 `close()`，不暴露 durable store、transaction runner、store connection 或 admission service。
- command handle options：`HostCommandHandleOptions`，显式描述 Host command handle 的 durable DB、artifact root、SQLite timeout / retry、payload inline threshold 与可选本地执行构造选项。
- local execution options：`HostLocalExecutionOptions`、`LocalWorkerHandle`、`LocalEngineWorker`、`LocalEngineWorkerFactory`，描述 Host 本地 dispatch scheduler 接入 runtime lane、Runner 配置、Agent policy、conversation memory policy 与 LocalProxy worker factory 的 typed 边界。
- Session facade：`ensure_session`、`create_session`、`get_session`、`close_session`，均返回 `SessionSnapshot`。
- Run facade：`start_run`、`submit_followup`、`get_run`、`stream_run_events`、`cancel_run`、`cancel_session_runs`；当前 command 路径覆盖 admission、pending dispatch wakeup、本地 no-tool dispatch baseline 与 active worker cancel 子集，读取路径只使用 durable Run / EventLog truth。
- Wait facade：`resolve_wait` 接收 active wait result，并按 outcome 原子恢复或收口等待中的 Run。
- deferred facade：`retry_run`、`replay_run`、`purge_session` 当前是 stable unsupported public functions，固定返回 `UNSUPPORTED_OPERATION`，不追加 EventLog，也不写 idempotency record。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`StartRunRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`，以及 `ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome`、`WaitAdapterKey`、`WaitProviderStatusRef`。
- snapshots / stream：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventView`、`HostEventStream`。
- error：`HostApiError`、`HostApiErrorDetail`、`SteerConflictDetail`。
- tooling construction options：`ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`、`default_framework_tool_policy_view`。

`dayu.host.api.__all__` 包含 request、snapshot、status、error、context、stream cursor 与本地执行配置契约类型。Session / Run read facade 位于 `dayu.host.read_api`，Session / Run command facade、Wait command facade 与 deferred facade 位于 `dayu.host.command`，并由包根导出，但不进入 `dayu.host.api`。Host construction tooling 类型位于 `dayu.host.tooling`，由包根导出，但不进入 `dayu.host.api`。

## Public Session Command Path

`create_host_command_handle(options, active_registry=None)` 会根据 `HostCommandHandleOptions` 打开 fresh/bootstrap 后的 Host durable SQLite store，并装配内部 no-op admission service 与 active worker cancel registry。`active_registry=None` 会为当前 command handle 创建 fresh registry，不与其它 handle 或 scheduler 共享；需要 active worker cancel 跨 command handle 与 scheduler 传播时，生产 composition root 必须把同一个 `ActiveWorkerRegistry` 对象同时传给 `create_host_command_handle(..., active_registry=...)` 与 `HostDispatchScheduler.open(..., active_registry=...)`。该同步 factory 当前不消费 `local_execution`，传入非空 `HostCommandHandleOptions.local_execution` 会 fail fast；本地 scheduler 需要由调用方显式 `await HostDispatchScheduler.open(...)` 装配和关闭，避免在同步 command handle 内隐藏 async worker lifecycle。该 handle 是 public facade 的 opaque command handle；关闭 handle 后再次调用 public facade 会返回 `HostApiError(code=INVALID_STATE, retryable=False)`。

当前已实现的 Session public facade：

- `ensure_session(host, request)`：按 `(scope, slot_key)` 原子创建或复用当前 slot Session，返回 durable truth 生成的 `SessionSnapshot`。
- `create_session(host, request)`：按 `client_request_id` 幂等创建显式新 Session，可选择重绑定 slot；同 key 同 semantic digest 返回同一 Session，同 key 不同 digest 返回 `IDEMPOTENCY_CONFLICT`。
- `get_session(host, session_id)`：通过只读 transaction 读取 Session row、当前 active Run id 与 queued Run id 列表；缺失时返回 `NOT_FOUND`。
- `close_session(host, session_id, request)`：只把 open Session 推进到 closed，保留 Session、EventLog、Run facts 与 slot binding；同一幂等 key 重放返回同一个 closed snapshot。

public semantic digest 在 facade 边界只使用显式请求字段与 `HostCallContext` 的语义 digest，不包含 runtime-only object、内部依赖或 metadata bag。
当前 `create_session` public facade 不持久化 `request.metadata`；metadata 持久化语义尚未成为 public contract。`ensure_session` 仍按 durable lifecycle 保存首次创建时的 metadata 摘要。

## Public Run Command Path

当前已实现的 Run public facade：

- `start_run(host, request)`：复用 internal admission，支持无 active Run 时 direct `RUNNING`、有 active Run 时按 `queue_policy` 执行 `queue` / `reject` / `attach_active`。`attach_active` 只记录幂等结果并返回当前 active `RunSnapshot`，不追加 canonical attach fact。
- `submit_followup(host, session_id, request)`：要求路径参数 `session_id` 等于 `request.session_id`。`behavior=queue` 复用 internal `submit_followup_queue`，active 存在时返回 `accepted_run_status=QUEUED`，无 active 时返回 `accepted_run_status=RUNNING`；`behavior=steer` 返回 `UNSUPPORTED_OPERATION` 且不追加 EventLog。
- `get_run(host, run_id)`：通过只读 transaction 读取 durable Run row，缺失时返回 `NOT_FOUND`。`current_attempt_id` 来自 Run row；`event_cursor` 是 Run row 中 input、accepted、queued、started、terminal event sequence 的最大非空值。所有从 durable Run row 构造的 public `RunSnapshot` 都使用同一映射：非终态 Run 的 `terminal_result_summary` 为 `None`；终态 Run 当前返回 status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)`，因为 Phase 4 尚未引入 typed terminal payload decoder，不从 untyped EventLog payload 字符串临时解析 summary refs。`outbox_summary` 在 Phase 4 始终为 `None`。
- `stream_run_events(host, run_id, cursor, limit=None)`：先校验目标 Run 存在，再按全局 EventLog `event_sequence > cursor.event_sequence` 扫描。`limit=None` 使用 `HOST_EVENT_STREAM_DEFAULT_LIMIT`，`limit <= 0` 或超过 `HOST_EVENT_STREAM_MAX_LIMIT` 返回 `INVALID_STATE`。`limit` 是全局 EventLog row 扫描窗口，也是返回事件上限；扫描后只返回 `row.run_id == run_id` 的 `HostEventView`，并把 EventLog row 的 `event_class` 映射为 public `HostEventClass`，调用方可区分 `canonical_fact`、`preview`、`diagnostic` 与 `projection_signal`。`next_cursor` 是本次扫描到的最大全局 `event_sequence`；没有扫描到 row 时等于输入 cursor。扫描窗口内只有无关 Run 事件时，返回空 `events` 但仍推进 `next_cursor`。
- `cancel_run(host, run_id, request)`：复用 internal cancel，支持 queued Run cancel、pre-dispatch `RUNNING` / Attempt `STARTING` / dispatch `PENDING` cancel、pre-accept dispatching cancel、active worker cancel 与 `WAITING` Run cancel；active worker cancel 会先把 Run 推进到 `CANCELLING`，再通过 active worker registry best-effort 传播取消。`WAITING` cancel 会标记 active wait records 为 `cancelled` 并把 Run 收口为 `CANCELLED`，不创建 resume Attempt；`RECOVERING` 取消由 Phase 11 负责。
- `cancel_session_runs(host, session_id, request)`：在一个 write transaction 内批量取消同 Session 下 queued、pre-dispatch / pre-accept dispatching、active worker 与 `WAITING` Run。若存在 `RECOVERING` 或其它 unsupported non-terminal Run，会在追加任何 cancel fact 前返回 `UNSUPPORTED_OPERATION`；active worker target 在 commit 后通过 registry best-effort 传播取消，`WAITING` wait abandon 只依赖 poller / adapter 后续观察。

`stream_run_events` 只暴露 `event_sequence`、`event_id`、`event_class`、`event_type`、`session_id`、`run_id`、`payload_ref` 与 `payload_digest`，不暴露 policy decision JSON、reason JSON 或 inline payload JSON。该 API 不读取 projection checkpoint、memory state、outbox state、in-memory subscription position、session-local cursor 或 client sequence。

`cancel_session_runs` 的幂等 scope 是 `(operation=cancel_session_runs, scope_id=session_id, idempotency_key=request.client_request_id)`。semantic digest 只包含 session id、请求上下文 digest、reason 与 mode，不包含当前 Run 列表；同 key 重放返回当前 `SessionSnapshot`，不会取消首次操作后新接受的 Run。没有 supported non-terminal Run 时只记录 session-scope 幂等结果，不追加 cancel fact。

当前 public `submit_followup(queue)` 暂使用 Host facade 内部默认 execution target 作为 policy resolution output；完整 policy provider / execution target resolution 装配不在当前实现范围。

当前 stable unsupported public facade：

- `retry_run(host, run_id, request)`
- `replay_run(host, run_id, request)`
- `purge_session(host, session_id, request)`

这些函数保留稳定签名，但当前固定返回 `HostApiError(code=UNSUPPORTED_OPERATION, retryable=False, detail=None)`，不读取或写入 EventLog、idempotency record、purge tombstone 或 retry / replay Run。

## Public Wait Command Path

`resolve_wait(host, wait_id, request)` 通过 Host durable wait resolution service 接收 active wait result。`ResolveWaitRequest` 必须携带 UTC-aware `observed_at`、`source`（`poll` / `callback` / `manual`）、`idempotency_key` 与强类型 `outcome` envelope。幂等作用域是 `(wait_id, request.idempotency_key)`；semantic digest 只反映 wait id、幂等键与 outcome 身份，`observed_at` / `source` 保留在首次提交的 payload / audit / diagnostic 中；同 key 同 outcome 重放返回当前 durable `RunSnapshot`，同 key 不同 outcome 返回 `IDEMPOTENCY_CONFLICT`。目标 wait 缺失返回 `NOT_FOUND`，非 active / 非等待中状态返回 `INVALID_STATE`。

`ResolveWaitCompletedOutcome` 与工具级 `ResolveWaitCancelledOutcome` 会在同一个 write transaction 内关闭 wait record、写入 `RESUME_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`、把 Run 从 `WAITING` 恢复到 `RUNNING`、创建新的 resume Attempt 与 pending dispatch record，并在 commit 后 best-effort 唤醒 dispatch scheduler。新的 resume `RUN_STARTED` 使用 `start_reason=resume`，RunInputBuilder 会从其引用的 `TOOL_RESULT_ACCEPTED` 重建 accepted wait/tool fact system message，交给下一次 Engine Attempt。

`ResolveWaitFailedOutcome` 会关闭 wait record 并把 Run 收口为 `FAILED`；`ResolveWaitLostOutcome` 会写入 lost 工具事实并把 Run 收口为 `LOST`。这两个 outcome 不创建 resume Attempt，也不触发 pending dispatch wakeup。

取消已经进入 `WAITING` 的 Run 时，`cancel_run` 与 `cancel_session_runs` 会复用同一 Host admission transition：写入 cancel facts、把 active wait records 标记为 `cancelled`、把 Run 收口为 `CANCELLED`，不创建 resume Attempt。取消后的 late result、`LOST` wait 的 late result 或 terminal Run 上的 late result 只写入 `WAIT_LATE_RESULT_REJECTED` diagnostic，不创建 resume Attempt，不触发 projection catch-up，并使用独立 `wait_late_rejection` 幂等 scope；同 key 同 digest 不重复写 diagnostic，同 key 不同 digest 返回 `IDEMPOTENCY_CONFLICT`。

Host 还提供最小 `WaitPoller` / `WaitPollAdapter` 层内契约。poller 只读取 durable poll wait 快照，外部 adapter 调用发生在 Host transaction 外；ready / lost 结果统一提交给 `resolve_wait`，cancelled wait 只通知 adapter abandon。adapter 未注册或单条 `poll_wait` / `abandon_wait` 抛出普通 `Exception` 时只计入本轮 `adapter_errors` 并继续后续 wait record；这些路径会输出包含 wait id 与 adapter key 的 warning 日志，不吞 `BaseException`。当前 poller 只提供单轮 `poll_once()` 入口，不包含后台调度循环或外部 job physical cancel 保证。

Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 事件当前只作为 diagnostic confirmation 处理：Host 只在 envelope identity、当前 `WAITING` / `SUSPENDED` 状态、active wait record、最新 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` canonical refs 与 Engine awaiting record 相互匹配时记为已确认；缺失或不匹配只写未确认 diagnostic / rejection。Host 不从 EngineEvent 创建 wait record，不把 Run 推入 `WAITING`，也不因迟到确认把已经 `WAITING` 的 Run 失败收口。callback HTTP endpoint、callback 认证 / 重放防护、recovery scan、远端 worker wait 恢复、外部 job physical cancel / revoke、durable duplicate ledger 与 durable tool trace projection 均未实现。

## Host Tooling Options

`HostToolingOptions` 是 Host construction / composition root 接收业务工具的 typed input boundary。它包含：

- `business_tool_bundle`：外部装配好的业务 `ToolBundle`。
- `source_refs`：非空 `ToolBundleSourceRef` 元组，用于解释业务工具来源。
- `framework_tool_policy`：construction 期 framework tool 预留名与启用集合视图。

`ToolBundleSourceKind` 当前覆盖 `explicit_provider`、`config_binding`、`package_entrypoint`、`service_composition`。`ToolBundleSourceRef` 只保存来源类别、来源 id、可选版本引用和可选内容摘要；它不携带 callable、provider 对象或业务模块对象。

默认 `FrameworkToolPolicyView` 预留 `FrameworkToolName.FETCH_MORE`，但默认不启用任何 framework tool。`HostToolingOptions` 会拒绝业务 `ToolBundle` 中与预留 framework tool 名称冲突的工具，例如 `fetch_more`。

## ToolRuntime Boundary

`dayu.host.tool_runtime` 当前提供 P6-S1 到 P6-S6 的 ToolRuntime typed boundary，不从 `dayu.host` 包根导出，也不进入 `dayu.host.api`。它负责把 Host construction 阶段传入的业务 `ToolBundle` 与 framework tool policy 投影为同一个 `EffectiveToolBundle`，并让 ToolRuntime handle 同时携带 Engine 可见的 `tool_schemas` 与实际执行入口 `tool_executor`。RunInputBuilder 的 tool-enabled factory 只接受同一个 `ToolRuntimeHandle` 投影出的 schema 与 executor；no-tool / replay factory 仍输出空 schema、`NoToolExecutor` 与 `AgentPolicy.allow_tool_calls=False`。

当前 ToolRuntime 已实现 Host accept barrier 的 typed candidate / ack / rejected / timeout contract 与默认 durable accept port。`DefaultHostToolFactAcceptPort` 通过既有 transaction runner、EventLog primitive 与 idempotency primitive 校验 Run / Attempt / execution identity，在同一事务中写入 `TOOL_CALL_REQUESTED`、必要的 `TOOL_CALL_GOVERNED` 与非 reuse 的 `TOOL_RESULT_ACCEPTED` canonical facts；同一 accept scope + key + semantic digest 返回既有 ack，同 key 不同 digest 返回 idempotency conflict rejected ack。EngineEvent ingest 的工具事件只作为 preview / diagnostic，不是工具 canonical fact 写入入口。

当前 ToolRuntime 已实现 P6-S3 批式 `ToolExecutor` wrapper：按 effective bundle 查找并异步调用业务 callable，将 callable 异常归一为 `ToolFailedOutcome`，对普通 completed / failed / cancelled 工具结果先提交 Host accept barrier，只有收到 `ToolFactAcceptedAck` 后才把结果返回给 Engine。`ToolFactRejectedAck` 与 accept timeout / ack lost 有限重试耗尽都会返回受治理的工具错误，不暴露原始业务结果。工具结果返回 Engine 前会按当前 payload inline 阈值做 LLM inline 大小治理；超限结果转为带 diagnostic ref 的 governed tool error，不把原始大结果塞入 Engine messages。side-effect / paid 工具当前通过 Host 内部 `ToolRuntimePolicyView` 指定工具级幂等 key 参数绑定，缺失 key 时 callable 不会被调用。

当前 ToolRuntime 已实现 P7-S2 awaiting accept path：当 `ToolAwaitingOutcome` 命中 Host wait adapter registry 且 awaiting accept port 返回 accepted ack 时，Host 在单个 write transaction 内写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`，创建 active wait record，并把 Run / Attempt 推进到 `WAITING` / `SUSPENDED`；ToolRuntime 只有收到 accepted ack 后才把 awaiting outcome 返回给 Engine。同一 accept key + 同 digest 重放返回既有 refs；同 key + 不同 digest 返回 rejected ack。缺少 adapter binding、poll binding 无 external job ref、awaiting accept rejected / timeout 都返回受治理工具错误，不走普通 `TOOL_RESULT_ACCEPTED` 路径。批内一旦某个工具 accepted awaiting，后续工具调用不再调用业务 callable，只返回受治理错误。

当前 ToolRuntime 已实现 P6-S4 run-scoped truncation / `fetch_more` 普通工具路径。`TruncationManager` 是 ToolRuntime-local 内存能力，不写 durable cursor 表；截断后的普通工具结果只暴露不透明 cursor 与 scope token。启用 `FETCH_MORE` framework tool 且启用 truncation manager 时，`EffectiveToolBundleBuilder` 注入同一个 effective bundle 内的 `fetch_more` schema 与 callable；`fetch_more` 作为普通工具经过 `ToolExecutor`、dispatcher、Host accept barrier 与 EventLog canonical path。截断策略覆盖 `text_chars`、`text_lines`、`list_items` 与 `binary_bytes`；cursor 校验覆盖 run scope、scope token、TTL、single-use、missing cursor、invalid limit 与 remainder digest mismatch；截断结果与 `fetch_more` continuation 仍受 LLM inline 大小治理约束，超限时返回普通工具错误，不进入 wait / recovery。

当前 ToolRuntime 已实现 P6-S5 run-local duplicate governance 与最小 diagnostic emitter。`InMemoryRunScopedDuplicateGovernanceRegistry` 在同一 Host 进程内按 Run 持有短生命周期 duplicate 记忆，使同一 Run 的多个 ToolRuntime handle 可共享 accepted fact；不同 Run 互相隔离，且不写 durable duplicate ledger，不承诺 crash / restart recovery。duplicate key 基于 tool identity digest、normalized arguments digest 与可选 semantic duplicate key，不包含 `index_in_iteration`；同 iteration 内两个相同工具和相同 normalized arguments 仍会进入治理。duplicate action 覆盖 `allow`、`reuse`、`hint`、`require_justification` 与 `hard_stop`；`reuse` 只在 Host accepted governance 后把 prior accepted outcome 返回给 Engine，引用 prior accepted refs，不调用业务 callable，也不追加第二个 `TOOL_RESULT_ACCEPTED`。duplicate governed candidate 会校验 policy kind、prior refs、reason 与 message 均匹配当前 duplicate decision。`ToolTraceDiagnosticEmitter` 当前提供 no-op、确定性引用与内存测试实现；diagnostic refs 会进入 governed candidate、accepted ack、rejected ack 或 timeout governed error 的结构化路径，但不写 audit、trace projection 或 EventLog。

当前本地 `HostDispatchScheduler` 已接入 tool-enabled composition wiring：当 `HostLocalExecutionOptions.tooling_options` 非空且 `AgentPolicy.allow_tool_calls=True` 时，scheduler 会为当前 Attempt 构造 ToolRuntime handle，并用 tool-enabled RunInputBuilder 把同源 `tool_schemas` 与 `tool_executor` 交给 worker；若 `HostToolingOptions.wait_adapter_registry` 非空，同一路径会注入 Host awaiting accept port 与 wait adapter registry，使 production local dispatch 可把 `ToolAwaitingOutcome` 接受为 `WAITING` / `SUSPENDED` 与 active wait record。未提供 tooling 或 policy 禁用工具时仍走 no-tool builder。

当前 ToolRuntime 仍未实现 policy provider resolution、attempt tool snapshot durability、callback endpoint、durable duplicate ledger 与 durable tool trace projection。

## Conversation Memory Contracts

`dayu.host.memory` 当前提供 Phase 9 Conversation Memory 的 typed contracts、EventLog-to-memory pure builder、deterministic digest helpers 与 RunInputBuilder memory view 所需的 repair / diagnostic contracts，不从包根导出，也不进入 `dayu.host.api`。Memory 是 EventLog 可重建的 session-level read model，不是 Host governance truth。

当前 memory view 分为 `PinnedStateView`、`VerifiedFactView`、`WorkingAssumptionView` 与 `ConversationContinuityView`。`VerifiedFactView` 只接受 tool provenance 与 `tool_verified` claim status；用户、assistant 与 Host projection 产物只能进入 assumption / continuity 视图。`MemoryClaimStatus` 预留 `candidate`、`conflicted`、`stale` 与 `superseded` 以支持后续检索 / 长期记忆能力，但当前 P9 active view 不主动合成这些状态。

Memory refs 只使用 Host-neutral `OpaqueMemoryRef` / `HostNeutralRefKind`，保存 ref id、digest 与 provenance，不保存财报 chunk 原文、网页新闻、公告、研报摘录或业务 subject 结构。`TOOL_RESULT_ACCEPTED` 是当前唯一会投影为 `VerifiedFactView` 的 event type；缺少 fact summary 时使用 tool name、payload ref / digest 与 digest ref 组成的中立 fallback，并记录 diagnostic。`RUN_SUCCEEDED` final answer 与 `USER_INPUT_ACCEPTED` 只进入 pinned / continuity 视图，不会成为 verified fact。`calculate_memory_snapshot_digest(...)` 只覆盖 cursor、policy digest、四类 view 与 deterministic diagnostic 字段，排除 `snapshot_id`、`built_at`、`diagnostic_id` 与 `recorded_at`。

RunInputBuilder 可通过 `DurableMemorySnapshotProvider` 读取 durable memory snapshot。Provider 按当前 Attempt `ATTEMPT_STARTED` 前的 EventLog cursor 读取不超过该 cursor 的最新 snapshot，避免同 Session queued follow-up 的未来输入泄漏；小滞后可从 EventLog delta 做只读 inline repair，缺失、损坏、超阈值滞后或 ahead-of-required snapshot 会抛出 `MemoryProjectionRepairRequired`，不会推进 projection checkpoint，也不会修改 Run / Attempt / EventLog。Memory messages 按目标约束、确认主体与口径、tool-verified facts、open questions / assumptions、recent raw turns、episode summaries 的顺序注入；当前用户 prompt 始终由 RunInputBuilder 最后的 `UserMessage` 提供。本地 `HostDispatchScheduler` 在 worker accept 前使用 `HostLocalExecutionOptions.memory_projection_policy` 把 conversation memory projection 追平到当前 Attempt 所需 cursor，并把同一 policy 的 `DurableMemorySnapshotProvider` 注入 no-tool 与 tool-enabled builder。

`dayu.host.memory_repair` 提供 Conversation Memory projection rebuild / catch-up entry。`rebuild_conversation_memory_projection(...)` 使用 existing `ProjectionRunner` 与 `ConversationMemoryProjectionConsumer` reset 后 replay committed EventLog；`catch_up_conversation_memory_projection(...)` 只追平 projection-local checkpoint。二者都不追加 EventLog，不修改 Run / Attempt / wait / dispatch 状态。通用 `ProjectionCatchupPort` 位于 `dayu.host.projection`；admission、ToolRuntime accepted tool fact path 与成功的 `resolve_wait` 可显式注入 concrete catch-up port 并在对应 write transaction commit 后 best-effort 调用，失败时只记录 projection-local `WARNING` 与 `error_type`，并保留已提交的 durable command / accept 结果。`create_host_admission_service(...)` 默认仍使用 no-op catch-up port，便于测试 / dev 显式控制。本地 dispatch 的 worker 启动路径会按当前 Attempt 所需 EventLog cursor 同步调用 conversation memory catch-up；若 durable snapshot 仍需要 repair，Run 使用 memory repair required 原因失败收口，不归类为 worker startup timeout。

## Durable Foundation

`dayu.host.durable` 是 Host 内部 durable foundation 子包，不从 `dayu.host` 包根导出，也不进入 `dayu.host.api`。

当前已实现：

- SQLite fresh bootstrap、schema version 校验、WAL / foreign key / busy timeout 配置与 transaction runner。
- canonical JSON、UTC timestamp 与 sha256 digest helper。
- EventLog append / read primitive：在调用方提供的 `HostTransaction` 内追加事件、分配全局 `event_sequence`、处理同体 `event_id` 幂等重复与异体冲突，并按 cursor 补读。`canonical_fact` 的 inline `payload_json` 受当前 payload inline 阈值约束，超限内容必须使用 payload descriptor / artifact ref 与 digest 边界。
- Idempotency primitive：以 `(scope_kind, scope_id, idempotency_key)` 绑定 `semantic_input_digest` 与显式 result ref，同 key 不同 digest 返回结构化冲突。
- Phase 8 projection / minimal read model：`ProjectionRunner` 只消费 committed EventLog，并推进 consumer-local checkpoint、记录 projection-local failure。当前固定 single consumer `host.minimal-read-model` 独占投影 `host_run_results` 与 `host_session_timeline_items`，作为内部 RunResult / Session timeline 读取基座；reset 后从 EventLog replay 是合法 repair 路径。投影 stale、缺失或 repair 失败不改变 durable Run / Session truth，也不影响 `stream_run_events` 的 EventLog-backed cursor 语义。`repair_minimal_read_models(...)` 使用注入的 `HostTransactionRunner` 分两阶段 reset 与 replay，不提供 public command facade。
- Phase 9 memory projection durable foundation：当前 schema 创建 `host_memory_snapshots`、`host_memory_items` 与 `host_memory_diagnostics` 三张表，`dayu.host.durable.memory` 提供 transaction-scoped snapshot / diagnostic read-write primitive、consumer-scoped reset helper 和 `ConversationMemoryProjectionConsumer`。该 consumer 只消费 committed canonical EventLog facts，在 ProjectionRunner 提供的同一 transaction 内写 memory-owned snapshot tables；checkpoint 推进仍由 ProjectionRunner 负责。它不启动 transaction，不修改 Run / Attempt / wait / dispatch 治理状态，不写 EventLog。RunInputBuilder 的 durable memory provider 只读 snapshot 与 EventLog delta；repair / catch-up 编排由 `dayu.host.memory_repair` 复用 ProjectionRunner 完成。
- Payload descriptor primitive：支持 `sqlite_payload` 与 `artifact_ref` 两类 descriptor；SQLite payload row 与 descriptor 可在同一 transaction 内写入，EventLog 可引用既有 descriptor 与 digest。
- Local artifact helper：在显式注入的 artifact root 下写入 `.tmp` 临时文件，完成 flush / fsync、digest 校验与 atomic rename 后返回最终 `LocalArtifactRef`；SQLite rollback 后已发布但未引用的文件只属于 cleanup / diagnostics orphan，不是 accepted fact。
- Host instance liveness primitive：支持当前 instance register、heartbeat、mark stopping / stopped 与 read row；该 row 只表达本机 Host instance 生命周期诊断。
- Phase 3 / 5 state schema / row codec：创建 Session、slot、Run、Attempt 与 attempt dispatch record durable tables；dispatch record 当前覆盖 `pending`、`waiting_for_lane`、`dispatching`、`cancelled` 四种状态，typed row codec 与低层 helper 负责状态枚举、SQLite row 转换、Session snapshot 读取和事务内 CAS mutation。
- Phase 3 / 5 internal lifecycle / transition primitives：在调用方提供的 `HostTransaction` 内实现 Session / slot lifecycle，以及 Run / Attempt / dispatch record 的低层 transition helper；当前 durable primitive 覆盖 pre-dispatch cancel、`pending -> waiting_for_lane -> dispatching` 诊断推进、worker accepted refs、Attempt `STARTING -> RUNNING`、active Run `RUNNING -> CANCELLING` 和 active cancel terminal closeout。EventLog fact 与 state row mutation 必须处于同一 SQLite write transaction。
- Phase 5 / 6 / 9 RunInputBuilder boundary：通过 typed providers 从 durable Run / Attempt / dispatch record、canonical EventLog facts 与 memory snapshot 构造 deterministic `AgentRunRequest`；只接受同一 snapshot identity 下的 Run `RUNNING`、Attempt `STARTING`、dispatch record `DISPATCHING` 当前事实。当前用户 prompt 只来自 durable `USER_INPUT_ACCEPTED`，historical raw turns 只能经 memory budget 后注入，resume-specific continuity 仍由 SessionContinuityProvider 提供。no-op memory / compact providers 不创建 durable rows。no-tool / replay 模式输出 `disable_tools=True`、`tool_schemas=()`、`AgentPolicy.allow_tool_calls=False`；tool-enabled 模式要求 `disable_tools=False`、`AgentPolicy.allow_tool_calls=True`，且 schema 与 executor 必须来自同一个 `ToolRuntimeHandle`。
- Phase 5 dispatch scheduler / LocalProxy baseline：`HostDispatchScheduler` 接收 pending dispatch wakeup，将 dispatch record 从 `pending` 推进到 `waiting_for_lane`，通过独立 runtime lane DB acquire capacity，再经 durable recheck 推进到 `dispatching`；durable recheck 遇到 transaction retry exhausted 时释放 lane 并重排当前 dispatch，不按 worker startup timeout 收口；后台 drain loop 持续轮询直到 scheduler close，避免 empty / sleep 窗口内的 wakeup 被遗留，未预期异常退出会记录 warning。worker accept 前会按本地执行 memory policy 同步追平 conversation memory projection，并把 durable memory provider 注入 RunInputBuilder。worker accept 后追加 `ATTEMPT_RUNNING`、推进 Attempt `STARTING -> RUNNING`，并记录 worker accept refs；worker startup timeout / accept failure 会按 `timed_out` 路径收口，若 startup closeout 自身失败则记录 warning 并继续释放 lane；memory projection repair required 使用独立 closeout reason，不归类为 worker startup timeout。Default LocalProxy worker 调用 Engine public `run_agent_messages(request)` 并暴露 single-use EngineEvent stream；同一 handle 不能重复打开 events，handle close 后不再允许读取 events，close 会关闭已打开的底层 Engine generator。scheduler 消费 worker event stream 时把自身作为 admission wakeup port 传给 `EngineEventIngestor`，active task 的 finally 单点负责 active registry 注销、worker handle close 与 lane release；`HostDispatchScheduler.open(..., active_registry=None)` 会创建 scheduler-local registry，不使用模块级 singleton；scheduler close 只传播 cancel signal 并取消 active task。`final_answer` 收口为 `SUCCEEDED`，`run_failed` 与 clean EOF without terminal 收口为 `FAILED`，worker stream crash / unknown terminal 收口为 `LOST`；terminal closeout 后会触发 queued Run promotion 并唤醒 promoted dispatch。
- Phase 5 / 7 EngineEvent ingest mapping：`EngineEventIngestor` 只接收 Host-owned `EngineEventCandidate` envelope，不要求 Engine 公共 `EngineEvent` 携带 Host Attempt identity；当前映射覆盖 final answer succeeded、run failed、active cancel 后 run cancelled、usage projection signal、preview / diagnostic、unsupported recovery diagnostic + failed closeout、Engine awaiting / suspended confirmation diagnostic、clean EOF failed closeout 和 worker lost closeout。Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 事件必须匹配 Host awaiting accept path 已 durable accepted 的 wait record 与 canonical refs 才记为确认；不匹配时不创建 wait record，也不把已经 `WAITING` 的 Run 失败收口。preview 事件只有在 `EngineEventType` 与对应 data 类型同时匹配时才写入 preview payload，否则写 rejected diagnostic。terminal closeout 后会触发 queue promotion wakeup，duplicate terminal replay 也会重试 promotion wakeup。
- Phase 7 wait record / resolve / cancel / poll foundation：创建 `host_wait_records` fresh schema / index / CHECK 约束，提供 typed wait record status、resume policy、snapshot / external job refs、row codec、insert / read / CAS helper 与 `RunStartReason.RESUME`。ToolRuntime awaiting accept path 已使用该 foundation 创建 active wait record 并推进 Run / Attempt 到 `WAITING` / `SUSPENDED`；public `resolve_wait` 已接入 wait record mutation、resolution idempotency、completed / tool-cancelled resume Attempt、failed closeout、lost closeout 与 late result diagnostic；public cancel 已支持 `WAITING` Run closeout；最小 poller 已支持 active poll waits 的 ready / lost / cancelled observation。callback endpoint 尚未接入。

durable foundation 当前不实现 policy provider set、RemoteProxy、recovery classifier、lease / fencing / takeover、artifact cleanup scheduler、audit、outbox、ToolRuntime durable snapshot 或 ToolRuntime durable cursor。

## Internal Admission

`dayu.host.admission` 是 Host 内部 command 编排模块，不从 `dayu.host` 包根导出，也不是 public facade。

当前已实现：

- `start_run`：在 open Session 上根据 `queue_policy` 执行 direct start、queue、reject 或 attach active；创建 running Run 时只写 pending dispatch record，不启动真实 dispatch。
- `submit_followup_queue`：接收调用方显式提供的 `resolved_execution_target`，在 active Run 存在时创建 queued Run，在无 active Run 时直接创建 running Run、STARTING Attempt 与 pending dispatch record。
- `promote_next_queued_run`：按 queued Run 的 accepted `event_sequence` FIFO promotion 一个 Run；active Run 存在时返回 skipped。
- `cancel_run`：支持 queued Run cancel、pre-dispatch STARTING cancel、active worker cancel 与 WAITING cancel；queued cancel 不创建 Attempt，pre-dispatch cancel 会把 pending dispatch record、Attempt 与 Run 同事务收口为 cancelled，WAITING cancel 会标记 active wait records 为 cancelled 并把 Run 收口为 cancelled。
- `closeout_attempt_terminal`：支持 STARTING Attempt / RUNNING Run 的 succeeded、failed、lost terminal closeout；成功释放 active slot 后在新事务中尝试 FIFO promotion。
- operation idempotency：start / follow-up 使用显式 operation scope，同 key 同 digest 返回既有 Run，不同 digest 返回结构化 conflict；follow-up queue digest 不包含 `resolved_execution_target`。
- wakeup port：暴露 pending dispatch 和 queue promotion wakeup 端口；admission 默认可使用 no-op / 测试 spy，dispatch scheduler 则实现该端口以连接 terminal closeout 后的 FIFO promotion 与 pending dispatch 唤醒。
- post-commit wakeup 边界：active slot 释放后的 durable promotion 先于 queue promotion wakeup；promotion 已提交后的 dispatch / queue wakeup `RuntimeError` 只按 best-effort 处理，不回滚或掩盖 durable promotion 结果。
- 多进程 durable invariant：当前测试覆盖同 slot ensure 只绑定一个 Session、同 Session admission 最多一个 active Run、跨进程 follow-up 幂等重放 / 冲突、queued Run 按 accepted `event_sequence` FIFO promotion、queued cancel 与 promotion 的 first-committer-wins，以及 EventLog `event_sequence` 全局唯一递增。

internal admission 当前不实现 policy provider integration、steer、retry / replay 或 recovery cancellation。
internal admission 当前的 session-scope cancel 支持 queued、pre-dispatch / pre-accept dispatching、active worker 与 WAITING 子集；Phase 11 负责 `RECOVERING` cancel。

## 校验边界

所有公共 dataclass 均使用 `frozen=True, slots=True`。枚举使用 `enum.StrEnum`，字符串值为稳定的 snake_case 值。

当前构造期校验覆盖：

- id / name / reason 字段拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 拒绝负数。
- `SubmitFollowupRequest` 中 `behavior=steer` 必须携带 `target_run_id`，`behavior=queue` 不得携带 `target_run_id`。
- `FollowupSnapshot` 使用 `accepted_run_id` / `accepted_run_status` 表达 accepted Run；queue 分支只允许 `QUEUED` 或 `RUNNING`，`QUEUED` 时 `queued_run_id` 必须等于 `accepted_run_id`，`RUNNING` 时 `queued_run_id` 必须为 `None`，queue 分支不得携带 `target_run_id`。
- `CreateSessionRequest.bind_slot=True` 时必须同时提供 `scope` 与 `slot_key`。
- `CancelRunRequest` 与 `CancelSessionRunsRequest` 当前只接受 `CancelMode.GRACEFUL`。
- `HostApiErrorCode` 包含 `UNSUPPORTED_OPERATION`；`HostApiError.detail` 只接受 `HostApiErrorDetail` typed union 成员，当前成员为 `SteerConflictDetail`。
- `HostCommandHandleOptions` 校验可选 handle id 非空、路径字段为 `pathlib.Path`、布尔字段为 `bool`、timeout / delay / backoff / payload threshold 为正数、写重试次数非负；`create_host_command_handle` 对非空 `local_execution` fail fast。
- `HostLocalExecutionOptions` 校验 lane 配置、RunnerSpec、RunnerCallOptions、AgentPolicy、worker factory、可选 `tooling_options` 与 truncation manager 开关；worker factory 是结构协议，运行时不做 `hasattr` / `getattr` 式协议探测，由 pyright 与显式 scheduler 装配点保障。
- `ToolBundleSourceRef.source_id` 拒绝空字符串或纯空白；可选版本引用与内容摘要存在时也必须非空。
- `HostToolingOptions.source_refs` 必须非空。
- `FrameworkToolPolicyView.enabled_framework_tools` 必须是 `reserved_framework_tool_names` 子集。
- 业务 `ToolBundle` 不得占用 reserved framework tool name。
- `HostPayloadRef`、`WaitAdapterKey`、`WaitProviderStatusRef` 与 resolve wait outcome 类型拒绝空白 id / kind / digest / message / diagnostic ref，长度按公共 `HOST_WAIT_*_MAX_LENGTH` 常量校验；`ResolveWaitRequest.observed_at` 必须是 UTC-aware `datetime`。

## 架构边界

`dayu.host` 可以在 LocalProxy 边界沿 `UI -> Service -> Host -> Engine` 方向调用 Engine public entry；Engine 不导入 Host。`dayu.host` 不导入 `dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

业务工具发现、provider / 配置绑定、包入口扫描和 Service composition 发生在 Host 外部。Host 只接收外部已经形成的业务 `ToolBundle`，不扫描业务工具包，也不导入具体财报工具模块。`business_tool_bundle` 不进入 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resolve wait 等 per-run request。

Host 若在后续实现中复用 `dayu.runtime.filelock`，只能把它用于普通文件短临界区互斥。lock marker 文件不是 Host 治理真源，不能用于判断 Run / Attempt owner、worker liveness、EventLog ordering、recovery 或 takeover；这些事实只能来自 Host durable store、EventLog、状态索引和事务。`RuntimeFileLock` 也不承诺 reentrant lock 语义，Host 代码不得依赖同一实例重复 acquire 的第三方行为。

当前未实现：

- policy provider set、RemoteProxy、recovery classifier、lease / fencing / takeover。
- artifact cleanup scheduler 与 diagnostics table。
- ToolRuntime policy resolution。
- wait callback endpoint 与 poller 后台调度循环。
- durable duplicate ledger、durable tool trace projection。
- ToolsDiscovery / ScenePrepare provider contract、tool profile registry、Attempt tool snapshot durability。
- command-handle 本地 scheduler lifecycle wiring、Fins 业务语义、Service / UI 装配逻辑。

## 测试

Host 公共契约测试位于 `tests/host/`：

```bash
pytest tests/host -q
python -m pyright dayu/host tests/host
```

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host payload / wait adapter / resolve wait outcome 校验、Host tooling options 校验、Conversation Memory typed contract / projection builder / durable round-trip / deterministic digest / Host-neutral boundary / anti-hallucination matrix / repair rebuild / catch-up failure path、ToolRuntime effective bundle / handle 同源约束、ToolRuntime accept barrier 幂等 / 冲突 / stale execution / canonical facts、ToolRuntimeExecutor accepted ack barrier / rejected ack / timeout retry / side-effect idempotency guard / awaiting accepted ack / awaiting rejected / awaiting timeout / awaiting missing adapter / awaiting missing external job / awaiting batch stop / no-tool defense / mixed batch、ToolRuntime truncation / `fetch_more` scope guard、run-local duplicate governance matrix、diagnostic emitter refs、Host import 边界、弱类型守卫、Host command handle factory / close lifecycle、Session public facade 幂等、冲突、读取与关闭语义，以及 Run public facade 的 start / follow-up queue / steer unsupported / get_run / EventLog stream / cancel / session-scope cancel / WAITING cancel / retry-replay-purge deferred unsupported 函数。

durable foundation、RunInputBuilder、dispatch scheduler / LocalProxy、EngineEvent ingest mapping、ToolRuntime accept barrier / executor 与 internal admission 测试覆盖 SQLite schema bootstrap / transaction runner、EventLog append / read / idempotency、payload descriptor、local artifact helper、host instance liveness、EventLog 多进程 sequence smoke、projection checkpoint / failure、minimal RunResult / Session timeline projection 与 repair、memory projection table / CHECK / FK / index、memory snapshot 与 checkpoint 同事务 rollback、memory diagnostic durable round-trip、ConversationMemoryProjectionConsumer 从 committed EventLog 构建 snapshot、memory projection reset / rebuild / catch-up failure、tool verified fact provenance、final answer / user input 不升格为 verified fact、history pool budget 与 recent raw turn floor、Session lifecycle、Run / Attempt transition primitive、dispatch record 四状态 schema、wait record schema / row codec / DDL CHECK / CAS helper、awaiting accept 三事实原子写入 / wait record 创建 / WAITING 和 SUSPENDED 状态推进 / replay / conflict / stale execution reject、resolve_wait completed resume / tool-cancelled resume / failed closeout / lost closeout / idempotent replay / conflict / resume RunInputBuilder continuity / late result diagnostic / after-commit catch-up failure tolerance、WAITING cancel / session-scope WAITING cancel、wait poller ready / not-ready / cancelled abandon、waiting / dispatching / worker accept refs、active cancel durable primitive、RunInputBuilder durable prompt / canonical continuity / no-tool request / tool-enabled ToolRuntime handle 投影 / 非可派发状态拒绝、scheduler pending / waiting / dispatching / worker accept / promotion catch-up failure tolerance、pre-accept cancel race、lane acquire timeout、worker startup timeout、active task 资源释放、LocalProxy Engine entry boundary、final answer / failed / cancelled / usage / preview data 校验 / unsupported recovery EngineEvent mapping / Engine awaiting confirmation diagnostic、Engine 工具事件 preview 边界、clean EOF / worker lost closeout、terminal duplicate promotion retry、accept key 幂等重放 / conflict / stale execution reject / reuse governance canonical fact / accepted tool fact after-commit catch-up failure tolerance、ToolRuntimeExecutor fake business tool accepted 后返回、accept reject / timeout 不泄漏 raw result、side-effect 缺 key 不调用 callable、duplicate key 规范化与排除 `index_in_iteration`、`allow` / `reuse` / `hint` / `require_justification` / `hard_stop` matrix、diagnostic refs、Engine 经 ToolRuntime durable accepted 后继续第二轮、start / follow-up admission、queue policy、idempotency、FIFO promotion、queued / pre-dispatch cancel、terminal closeout、admission 多进程 durable invariant，以及 Host 包根不导出 durable 内部模块。
