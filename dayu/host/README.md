# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 当前提供 Host 公共 API 的类型契约、Session public command facade 和 Host construction 的业务工具输入边界，供 UI / Service 按 `UI -> Service -> Host -> Engine` 的依赖方向向下引用。

当前包根导出包含以下类型：

- constants：`HOST_EVENT_STREAM_DEFAULT_LIMIT`、`HOST_EVENT_STREAM_MAX_LIMIT`。
- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`。
- command handle：`HostCommandHandle`、`create_host_command_handle`、`HostCommandFacet`；public handle 只暴露稳定 `host_handle_id` 与幂等 `close()`，不暴露 durable store、transaction runner、store connection 或 admission service。
- command handle options：`HostCommandHandleOptions`，显式描述 Host command handle 的 durable DB、artifact root、SQLite timeout / retry 与 payload inline threshold 构造选项。
- Session facade：`ensure_session`、`create_session`、`get_session`、`close_session`，均返回 `SessionSnapshot`。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`StartRunRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`。
- snapshots / stream：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventView`、`HostEventStream`。
- error：`HostApiError`、`HostApiErrorDetail`、`SteerConflictDetail`。
- tooling construction options：`ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`、`default_framework_tool_policy_view`。

`dayu.host.api.__all__` 仍只包含 request、snapshot、status、error、context 与 stream cursor 类型。Session facade 位于 `dayu.host.command` / `dayu.host.read_api` 并由包根导出，但不进入 `dayu.host.api`。Host construction tooling 类型位于 `dayu.host.tooling`，由包根导出，但不进入 `dayu.host.api`。

## Public Session Command Path

`create_host_command_handle(options)` 会根据 `HostCommandHandleOptions` 打开 fresh/bootstrap 后的 Host durable SQLite store，并装配内部 no-op admission service 依赖。该 handle 是 public facade 的 opaque command handle；关闭 handle 后再次调用 public facade 会返回 `HostApiError(code=INVALID_STATE, retryable=False)`。

当前已实现的 Session public facade：

- `ensure_session(host, request)`：按 `(scope, slot_key)` 原子创建或复用当前 slot Session，返回 durable truth 生成的 `SessionSnapshot`。
- `create_session(host, request)`：按 `client_request_id` 幂等创建显式新 Session，可选择重绑定 slot；同 key 同 semantic digest 返回同一 Session，同 key 不同 digest 返回 `IDEMPOTENCY_CONFLICT`。
- `get_session(host, session_id)`：通过只读 transaction 读取 Session row、当前 active Run id 与 queued Run id 列表；缺失时返回 `NOT_FOUND`。
- `close_session(host, session_id, request)`：只把 open Session 推进到 closed，保留 Session、EventLog、Run facts 与 slot binding；同一幂等 key 重放返回同一个 closed snapshot。

public semantic digest 在 facade 边界只使用显式请求字段与 `HostCallContext` 的语义 digest，不包含 runtime-only object、内部依赖或 metadata bag。
当前 `create_session` public facade 不持久化 `request.metadata`；metadata 持久化语义尚未成为 public contract。`ensure_session` 仍按 durable lifecycle 保存首次创建时的 metadata 摘要。

## Host Tooling Options

`HostToolingOptions` 是 Host construction / composition root 接收业务工具的 typed input boundary。它包含：

- `business_tool_bundle`：外部装配好的业务 `ToolBundle`。
- `source_refs`：非空 `ToolBundleSourceRef` 元组，用于解释业务工具来源。
- `framework_tool_policy`：construction 期 framework tool 预留名与启用集合视图。

`ToolBundleSourceKind` 当前覆盖 `explicit_provider`、`config_binding`、`package_entrypoint`、`service_composition`。`ToolBundleSourceRef` 只保存来源类别、来源 id、可选版本引用和可选内容摘要；它不携带 callable、provider 对象或业务模块对象。

