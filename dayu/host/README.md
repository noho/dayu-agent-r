# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 包根当前提供普通 Service-facing 的 Host public contract：`open_host(options)` opener、异步 `Host` / `HostHandle` 协议、`OpenHostOptions`、普通 Run 执行基线、Host-owned compactor runner 基线、Host-owned typed `HostEvent` 终态视图、生命周期异常 `HostClosedError`、普通 Session / Run request / snapshot 类型，以及 Host construction 的业务工具输入边界。低层同步 command handle、`start_run` / `StartRunRequest`、command-handle construction types、run-level event 补读与本地执行装配仍保留在内部模块路径，普通 Service 不应从包根依赖这些名字。

`open_host(options)` 当前会装配 durable store、共享 `ActiveWorkerRegistry`、本地 `HostDispatchScheduler`、memory projection catch-up、Host-owned LLM compactor、compact artifact root 与 command wakeup port，并在 Host 内部生成本次 opener runtime 的诊断 / liveness id；普通 Service 不传入也不依赖 `host_handle_id`，也不提供 compactor port、prompt、candidate builder 或 compact policy ref。普通 `submit_followup(queue)`、`submit_followup(steer)`、`retry_run`、`replay_run` 与 `resolve_wait` 经 public async handle 接受后会在 commit 后唤醒 scheduler 并进入本地 dispatch；调用方不需要手工持有 scheduler、durable store、registry 或 wakeup port。`SubmitFollowupRequest` 当前使用 typed prompt / per-run override 字段：`system_prompt`、`user_prompt`、`tool_names`、`runner_spec`、`runner_options`、`agent_policy`；Host 在 admission 写入每次 Run 的 effective execution config 与 effective business tool set，并由 dispatch 读取同一冻结视图。`watch_session_events(session_id)` 是普通 Service-facing session-level live event entry，返回 Host-owned typed `HostEvent` async iterator；terminal `SUCCEEDED` event 内联 `HostFinalAnswerView`，`FAILED` / `CANCELLED` event 提供 typed terminal status 与展示安全字段。该 watch 不接收 cursor、不做离线补读，terminal event 不结束 iterator；consumer 提前取消只关闭本次订阅，不取消 Run、不写 EventLog。`host.close()` 与 async context manager 退出只关闭当前 opener runtime，按顺序停止 scheduler、flush memory projection 并关闭 durable store，不写 cancel / failed terminal facts；重复 close 幂等，close 后 public handle 方法返回 `HostClosedError`。

Host 的可观测日志遵循 `dayu/README.md` 的级别语义。`INFO` 只记录 opener / scheduler / public handle 启停这类 runtime 生命周期摘要；`VERBOSE` 记录 public watch attach、command accepted / committed、queue promotion、context governance 决策、compact start / accepted、dispatch 状态推进、worker accept、EngineEvent ingest、worker lifecycle closeout 与 worker event consume 骨架；`DEBUG` 记录 CAS miss、skip、预算估算 digest 与其它受控诊断细节；`WARN` / `ERROR` / `CRITICAL` 分别用于可恢复异常、本次操作失败和 durable invariant / contract 破坏。Host 日志不输出完整 prompt、工具参数 / 结果、provider secret 或大 payload。

当前包根导出包含以下类型：

- constants：`HOST_EVENT_STREAM_DEFAULT_LIMIT`、`HOST_EVENT_STREAM_MAX_LIMIT`，以及 wait record / wait adapter / wait snapshot / external job / payload ref 的公共长度上限常量。
- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostEventClass`、`HostEventKind`、`HostTerminalStatus`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`、`HostPayloadRef`。
- opener / handle：`open_host`、`OpenHostOptions`、`OrdinaryRunExecutionBaseline`、`CompactorRunnerBaseline`、`Host`、`HostHandle`、`HostClosedError`。
- local worker protocols：`LocalWorkerHandle`、`LocalEngineWorker`、`LocalEngineWorkerFactory`，用于 typed construction boundary；`HostLocalExecutionOptions` 是内部本地执行装配类型，不作为包根模块属性暴露。
- Session facade：`ensure_session`、`create_session`、`get_session`、`close_session`，均返回 `SessionSnapshot`。
- Run facade：`submit_followup`、`get_run`、`cancel_run`、`cancel_session_runs`、`retry_run`、`replay_run`；`start_run` 与 run-level `stream_run_events` 已降级为低层 / diagnostic 路径，不再进入包根普通 Service-facing contract。
- Event watch：`watch_session_events(session_id)` 只在 `open_host(options)` 返回的 async handle 上提供，Service 从 terminal `HostEvent.final_answer` 渲染最终回答，不读取内部 payload table。
- Wait facade：`resolve_wait` 接收 active wait result，并按 outcome 原子恢复或收口等待中的 Run。
- deferred facade：`purge_session` 当前是 stable unsupported public function，固定返回 `UNSUPPORTED_OPERATION`，不追加 EventLog，也不写 idempotency record；recovery-only retry / replay variants 仍未接入普通 public contract。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`，以及 `ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome`、`WaitAdapterKey`、`WaitProviderStatusRef`。
- snapshots / event：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostFinalAnswerView`、`HostEvent`。
- error：`HostApiError`、`HostApiErrorDetail`、`SteerConflictDetail`。
- tooling construction options：`ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`、`default_framework_tool_policy_view`。

`dayu.host.api.__all__` 包含 request、snapshot、status、error、context、stream cursor、public opener options、HostEvent typed view，以及低层 `StartRunRequest`、command-handle construction types 与本地执行配置契约类型。Session / Run read facade 位于 `dayu.host.read_api`，低层 command handle、`start_run`、Session / Run command facade、Wait command facade 与 deferred facade 位于 `dayu.host.command`；普通 Service-facing 包根导出保留 P10.5 冻结的 opener / handle 入口。Host construction tooling 类型位于 `dayu.host.tooling`，由包根导出，但不进入 `dayu.host.api`。

## Low-level Session Command Path

