# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 当前提供 Host 公共 API 的类型契约和 Host construction 的业务工具输入边界，供 UI / Service 按 `UI -> Service -> Host -> Engine` 的依赖方向向下引用。

当前包根导出包含以下类型：

- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`。
- command handle 协议：`HostCommandFacet`，只暴露 `host_handle_id`。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`StartRunRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`。
- snapshots / stream：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventView`、`HostEventStream`。
- error：`HostApiError`。
- tooling construction options：`ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`、`default_framework_tool_policy_view`。

`dayu.host.api.__all__` 仍只包含 request、snapshot、status、error、context 与 stream cursor 类型。Host construction tooling 类型位于 `dayu.host.tooling`，由包根导出，但不进入 `dayu.host.api`。

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
- Phase 3 state schema / row codec：创建 Session、slot、Run、Attempt 与 attempt dispatch record durable tables；typed row codec 只负责状态枚举与 SQLite row 转换。

durable foundation 当前不实现 Host command function、Session / Run / Attempt lifecycle command、admission、promotion、cancel、recovery classifier、lease / fencing / takeover、artifact cleanup scheduler、projection、audit、outbox、ToolRuntime 或 Engine dispatch。

## 校验边界

所有公共 dataclass 均使用 `frozen=True, slots=True`。枚举使用 `enum.StrEnum`，字符串值为稳定的 snake_case 值。

当前构造期校验覆盖：

- id / name / reason 字段拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 拒绝负数。
- `SubmitFollowupRequest` 中 `behavior=steer` 必须携带 `target_run_id`，`behavior=queue` 不得携带 `target_run_id`。
- `CreateSessionRequest.bind_slot=True` 时必须同时提供 `scope` 与 `slot_key`。
- `CancelRunRequest` 与 `CancelSessionRunsRequest` 当前只接受 `CancelMode.GRACEFUL`。
- `ToolBundleSourceRef.source_id` 拒绝空字符串或纯空白；可选版本引用与内容摘要存在时也必须非空。
- `HostToolingOptions.source_refs` 必须非空。
- `FrameworkToolPolicyView.enabled_framework_tools` 必须是 `reserved_framework_tool_names` 子集。
- 业务 `ToolBundle` 不得占用 reserved framework tool name。

## 架构边界

`dayu.host` 不导入 `dayu.engine`、`dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

业务工具发现、provider / 配置绑定、包入口扫描和 Service composition 发生在 Host 外部。Host 只接收外部已经形成的业务 `ToolBundle`，不扫描业务工具包，也不导入具体财报工具模块。`business_tool_bundle` 不进入 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resolve wait 等 per-run request。

Host 若在后续实现中复用 `dayu.runtime.filelock`，只能把它用于普通文件短临界区互斥。lock marker 文件不是 Host 治理真源，不能用于判断 Run / Attempt owner、worker liveness、EventLog ordering、recovery 或 takeover；这些事实只能来自 Host durable store、EventLog、状态索引和事务。`RuntimeFileLock` 也不承诺 reentrant lock 语义，Host 代码不得依赖同一实例重复 acquire 的第三方行为。

当前未实现：

- Host command function。
- Session / Run / Attempt 状态机、dispatch record、policy provider set、recovery classifier、lease / fencing / takeover。
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

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host tooling options 校验、Host import 边界与弱类型守卫。

durable foundation 测试覆盖 SQLite schema bootstrap / transaction runner、EventLog append / read / idempotency、payload descriptor、local artifact helper、host instance liveness、EventLog 多进程 sequence smoke，以及 Host 包根不导出 durable 内部模块。