默认 `FrameworkToolPolicyView` 预留 `FrameworkToolName.FETCH_MORE`，但默认不启用任何 framework tool。`HostToolingOptions` 会拒绝业务 `ToolBundle` 中与预留 framework tool 名称冲突的工具，例如 `fetch_more`。

## Durable Foundation

`dayu.host.durable` 是 Host 内部 durable foundation 子包，不从 `dayu.host` 包根导出，也不进入 `dayu.host.api`。

当前已实现：

- SQLite fresh bootstrap、schema version 校验、WAL / foreign key / busy timeout 配置与 transaction runner。
- canonical JSON、UTC timestamp 与 sha256 digest helper。
- EventLog append / read primitive：在调用方提供的 `HostTransaction` 内追加事件、分配全局 `event_sequence`、处理同体 `event_id` 幂等重复与异体冲突，并按 cursor 补读。
- Idempotency primitive：以 `(scope_kind, scope_id, idempotency_key)` 绑定 `semantic_input_digest` 与显式 result ref，同 key 不同 digest 返回结构化冲突。
- Payload descriptor primitive：支持 `sqlite_payload` 与 `artifact_ref` 两类 descriptor；SQLite payload row 与 descriptor 可在同一 transaction 内写入，EventLog 可引用既有 descriptor 与 digest。
- Local artifact helper：在显式注入的 artifact root 下写入 `.tmp` 临时文件，完成 flush / fsync、digest 校验与 atomic rename 后返回最终 `LocalArtifactRef`；SQLite rollback 后已发布但未引用的文件只属于 cleanup / diagnostics orphan，不是 accepted fact。
- Host instance liveness primitive：支持当前 instance register、heartbeat、mark stopping / stopped 与 read row；该 row 只表达本机 Host instance 生命周期诊断。
- Phase 3 state schema / row codec：创建 Session、slot、Run、Attempt 与 attempt dispatch record durable tables；typed row codec 与低层 helper 负责状态枚举、SQLite row 转换、Session snapshot 读取和事务内 CAS mutation。
- Phase 3 internal lifecycle / transition primitives：在调用方提供的 `HostTransaction` 内实现 Session / slot lifecycle，以及 Run / Attempt / pending dispatch record 的低层 transition helper；EventLog fact 与 state row mutation 必须处于同一 SQLite write transaction。

durable foundation 当前不实现 policy provider set、queue scanning / after-commit wakeup、scheduler、lane acquire、WorkerProxy / LocalProxy / RemoteProxy、Engine dispatch、EngineEvent ingest、recovery classifier、lease / fencing / takeover、artifact cleanup scheduler、projection、audit、outbox 或 ToolRuntime。

## Internal Admission

`dayu.host.admission` 是 Host 内部 command 编排模块，不从 `dayu.host` 包根导出，也不是 public facade。

当前已实现：

- `start_run`：在 open Session 上根据 `queue_policy` 执行 direct start、queue、reject 或 attach active；创建 running Run 时只写 pending dispatch record，不启动真实 dispatch。
- `submit_followup_queue`：接收调用方显式提供的 `resolved_execution_target`，在 active Run 存在时创建 queued Run，在无 active Run 时直接创建 running Run、STARTING Attempt 与 pending dispatch record。
- `promote_next_queued_run`：按 queued Run 的 accepted `event_sequence` FIFO promotion 一个 Run；active Run 存在时返回 skipped。
- `cancel_run`：支持 queued Run cancel 与 pre-dispatch STARTING cancel；queued cancel 不创建 Attempt，pre-dispatch cancel 会把 pending dispatch record、Attempt 与 Run 同事务收口为 cancelled。
- `closeout_attempt_terminal`：支持 STARTING Attempt / RUNNING Run 的 succeeded、failed、lost terminal closeout；成功释放 active slot 后在新事务中尝试 FIFO promotion。
- operation idempotency：start / follow-up 使用显式 operation scope，同 key 同 digest 返回既有 Run，不同 digest 返回结构化 conflict；follow-up queue digest 不包含 `resolved_execution_target`。
- no-op / 测试 wakeup port：只暴露 pending dispatch 和 queue promotion wakeup 端口，不执行 Engine、WorkerProxy、scheduler 或 lane acquire。
- post-commit wakeup 边界：active slot 释放后的 durable promotion 先于 queue promotion wakeup；promotion 已提交后的 dispatch / queue wakeup `RuntimeError` 只按 best-effort 处理，不回滚或掩盖 durable promotion 结果。
- 多进程 durable invariant：当前测试覆盖同 slot ensure 只绑定一个 Session、同 Session admission 最多一个 active Run、跨进程 follow-up 幂等重放 / 冲突、queued Run 按 accepted `event_sequence` FIFO promotion、queued cancel 与 promotion 的 first-committer-wins，以及 EventLog `event_sequence` 全局唯一递增。