`create_host_command_handle(options, active_registry=None)` 会根据 `HostCommandHandleOptions` 打开 fresh/bootstrap 后的 Host durable SQLite store，并装配内部 no-op admission service 与 active worker cancel registry。`active_registry=None` 会为当前 command handle 创建 fresh registry，不与其它 handle 或 scheduler 共享；需要普通生产 runtime 时应优先使用 `open_host(options)`，由 opener 在内部共享 registry 并连接 scheduler wakeup。该同步 factory 当前不消费 `local_execution`，传入非空 `HostCommandHandleOptions.local_execution` 会 fail fast；低层测试或诊断路径如需本地 scheduler，仍需显式 `await HostDispatchScheduler.open(...)` 装配和关闭，避免在同步 command handle 内隐藏 async worker lifecycle。`compose_host_local_execution_options(options)` 供低层 composition 在打开 scheduler 前把 command options 中的 context budget 字段转为 typed `ContextBudgetPolicy`，并把 command artifact root 作为 compact artifact root 注入本地执行配置；它不读取 Engine spec、per-run metadata、caller payload 或 provider overflow budget。该 handle 是低层 command facade 的 opaque handle；关闭 handle 后再次调用低层 facade 会返回 `HostApiError(code=INVALID_STATE, retryable=False)`。

当前低层 Session command facade：

- `ensure_session(host, request)`：按 `(scope, slot_key)` 原子创建或复用当前 slot Session，返回 durable truth 生成的 `SessionSnapshot`。
- `create_session(host, request)`：按 `client_request_id` 幂等创建显式新 Session，可选择重绑定 slot；同 key 同 semantic digest 返回同一 Session，同 key 不同 digest 返回 `IDEMPOTENCY_CONFLICT`。
- `get_session(host, session_id)`：通过只读 transaction 读取 Session row、当前 active Run id 与 queued Run id 列表；缺失时返回 `NOT_FOUND`。
- `close_session(host, session_id, request)`：只把 open Session 推进到 closed，保留 Session、EventLog、Run facts 与 slot binding；同一幂等 key 重放返回同一个 closed snapshot。

public semantic digest 在 facade 边界只使用显式请求字段与 `HostCallContext` 的语义 digest，不包含 runtime-only object、内部依赖或 metadata bag。
当前 `create_session` public facade 不持久化 `request.metadata`；metadata 持久化语义尚未成为 public contract。`ensure_session` 仍按 durable lifecycle 保存首次创建时的 metadata 摘要。

## Low-level Run Command Path

当前低层 Run command facade：