internal admission 当前不实现 policy provider integration、真实 dispatch、dispatching / active worker cancel propagation、EngineEvent ingest、steer、retry / replay、wait cancellation、recovery cancellation 或 session-scope cancel facade。

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
- `HostCommandHandleOptions` 校验可选 handle id 非空、路径字段为 `pathlib.Path`、布尔字段为 `bool`、timeout / delay / backoff / payload threshold 为正数、写重试次数非负。
- `ToolBundleSourceRef.source_id` 拒绝空字符串或纯空白；可选版本引用与内容摘要存在时也必须非空。
- `HostToolingOptions.source_refs` 必须非空。
- `FrameworkToolPolicyView.enabled_framework_tools` 必须是 `reserved_framework_tool_names` 子集。
- 业务 `ToolBundle` 不得占用 reserved framework tool name。

## 架构边界

`dayu.host` 不导入 `dayu.engine`、`dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

业务工具发现、provider / 配置绑定、包入口扫描和 Service composition 发生在 Host 外部。Host 只接收外部已经形成的业务 `ToolBundle`，不扫描业务工具包，也不导入具体财报工具模块。`business_tool_bundle` 不进入 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resolve wait 等 per-run request。

Host 若在后续实现中复用 `dayu.runtime.filelock`，只能把它用于普通文件短临界区互斥。lock marker 文件不是 Host 治理真源，不能用于判断 Run / Attempt owner、worker liveness、EventLog ordering、recovery 或 takeover；这些事实只能来自 Host durable store、EventLog、状态索引和事务。`RuntimeFileLock` 也不承诺 reentrant lock 语义，Host 代码不得依赖同一实例重复 acquire 的第三方行为。

当前未实现：

- Run public command facade、EventLog stream public facade、policy provider set、dispatch scheduler、WorkerProxy / LocalProxy / RemoteProxy、dispatching / active worker cancel propagation、wait cancellation、recovery classifier、lease / fencing / takeover。
- artifact cleanup scheduler 与 diagnostics table。
- ToolRuntime construction、ToolRuntime policy resolution、framework tool injection。
- ToolsDiscovery / ScenePrepare provider contract、tool profile registry、Attempt tool snapshot durability。
- Engine 调用路径、Fins 业务语义、Service / UI 装配逻辑。

## 测试

Host 公共契约测试位于 `tests/host/`：

```bash
pytest tests/host -q
python -m pyright dayu/host tests/host
```

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host tooling options 校验、Host import 边界、弱类型守卫、Host command handle factory / close lifecycle，以及 Session public facade 幂等、冲突、读取与关闭语义。

durable foundation 与 internal admission 测试覆盖 SQLite schema bootstrap / transaction runner、EventLog append / read / idempotency、payload descriptor、local artifact helper、host instance liveness、EventLog 多进程 sequence smoke、Session lifecycle、Run / Attempt transition primitive、start / follow-up admission、queue policy、idempotency、FIFO promotion、queued / pre-dispatch cancel、terminal closeout、admission 多进程 durable invariant，以及 Host 包根不导出 durable 内部模块。