- `start_run(host, request)`：复用 internal admission，支持无 active / start-blocking Run 时接受为 `ACCEPTED`，有 active / start-blocking Run 时按 `queue_policy` 执行 `queue` / `reject` / `attach_active`。`ACCEPTED` Run 尚无 Attempt；`attach_active` 只附着已有 active Attempt，目标仍处于 `ACCEPTED` 时返回 conflict，不追加 canonical attach fact。
- `submit_followup(host, session_id, request)`：要求路径参数 `session_id` 等于 `request.session_id`。低层 command handle 缺少 opener ordinary baseline 时会 fail closed；普通 Service-facing 路径应使用 `open_host(options)`，由 opener 注入 ordinary baseline、冻结 effective execution config / tool set，并在 admission commit 后唤醒 scheduler pre-start governance。`behavior=steer` 只接受同 Session active `RUNNING` / `WAITING` 目标 Run。
- `get_run(host, run_id)`：通过只读 transaction 读取 durable Run row，缺失时返回 `NOT_FOUND`。`current_attempt_id` 来自 Run row；`event_cursor` 是 Run row 中 input、accepted、queued、started、terminal event sequence 的最大非空值。所有从 durable Run row 构造的 public `RunSnapshot` 都使用同一映射：非终态 Run 的 `terminal_result_summary` 为 `None`；终态 Run 当前返回 status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)`，因为 Phase 4 尚未引入 typed terminal payload decoder，不从 untyped EventLog payload 字符串临时解析 summary refs。`outbox_summary` 在 Phase 4 始终为 `None`。
- `stream_run_events(host, run_id, cursor, limit=None)`：该函数位于 `dayu.host.read_api`，只作为内部 diagnostic / 低层测试路径。它先校验目标 Run 存在，再按全局 EventLog `event_sequence > cursor.event_sequence` 扫描。`limit=None` 使用 `HOST_EVENT_STREAM_DEFAULT_LIMIT`，`limit <= 0` 或超过 `HOST_EVENT_STREAM_MAX_LIMIT` 返回 `INVALID_STATE`。`limit` 是全局 EventLog row 扫描窗口，也是返回事件上限；扫描后只返回 `row.run_id == run_id` 的 `HostEventView`，并把 EventLog row 的 `event_class` 映射为 `HostEventClass`，调用方可区分 `canonical_fact`、`preview`、`diagnostic` 与 `projection_signal`。`next_cursor` 是本次扫描到的最大全局 `event_sequence`；没有扫描到 row 时等于输入 cursor。扫描窗口内只有无关 Run 事件时，返回空 `events` 但仍推进 `next_cursor`。
- `cancel_run(host, run_id, request)`：复用 internal cancel，支持 queued Run cancel、pre-dispatch `RUNNING` / Attempt `STARTING` / dispatch `PENDING` cancel、pre-accept dispatching cancel、active worker cancel 与 `WAITING` Run cancel；active worker cancel 会先把 Run 推进到 `CANCELLING`，再通过 active worker registry best-effort 传播取消。`WAITING` cancel 会标记 active wait records 为 `cancelled` 并把 Run 收口为 `CANCELLED`，不创建 resume Attempt；`RECOVERING` 取消由 Phase 11 负责。
- `cancel_session_runs(host, session_id, request)`：在一个 write transaction 内批量取消同 Session 下 queued、pre-dispatch / pre-accept dispatching、active worker 与 `WAITING` Run。若存在 `RECOVERING` 或其它 unsupported non-terminal Run，会在追加任何 cancel fact 前返回 `UNSUPPORTED_OPERATION`；active worker target 在 commit 后通过 registry best-effort 传播取消，`WAITING` wait abandon 只依赖 poller / adapter 后续观察。

`stream_run_events` 只暴露 `event_sequence`、`event_id`、`event_class`、`event_type`、`session_id`、`run_id`、`payload_ref` 与 `payload_digest`，不暴露 policy decision JSON、reason JSON 或 inline payload JSON。该 API 不读取 projection checkpoint、memory state、outbox state、in-memory subscription position、session-local cursor 或 client sequence；普通 Service 不从包根导入或使用该 diagnostic DTO。

`cancel_session_runs` 的幂等 scope 是 `(operation=cancel_session_runs, scope_id=session_id, idempotency_key=request.client_request_id)`。semantic digest 只包含 session id、请求上下文 digest、reason 与 mode，不包含当前 Run 列表；同 key 重放返回当前 `SessionSnapshot`，不会取消首次操作后新接受的 Run。没有 supported non-terminal Run 时只记录 session-scope 幂等结果，不追加 cancel fact。

当前 public `submit_followup(queue)` 暂使用 Host facade 内部默认 execution target 作为 policy resolution output；完整 policy provider / execution target resolution 装配不在当前实现范围。`tool_names=None` 表示使用 construction-time 全量业务工具，空 `frozenset()` 表示禁用业务工具，非空集合表示只暴露指定业务工具；unknown tool name 在 admission 写入 durable canonical facts 前返回结构化错误。

当前 ordinary public retry / replay 已接入 Host admission：`retry_run(host, run_id, request)` 只接受普通本地 `FAILED` 源 Run，按源 Run 限制一次 ordinary retry；`replay_run(host, run_id, request)` 只接受 `SUCCEEDED` 源 Run，并创建 no-tool 修复 Run。两者对非目标源状态返回 `INVALID_STATE`，不写入 retry / replay facts。

当前 stable unsupported public facade：

- `purge_session(host, session_id, request)`

该函数保留稳定签名，但当前固定返回 `HostApiError(code=UNSUPPORTED_OPERATION, retryable=False, detail=None)`，不读取或写入 EventLog、idempotency record 或 purge tombstone。

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

当前 ToolRuntime 已实现 P6-S4 run-scoped truncation / `fetch_more` 普通工具路径。`TruncationManager` 是 ToolRuntime-local 内存能力，不写 durable cursor 表；截断后的普通工具结果只暴露不透明 cursor 与 scope token。启用 `FETCH_MORE` framework tool 且启用 truncation manager 时，`EffectiveToolBundleBuilder` 注入同一个 effective bundle 内的 `fetch_more` schema 与 callable；`fetch_more` 作为普通工具经过 `ToolExecutor`、dispatcher、Host accept barrier 与 EventLog canonical path。截断策略覆盖 `text_chars`、`text_lines`、`list_items` 与 `binary_bytes`；cursor 校验覆盖 run scope、scope token、TTL、single-use、missing cursor、invalid limit 与 remainder digest mismatch；截断结果与 `fetch_more` continuation 仍受 LLM inline 大小治理约束，超限时返回普通工具错误，不进入 wait / recovery，且不会保留未返回的截断 cursor。

当前 ToolRuntime 已实现 P6-S5 run-local duplicate governance 与最小 diagnostic emitter。`InMemoryRunScopedDuplicateGovernanceRegistry` 在同一 Host 进程内按 Run 持有短生命周期 duplicate 记忆，使同一 Run 的多个 ToolRuntime handle 可共享 accepted fact；不同 Run 互相隔离，且不写 durable duplicate ledger，不承诺 crash / restart recovery。duplicate key 基于 tool identity digest、normalized arguments digest 与可选 semantic duplicate key，不包含 `index_in_iteration`；同 iteration 内两个相同工具和相同 normalized arguments 仍会进入治理。duplicate action 覆盖 `allow`、`reuse`、`hint`、`require_justification` 与 `hard_stop`；`reuse` 只在 Host accepted governance 后把 prior accepted outcome 返回给 Engine，引用 prior accepted refs，不调用业务 callable，也不追加第二个 `TOOL_RESULT_ACCEPTED`。duplicate governed candidate 会校验 policy kind、prior refs、reason 与 message 均匹配当前 duplicate decision。`ToolTraceDiagnosticEmitter` 当前提供 no-op、确定性引用与内存测试实现；diagnostic refs 会进入 governed candidate、accepted ack、rejected ack 或 timeout governed error 的结构化路径，但不写 audit、trace projection 或 EventLog。

当前本地 `HostDispatchScheduler` 已接入 tool-enabled composition wiring：当 `HostLocalExecutionOptions.tooling_options` 非空且 `AgentPolicy.allow_tool_calls=True` 时，scheduler 会为当前 Attempt 构造 ToolRuntime handle，并用 tool-enabled RunInputBuilder 把同源 `tool_schemas` 与 `tool_executor` 交给 worker；若 `HostToolingOptions.wait_adapter_registry` 非空，同一路径会注入 Host awaiting accept port 与 wait adapter registry，使 production local dispatch 可把 `ToolAwaitingOutcome` 接受为 `WAITING` / `SUSPENDED` 与 active wait record。未提供 tooling 或 policy 禁用工具时仍走 no-tool builder。

当前 ToolRuntime 仍未实现 policy provider resolution、attempt tool snapshot durability、callback endpoint、durable duplicate ledger 与 durable tool trace projection。

## Conversation Memory Contracts

`dayu.host.memory` 当前提供 Phase 9 Conversation Memory 的 typed contracts、EventLog-to-memory pure builder、deterministic digest helpers 与 RunInputBuilder memory view 所需的 repair / diagnostic contracts，不从包根导出，也不进入 `dayu.host.api`。Memory 是 EventLog 可重建的 session-level read model，不是 Host governance truth。

当前 memory view 分为 `PinnedStateView`、`VerifiedFactView`、`WorkingAssumptionView` 与 `ConversationContinuityView`。`VerifiedFactView` 只接受 tool provenance 与 `tool_verified` claim status；用户、assistant 与 Host projection 产物只能进入 assumption / continuity 视图。`MemoryClaimStatus` 预留 `candidate`、`conflicted`、`stale` 与 `superseded` 以支持后续检索 / 长期记忆能力，但当前 P9 active view 不主动合成这些状态。

Memory refs 只使用 Host-neutral `OpaqueMemoryRef` / `HostNeutralRefKind`，保存 ref id、digest 与 provenance，不保存财报 chunk 原文、网页新闻、公告、研报摘录或业务 subject 结构。`TOOL_RESULT_ACCEPTED` 是当前唯一会投影为 `VerifiedFactView` 的 event type；缺少 fact summary 时使用 tool name、payload ref / digest 与 digest ref 组成的中立 fallback，并记录 diagnostic。`RUN_SUCCEEDED` final answer 与 `USER_INPUT_ACCEPTED` 只进入 pinned / continuity 视图，不会成为 verified fact。`calculate_memory_snapshot_digest(...)` 只覆盖 cursor、policy digest、四类 view 与 deterministic diagnostic 字段，排除 `snapshot_id`、`built_at`、`diagnostic_id` 与 `recorded_at`。

RunInputBuilder 可通过 `DurableMemorySnapshotProvider` 读取 durable memory snapshot。Provider 按当前 Attempt `ATTEMPT_STARTED` 前的 EventLog cursor 读取不超过该 cursor 的最新 snapshot，避免同 Session queued follow-up 的未来输入泄漏；小滞后可从 EventLog delta 做只读 inline repair，缺失、损坏、超阈值滞后或 ahead-of-required snapshot 会抛出 `MemoryProjectionRepairRequired`，不会推进 projection checkpoint，也不会修改 Run / Attempt / EventLog。Memory messages 按目标约束、确认主体与口径、tool-verified facts、open questions / assumptions、recent raw turns、episode summaries 的顺序注入；当前用户 prompt 始终由 RunInputBuilder 最后的 `UserMessage` 提供。本地 `HostDispatchScheduler` 在 worker accept 前使用 `HostLocalExecutionOptions.memory_projection_policy` 把 conversation memory projection 追平到当前 Attempt 所需 cursor，并把同一 policy 的 `DurableMemorySnapshotProvider` 注入 no-tool 与 tool-enabled builder。

`dayu.host.memory_repair` 提供 Conversation Memory projection rebuild / catch-up entry。`rebuild_conversation_memory_projection(...)` 使用 existing `ProjectionRunner` 与 `ConversationMemoryProjectionConsumer` reset 后 replay committed EventLog；`catch_up_conversation_memory_projection(...)` 只追平 projection-local checkpoint。二者都不追加 EventLog，不修改 Run / Attempt / wait / dispatch 状态。通用 `ProjectionCatchupPort` 位于 `dayu.host.projection`；admission、ToolRuntime accepted tool fact path 与成功的 `resolve_wait` 可显式注入 concrete catch-up port 并在对应 write transaction commit 后 best-effort 调用，失败时只记录 projection-local `WARNING` 与 `error_type`，并保留已提交的 durable command / accept 结果。`create_host_admission_service(...)` 默认仍使用 no-op catch-up port，便于测试 / dev 显式控制。本地 dispatch 的 worker 启动路径会按当前 Attempt 所需 EventLog cursor 同步调用 conversation memory catch-up；若 durable snapshot 仍需要 repair，Run 使用 memory repair required 原因失败收口，不归类为 worker startup timeout。

## Context Governance Boundary

普通 public opener 只通过 `CompactorRunnerBaseline` 接收 compactor 独立 `RunnerSpec`、`RunnerCallOptions` 与 compact artifact root。`open_host(options)` 在 Host 内部构造 `LLMContextCompactor`，该 compactor 使用 Host-owned prompt、禁用工具的 Engine request 和 Host-owned candidate mapper，并通过 async `ContextCompactor` port 直接 await Engine public runner；普通调用方不能传入 compact prompt、candidate builder、quality override、raw policy ref 或低层 compactor port。`CompactorRunnerBaseline` 不进入 `dayu.host.api` 之外的低层装配语义，也不替代 `ContextBudgetPolicy`；semantic repair 次数由 `ContextBudgetPolicy.max_compaction_attempts_per_operation` 控制。

`dayu.host.compaction` 当前提供 Phase 10 Context Governance 的 typed compactor boundary，不从包根导出，也不进入 `dayu.host.api`。`ContextCompactor` 只接收 `CompactionRequest` 并返回 `CompactionCandidate`；它作为 Host 内部 / 低层测试 seam 使用。LLM 或 fake compactor 输出都只是 candidate，Host 必须先通过 quality check 才能写 compact artifact 或后续 canonical compact event。

`CompactionRequest` 显式携带 trigger source、Session / Run refs、Attempt / execution refs、输入 event refs、memory snapshot cursor、当前用户输入摘要、tool fact refs、verified fact refs、recent / older raw turn refs、既有 episode summary refs 与 compact 前预算估算。proactive compact 的 Attempt / execution refs 可以为 `None`；reactive compact 必须携带非空 Attempt / execution refs。`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`PreservationEvidence`、`CompactQualityCheckResult` 与 `CompactionCandidate` 均为 frozen slots dataclass；pinned state patch 对 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 使用字段级 missing / clear / replace 三态，不使用 untyped JSON bag。

`dayu.host.context_governance.check_compaction_candidate(...)` 当前只实现 compact quality check：拒绝丢失当前用户输入、丢失 accepted tool fact refs、episode summary 伪造 verified fact、缺 preservation evidence、evidence anchor 未保留，以及 pinned patch 三态非法或引用不存在的 evidence。该 checker 不 append EventLog，不写 memory snapshot，也不执行 proactive / reactive orchestration。

`dayu.host.compact_artifact.CompactArtifactStore` 当前把已接受 candidate 写为 canonical JSON artifact，并在调用方事务内复用 `PayloadStore.write_payload_descriptor_for_artifact(...)` 写 payload descriptor。artifact 内容包含 compaction request digest、accepted candidate、quality result、compact 前后预算、输入 snapshot refs、dropped / summarized ranges、preserved fact refs 与 policy digest；artifact store 只返回 descriptor / artifact ref / digest，不 append EventLog。

`dayu.host.context_events` 提供 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED` 与 `CONTEXT_COMPACTION_FAILED` 的 typed payload builder / validator。`CONTEXT_COMPACTED` 是 accepted compact output 的 canonical memory input；Conversation Memory projection 从该事件读取 episode summary candidate 与 pinned state patch candidate，并保持 verified facts 只来自 `TOOL_RESULT_ACCEPTED`。

`HostCommandHandleOptions.context_window_size` 与 `reserved_output_tokens` 是 Host Context Governance 的必填 production composition 输入；调用方必须按实际 provider / deployment context 显式传入，不存在生产默认值。`context_budget_hard_threshold_tokens` 与 `context_budget_minimum_protection_tokens` 可选覆盖 policy 计算边界，hard threshold 必须至少为 2，确保 compact 后仍存在正整数预算且低于 hard block 边界；未传 minimum protection 时按当前显式 window / reserved 组合使用 Host 默认 policy 下的保护值。`compose_host_local_execution_options(...)` 会用这些字段构造 `ContextBudgetPolicy` 并覆盖 `HostLocalExecutionOptions.context_budget_policy`；memory projection policy 保持独立，只控制 memory view 与 RunInputBuilder memory 注入，不参与 budget / compact 决策。

本地 `HostDispatchScheduler.wake_queue_promotion(...)` 当前也是 pre-start Context Governance gate：先选择同 Session 的 accepted Run；若不存在 active/start-blocking Run，则选择最早 queued Run。Run 在 admission commit 后先保持 `ACCEPTED` 或 `QUEUED`，scheduler 评估 context budget 后才写 `RUN_STARTED`、`ATTEMPT_STARTED` 与 pending dispatch record。未配置 context budget policy 时直接允许启动；soft threshold 会在每个 Run 最多一次 proactive compact 内写 `CONTEXT_COMPACTION_REQUESTED`、调用 Host-owned compactor、通过 quality check 后写 compact artifact 与 `CONTEXT_COMPACTED`，随后追平 conversation memory projection 再启动 Attempt。hard threshold、compact 失败、compact 后仍越过 hard threshold 或 durable compact-count facts 损坏时会写 `CONTEXT_COMPACTION_FAILED` 与 attempt-free `RUN_FAILED`，不会创建 Attempt row 或 dispatch record。`CONTEXT_COMPACTION_FAILED` 不进入生产 memory projection filter。

`EngineEventIngestor` 接收 Engine `context_compaction_requested` 时只把它视为 reactive fallback，不把 Engine `budget_state` 当 Host 预算真源。ingest 仍先校验 envelope 的 Attempt / execution / dispatch identity；接受后使用 Host `ContextBudgetPolicy` 和 estimator 写 `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`，关闭当前 Attempt 为 `FAILED` 并追加 `RUN_RECOVERING`。reactive compact 每个 Run 第一版最多一次，计数来自 committed request facts；计数损坏、compactor / artifact root 缺失、quality check 失败或 compact 后仍越过 hard threshold 时写 `CONTEXT_COMPACTION_FAILED` 并把 Run 收口为 `FAILED`，不进入 `LOST`。compact accepted 时写 artifact 与 `CONTEXT_COMPACTED`，追平 conversation memory projection 后用新的 Attempt / execution / dispatch record 写 `RUN_STARTED(start_reason=recovery)` 与 `ATTEMPT_STARTED`，再唤醒 scheduler dispatch；旧 Attempt 后续事件按 stale / duplicate 处理，不 resume 或 takeover。

`dayu.host.fake_compaction.FakeContextCompactor` 只供测试与本地开发显式注入。生产默认路径不得隐式使用该 fake compactor。

## Durable Foundation

`dayu.host.durable` 是 Host 内部 durable foundation 子包，不从 `dayu.host` 包根导出，也不进入 `dayu.host.api`。

当前已实现：

- SQLite fresh bootstrap、schema version 校验、WAL / foreign key / busy timeout 配置与 transaction runner；每个 `HostTransaction` 携带当前 durable store 的 payload inline 阈值。
- canonical JSON、UTC timestamp 与 sha256 digest helper。
- EventLog append / read primitive：在调用方提供的 `HostTransaction` 内追加事件、分配全局 `event_sequence`、处理同体 `event_id` 幂等重复与异体冲突、按 cursor 补读，并支持在同一 transaction 内按 Run、event type 与 durable-neutral inline payload 文本过滤器统计 committed canonical facts。`canonical_fact` 的 inline `payload_json` 受当前 durable store 注入的 payload inline 阈值约束，超限内容必须使用 payload descriptor / artifact ref 与 digest 边界。
- Idempotency primitive：以 `(scope_kind, scope_id, idempotency_key)` 绑定 `semantic_input_digest` 与显式 result ref，同 key 不同 digest 返回结构化冲突。
- Phase 8 projection / minimal read model：`ProjectionRunner` 只消费 committed EventLog，并推进 consumer-local checkpoint、记录 projection-local failure。当前固定 single consumer `host.minimal-read-model` 独占投影 `host_run_results` 与 `host_session_timeline_items`，作为内部 RunResult / Session timeline 读取基座；reset 后从 EventLog replay 是合法 repair 路径。投影 stale、缺失或 repair 失败不改变 durable Run / Session truth，也不影响 `stream_run_events` 的 EventLog-backed cursor 语义。`repair_minimal_read_models(...)` 使用注入的 `HostTransactionRunner` 分两阶段 reset 与 replay，不提供 public command facade。
- Phase 9 memory projection durable foundation：当前 schema 创建 `host_memory_snapshots`、`host_memory_items` 与 `host_memory_diagnostics` 三张表，`dayu.host.durable.memory` 提供 transaction-scoped snapshot / diagnostic read-write primitive、consumer-scoped reset helper 和 `ConversationMemoryProjectionConsumer`。该 consumer 只消费 committed canonical EventLog facts，包括 `TOOL_RESULT_ACCEPTED`、`USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED` 与 accepted `CONTEXT_COMPACTED`；`CONTEXT_COMPACTION_FAILED` 不进入生产 memory filter。consumer 在 ProjectionRunner 提供的同一 transaction 内写 memory-owned snapshot tables；checkpoint 推进仍由 ProjectionRunner 负责。它不启动 transaction，不修改 Run / Attempt / wait / dispatch 治理状态，不写 EventLog。RunInputBuilder 的 durable memory provider 只读 snapshot 与 EventLog delta；repair / catch-up 编排由 `dayu.host.memory_repair` 复用 ProjectionRunner 完成。
- Payload descriptor primitive：支持 `sqlite_payload` 与 `artifact_ref` 两类 descriptor；SQLite payload row 与 descriptor 可在同一 transaction 内写入，EventLog 可引用既有 descriptor 与 digest。
- Local artifact helper：在显式注入的 artifact root 下写入 `.tmp` 临时文件，完成 flush / fsync、digest 校验与 atomic rename 后返回最终 `LocalArtifactRef`；SQLite rollback 后已发布但未引用的文件只属于 cleanup / diagnostics orphan，不是 accepted fact。
- Host instance liveness primitive：支持当前 instance register、heartbeat、mark stopping / stopped 与 read row；该 row 只表达本机 Host instance 生命周期诊断。
- Phase 3 / 5 state schema / row codec：创建 Session、slot、Run、Attempt 与 attempt dispatch record durable tables；dispatch record 当前覆盖 `pending`、`waiting_for_lane`、`dispatching`、`cancelled` 四种状态，typed row codec 与低层 helper 负责状态枚举、SQLite row 转换、Session snapshot 读取和事务内 CAS mutation。
- Phase 3 / 5 internal lifecycle / transition primitives：在调用方提供的 `HostTransaction` 内实现 Session / slot lifecycle，以及 Run / Attempt / dispatch record 的低层 transition helper；当前 durable primitive 覆盖 pre-dispatch cancel、`pending -> waiting_for_lane -> dispatching` 诊断推进、worker accepted refs、Attempt `STARTING -> RUNNING`、active Run `RUNNING -> CANCELLING` 和 active cancel terminal closeout。EventLog fact 与 state row mutation 必须处于同一 SQLite write transaction。
- Phase 5 / 6 / 9 RunInputBuilder boundary：通过 typed providers 从 durable Run / Attempt / dispatch record、canonical EventLog facts 与 memory snapshot 构造 deterministic `AgentRunRequest`；只接受同一 snapshot identity 下的 Run `RUNNING`、Attempt `STARTING`、dispatch record `DISPATCHING` 当前事实。当前用户 prompt 只来自 durable `USER_INPUT_ACCEPTED`，historical raw turns 只能经 memory budget 后注入，resume-specific continuity 仍由 SessionContinuityProvider 提供。no-op memory / compact providers 不创建 durable rows。no-tool / replay 模式输出 `disable_tools=True`、`tool_schemas=()`、`AgentPolicy.allow_tool_calls=False`；tool-enabled 模式要求 `disable_tools=False`、`AgentPolicy.allow_tool_calls=True`，且 schema 与 executor 必须来自同一个 `ToolRuntimeHandle`。
- Phase 5 / 10 dispatch scheduler / LocalProxy baseline：`HostDispatchScheduler` 接收 accepted/queued pre-start wakeup 与 pending dispatch wakeup。pre-start wakeup 先执行 Context Governance gate，再创建 Attempt 与 dispatch record；pending dispatch wakeup 将 dispatch record 从 `pending` 推进到 `waiting_for_lane`，通过独立 runtime lane DB acquire capacity，再经 durable recheck 推进到 `dispatching`。durable recheck 遇到 transaction retry exhausted 时释放 lane并重排当前 dispatch，不按 worker startup timeout 收口；后台 drain loop 持续轮询直到 scheduler close，避免 empty / sleep 窗口内的 wakeup 被遗留，未预期异常退出会记录 warning。worker accept 前会按本地执行 memory policy 同步追平 conversation memory projection，并把 durable memory provider 与 durable compact artifact provider 注入 RunInputBuilder。worker accept 后追加 `ATTEMPT_RUNNING`、推进 Attempt `STARTING -> RUNNING`，并记录 worker accept refs；worker startup timeout / accept failure 会按 `timed_out` 路径收口，若 startup closeout 自身失败则记录 warning 并继续释放 lane；memory projection repair required 使用独立 closeout reason，不归类为 worker startup timeout。Default LocalProxy worker 调用 Engine public `run_agent_messages(request)` 并暴露 single-use EngineEvent stream；同一 handle 不能重复打开 events，handle close 后不再允许读取 events，close 会关闭已打开的底层 Engine generator。scheduler 消费 worker event stream 时把自身作为 admission wakeup port 和 reactive Context Governance 配置传给 `EngineEventIngestor`，active task 的 finally 单点负责 active registry 注销、worker handle close 与 lane release；`HostDispatchScheduler.open(..., active_registry=None)` 会创建 scheduler-local registry，不使用模块级 singleton；scheduler close 只传播 cancel signal 并取消 active task。`final_answer` 收口为 `SUCCEEDED`，`run_failed` 与 clean EOF without terminal 收口为 `FAILED`，worker stream crash / unknown terminal 收口为 `LOST`；reactive context overflow 可恢复为新 Attempt，terminal closeout 后会触发 queued Run pre-start governance wakeup。
- Phase 5 / 7 EngineEvent ingest mapping：`EngineEventIngestor` 只接收 Host-owned `EngineEventCandidate` envelope，不要求 Engine 公共 `EngineEvent` 携带 Host Attempt identity；当前映射覆盖 final answer succeeded、run failed、active cancel 后 run cancelled、usage projection signal、preview / diagnostic、unsupported recovery diagnostic + failed closeout、Engine awaiting / suspended confirmation diagnostic、clean EOF failed closeout 和 worker lost closeout。final answer 只有在 `content` 非空白时才写入 `RUN_SUCCEEDED`；空白 final answer 会按 `empty_final_answer` 收口为 `FAILED`，避免写入 public HostEvent 无法投影的成功事实。Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 事件必须匹配 Host awaiting accept path 已 durable accepted 的 wait record 与 canonical refs 才记为确认；不匹配时不创建 wait record，也不把已经 `WAITING` 的 Run 失败收口。preview 事件只有在 `EngineEventType` 与对应 data 类型同时匹配时才写入 preview payload，否则写 rejected diagnostic。terminal closeout 后会触发 queue promotion wakeup，duplicate terminal replay 也会重试 promotion wakeup。
- Phase 7 wait record / resolve / cancel / poll foundation：创建 `host_wait_records` fresh schema / index / CHECK 约束，提供 typed wait record status、resume policy、snapshot / external job refs、row codec、insert / read / CAS helper 与 `RunStartReason.RESUME`。ToolRuntime awaiting accept path 已使用该 foundation 创建 active wait record 并推进 Run / Attempt 到 `WAITING` / `SUSPENDED`；public `resolve_wait` 已接入 wait record mutation、resolution idempotency、completed / tool-cancelled resume Attempt、failed closeout、lost closeout 与 late result diagnostic；public cancel 已支持 `WAITING` Run closeout；最小 poller 已支持 active poll waits 的 ready / lost / cancelled observation。callback endpoint 尚未接入。

durable foundation 当前不实现 policy provider set、RemoteProxy、recovery classifier、lease / fencing / takeover、artifact cleanup scheduler、audit、outbox、ToolRuntime durable snapshot 或 ToolRuntime durable cursor。

## Internal Admission

`dayu.host.admission` 是 Host 内部 command 编排模块，不从 `dayu.host` 包根导出，也不是 public facade。

当前已实现：

- `start_run`：在 open Session 上根据 `queue_policy` 执行 accepted pre-start、queue、reject 或 attach active。无 active/start-blocking Run 时创建 `ACCEPTED` Run、`USER_INPUT_ACCEPTED` 与 `RUN_ACCEPTED`，不创建 Attempt 或 dispatch record；accepted Run 视为 active/start-blocking，`reject` 与 `attach_active` 都返回 conflict，`queue` 排到其后。
- `submit_followup_queue`：接收调用方显式提供的 `resolved_execution_target`；有 active/start-blocking Run 时创建 queued Run，无 active/start-blocking Run 时创建 `ACCEPTED` Run，后续由 scheduler governance gate 启动。
- `submit_followup_steer`：只接受同 Session active `RUNNING` / `WAITING` 目标 Run；在同一 Run 上追加 steer 输入，创建新 Attempt / execution / dispatch record 并切换 current Attempt，`RUNNING` 旧 Attempt 会以 `STEERED` 收口，`WAITING` active wait records 会被取消，commit 后唤醒 pending dispatch。
- `retry_run`：只接受普通本地 `FAILED` 源 Run；源 Run 保持 immutable，创建关联新 Run，按 `(source_run_id, client_request_id)` 幂等，当前 policy 每个源 Run 只允许一个 ordinary retry。
- `replay_run`：只接受 `SUCCEEDED` 源 Run；创建关联新 Run，使用修复指令作为新输入，并冻结为 no-tool execution / tool set，不向源 Run EventLog 写入新的工具事实。
- `promote_next_queued_run`：保留为低层 admission helper；production scheduler 的 queue wakeup 走同一个 pre-start governance gate，不再由 terminal / cancel closeout 在 admission transaction 后直接创建 Attempt。
- `cancel_run`：支持 accepted / queued Run cancel、pre-dispatch STARTING cancel、active worker cancel 与 WAITING cancel；accepted / queued cancel 不创建 Attempt，pre-dispatch cancel 会把 pending dispatch record、Attempt 与 Run 同事务收口为 cancelled，WAITING cancel 会标记 active wait records 为 cancelled 并把 Run 收口为 cancelled。
- `closeout_attempt_terminal`：支持 STARTING Attempt / RUNNING Run 的 succeeded、failed、lost terminal closeout；成功释放 active slot 后在新事务中尝试 FIFO promotion。
- operation idempotency：start / follow-up 使用显式 operation scope，同 key 同 digest 返回既有 Run，不同 digest 返回结构化 conflict；follow-up queue digest 不包含 `resolved_execution_target`。
- wakeup port：暴露 pending dispatch 和 queue promotion wakeup 端口；admission 默认可使用 no-op / 测试 spy，dispatch scheduler 则实现该端口以连接 terminal closeout 后的 FIFO promotion 与 pending dispatch 唤醒。
- post-commit wakeup 边界：active slot 释放后的 durable promotion 先于 queue promotion wakeup；promotion 已提交后的 dispatch / queue wakeup `RuntimeError` 只按 best-effort 处理，不回滚或掩盖 durable promotion 结果。
- 多进程 durable invariant：当前测试覆盖同 slot ensure 只绑定一个 Session、同 Session admission 最多一个 active Run、跨进程 follow-up 幂等重放 / 冲突、queued Run 按 accepted `event_sequence` FIFO promotion、queued cancel 与 promotion 的 first-committer-wins，以及 EventLog `event_sequence` 全局唯一递增。

internal admission 当前不实现 policy provider integration、LOST / RECOVERING retry、startup recovery、positive orphan proof、stuck cancel watchdog 或 recovery cancellation。
internal admission 当前的 session-scope cancel 支持 queued、pre-dispatch / pre-accept dispatching、active worker 与 WAITING 子集；Phase 11 负责 `RECOVERING` cancel。

## 校验边界

所有公共 dataclass 均使用 `frozen=True, slots=True`。枚举使用 `enum.StrEnum`，字符串值为稳定的 snake_case 值。

当前构造期校验覆盖：

- id / name / reason 字段拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 拒绝负数。
- `SubmitFollowupRequest` 中 `behavior=steer` 必须携带 `target_run_id`，`behavior=queue` 不得携带 `target_run_id`；`user_prompt` 必填，`system_prompt` 可选，`tool_names` 只接受 `frozenset[str] | None`，per-run `runner_spec` / `runner_options` / `agent_policy` 只接受完整 typed value 或 `None`。
- `FollowupSnapshot` 使用 `accepted_run_id` / `accepted_run_status` 表达 accepted Run；`command_watermark` 是 command commit 后的 durable read watermark，不是 watch cursor；queue 分支 `QUEUED` 时 `queued_run_id` 必须等于 `accepted_run_id`，非 `QUEUED` 时 `queued_run_id` 必须为 `None`，queue 分支不得携带 `target_run_id`。
- `CreateSessionRequest.bind_slot=True` 时必须同时提供 `scope` 与 `slot_key`。
- `CancelRunRequest` 与 `CancelSessionRunsRequest` 当前只接受 `CancelMode.GRACEFUL`。
- `HostApiErrorCode` 包含 `UNSUPPORTED_OPERATION`；`HostApiError.detail` 只接受 `HostApiErrorDetail` typed union 成员，当前成员为 `SteerConflictDetail`。
- `HostCommandHandleOptions` 校验可选 handle id 非空、路径字段为 `pathlib.Path`、布尔字段为 `bool`、timeout / delay / backoff / payload threshold 为正数、写重试次数非负，并要求调用方显式提供 context window / reserved output，再校验 hard threshold / minimum protection tokens 共同组成合法 ContextBudgetPolicy；`create_host_command_handle` 对非空 `local_execution` fail fast。
- `HostLocalExecutionOptions` 校验 lane 配置、RunnerSpec、RunnerCallOptions、AgentPolicy、worker factory、可选 context budget policy、可选 compactor runner baseline、可选 `tooling_options` 与 truncation manager 开关；worker factory 是结构协议，运行时不做 `hasattr` / `getattr` 式协议探测，由 pyright 与显式 scheduler 装配点保障。
- `ToolBundleSourceRef.source_id` 拒绝空字符串或纯空白；可选版本引用与内容摘要存在时也必须非空。
- `HostToolingOptions.source_refs` 必须非空。
- `FrameworkToolPolicyView.enabled_framework_tools` 必须是 `reserved_framework_tool_names` 子集。
- 业务 `ToolBundle` 不得占用 reserved framework tool name。
- `HostPayloadRef`、`WaitAdapterKey`、`WaitProviderStatusRef` 与 resolve wait outcome 类型拒绝空白 id / kind / digest / message / diagnostic ref，长度按公共 `HOST_WAIT_*_MAX_LENGTH` 常量校验；`ResolveWaitRequest.observed_at` 必须是 UTC-aware `datetime`。

## 架构边界

`dayu.host` 可以在 LocalProxy 边界沿 `UI -> Service -> Host -> Engine` 方向调用 Engine public entry；Engine 不导入 Host。`dayu.host` 不导入 `dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

业务工具发现、provider / 配置绑定、包入口扫描和 Service composition 发生在 Host 外部。Host 只接收外部已经形成的业务 `ToolBundle`，不扫描业务工具包，也不导入具体财报工具模块。`business_tool_bundle` 不进入 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resolve wait 等 per-run request；per-run 工具选择只能通过 `SubmitFollowupRequest.tool_names` 表达。

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

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host payload / wait adapter / resolve wait outcome 校验、Host tooling options 校验、Context Budget policy / conservative estimator / EventLog committed fact 统计、Context Governance compactor typed contract / fake compactor / quality check / compact artifact store、Conversation Memory typed contract / projection builder / durable round-trip / deterministic digest / Host-neutral boundary / anti-hallucination matrix / repair rebuild / catch-up failure path、ToolRuntime effective bundle / handle 同源约束、ToolRuntime accept barrier 幂等 / 冲突 / stale execution / canonical facts、ToolRuntimeExecutor accepted ack barrier / rejected ack / timeout retry / side-effect idempotency guard / awaiting accepted ack / awaiting rejected / awaiting timeout / awaiting missing adapter / awaiting missing external job / awaiting batch stop / no-tool defense / mixed batch、ToolRuntime truncation / `fetch_more` scope guard、run-local duplicate governance matrix、diagnostic emitter refs、Host import 边界、弱类型守卫、Host command handle factory / close lifecycle、Session public facade 幂等、冲突、读取与关闭语义，以及低层 `start_run`、Run public follow-up queue / follow-up steer / get_run / EventLog stream / cancel / session-scope cancel / WAITING cancel / retry / replay / purge deferred unsupported 函数。

durable foundation、RunInputBuilder、dispatch scheduler / LocalProxy、EngineEvent ingest mapping、ToolRuntime accept barrier / executor 与 internal admission 测试覆盖 SQLite schema bootstrap / transaction runner、EventLog append / read / idempotency、payload descriptor、local artifact helper、host instance liveness、EventLog 多进程 sequence smoke、projection checkpoint / failure、minimal RunResult / Session timeline projection 与 repair、memory projection table / CHECK / FK / index、memory snapshot 与 checkpoint 同事务 rollback、memory diagnostic durable round-trip、ConversationMemoryProjectionConsumer 从 committed EventLog 构建 snapshot、memory projection reset / rebuild / catch-up failure、tool verified fact provenance、final answer / user input 不升格为 verified fact、history pool budget 与 recent raw turn floor、Session lifecycle、Run / Attempt transition primitive、dispatch record 四状态 schema、wait record schema / row codec / DDL CHECK / CAS helper、awaiting accept 三事实原子写入 / wait record 创建 / WAITING 和 SUSPENDED 状态推进 / replay / conflict / stale execution reject、resolve_wait completed resume / tool-cancelled resume / failed closeout / lost closeout / idempotent replay / conflict / resume RunInputBuilder continuity / late result diagnostic / after-commit catch-up failure tolerance、WAITING cancel / session-scope WAITING cancel、wait poller ready / not-ready / cancelled abandon、waiting / dispatching / worker accept refs、active cancel durable primitive、RunInputBuilder durable prompt / canonical continuity / no-tool request / tool-enabled ToolRuntime handle 投影 / 非可派发状态拒绝、scheduler pending / waiting / dispatching / worker accept / promotion catch-up failure tolerance、pre-accept cancel race、lane acquire timeout、worker startup timeout、active task 资源释放、LocalProxy Engine entry boundary、final answer / failed / cancelled / usage / preview data 校验 / unsupported recovery EngineEvent mapping / Engine awaiting confirmation diagnostic、Engine 工具事件 preview 边界、clean EOF / worker lost closeout、terminal duplicate promotion retry、accept key 幂等重放 / conflict / stale execution reject / reuse governance canonical fact / accepted tool fact after-commit catch-up failure tolerance、ToolRuntimeExecutor fake business tool accepted 后返回、accept reject / timeout 不泄漏 raw result、side-effect 缺 key 不调用 callable、duplicate key 规范化与排除 `index_in_iteration`、`allow` / `reuse` / `hint` / `require_justification` / `hard_stop` matrix、diagnostic refs、Engine 经 ToolRuntime durable accepted 后继续第二轮、start / follow-up admission、queue policy、idempotency、FIFO promotion、queued / pre-dispatch cancel、terminal closeout、admission 多进程 durable invariant，以及 Host 包根不导出 durable 内部模块。
